"""Segmentation behind one interface. ``ClassicalSegmenter`` is the baseline (ADR-006); a learned
segmenter (M5) will implement the same ``segment`` method and be selected by config."""

from __future__ import annotations

from typing import Protocol

import cv2
import numpy as np

from .config import PipelineParams
from .ir import Preprocessed, Segmentation


class Segmenter(Protocol):
    name: str

    def segment(self, pre: Preprocessed, params: PipelineParams) -> Segmentation: ...


def estimate_levels(gray: np.ndarray) -> dict:
    """Estimate background / floor / wall grey levels from the histogram (no hard-coded colours)."""
    hist = np.bincount(gray.ravel(), minlength=256).astype(float)
    # background = most common value on a 3-px border (plans sit on paper); robust when floor > paper area
    border = np.concatenate([gray[:3].ravel(), gray[-3:].ravel(), gray[:, :3].ravel(), gray[:, -3:].ravel()])
    bg = int(np.argmax(np.bincount(border, minlength=256)))
    if bg < 200:  # dark or cropped border: fall back to the brightest dominant level
        bg = int(np.argmax(hist[235:]) + 235) if hist[235:].max() > 0 else 255
    h2 = hist.copy()
    h2[max(bg - 4, 0) :] = 0
    h2[:120] = 0
    floor = int(np.argmax(h2))
    h3 = hist.copy()
    h3[floor - 20 :] = 0
    h3[:60] = 0
    wall = int(np.argmax(h3)) if h3.max() > 0 else floor - 50
    return {"background": bg, "floor": floor, "wall": wall}


def border_connected(mask: np.ndarray) -> np.ndarray:
    """Pixels of ``mask`` connected to the image border."""
    m = mask.astype(np.uint8)
    n, lab = cv2.connectedComponents(m, connectivity=4)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    return np.isin(lab, list(border)) & mask


class ClassicalSegmenter:
    name = "classical"

    def segment(self, pre: Preprocessed, params: PipelineParams) -> Segmentation:
        g = pre.gray
        lv = estimate_levels(g)
        floor = np.abs(g.astype(int) - lv["floor"]) <= params.floor_tolerance
        # fill thin dark strokes (door arcs, residual text) inside floor
        floor = cv2.morphologyEx(floor.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) > 0
        wall_thr = min(params.wall_max_gray, (lv["floor"] + lv["wall"]) // 2 + 8)
        wall = g <= wall_thr
        # walls are thick; remove 1-2 px strokes (arcs, outlines of door slabs, text)
        wall = cv2.morphologyEx(wall.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
        floor &= ~wall
        light = g >= lv["background"] - 6
        background = border_connected(light & ~floor)
        stairs = detect_stairs(g, lv, wall | background, params)
        partitions = detect_partitions(g, lv, wall_thr, wall, background, stairs, params)
        return Segmentation(
            wall=wall,
            floor=floor,
            background=background,
            levels=lv,
            method=self.name,
            stairs=stairs,
            partitions=partitions,
        )


def detect_stairs(g: np.ndarray, lv: dict, exclude: np.ndarray, params: PipelineParams) -> np.ndarray:
    """Stairs in floor-planner exports are a smooth grey gradient near the floor colour, while real floor
    is flat. Dense 'near-but-not-equal to floor' pixels over a window = stair texture."""
    d = np.abs(g.astype(int) - lv["floor"])
    near = ((d >= 2) & (d <= 16) & ~exclude).astype(np.float32)
    k = max(9, int(min(g.shape) * params.stairs_window_frac))
    dens = cv2.blur(near, (k, k))
    m = cv2.morphologyEx(
        (dens > params.stairs_density).astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)
    )
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    keep = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= params.stairs_min_area_frac * k * k]
    return np.isin(lab, keep) & ~exclude


SEGMENTERS: dict[str, Segmenter] = {"classical": ClassicalSegmenter()}


def detect_partitions(
    g: np.ndarray,
    lv: dict,
    wall_thr: int,
    wall: np.ndarray,
    background: np.ndarray,
    stairs: np.ndarray,
    params: PipelineParams,
) -> np.ndarray:
    """Thin straight lines that divide spaces (open-plan partitions, study rooms, shelving).

    Kept: long horizontal/vertical thin strokes with floor on both sides. Rejected: door arcs and text
    (short/curved), door-slab outlines (next to a white slab), stair arrows (inside stairs), and the
    image border (next to background)."""
    k3 = np.ones((3, 3), np.uint8)
    thin = ((g <= lv["floor"] - 12) & ~cv2.dilate(wall.astype(np.uint8), k3).astype(bool)).astype(np.uint8)
    L = max(25, int(min(g.shape) * params.partition_min_len_frac))
    part = np.zeros_like(thin)
    for k in (np.ones((1, L), np.uint8), np.ones((L, 1), np.uint8)):
        part |= cv2.morphologyEx(thin, cv2.MORPH_OPEN, k)
    white = (g >= lv["background"] - 9) | background
    bad = cv2.dilate(white.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    bad |= cv2.dilate(stairs.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
    part = part.astype(bool) & ~bad
    # drop fragments that became short after filtering
    n, lab, st, _ = cv2.connectedComponentsWithStats(part.astype(np.uint8), connectivity=8)
    keep = [i for i in range(1, n) if max(st[i, cv2.CC_STAT_WIDTH], st[i, cv2.CC_STAT_HEIGHT]) >= L]
    return np.isin(lab, keep)


def remove_text_blobs(
    wall: np.ndarray, max_fill: float = 0.45, max_size_frac: float = 0.2
) -> tuple[np.ndarray, np.ndarray]:
    """Split dark pixels into walls and bold text.

    Bold labels are components separate from the wall network that are sparse (strokes fill little of
    their bounding box), smaller than ``max_size_frac`` of the image's short side, and made of thin strokes
    (a 5x5 opening erases them). Everything else stays a wall."""
    n, lab, st, _ = cv2.connectedComponentsWithStats(wall.astype(np.uint8), connectivity=8)
    if n <= 2:
        return wall, np.zeros_like(wall)
    main = int(np.argmax(st[1:, cv2.CC_STAT_AREA])) + 1
    limit = max_size_frac * min(wall.shape)
    solid = cv2.morphologyEx(wall.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)) > 0
    drop = np.zeros(n, bool)
    for i in range(1, n):
        if i == main:
            continue
        w, h, a = st[i, cv2.CC_STAT_WIDTH], st[i, cv2.CC_STAT_HEIGHT], st[i, cv2.CC_STAT_AREA]
        if max(w, h) > limit or a / max(w * h, 1) > max_fill:
            continue
        x, y = st[i, cv2.CC_STAT_LEFT], st[i, cv2.CC_STAT_TOP]
        comp = lab[y : y + h, x : x + w] == i
        if (solid[y : y + h, x : x + w] & comp).sum() < 0.25 * a:  # mostly thin strokes
            drop[i] = True
    text_like = drop[lab] & wall
    return wall & ~text_like, text_like
