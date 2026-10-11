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


STYLES = ("greyfill", "blackwalls", "thinlines", "doubleline", "colored", "scanned")


def render_style(plan: SynthPlan, style: str, seed: int = 0) -> np.ndarray:
    """Re-draw a synthetic plan in another drawing convention, keeping the same geometry.

    greyfill   - floor-planner export (grey floor, grey walls) - the original rendering
    blackwalls - CAD-like: white floor, solid black walls, black labels
    thinlines  - single-line drawing: 2 px black walls, white everything else
    doubleline - architectural: each wall drawn as two thin parallel lines, white in between
    colored    - every room filled with its own pastel colour, dark grey walls
    scanned    - blackwalls printed and scanned: yellowed paper, uneven light, blur, noise, 1.5 deg tilt, JPEG
    """
    rng = np.random.default_rng(seed)
    g = plan.rgb[:, :, 0]
    wall = g == 191
    bg = g == 255
    text = g < 150
    h, w = g.shape
    ox, oy = plan.extra["origin_px"]

    def arcs(img, color, th=1):
        for r in plan.rooms:
            if not r.door:
                continue
            side, off = r.door
            d = _px(DOOR_M)
            if side in ("top", "bottom"):
                y = oy + _px(r.y0 if side == "top" else r.y1)
                x = ox + _px(r.x0 + off)
                sgn = 1 if side == "top" else -1
                cv2.ellipse(
                    img,
                    (x, y),
                    (d, d),
                    0,
                    0 if sgn > 0 else 270,
                    90 if sgn > 0 else 360,
                    color,
                    th,
                    cv2.LINE_AA,
                )
            else:
                x = ox + _px(r.x0 if side == "left" else r.x1)
                y = oy + _px(r.y0 + off)
                sgn = 1 if side == "left" else -1
                cv2.ellipse(
                    img,
                    (x, y),
                    (d, d),
                    0,
                    0 if sgn > 0 else 90,
                    90 if sgn > 0 else 180,
                    color,
                    th,
                    cv2.LINE_AA,
                )

    if style == "greyfill":
        return plan.rgb.copy()
    out = np.full((h, w, 3), 255, np.uint8)
    if style in ("blackwalls", "scanned"):
        out[wall] = 20
        arcs(out, (90, 90, 90))
        out[text] = 30
    elif style == "thinlines":
        from skimage.morphology import skeletonize

        skel = skeletonize(wall)
        thin = cv2.dilate(skel.astype(np.uint8), np.ones((2, 2), np.uint8)) > 0
        out[thin] = 0
        arcs(out, (120, 120, 120))
        out[text] = 40
    elif style == "doubleline":
        fat = cv2.dilate(wall.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        outline = fat & ~cv2.erode(fat.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        out[outline] = 0
        arcs(out, (120, 120, 120))
        out[text] = 40
    elif style == "colored":
        out[~bg] = (245, 245, 240)
        palette = [
            (255, 220, 200),
            (200, 230, 255),
            (210, 245, 210),
            (255, 245, 190),
            (235, 210, 245),
            (250, 200, 215),
            (200, 245, 240),
            (230, 230, 200),
            (220, 220, 250),
        ]
        for i, r in enumerate(plan.rooms):
            x0, y0, x1, y1 = (ox + _px(r.x0), oy + _px(r.y0), ox + _px(r.x1), oy + _px(r.y1))
            region = np.zeros((h, w), bool)
            region[y0:y1, x0:x1] = True
            out[region & ~wall & ~bg] = palette[i % len(palette)]
        out[wall] = (70, 70, 70)
        arcs(out, (110, 110, 110))
        out[text] = (40, 40, 40)
    else:
        raise ValueError(f"unknown style {style}")
    if style == "scanned":
        paper = np.array([238, 232, 215], np.float32)
        img = out.astype(np.float32) / 255.0 * paper
        yy, xx = np.mgrid[0:h, 0:w]
        light = 1.0 - 0.12 * ((xx / w - 0.3) ** 2 + (yy / h - 0.4) ** 2)
        img *= light[..., None]
        img = cv2.GaussianBlur(img, (3, 3), 0.8)
        img += rng.normal(0, 6, img.shape)
        img = np.clip(img, 0, 255).astype(np.uint8)
        M = cv2.getRotationMatrix2D((w / 2, h / 2), 1.5, 1.0)
        img = cv2.warpAffine(img, M, (w, h), borderValue=tuple(int(v) for v in paper))
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        out = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return out
