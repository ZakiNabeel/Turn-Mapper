"""Synthetic floor plans with known ground truth, for tests and contract fixtures.

Drawn in the same flat style as floor-planner exports (paper 255, floor 238, walls 191), so the
classical pipeline can be tested end to end without real (permission-restricted) plans.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

PX_PER_M = 25.0  # 0.04 m/px
WALL_M = 0.16
DOOR_M = 0.9


@dataclass
class SynthRoom:
    label: str
    x0: float
    y0: float
    x1: float
    y1: float
    door: tuple[str, float] | None  # (side, offset along side in m) or None = no door


@dataclass
class SynthPlan:
    rgb: np.ndarray
    m_per_px: float
    rooms: list[SynthRoom]
    corridor: tuple[float, float, float, float]
    extra: dict = field(default_factory=dict)

    @property
    def rooms_with_doors(self) -> list[SynthRoom]:
        return [r for r in self.rooms if r.door]


def _px(v: float) -> int:
    return int(round(v * PX_PER_M))


def make_plan(variant: str = "basic") -> SynthPlan:
    """``basic``: 30x12 m, central corridor, 4 rooms above and 3 below (one without a door).
    ``lshape``: adds a vertical corridor wing with 2 more rooms (tests junctions)."""
    W, H = (30.0, 12.0) if variant == "basic" else (30.0, 22.0)
    margin = 1.0
    img = np.full((_px(H + 2 * margin), _px(W + 2 * margin), 3), 255, np.uint8)
    ox = oy = margin

    def rect(x0, y0, x1, y1, color):
        cv2.rectangle(img, (_px(ox + x0), _px(oy + y0)), (_px(ox + x1), _px(oy + y1)), color, -1)

    def wall(x0, y0, x1, y1):
        t = max(_px(WALL_M) // 2, 1)
        a = (_px(ox + x0), _px(oy + y0))
        b = (_px(ox + x1), _px(oy + y1))
        cv2.rectangle(
            img,
            (min(a[0], b[0]) - t, min(a[1], b[1]) - t),
            (max(a[0], b[0]) + t, max(a[1], b[1]) + t),
            (191, 191, 191),
            -1,
        )

    rooms = [
        SynthRoom("R-101", 0, 0, 7, 5, ("bottom", 3.0)),
        SynthRoom("R-102", 7, 0, 14, 5, ("bottom", 2.0)),
        SynthRoom("R-103", 14, 0, 22, 5, ("bottom", 4.0)),
        SynthRoom("R-104", 22, 0, 30, 5, ("bottom", 1.0)),
        SynthRoom("R-105", 0, 8, 10, 12, ("top", 4.0)),
        SynthRoom("R-106", 10, 8, 20, 12, ("top", 6.0)),
        SynthRoom("R-107", 20, 8, 30, 12, None),  # no door -> must be reported, not routed to
    ]
    corridor = (0.0, 5.0, 30.0, 8.0)
    building = [(0.0, 0.0, W, 12.0)]
    if variant == "lshape":
        # corridor wing going down from x=12..15, rooms either side
        rooms[5] = SynthRoom("R-106", 15, 8, 20, 12, ("left", 2.0))
        rooms[4] = SynthRoom("R-105", 0, 8, 12, 12, ("top", 4.0))
        rooms += [
            SynthRoom("R-108", 4, 12, 12, 22, ("right", 3.0)),
            SynthRoom("R-109", 15, 12, 23, 22, ("left", 5.0)),
        ]
        building = [(0.0, 0.0, W, 12.0), (4.0, 12.0, 23.0, 22.0)]
    for b in building:
        rect(*b, (238, 238, 238))
    for b in building:
        x0, y0, x1, y1 = b
        wall(x0, y0, x1, y0)
        wall(x0, y1, x1, y1)
        wall(x0, y0, x0, y1)
        wall(x1, y0, x1, y1)
    if variant == "lshape":
        # open the wing to the main corridor and clear the shared outline between the two parts
        rect(12.0 + WALL_M, 8.0, 15.0 - WALL_M, 22.0 - WALL_M, (238, 238, 238))
        rect(4.0 + WALL_M, 12.0 - WALL_M, 23.0 - WALL_M, 12.0 + WALL_M, (238, 238, 238))
        rect(23.0 + WALL_M, 12.0 - WALL_M, 30.0, 12.0 + WALL_M, (191, 191, 191))
        wall(4.0, 12.0, 4.0, 22.0)
        wall(23.0, 12.0, 23.0, 22.0)
        wall(12.0, 12.0, 12.0, 22.0)
        wall(15.0, 12.0, 15.0, 22.0)
        wall(0.0, 12.0, 4.0, 12.0)
        wall(23.0, 12.0, 30.0, 12.0)
        wall(15.0, 8.0, 15.0, 12.0)
    for r in rooms:
        wall(r.x0, r.y0, r.x1, r.y0)
        wall(r.x0, r.y1, r.x1, r.y1)
        wall(r.x0, r.y0, r.x0, r.y1)
        wall(r.x1, r.y0, r.x1, r.y1)
    if variant == "lshape":
        rect(12.0 + WALL_M, 8.0 + WALL_M, 15.0 - WALL_M, 12.0 + WALL_M, (238, 238, 238))
    for r in rooms:
        if not r.door:
            continue
        side, off = r.door
        half = WALL_M
        if side in ("top", "bottom"):
            y = r.y0 if side == "top" else r.y1
            rect(r.x0 + off, y - half, r.x0 + off + DOOR_M, y + half, (238, 238, 238))
        else:
            x = r.x0 if side == "left" else r.x1
            rect(x - half, r.y0 + off, x + half, r.y0 + off + DOOR_M, (238, 238, 238))
    for r in rooms:
        cx, cy = _px(ox + (r.x0 + r.x1) / 2), _px(oy + (r.y0 + r.y1) / 2)
        (tw, th), _ = cv2.getTextSize(r.label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.putText(
            img,
            r.label,
            (cx - tw // 2, cy + th // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (70, 70, 70),
            2,
            cv2.LINE_AA,
        )
    return SynthPlan(
        rgb=img,
        m_per_px=1.0 / PX_PER_M,
        rooms=rooms,
        corridor=corridor,
        extra={"origin_px": (_px(ox), _px(oy))},
    )
