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


def _odd(n: int) -> int:
    return int(n) | 1


def ink_map(g: np.ndarray) -> np.ndarray:
    """Darkness relative to the local paper/fill colour (0 = paper, 1 = black).

    A grey closing wider than any wall estimates the paper/room-fill colour under the strokes, so room
    fills (coloured rooms, grey floors) and uneven scan lighting are flattened away and only strokes
    remain."""
    k = _odd(max(15, int(0.03 * min(g.shape))))
    paper = cv2.morphologyEx(g, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    paper = cv2.blur(paper, (k, k))
    return np.clip((paper.astype(np.float32) - g) / np.maximum(paper, 1), 0, 1)


def noise_level(g: np.ndarray) -> float:
    """Robust pixel-noise estimate (scans/JPEG high, clean exports ~0)."""
    resid = g.astype(np.float32) - cv2.medianBlur(g, 3).astype(np.float32)
    return float(np.median(np.abs(resid)) / 0.6745 + np.mean(np.abs(resid)))


def straight_strokes(mask: np.ndarray, length: int) -> np.ndarray:
    """Pixels of ``mask`` lying on straight runs at least ``length`` long (h, v, both diagonals)."""
    m = mask.astype(np.uint8)
    out = np.zeros_like(m)
    d = _odd(max(3, int(round(length / np.sqrt(2)))))
    for k in (
        np.ones((1, length), np.uint8),
        np.ones((length, 1), np.uint8),
        np.eye(d, dtype=np.uint8),
        np.fliplr(np.eye(d, dtype=np.uint8)).copy(),
    ):
        out |= cv2.morphologyEx(m, cv2.MORPH_OPEN, k)
    return out > 0


class ClassicalSegmenter:
    name = "classical"

    def segment(self, pre: Preprocessed, params: PipelineParams) -> Segmentation:
        g = pre.gray
        h, w = g.shape
        lv = estimate_levels(g)
        gi = g.astype(int)
        floor_mass = float(
            np.mean(
                (np.abs(gi - lv["floor"]) <= params.floor_tolerance) & (np.abs(gi - lv["background"]) > 3)
            )
        )
        # "filled" = floors drawn in their own colour (floor-planner exports); else floor = paper colour
        filled = (lv["background"] - lv["floor"] >= 6) and floor_mass >= 0.10
        noise = noise_level(g)
        lv.update({"filled": bool(filled), "noise": round(noise, 2)})

        ink = ink_map(g)
        dark = ink > params.ink_threshold
        k3 = np.ones((3, 3), np.uint8)
        thick = cv2.morphologyEx(dark.astype(np.uint8), cv2.MORPH_OPEN, k3) > 0
        L = max(12, int(min(h, w) * params.wall_min_run_frac))
        thick_frac = thick.sum() / max(dark.sum(), 1)
        if thick_frac >= 0.35 and thick.sum() >= 0.004 * h * w:
            mode = "thick"
            # half-maximum trim: blur (scans, photos) spreads a wall's ink sideways and would inflate the
            # measured thickness (and every size derived from it); crisp walls are unaffected
            # Only for paper-floor plans: on filled plans the fill and thin grey walls sit near the
            # threshold and trimming breaks walls (measured on real filled plans, see RESULTS_GENERALITY).
            wall = thick
            if not filled and thick.any():
                peak = float(np.percentile(ink[thick], 90))
                core = thick & (ink >= 0.5 * peak)
                wall = cv2.morphologyEx(core.astype(np.uint8), cv2.MORPH_OPEN, k3) > 0
            # drop isolated thick blobs that are not straight runs (bold text, symbols, furniture icons)
            n, lab, st, _ = cv2.connectedComponentsWithStats(wall.astype(np.uint8), connectivity=8)
            if n > 2:
                straight = straight_strokes(wall, L)
                main = int(np.argmax(st[1:, cv2.CC_STAT_AREA])) + 1
                has_run = np.zeros(n, bool)
                has_run[np.unique(lab[straight])] = True
                keep = has_run.copy()
                keep[main] = True
                keep[0] = False
                wall = keep[lab]
        else:
            mode = "thin"  # single- or double-line drawings: walls are thin straight strokes
            wall = straight_strokes(dark, L)
            # fuse the two lines of a double-line wall into one solid wall (a single line is unaffected)
            wall = cv2.morphologyEx(wall.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
            wall = cv2.dilate(wall, k3) > 0
        lv["wall_mode"] = mode

        if filled:
            floor = np.abs(g.astype(int) - lv["floor"]) <= params.floor_tolerance
            floor = cv2.morphologyEx(floor.astype(np.uint8), cv2.MORPH_CLOSE, k3) > 0
            floor &= ~wall
            light = g >= lv["background"] - 6
            background = border_connected(light & ~floor)
        else:
            floor = ~wall & (ink < params.ink_threshold)
            background = np.zeros_like(wall)  # decided geometrically in vectorize (needs closed walls)
        clean = filled and noise <= params.stairs_max_noise
        stairs = detect_stairs(g, lv, wall | background, params) if clean else np.zeros_like(wall)
        wall_thr = min(params.wall_max_gray, (lv["floor"] + lv["wall"]) // 2 + 8)
        partitions = (
            detect_partitions(g, lv, wall_thr, wall, background, stairs, params)
            if clean and mode == "thick"
            else np.zeros_like(wall)
        )
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
    gf = g.astype(np.float32)
    local_std = np.sqrt(np.maximum(cv2.blur(gf * gf, (7, 7)) - cv2.blur(gf, (7, 7)) ** 2, 0))
    textured = local_std > 1.0  # a uniform fill (coloured room) is near the floor colour but flat
    near = ((d >= 2) & (d <= 16) & textured & ~exclude).astype(np.float32)
    k = max(9, int(min(g.shape) * params.stairs_window_frac))
    dens = cv2.blur(near, (k, k))
    m = cv2.morphologyEx(
        (dens > params.stairs_density).astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)
    )
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    keep = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= params.stairs_min_area_frac * k * k]
    return np.isin(lab, keep) & ~exclude


class _LazyLearned:
    """Imports torch only when the learned segmenter is actually used."""

    name = "learned"

    def segment(self, pre: Preprocessed, params: PipelineParams) -> Segmentation:
        from .learned.segmenter import LearnedSegmenter

        return LearnedSegmenter().segment(pre, params)


SEGMENTERS: dict[str, Segmenter] = {"classical": ClassicalSegmenter(), "learned": _LazyLearned()}


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
    # thin = a stroke darker than the local fill (not a whole region drawn in a darker colour)
    stroke = ink_map(g) > 0.05
    thin = (stroke & ~cv2.dilate(wall.astype(np.uint8), k3).astype(bool)).astype(np.uint8)
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
