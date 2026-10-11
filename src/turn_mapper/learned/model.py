"""U-Net segmentation model: build, checkpoints (with manifest + sha256), sliding-window inference."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from .classes import CLASSES
from .data import to_input


def _torch():
    try:
        import segmentation_models_pytorch as smp
        import torch
    except ImportError as e:  # keep the classical pipeline importable without the ML extra
        raise ImportError('learned segmenter needs the ML extra: pip install -e ".[ml]"') from e
    return torch, smp


def build_model(arch: str = "Unet", encoder: str = "resnet34", encoder_weights: str | None = "imagenet"):
    _, smp = _torch()
    return getattr(smp, arch)(
        encoder_name=encoder, encoder_weights=encoder_weights, in_channels=3, classes=len(CLASSES)
    )


def save_checkpoint(path: str | Path, model, meta: dict) -> dict:
    torch, _ = _torch()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "classes": list(CLASSES), **meta}, path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {"file": path.name, "sha256": sha, "classes": list(CLASSES), **meta}
    path.with_suffix(".json").write_text(json.dumps(manifest, indent=1, default=str))
    return manifest


def load_checkpoint(path: str | Path, device: str = "cpu"):
    torch, _ = _torch()
    ck = torch.load(str(path), map_location=device, weights_only=False)
    if list(ck.get("classes", [])) != list(CLASSES):
        raise ValueError(f"checkpoint classes {ck.get('classes')} != {list(CLASSES)}")
    model = build_model(ck.get("arch", "Unet"), ck.get("encoder", "resnet34"), encoder_weights=None)
    model.load_state_dict(ck["state_dict"])
    model.to(device).eval()
    return model, ck


def predict_proba(model, gray: np.ndarray, tile: int = 512, overlap: int | None = None, device: str = "cpu"):
    """Class probabilities CxHxW for a whole plan, by overlapping tiles blended with a smooth window."""
    torch, _ = _torch()
    h, w = gray.shape
    overlap = tile // 4 if overlap is None else min(overlap, tile // 2)
    stride = tile - overlap
    H = max(tile, int(np.ceil((h - tile) / stride)) * stride + tile) if h > tile else tile
    W = max(tile, int(np.ceil((w - tile) / stride)) * stride + tile) if w > tile else tile
    pad_val = int(np.median(np.concatenate([gray[0], gray[-1], gray[:, 0], gray[:, -1]])))
    g = np.full((H, W), pad_val, np.uint8)
    g[:h, :w] = gray
    x = torch.from_numpy(to_input(g))
    win = np.outer(np.hanning(tile) + 1e-3, np.hanning(tile) + 1e-3).astype(np.float32)
    acc = np.zeros((len(CLASSES), H, W), np.float32)
    wsum = np.zeros((H, W), np.float32)
    with torch.no_grad():
        for y in range(0, H - tile + 1, stride):
            for x0 in range(0, W - tile + 1, stride):
                inp = x[:, y : y + tile, x0 : x0 + tile][None].to(device)
                p = torch.softmax(model(inp), 1)[0].cpu().numpy()
                acc[:, y : y + tile, x0 : x0 + tile] += p * win
                wsum[y : y + tile, x0 : x0 + tile] += win
    return (acc / wsum)[:, :h, :w]
