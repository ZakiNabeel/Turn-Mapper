"""Masks -> spaces, doors and walls (pixel space).

Key idea: close short gaps in walls (door openings) with oriented line kernels. Connected
components of the remaining free space are spaces (rooms / circulation). The pixels the closing
added are door openings, which re-connect the spaces they touch.
"""

from __future__ import annotations

from collections.abc import Mapping

import cv2
import numpy as np
from scipy import ndimage
from shapely.affinity import translate
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union
from skimage.morphology import skeletonize

from .config import PipelineParams
from .ir import Door, GeometryPx, Region, Segmentation, TextBox


def wall_thickness_px(wall: np.ndarray) -> float:
    if wall.sum() == 0:
        return 3.0
    dt = cv2.distanceTransform(wall.astype(np.uint8), cv2.DIST_L2, 3)
    sk = skeletonize(wall)
    vals = dt[sk]
    return float(max(np.median(vals) * 2, 1.0)) if vals.size else 3.0


def _line_kernel(length: int, orientation: str) -> np.ndarray:
    length = max(int(length) | 1, 3)
    if orientation == "h":
        return np.ones((1, length), np.uint8)
    if orientation == "v":
        return np.ones((length, 1), np.uint8)
    d = max(int(round(length / np.sqrt(2))) | 1, 3)
    k = np.eye(d, dtype=np.uint8)
    return k if orientation == "d1" else np.fliplr(k).copy()


def close_wall_gaps(wall: np.ndarray, gap_px: int, thickness: float) -> np.ndarray:
    """Close door-sized gaps *along* walls without filling across rooms or cutting corners.

    For each orientation, a gap pixel is filled only if (a) the plain morphological closing with a
    line kernel of that orientation fills it and (b) a genuine wall run of the same orientation is
    within ``gap_px`` along that direction. (b) stops narrow rooms (bounded by perpendicular walls)
    from being filled and stops diagonal kernels from cutting room corners.
    """
    w = wall.astype(np.uint8)
    out = w.copy()
    run = max(int(round(3 * thickness)), 5)
    for o in ("h", "v", "d1", "d2"):
        k_gap = _line_kernel(gap_px, o)
        runs = cv2.morphologyEx(w, cv2.MORPH_OPEN, _line_kernel(run, o))
        if not runs.any():
            continue
        near = cv2.dilate(runs, _line_kernel(2 * gap_px + 1, o))
        closed = cv2.morphologyEx(w, cv2.MORPH_CLOSE, k_gap)
        out |= closed & near
    return out > 0


