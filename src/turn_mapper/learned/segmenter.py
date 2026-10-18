"""LearnedSegmenter: the U-Net behind the same ``Segmenter`` interface as the classical one.

Everything after segmentation (wall-gap closing, doors, rooms, graph, POIs, validators, export) is shared,
so ``turn-mapper run plan.png --segmenter learned`` changes only how walls / floor / doors / stairs are found.

Weights: ``$TURN_SEG_WEIGHTS``, else ``$TURN_WEIGHTS_DIR/turn_seg.pt``, else ``weights/turn_seg.pt``.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import cv2
import numpy as np

from ..config import PipelineParams
from ..ir import Preprocessed, Segmentation
from .classes import BG, DOOR, ESCALATOR, LIFT, OTHER, STAIRS, WALL

_CACHE: dict[str, tuple] = {}


def weights_path() -> Path:
    if os.environ.get("TURN_SEG_WEIGHTS"):
        return Path(os.environ["TURN_SEG_WEIGHTS"])
    return Path(os.environ.get("TURN_WEIGHTS_DIR", "weights")) / "turn_seg.pt"


def _model(device: str):
    p = weights_path()
    if not p.exists():
        raise FileNotFoundError(
            f"no segmentation weights at {p}. Train them (docs/ML_GUIDE.md) and set TURN_SEG_WEIGHTS, "
            "or use --segmenter classical."
        )
    key = f"{p.resolve()}:{p.stat().st_mtime}:{device}"
    if key not in _CACHE:
        from .model import load_checkpoint

        model, ck = load_checkpoint(p, device)
        sha = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        _CACHE.clear()
        _CACHE[key] = (model, ck, sha)
    return _CACHE[key]


class LearnedSegmenter:
    name = "learned"

    def __init__(self, device: str | None = None):
        if device is None:
            try:
                import torch
            except ImportError as e:
                raise ImportError('learned segmenter needs the ML extra: pip install -e ".[ml]"') from e
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device

    def segment(self, pre: Preprocessed, params: PipelineParams) -> Segmentation:
        from ..segment import ClassicalSegmenter, border_connected, estimate_levels
        from ..vectorize import wall_thickness_px
        from .model import predict_proba

        model, ck, sha = _model(self.device)
        g = pre.gray_raw
        h, w = g.shape
        # bring the plan to the wall thickness the network was trained on (plans come at any resolution)
        s0 = 1.0
        train_t = ck.get("wall_px_median")
        if train_t:
            t = wall_thickness_px(ClassicalSegmenter().segment(pre, params).wall)
            s0 = float(np.clip(train_t / max(t, 1.0), 0.25, 4.0))
        tile = int(ck.get("crop", 512))
        best = None
        for mult in params.learned_scales or (1.0,):
            s = float(np.clip(s0 * mult, 0.2, 4.0))
            s = min(s, 4096 / max(h, w))
            gs = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
            prob = predict_proba(model, gs, tile=tile, device=self.device)
            conf = _confidence(prob)
            if best is None or conf > best[0]:
                best = (conf, s, prob)
        conf, s, prob = best
        if prob.shape[1:] != g.shape:
            prob = np.stack([cv2.resize(c, (w, h), interpolation=cv2.INTER_LINEAR) for c in prob])
        cls = prob.argmax(0).astype(np.uint8)

        wall = prob[WALL] > params.learned_wall_thr if params.learned_wall_thr is not None else cls == WALL
        if params.learned_min_wall_frag_t2 > 0:
            wall = drop_small_fragments(wall, params.learned_min_wall_frag_t2)
        outside = np.isin(cls, (BG, OTHER)) & ~wall
        background = border_connected(outside)
        floor = ~wall & ~background
        stairs = np.isin(cls, (STAIRS, ESCALATOR))
        doors = (cls == DOOR) & ~wall if params.learned_doors else None
        lv = estimate_levels(g)
        lv.update(
            {
                "filled": True,  # background comes from the network, not from colour or geometry
                "wall_mode": "learned",
                "learned": {
                    "weights_sha256_16": sha,
                    "scale": round(s, 3),
                    "scale_from_thickness": round(s0, 3),
                    "confidence": round(conf, 4),
                    "lift_px": int((cls == LIFT).sum()),
                },
            }
        )
        return Segmentation(
            wall=wall,
            floor=floor,
            background=background,
            levels=lv,
            method=self.name,
            stairs=stairs,
            partitions=None,
            doors=doors,
        )


def _confidence(prob: np.ndarray) -> float:
    """Mean top-class probability over the building (pixels not predicted as background). Used to pick the
    inference scale: a plan shown at the size the network was trained on gives confident predictions."""
    top = prob.max(0)
    inside = prob.argmax(0) != BG
    return float(top[inside].mean()) if inside.any() else 0.0


def drop_small_fragments(wall: np.ndarray, min_t2: float) -> np.ndarray:
    """Remove wall components smaller than ``min_t2`` x thickness^2 (stray strokes from text, furniture or
    hatching that would otherwise split a room); the connected wall network is untouched."""
    from ..vectorize import wall_thickness_px

    t = wall_thickness_px(wall)
    n, lab, st, _ = cv2.connectedComponentsWithStats(wall.astype(np.uint8), connectivity=8)
    if n <= 2:
        return wall
    keep = st[:, cv2.CC_STAT_AREA] >= min_t2 * t * t
    keep[0] = False
    keep[int(np.argmax(st[1:, cv2.CC_STAT_AREA])) + 1] = True
    return keep[lab]
