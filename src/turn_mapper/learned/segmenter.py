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
from .classes import BG, ESCALATOR, LIFT, OTHER, STAIRS, WALL

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
        s = 1.0
        train_t = ck.get("wall_px_median")
        if train_t:
            t = wall_thickness_px(ClassicalSegmenter().segment(pre, params).wall)
            s = float(np.clip(train_t / max(t, 1.0), 0.25, 4.0))
            s = min(s, 4096 / max(h, w))
        gs = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
        prob = predict_proba(model, gs, tile=int(ck.get("crop", 512)), device=self.device)
        if gs.shape != g.shape:
            prob = np.stack([cv2.resize(c, (w, h), interpolation=cv2.INTER_LINEAR) for c in prob])
        cls = prob.argmax(0).astype(np.uint8)

        wall = cls == WALL
        outside = np.isin(cls, (BG, OTHER))
        background = border_connected(outside)
        floor = ~wall & ~background
        stairs = np.isin(cls, (STAIRS, ESCALATOR))
        lv = estimate_levels(g)
        lv.update(
            {
                "filled": True,  # background comes from the network, not from colour or geometry
                "wall_mode": "learned",
                "learned": {
                    "weights_sha256_16": sha,
                    "scale": round(s, 3),
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
        )