def carve_door_slabs(
    wall: np.ndarray,
    gray: np.ndarray,
    levels: dict,
    background: np.ndarray,
    t: float,
    gap_px: int,
    ignore: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Some exports draw a door as a thin white slab *on top of* an unbroken wall line, so the wall has no
    gap. Find such slabs (thin, elongated, near-white, lying along a wall) and cut an opening through the
    wall across its thickness, so gap closing + door detection treat them like any other door."""
    white = (gray >= levels["background"] - 9) & ~background
    if ignore is not None:
        white &= ~ignore  # e.g. halo of a coloured highlight drawn over a wall
    n, lab, st, _ = cv2.connectedComponentsWithStats(white.astype(np.uint8), connectivity=8)
    out = wall.copy()
    carved = np.zeros_like(wall)
    near_wall = cv2.dilate(wall.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    for i in range(1, n):
        x, y, w, h, a = st[i]
        long_, short = max(w, h), min(w, h)
        if not (0.4 * gap_px <= long_ <= 1.2 * gap_px and short <= max(3, 0.8 * t) and long_ >= 3 * short):
            continue
        comp = lab[y : y + h, x : x + w] == i
        if (near_wall[y : y + h, x : x + w] & comp).sum() < 0.6 * a:
            continue  # must lie on/against a wall
        r = int(round(t)) + 3
        if w >= h:  # horizontal slab: cut vertically through the wall band
            sl = (slice(max(y - r, 0), y + h + r), slice(x, x + w))
        else:
            sl = (slice(y, y + h), slice(max(x - r, 0), x + w + r))
        carved[sl] |= out[sl]
        out[sl] = False
    return out, carved


def estimate_door_width_px(wall: np.ndarray, t: float) -> tuple[float | None, int]:
    """Measure door openings directly. From every wall-line end, march straight on along the wall until the
    next wall. A real opening shows up as a *mutual pair*: the end on one side reaches the end on the other
    side and vice versa (junction artefacts and corridor crossings rarely do). The median mutual distance is
    the door width, independent of how thick walls are drawn. Returns (width px or None, #pairs)."""
    from .graph import skeleton_polylines

    sk = skeletonize(wall)
    h, w = wall.shape
    reach = int(0.12 * min(h, w))
    ends = []  # (end_xy, hit_xy, distance)
    for line in skeleton_polylines(sk):
        if len(line) < 6:
            continue
        for end, back in ((line[0], line[min(5, len(line) - 1)]), (line[-1], line[max(-6, -len(line))])):
            d = np.subtract(end, back)
            n = np.hypot(*d)
            if n == 0:
                continue
            # skeleton ends hook slightly: snap the direction to the nearest multiple of 45 degrees
            ang = np.round(np.arctan2(d[1], d[0]) / (np.pi / 4)) * (np.pi / 4)
            if abs(np.arctan2(d[1], d[0]) - ang) > np.deg2rad(25):
                continue
            d = np.array([np.cos(ang), np.sin(ang)])
            for s in range(int(t) + 2, reach):
                x, y = int(round(end[0] + d[0] * s)), int(round(end[1] + d[1] * s))
                if not (0 <= x < w and 0 <= y < h):
                    break
                if wall[y, x]:
                    ends.append((np.asarray(end, float), np.array([x, y], float), s))
                    break
    tol = t + 4
    dists = []
    for i, (ei, hi, si) in enumerate(ends):
        for j, (ej, hj, _sj) in enumerate(ends):
            if i < j and np.hypot(*(ej - hi)) <= tol + si * 0.15 and np.hypot(*(hj - ei)) <= tol + si * 0.15:
                dists.append(float(np.hypot(*(ej - ei))) - t)
    dists = np.array([x for x in dists if x >= 4])
    if len(dists) < 2:
        return None, len(dists)
    return float(np.median(dists)), len(dists)


def mask_to_polygons(mask: np.ndarray, simplify_px: float = 1.0, min_area: float = 4.0) -> list[Polygon]:
    """Outer boundaries + holes of a binary mask as valid shapely polygons (pixel coords)."""
    m = mask.astype(np.uint8)
    contours, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    polys: list[Polygon] = []
    if hier is None:
        return polys
    hier = hier[0]
    for i, c in enumerate(contours):
        if hier[i][3] != -1 or len(c) < 3:
            continue
        holes = []
        j = hier[i][2]
        while j != -1:
            if len(contours[j]) >= 3 and cv2.contourArea(contours[j]) >= min_area:
                holes.append(contours[j][:, 0, :].astype(float))
            j = hier[j][0]
        p = Polygon(c[:, 0, :].astype(float), holes)
        if not p.is_valid:
            p = p.buffer(0)
        p = p.simplify(simplify_px, preserve_topology=True)
        if p.area >= min_area:
            if p.geom_type == "MultiPolygon":
                polys.extend(g for g in p.geoms if g.area >= min_area)
            else:
                polys.append(p)
    return polys


def _blob_segment(ys: np.ndarray, xs: np.ndarray) -> tuple[LineString, float, float]:
    pts = np.stack([xs, ys], 1).astype(np.float32)
    (cx, cy), (w, h), ang = cv2.minAreaRect(pts)
    long_, short = max(w, h), min(w, h)
    theta = np.deg2rad(ang if w >= h else ang + 90)
    dx, dy = np.cos(theta) * long_ / 2, np.sin(theta) * long_ / 2
    return LineString([(cx - dx, cy - dy), (cx + dx, cy + dy)]), float(long_ + 1), float(short + 1)


def vectorize(
    seg: Segmentation,
    gray_raw: np.ndarray,
    text: list[TextBox],
    params: PipelineParams,
    m_per_px: float | None,
    color_mask: np.ndarray | None = None,
) -> GeometryPx:
    t = wall_thickness_px(seg.wall)
    door_w, n_door_meas = (None, 0)
    if m_per_px:
        gap_px = int(round(params.door_max_width_m / m_per_px))
        gap_src = "scale"
    elif seg.levels.get("known_door_px"):
        # door swings read from the drawing give the door width directly
        gap_px, gap_src = int(round(1.3 * seg.levels["known_door_px"])), "known_doors"
    else:
        door_w, n_door_meas = estimate_door_width_px(seg.wall, t)
        filled = seg.levels.get("filled", True)
        if door_w is not None and n_door_meas >= 3 and not filled:
            # line drawings: wall thickness says little about door size, so measure the openings.
            # Filled plans keep the thickness ratio, which is reliable there (wall-end pairs on dense
            # real plans also catch furniture and corridor ends and inflate the gap).
            gap_px, gap_src = int(round(1.35 * door_w)), "measured_openings"
        else:
            gap_px, gap_src = int(round(params.door_gap_wall_ratio * t)), "wall_thickness_ratio"
    gap_px = int(np.clip(gap_px, 5, max(seg.wall.shape) // 8))
    walls_all, carved = carve_door_slabs(
        seg.wall, gray_raw, seg.levels, seg.background, t, gap_px, ignore=color_mask
    )
    net_doors = np.zeros_like(seg.wall)
    if seg.doors is not None and seg.doors.any():
        # network doors: grow a little across the opening (not into walls) so each one meets the walls at both
        # ends, then treat it like a carved slab: a known opening that splits spaces and becomes a door
        k = max(3, int(round(t)) | 1)
        grown = cv2.dilate(seg.doors.astype(np.uint8), np.ones((k, k), np.uint8)) > 0
        net_doors = grown & ~walls_all & ~seg.background
        carved = carved | net_doors
    n_slabs = int(cv2.connectedComponents(carved.astype(np.uint8))[0] - 1)
    if seg.partitions is not None and seg.partitions.any():
        # a thin line lying in a gap of a thick wall is a door leaf, not a partition
        door_band = close_wall_gaps(seg.wall, 2 * gap_px, t) & ~seg.wall  # 2x: double doors
        door_band = cv2.dilate(door_band.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        parts = seg.partitions & ~door_band
        n_p, lab_p, st_p, _ = cv2.connectedComponentsWithStats(parts.astype(np.uint8), connectivity=8)
        keep_p = [
            i for i in range(1, n_p) if max(st_p[i, cv2.CC_STAT_WIDTH], st_p[i, cv2.CC_STAT_HEIGHT]) > gap_px
        ]
        parts = np.isin(lab_p, keep_p)
        walls_all = walls_all | (cv2.dilate(parts.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
    wall_c = close_wall_gaps(walls_all, gap_px, t) | carved  # carved slabs are known door openings
    if not seg.levels.get("filled", True):
        # floor drawn in the paper colour: the outside is whatever the closed wall outline leaves connected
        # to the image border (colour cannot tell inside from outside)
        from .segment import border_connected

        seg.background = border_connected(~wall_c)
    if params.outdoor_apron_gaps > 0:
        # CAD sheets closed in by a drawing border: the outdoors inside the border is not walkable, except a
        # strip along the building (entrances, covered walkways, open-air corridors). Outdoors open to the
        # page edge stays void as before.
        border_free = seg.background | _border_free(wall_c)
        fo, frame = sheet_frame_outside(wall_c, border_free, t, return_frame=True)
        building = wall_c & ~frame
        dist = cv2.distanceTransform((~building).astype(np.uint8), cv2.DIST_L2, 3)
        seg.background = border_free | (fo & (dist > params.outdoor_apron_gaps * gap_px) & ~wall_c)
    elif params.sheet_frame_outside:
        # entrances are sealed with twice the door gap so the outdoors cannot flow into the corridors
        sealed = close_wall_gaps(wall_c, 2 * gap_px, t)
        seg.background = seg.background | (sheet_frame_outside(sealed, seg.background, t) & ~wall_c)
        frame = (
            sheet_frame_outside(wall_c, seg.background, t, return_frame=True)[1]
            if params.frame_footprint_gaps > 0
            else None
        )
        if frame is not None and frame.any():
            # buildings with wide openings (open-air walkways, courtyards) leak the framed outdoors into the
            # corridors; the outdoors is what lies outside the building outline (walls closed over wide gaps)
            # a strip along the outer walls stays: rooms on open-air walkways have their doors there
            building = wall_c & ~frame
            dist = cv2.distanceTransform((~building).astype(np.uint8), cv2.DIST_L2, 3)
            seg.background = seg.background | (
                frame_outdoors(building, params.frame_footprint_gaps * gap_px)
                & (dist > params.frame_apron_gaps * gap_px)
                & ~wall_c
            )

    free = ~wall_c & ~seg.background
    n, lab, stats, _ = cv2.connectedComponentsWithStats(free.astype(np.uint8), connectivity=4)
    min_area_px = (params.min_region_area_m2 / (m_per_px**2)) if m_per_px else (gap_px * 0.6) ** 2
    keep = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= min_area_px]
    # drop slivers no person fits in (the cavity between the two lines of a double-line wall)
    dt = cv2.distanceTransform(free.astype(np.uint8), cv2.DIST_L2, 3)
    min_width = max(2.5 * t, 0.3 * gap_px)
    widest = ndimage.maximum(dt, lab, keep) if keep else []
    keep = [i for i, r in zip(keep, np.atleast_1d(widest), strict=False) if 2 * r >= min_width]

    # doors = pixels added by closing, between spaces
    added = wall_c & ~walls_all & ~seg.background
    dn, dlab, dstats, _ = cv2.connectedComponentsWithStats(added.astype(np.uint8), connectivity=8)
    keep_set = set(keep)
    region_of = {i: f"s{i}" for i in keep}
    doors: list[Door] = []
    door_masks: dict[str, tuple[tuple[slice, slice], np.ndarray]] = {}  # door id -> (box, blob in box)
    kernel = np.ones((3, 3), np.uint8)
    for d in range(1, dn):
        x, y, w, h, area = dstats[d]
        if area < 3:
            continue
        sl = (slice(max(y - 2, 0), y + h + 2), slice(max(x - 2, 0), x + w + 2))
        blob = dlab[sl] == d
        ring = cv2.dilate(blob.astype(np.uint8), kernel, iterations=2) > 0
        touched = set(np.unique(lab[sl][ring])) & keep_set
        outside = bool((seg.background[sl] & ring).any())
        ys, xs = np.nonzero(blob)
        seg_line, long_, short = _blob_segment(ys + sl[0].start, xs + sl[1].start)
        if len(touched) < 2 and not (len(touched) == 1 and outside):
            continue
        # a door the network predicted may be wider than gap closing allows (double doors, wide openings)
        predicted = net_doors[sl][blob].mean() > 0.5
        max_long = gap_px * (3.5 if predicted else 1.25)
        door_shaped = long_ >= max(2.0 * t, 6) and short <= 3.5 * t + 2 and long_ <= max_long
        # openings where walls meet (e.g. a diagonal wall next to a door) produce triangular blobs;
        # accept them when they clearly join exactly two spaces and are not much bigger than a door
        junction_opening = len(touched) == 2 and long_ <= gap_px * 1.6 and area <= gap_px * gap_px * 0.5
        if not (door_shaped or junction_opening):
            continue
        did = f"d{len(doors) + 1}"
        doors.append(
            Door(
                id=did,
                segment=seg_line,
                center=seg_line.centroid,
                regions=tuple(sorted(region_of[i] for i in touched)),
                width_px=long_,
            )
        )
        door_masks[did] = (sl, blob)

    # door swings read from the drawing: each joins the two spaces on either side of its closed position,
    # whether or not gap closing produced an opening there (Esri-style openings)
    for a, b in seg.levels.get("known_doors", []):
        a, b = np.asarray(a, float), np.asarray(b, float)
        v = b - a
        length = float(np.hypot(*v))
        if length < 2:
            continue
        nrm = np.array([-v[1], v[0]]) / length
        mid = (a + b) / 2
        sides = []
        for sgn in (1, -1):
            lbl = 0
            for f in (0.3, 0.6, 1.0):
                x, y = (mid + sgn * f * length * nrm).round().astype(int)
                if 0 <= y < lab.shape[0] and 0 <= x < lab.shape[1] and lab[y, x] in keep_set:
                    lbl = int(lab[y, x])
                    break
            sides.append(lbl)
        if 0 in sides or sides[0] == sides[1]:
            continue
        pair = tuple(sorted(region_of[i] for i in sides))
        near_existing = any(
            set(d.regions) == set(pair) and d.center.distance(Point(*mid)) < length for d in doors
        )
        if near_existing:
            continue
        did = f"d{len(doors) + 1}"
        line = LineString([tuple(a), tuple(b)])
        doors.append(
            Door(id=did, segment=line, center=line.centroid, regions=pair, width_px=length, source="drawing")
        )
        # the opening itself becomes walkable (thick enough to bridge the wall)
        pad = int(max(3, 2 * t)) + 2
        x0, y0 = int(max(min(a[0], b[0]) - pad, 0)), int(max(min(a[1], b[1]) - pad, 0))
        x1, y1 = int(min(max(a[0], b[0]) + pad, lab.shape[1])), int(min(max(a[1], b[1]) + pad, lab.shape[0]))
        box = np.zeros((y1 - y0, x1 - x0), np.uint8)
        p0 = (int(round(a[0])) - x0, int(round(a[1])) - y0)
        p1 = (int(round(b[0])) - x0, int(round(b[1])) - y0)
        cv2.line(box, p0, p1, 1, int(max(3, 2 * t)))
        door_masks[did] = ((slice(y0, y1), slice(x0, x1)), box > 0)

    # classify spaces
    door_count = {rid: 0 for rid in region_of.values()}
    neighbours: dict[str, set] = {rid: set() for rid in region_of.values()}
    for dr in doors:
        for rid in dr.regions:
            door_count[rid] += 1
            neighbours[rid] |= set(dr.regions) - {rid}
    areas = {f"s{i}": float(stats[i, cv2.CC_STAT_AREA]) for i in keep}
    largest = max(areas, key=areas.get) if areas else None
    seed = largest
    if params.circulation_seed == "doors" and areas:
        # the corridor is the space most rooms open onto; the largest space can be a title block, a legend or
        # the outdoors on a CAD sheet
        best = max(areas, key=lambda r: (len(neighbours[r]), areas[r]))
        if len(neighbours[best]) >= params.circulation_min_doors:
            seed = best
    # circulation = the seed space, plus many-door spaces reachable from it through doors
    # (a cluster of cubicles behind a closed office is not a corridor)
    circ_set = {seed} if seed else set()
    ids = {rid: i for i, rid in region_of.items()}

    def elongation(rid: str) -> float:
        i = ids[rid]
        x, y, bw, bh = (int(v) for v in stats[i, :4])
        crop = (lab[y : y + bh, x : x + bw] == i).astype(np.uint8)
        cs, _ = cv2.findContours(
            cv2.copyMakeBorder(crop, 1, 1, 1, 1, cv2.BORDER_CONSTANT, 0),
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        perim = sum(cv2.arcLength(c, True) for c in cs)
        # a strip of length L and width W has perimeter^2 / (4 area) ~ L / W; a square room gives 4
        return perim * perim / (4 * areas[rid])

    use_shape = params.corridor_elongation > 0
    if use_shape and areas:
        # every long, narrow space that several other spaces open onto is circulation too (a corridor split
        # by fire doors, or corridors not joined to the seed through a detected door)
        for rid in ids:
            if (
                len(neighbours[rid]) >= params.circulation_min_doors
                and elongation(rid) >= params.corridor_elongation
            ):
                circ_set.add(rid)
    changed = True
    while changed:
        changed = False
        for dr in doors:
            if circ_set & set(dr.regions):
                for rid in dr.regions:
                    if rid in circ_set:
                        continue
                    # a corridor leads to several *different* spaces; 3 openings into one hall = still a room
                    many = len(neighbours[rid]) >= params.circulation_min_doors
                    # a narrow passage between two circulation spaces (corridor stretch between fire doors)
                    link = (
                        use_shape
                        and len(neighbours[rid] & circ_set) >= 2
                        and elongation(rid) >= params.corridor_elongation
                    )
                    if many or link:
                        circ_set.add(rid)
                        changed = True
    regions: list[Region] = []
    masks = RegionMasks(lab)
    for i in keep:
        rid = f"s{i}"
        x, y, bw, bh = (int(v) for v in stats[i, :4])
        x0, y0 = max(x - 1, 0), max(y - 1, 0)
        crop = lab[y0 : y + bh + 1, x0 : x + bw + 1] == i  # polygons from the region's box, not the page
        polys = mask_to_polygons(crop, simplify_px=1.0)
        if not polys:
            continue
        poly = translate(max(polys, key=lambda p: p.area), x0, y0)
        kind = "circulation" if rid in circ_set else "room"
        regions.append(Region(id=rid, polygon=poly, area_px=areas[rid], kind=kind))
        masks.add(rid, i)

    circ_ids = {r.id for r in regions if r.kind == "circulation"}
    walk = np.zeros_like(free)
    for rid in circ_ids:
        walk |= masks[rid]
    for dr in doors:
        if circ_ids & set(dr.regions):
            sl_d, blob_d = door_masks[dr.id]
            walk[sl_d] |= blob_d
    if params.bridge_circulation and len(circ_ids) > 1:
        # gap closing can cut a corridor where it narrows; a closed-off strip between two circulation
        # spaces is part of the corridor, door-shaped or not
        circ_idx = {int(r[1:]) for r in circ_ids}
        for d in range(1, dn):
            x, y, w, h, area = dstats[d]
            if area < 3:
                continue
            sl = (slice(max(y - 2, 0), y + h + 2), slice(max(x - 2, 0), x + w + 2))
            blob = dlab[sl] == d
            ring = cv2.dilate(blob.astype(np.uint8), kernel, iterations=2) > 0
            if len(set(np.unique(lab[sl][ring]).tolist()) & circ_idx) >= 2:
                walk[sl] |= blob
    walk = cv2.morphologyEx(walk.astype(np.uint8), cv2.MORPH_CLOSE, kernel) > 0
    wpolys = mask_to_polygons(walk, simplify_px=0.75)
    walkable = unary_union(wpolys) if wpolys else MultiPolygon()
    if walkable.geom_type == "Polygon":
        walkable = MultiPolygon([walkable])

    # export walls as actually used: door slabs carved out, partitions included
    wall_segments = wall_segments_from_mask(walls_all, t)
    return GeometryPx(
        regions=regions,
        doors=doors,
        walkable=walkable,
        wall_segments=wall_segments,
        wall_mask_closed=wall_c,
        debug={
            "wall_thickness_px": t,
            "door_gap_px": gap_px,
            "door_gap_source": gap_src,
            "door_width_measured_px": door_w,
            "door_measurements": n_door_meas,
            "door_slabs_carved": n_slabs,
            "walk_mask": walk,
            "region_masks": masks,
        },
    )


def wall_segments_from_mask(wall: np.ndarray, thickness: float) -> list:
    """Wall centre-lines as straight segments (via skeleton tracing + simplification)."""
    from .graph import skeleton_polylines

    sk = skeletonize(wall)
    segs = []
    for line in skeleton_polylines(sk):
        if len(line) < 2:
            continue
        ls = LineString(line).simplify(max(thickness * 0.6, 1.0))
        coords = list(ls.coords)
        for a, b in zip(coords[:-1], coords[1:], strict=False):
            if Point(a).distance(Point(b)) >= max(thickness, 2):
                segs.append((tuple(a), tuple(b), thickness))
    return segs


class RegionMasks(Mapping):
    """Region id -> boolean mask, computed on demand from the label image (one full-page mask per region
    would need gigabytes on large CAD sheets with hundreds of spaces)."""

    def __init__(self, lab: np.ndarray):
        self.lab = lab
        self.idx: dict[str, int] = {}

    def add(self, rid: str, i: int) -> None:
        self.idx[rid] = i

    def __getitem__(self, rid: str) -> np.ndarray:
        return self.lab == self.idx[rid]

    def __iter__(self):
        return iter(self.idx)

    def __len__(self) -> int:
        return len(self.idx)


def _border_free(wall: np.ndarray) -> np.ndarray:
    from .segment import border_connected

    return border_connected(~wall)


def frame_outdoors(building: np.ndarray, radius: float) -> np.ndarray:
    """Pixels outside the building outline: the walls closed (dilate then erode, by distance) over gaps up
    to 2 x radius, holes filled; whatever stays connected to the image border is outdoors."""
    from .segment import border_connected

    r = max(float(radius), 1.0)
    grown = cv2.distanceTransform((~building).astype(np.uint8), cv2.DIST_L2, 5) <= r
    closed = cv2.distanceTransform(grown.astype(np.uint8), cv2.DIST_L2, 5) > r
    return border_connected(~closed)


def sheet_frame_outside(
    wall: np.ndarray, background: np.ndarray, t: float, return_frame: bool = False
) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
    """Outdoor space enclosed by a drawing-sheet border (CAD exports draw a frame round the page).

    Without this the outdoors inside the frame is one huge closed space and becomes the "corridor". A frame
    is a wall component whose bounding box spans most of the image and that runs along at least three of
    its own bounding-box edges. The outdoors is then the free space that hugs the inside of the frame: one
    component touching at least half of the frame's inner perimeter and covering at least a quarter of the
    framed area. A building drawn up to the image edge does not qualify: the spaces along its outer wall are
    many separate rooms, none of which runs round half the perimeter."""
    h, w = wall.shape
    out = np.zeros_like(wall)
    frames = np.zeros_like(wall)
    n, lab, st, _ = cv2.connectedComponentsWithStats(wall.astype(np.uint8), connectivity=8)
    free = ~wall & ~background
    band = max(3, int(round(2 * t)) + 2)
    for i in range(1, n):
        x, y, bw, bh, _ = st[i]
        if bw < 0.6 * w or bh < 0.6 * h:
            continue
        comp = lab[y : y + bh, x : x + bw] == i
        edges = [comp[:band].any(0), comp[-band:].any(0), comp[:, :band].any(1), comp[:, -band:].any(1)]
        if sum(e.mean() >= 0.9 for e in edges) < 3:
            continue
        frames |= lab == i
        inner = np.zeros_like(wall)
        y0, y1, x0, x1 = y + band, y + bh - band, x + band, x + bw - band
        if y1 - y0 < 3 * band or x1 - x0 < 3 * band:
            continue
        ring = np.zeros_like(wall)
        ring[y0 : y0 + band, x0:x1] = True
        ring[y1 - band : y1, x0:x1] = True
        ring[y0:y1, x0 : x0 + band] = True
        ring[y0:y1, x1 - band : x1] = True
        inner[y0:y1, x0:x1] = True
        fn_, flab = cv2.connectedComponents((free & inner).astype(np.uint8), connectivity=4)
        if fn_ <= 1:
            continue
        hits = np.bincount(flab[ring & free], minlength=fn_)
        hits[0] = 0
        best = int(hits.argmax())
        perim = int((ring & free).sum())
        area = int((flab == best).sum())
        if perim and hits[best] >= 0.5 * perim and area >= 0.25 * (y1 - y0) * (x1 - x0):
            out |= flab == best
    return (out, frames) if return_frame else out
