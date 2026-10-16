"""Stairs and lifts -> Transition features with a walkable anchor point.

Stairs come from the segmentation's stair-texture mask; lifts from rooms whose OCR text says
"Elevator"/"Lift". The anchor is where a person stands to use the transition (stair foot / lift
door), always inside the walkable mask so the graph edge to it is valid. Multi-floor linking
(M9) will pair transition nodes across floors; on a single floor they are routable destinations.
"""

from __future__ import annotations

import cv2
import numpy as np
from shapely.geometry import Point

from .ir import GeometryPx, Issue, Segmentation, Transition
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
) -> list[Issue]:
    issues: list[Issue] = []
    walk = geom.debug["walk_mask"]
    stairs = seg.stairs if seg.stairs is not None else np.zeros_like(walk)
    walk_free = walk & ~cv2.dilate(stairs.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    reach = max_reach_m / m_per_px
    out: list[Transition] = []

    n, lab = cv2.connectedComponents(stairs.astype(np.uint8))
    for i in range(1, n):
        blob = lab == i
        # D-07: a flight of stairs is a fat blob; a door swing arc or a text stroke labelled 'stairs' by a
        # learned model is a thin ring/line with little area. Drop what cannot be a flight.
        area_m2 = float(blob.sum()) * m_per_px**2
        inradius_m = float(cv2.distanceTransform(blob.astype(np.uint8), cv2.DIST_L2, 3).max()) * m_per_px
        if area_m2 < min_area_m2 or inradius_m < min_inradius_m:
            issues.append(
                Issue("STAIRS_TOO_SMALL", f"stair-like blob of {area_m2:.1f} m2 ignored (arc/symbol)")
            )
            continue
        polys = mask_to_polygons(blob, simplify_px=1.5)
        if not polys:
            continue
        poly = max(polys, key=lambda p: p.area)
        # stair foot: walkable pixels touching the stair blob; fall back to nearest walkable pixel
        ring = cv2.dilate(blob.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool) & walk_free
        c = poly.centroid
        anchor = _nearest_pixel(ring, (c.x, c.y)) if ring.any() else _nearest_pixel(walk_free, (c.x, c.y))
        if anchor is None or Point(anchor).distance(poly) > reach:
            issues.append(Issue("STAIRS_UNREACHABLE", "stairs detected but no walkable point next to them"))
            continue
        out.append(Transition(id=f"t{len(out) + 1}", type="stairs", polygon=poly, anchor=Point(anchor)))

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
    geom.transitions = out
    geom.debug["stairs_mask"] = stairs
    return issues
