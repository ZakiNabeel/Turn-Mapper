"""Stairs and lifts -> Transition features with a walkable anchor point.

Stairs come from the segmentation's stair-texture mask; lifts from rooms whose OCR text says
"Elevator"/"Lift". The anchor is where a person stands to use the transition (stair foot / lift
door), always inside the walkable mask so the graph edge to it is valid. Multi-floor linking
(M9) will pair transition nodes across floors; on a single floor they are routable destinations.
"""

from __future__ import annotations

import re

import cv2
import numpy as np
from shapely.geometry import Point
from shapely.geometry import box as _box

from .ir import GeometryPx, Issue, Segmentation, TextBox, Transition
from .vectorize import mask_to_polygons


def _nearest_pixel(mask: np.ndarray, xy: tuple[float, float]) -> tuple[float, float] | None:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    i = int(np.argmin((xs - xy[0]) ** 2 + (ys - xy[1]) ** 2))
    return float(xs[i]), float(ys[i])


def find_transitions(
    geom: GeometryPx,
    seg: Segmentation,
    m_per_px: float,
    max_reach_m: float = 2.0,
    min_area_m2: float = 1.0,
    min_inradius_m: float = 0.0,
    words: list[TextBox] | None = None,
) -> list[Issue]:
    issues: list[Issue] = []
    walk = geom.debug["walk_mask"]
    stairs = seg.stairs if seg.stairs is not None else np.zeros_like(walk)
    walk_free = walk & ~cv2.dilate(stairs.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    reach = max_reach_m / m_per_px
    out: list[Transition] = []

    lifts = seg.lifts if seg.lifts is not None else np.zeros_like(walk)
    for mask, ttype, code in ((stairs, "stairs", "STAIRS"), (lifts & ~stairs, "lift", "LIFT")):
        n, lab = cv2.connectedComponents(mask.astype(np.uint8))
        for i in range(1, n):
            blob = lab == i
            # D-07: a flight of stairs (or a lift car) is a fat blob; a door swing arc or a text stroke that a
            # learned model labelled is a thin ring/line with little area. Drop what cannot be one.
            area_m2 = float(blob.sum()) * m_per_px**2
            inradius_m = float(cv2.distanceTransform(blob.astype(np.uint8), cv2.DIST_L2, 3).max()) * m_per_px
            if area_m2 < min_area_m2 or inradius_m < min_inradius_m:
                issues.append(
                    Issue(f"{code}_TOO_SMALL", f"{ttype}-like blob of {area_m2:.1f} m2 ignored (arc/symbol)")
                )
                continue
            polys = mask_to_polygons(blob, simplify_px=1.5)
            if not polys:
                continue
            poly = max(polys, key=lambda p: p.area)
            # where a person stands: walkable pixels touching the blob; else the nearest walkable pixel
            free = walk_free & ~blob
            ring = cv2.dilate(blob.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool) & free
            c = poly.centroid
            anchor = _nearest_pixel(ring, (c.x, c.y)) if ring.any() else _nearest_pixel(free, (c.x, c.y))
            if anchor is None or Point(anchor).distance(poly) > reach:
                issues.append(
                    Issue(f"{code}_UNREACHABLE", f"{ttype} detected but no walkable point next to it")
                )
                continue
            out.append(Transition(id=f"t{len(out) + 1}", type=ttype, polygon=poly, anchor=Point(anchor)))

    for r in geom.regions:
        if r.kind != "transition":
            continue
        text = f"{r.label or ''} {r.name or ''}".lower()
        if "stair" in text:
            ttype = "stairs"
        elif "elevator" in text or "lift" in text:
            ttype = "lift"
        else:
            continue
        if any(t.type == ttype and t.polygon.distance(r.polygon) * m_per_px < 3.0 for t in out):
            continue  # already found from the segmentation (a learned model's stair/lift class)
        mask = geom.debug["region_masks"][r.id]
        near = cv2.dilate(mask.astype(np.uint8), np.ones((5, 5), np.uint8), iterations=max(1, int(reach / 4)))
        cand = near.astype(bool) & walk_free
        c = r.polygon.centroid
        anchor = _nearest_pixel(cand, (c.x, c.y))
        if anchor is None:
            issues.append(
                Issue("LIFT_UNREACHABLE", f"{ttype} found but no walkable point within reach", r.id)
            )
            continue
        out.append(
            Transition(
                id=f"t{len(out) + 1}", type=ttype, polygon=r.polygon, anchor=Point(anchor), region_id=r.id
            )
        )
    out += _lifts_from_text(words or [], out, walk_free, m_per_px, len(out))
    geom.transitions = out
    geom.debug["stairs_mask"] = stairs
    return issues


LIFT_WORD = re.compile(r"^(elevators?|lifts?|elev\.?)$", re.IGNORECASE)


def _lifts_from_text(
    text: list[TextBox], found: list[Transition], walk_free: np.ndarray, m_per_px: float, n0: int
) -> list[Transition]:
    """Lifts whose shaft was not detected as a room: an 'Elevator' / 'Lift' word on the plan marks one.

    The anchor is the nearest walkable pixel within 4 m of the word. Words inside or beside a lift that was
    already found (within 3 m) are skipped, as are two words for the same shaft."""
    out: list[Transition] = []
    lifts = [t for t in found if t.type == "lift"]
    for tb in text:
        if not LIFT_WORD.match(tb.text.strip().strip(".,:;()[]")):
            continue
        cx, cy = tb.center
        pt = Point(cx, cy)
        if any(pt.distance(t.polygon) * m_per_px < 3.0 for t in lifts + out):
            continue
        r = int(round(4.0 / m_per_px))
        h, w = walk_free.shape
        x0, y0, x1, y1 = (
            max(int(cx) - r, 0),
            max(int(cy) - r, 0),
            min(int(cx) + r + 1, w),
            min(int(cy) + r + 1, h),
        )
        anchor = _nearest_pixel(walk_free[y0:y1, x0:x1], (cx - x0, cy - y0))
        if anchor is None or np.hypot(anchor[0] + x0 - cx, anchor[1] + y0 - cy) > r:
            continue
        bx0, by0, bx1, by1 = tb.box
        out.append(
            Transition(
                id=f"t{n0 + len(out) + 1}",
                type="lift",
                polygon=_box(bx0, by0, bx1, by1),
                anchor=Point(anchor[0] + x0, anchor[1] + y0),
            )
        )
    return out
