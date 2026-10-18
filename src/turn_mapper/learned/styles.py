"""Draw a training image from a class mask in one of many drawing conventions.

The learned segmenter failed on thin-line and double-line drawings because CubiCasa5K has none
(docs/RESULTS_ML_2026-10-12.md). Rendering vector datasets (ResPlan) and procedural institutional layouts in
every convention we meet in practice gives exact masks for all of them.

``render(mask, extras, style, rng)`` -> RGB uint8. ``extras`` carries what a mask alone does not: door swings
(hinge point, closed-leaf end, swing side) and text labels, in pixels.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .classes import BG, DOOR, ESCALATOR, LIFT, OTHER, ROOM, STAIRS, WALKABLE, WALL

STYLES = ("greyfill", "blackwalls", "thinlines", "doubleline", "hatched", "colored", "scanned", "cad")
INSIDE = (ROOM, WALKABLE, DOOR, STAIRS, LIFT, ESCALATOR, OTHER)


@dataclass
class Extras:
    doors: list[tuple[tuple[float, float], tuple[float, float], int]] = field(default_factory=list)
    labels: list[tuple[tuple[float, float], str]] = field(default_factory=list)
    furniture: list[tuple[int, int, int, int]] = field(
        default_factory=list
    )  # x0, y0, x1, y1 px (inside rooms)


def _arcs(img: np.ndarray, ex: Extras, color, th: int = 1) -> None:
    for hinge, end, side in ex.doors:
        hx, hy = hinge
        vx, vy = end[0] - hx, end[1] - hy
        r = float(np.hypot(vx, vy))
        if r < 3:
            continue
        a0 = np.degrees(np.arctan2(vy, vx))
        a1 = a0 + 90 * side
        lo, hi = sorted((a0, a1))
        cv2.ellipse(img, (int(hx), int(hy)), (int(r), int(r)), 0, lo, hi, color, th, cv2.LINE_AA)
        t = np.radians(a1)  # the open leaf
        cv2.line(
            img,
            (int(hx), int(hy)),
            (int(hx + r * np.cos(t)), int(hy + r * np.sin(t))),
            color,
            th,
            cv2.LINE_AA,
        )


def _text(img: np.ndarray, ex: Extras, color, rng: np.random.Generator, scale_px: float) -> None:
    font = [cv2.FONT_HERSHEY_SIMPLEX, cv2.FONT_HERSHEY_DUPLEX, cv2.FONT_HERSHEY_PLAIN][
        int(rng.integers(0, 3))
    ]
    fs = float(np.clip(scale_px / 32 * rng.uniform(0.7, 1.2), 0.3, 0.9))
    for (x, y), s in ex.labels:
        (tw, th), _ = cv2.getTextSize(s, font, fs, 1)
        cv2.putText(
            img, s, (int(x - tw / 2), int(y + th / 2)), font, fs, color, 1 + int(fs > 0.8), cv2.LINE_AA
        )


def _wall_core(mask: np.ndarray) -> np.ndarray:
    return mask == WALL


def _outline(w: np.ndarray, k: int = 3) -> np.ndarray:
    w8 = w.astype(np.uint8)
    return w & ~cv2.erode(w8, np.ones((k, k), np.uint8)).astype(bool)


def _stairs(img: np.ndarray, mask: np.ndarray, color, rng: np.random.Generator) -> None:
    st = np.isin(mask, (STAIRS, ESCALATOR))
    if not st.any():
        return
    period = int(rng.integers(5, 11))
    yy, xx = np.indices(mask.shape)
    lines = ((xx if rng.random() < 0.5 else yy) % period) == 0
    img[st & lines] = color


def _furniture(img: np.ndarray, ex: Extras, color) -> None:
    for x0, y0, x1, y1 in ex.furniture:
        cv2.rectangle(img, (x0, y0), (x1, y1), color, 1, cv2.LINE_AA)


def render(mask: np.ndarray, ex: Extras, style: str, rng: np.random.Generator) -> np.ndarray:
    h, w = mask.shape
    wall = _wall_core(mask)
    inside = np.isin(mask, INSIDE)
    t = max(2.0, float(np.median(_thickness_samples(wall))) if wall.any() else 4.0)
    out = np.full((h, w, 3), 255, np.uint8)
    dark = int(rng.integers(0, 50))
    if style == "greyfill":
        paper = int(rng.integers(245, 256))
        floor = int(rng.integers(225, 242))
        out[:] = paper
        out[inside] = floor
        out[wall] = int(rng.integers(150, 200))
        _arcs(out, ex, (160, 160, 160))
        _text(out, ex, (70, 70, 70), rng, t * 3)
    elif style == "blackwalls":
        out[wall] = dark
        _stairs(out, mask, (120, 120, 120), rng)
        _furniture(out, ex, (170, 170, 170))
        _arcs(out, ex, (90, 90, 90))
        _text(out, ex, (30, 30, 30), rng, t * 3)
    elif style == "thinlines":
        from skimage.morphology import skeletonize

        k = int(rng.integers(1, 3))
        thin = cv2.dilate(skeletonize(wall).astype(np.uint8), np.ones((k + 1, k + 1), np.uint8)) > 0
        out[thin] = dark
        _stairs(out, mask, (140, 140, 140), rng)
        _furniture(out, ex, (180, 180, 180))
        _arcs(out, ex, (120, 120, 120))
        _text(out, ex, (40, 40, 40), rng, t * 3)
    elif style == "doubleline":
        # line weight 1-2 px; the pair sits on the wall faces or up to 2 px outside them
        d = int(rng.integers(0, 3))
        fat = cv2.dilate(wall.astype(np.uint8), np.ones((2 * d + 1, 2 * d + 1), np.uint8)) > 0 if d else wall
        out[_outline(fat, int(rng.choice([3, 3, 5])))] = dark
        _stairs(out, mask, (140, 140, 140), rng)
        _furniture(out, ex, (180, 180, 180))
        _arcs(out, ex, (110, 110, 110))
        _text(out, ex, (40, 40, 40), rng, t * 3)
    elif style == "hatched":
        out[_outline(wall)] = dark
        yy, xx = np.indices(mask.shape)
        period = int(rng.integers(4, 8))
        out[wall & (((xx + yy) % period) == 0)] = dark + 40
        _stairs(out, mask, (140, 140, 140), rng)
        _arcs(out, ex, (110, 110, 110))
        _text(out, ex, (40, 40, 40), rng, t * 3)
    elif style == "colored":
        out[inside] = (245, 245, 240)
        n, lab = cv2.connectedComponents((mask == ROOM).astype(np.uint8))
        pal = rng.integers(185, 256, (max(n, 1), 3)).astype(np.uint8)
        rooms = mask == ROOM
        out[rooms] = pal[lab[rooms]]
        out[mask == WALKABLE] = rng.integers(215, 256, 3).astype(np.uint8)
        out[wall] = int(rng.integers(40, 110))
        _stairs(out, mask, (110, 110, 110), rng)
        _arcs(out, ex, (110, 110, 110))
        _text(out, ex, (40, 40, 40), rng, t * 3)
    elif style == "scanned":
        out[wall] = dark
        _stairs(out, mask, (120, 120, 120), rng)
        _arcs(out, ex, (90, 90, 90))
        _text(out, ex, (30, 30, 30), rng, t * 3)
        out = _scan(out, rng)
    elif style == "cad":  # thin outlines, door swings, furniture, dimension lines, grid bubbles
        out[_outline(wall)] = dark
        _stairs(out, mask, (90, 90, 90), rng)
        _furniture(out, ex, (130, 130, 130))
        _arcs(out, ex, (60, 60, 60))
        _text(out, ex, (20, 20, 20), rng, t * 3)
        _dimensions(out, mask, rng)
    else:
        raise ValueError(f"unknown style {style}")
    return out


def _thickness_samples(wall: np.ndarray) -> np.ndarray:
    d = cv2.distanceTransform(wall.astype(np.uint8), cv2.DIST_L2, 3)
    v = d[d > 0]
    if not len(v):
        return np.array([4.0])
    return np.array([2 * np.percentile(v, 90)])


def _scan(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    h, w = img.shape[:2]
    paper = rng.uniform(215, 245, 3).astype(np.float32)
    f = img.astype(np.float32) / 255.0 * paper
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy = rng.uniform(0.2, 0.8, 2)
    f *= (1.0 - rng.uniform(0.05, 0.18) * ((xx / w - cx) ** 2 + (yy / h - cy) ** 2))[..., None]
    f = cv2.GaussianBlur(f, (3, 3), rng.uniform(0.4, 1.1))
    f += rng.normal(0, rng.uniform(3, 9), f.shape)
    f = np.clip(f, 0, 255).astype(np.uint8)
    q = int(rng.integers(35, 80))
    return cv2.imdecode(cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, q])[1], cv2.IMREAD_COLOR)


def _dimensions(img: np.ndarray, mask: np.ndarray, rng: np.random.Generator) -> None:
    ys, xs = np.nonzero(mask != BG)
    if not len(xs):
        return
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    h, w = mask.shape
    col = (110, 110, 110)
    yd = max(3, y0 - int(rng.integers(8, 20)))
    cv2.line(img, (x0, yd), (x1, yd), col, 1)
    for x in np.linspace(x0, x1, int(rng.integers(3, 7))).astype(int):
        cv2.line(img, (x, yd - 4), (x, yd + 4), col, 1)
    xd = min(w - 4, x1 + int(rng.integers(8, 20)))
    cv2.line(img, (xd, y0), (xd, y1), col, 1)
    if rng.random() < 0.5:  # grid bubbles
        for x in np.linspace(x0, x1, int(rng.integers(3, 6))).astype(int):
            cv2.circle(img, (int(x), max(8, yd - 12)), 6, col, 1, cv2.LINE_AA)


def geometric_aug(
    img: np.ndarray, mask: np.ndarray, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """Rotations by 90 degrees and flips (the loader adds crops/scale jitter)."""
    k = int(rng.integers(0, 4))
    img, mask = np.rot90(img, k), np.rot90(mask, k)
    if rng.random() < 0.5:
        img, mask = img[:, ::-1], mask[:, ::-1]
    return np.ascontiguousarray(img), np.ascontiguousarray(mask)


__all__ = ["STYLES", "Extras", "render", "geometric_aug", "BG", "WALL"]
