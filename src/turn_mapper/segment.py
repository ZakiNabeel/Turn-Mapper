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
        return Segmentation(wall=wall, floor=floor, background=background, levels=lv, method=self.name)


SEGMENTERS: dict[str, Segmenter] = {"classical": ClassicalSegmenter()}
