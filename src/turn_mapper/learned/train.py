"""Train or fine-tune the TURN segmentation model.

Pre-train on CubiCasa5K (after ``turn-mapper ml prepare-cubicasa``):
    turn-mapper ml train --data data/cubicasa_masks --out weights/turn_seg_cubicasa.pt --epochs 40

Fine-tune on our own annotated plans, starting from that checkpoint:
    turn-mapper ml train --data data/fast_masks --init weights/turn_seg_cubicasa.pt \
        --out weights/turn_seg_fast.pt --epochs 60 --lr 5e-5

Loss = cross-entropy + Dice (Dice keeps thin classes such as walls and doors from being ignored).
Validation metric = mean IoU over the classes present in the validation masks.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from .classes import CLASSES, IGNORE
from .data import MaskDataset
from .model import _torch, build_model, load_checkpoint, predict_proba, save_checkpoint


def confusion(pred: np.ndarray, gt: np.ndarray, n: int = len(CLASSES)) -> np.ndarray:
    m = gt != IGNORE
    return np.bincount(n * gt[m].astype(int) + pred[m], minlength=n * n).reshape(n, n)


def iou_from_conf(conf: np.ndarray) -> dict:
    tp = np.diag(conf).astype(float)
    denom = conf.sum(0) + conf.sum(1) - tp
    present = conf.sum(1) > 0
    per = {
        CLASSES[i]: (round(tp[i] / denom[i], 4) if present[i] and denom[i] > 0 else None)
        for i in range(len(tp))
    }
    vals = [v for v in per.values() if v is not None]
    return {"mIoU": round(float(np.mean(vals)), 4) if vals else 0.0, "per_class": per}


def evaluate(model, dirs, split="val", device="cpu", tile=512, max_items: int | None = None) -> dict:
    ds = MaskDataset(dirs, split=split, train=False)
    conf = np.zeros((len(CLASSES), len(CLASSES)), np.int64)
    for i in range(min(len(ds), max_items or len(ds))):
        img, mask = ds.load(i)
        pred = predict_proba(model, img, tile=tile, device=device).argmax(0)
        conf += confusion(pred, mask)
    return iou_from_conf(conf)


def train(
    data: list[str],
    out: str,
    epochs: int = 40,
    batch: int = 8,
    crop: int = 512,
    lr: float = 1e-4,
    encoder: str = "resnet34",
    encoder_weights: str | None = "imagenet",
    init: str | None = None,
    restyle_p: float = 0.3,
    max_iters: int | None = None,
    val_items: int | None = 50,
    workers: int = 2,
    device: str | None = None,
    seed: int = 0,
) -> dict:
    torch, smp = _torch()
    torch.manual_seed(seed)
    np.random.seed(seed)
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    if init:
        model, ck = load_checkpoint(init, device)
        encoder = ck.get("encoder", encoder)
        model.train()
    else:
        model = build_model("Unet", encoder, encoder_weights).to(device)
    ds = MaskDataset(data, "train", crop=crop, restyle_p=restyle_p, seed=seed)
    if len(ds) < 64:  # tiny fine-tuning sets: an "epoch" = at least 64 random crops
        ds.items = ds.items * int(np.ceil(64 / len(ds)))
    loader = torch.utils.data.DataLoader(
        ds, batch_size=batch, shuffle=True, num_workers=workers, drop_last=len(ds) > batch
    )
    ce = torch.nn.CrossEntropyLoss(ignore_index=IGNORE)
    dice = smp.losses.DiceLoss("multiclass", ignore_index=IGNORE)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    total = max_iters or epochs * len(loader)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=total, pct_start=0.05)
    has_val = any((Path(d) / "val.txt").exists() and (Path(d) / "val.txt").read_text().strip() for d in data)
    meta = {
        "arch": "Unet",
        "encoder": encoder,
        "init": init,
        "data": data,
        "crop": crop,
        "lr": lr,
        "batch": batch,
        "restyle_p": restyle_p,
        "wall_px_median": wall_px_median(data),
    }
    best, it, log, t0 = -1.0, 0, [], time.time()
    out_p = Path(out)
    for ep in range(epochs):
        ds._epoch = ep
        model.train()
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            logits = model(x)
            loss = ce(logits, y) + dice(logits, y)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            it += 1
            if it % 50 == 0 or it == 1:
                print(f"ep {ep} it {it}/{total} loss {loss.item():.4f} {time.time() - t0:.0f}s", flush=True)
            if it >= total:
                break
        model.eval()
        metrics = evaluate(model, data, "val", device, crop, val_items) if has_val else {"mIoU": None}
        log.append({"epoch": ep, "iters": it, "loss": round(loss.item(), 4), **metrics})
        print(json.dumps(log[-1]), flush=True)
        score = metrics["mIoU"] if metrics["mIoU"] is not None else -float(loss.item())
        if score > best:
            best = score
            save_checkpoint(out_p, model, {**meta, "epoch": ep, "iters": it, "val": metrics})
        if it >= total:
            break
    (out_p.with_suffix(".log.json")).write_text(json.dumps(log, indent=1))
    return {"best": best, "checkpoint": str(out_p), "log": log}


def wall_px_median(dirs: list[str], n: int = 30) -> float | None:
    """Typical wall thickness in the training images (px). Inference rescales plans to match it."""
    import cv2

    from ..vectorize import wall_thickness_px

    vals = []
    for d in dirs:
        for p in sorted((Path(d) / "masks").glob("*.png"))[:n]:
            m = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
            if (m == 1).sum() > 100:
                vals.append(wall_thickness_px(m == 1))
    return round(float(np.median(vals)), 2) if vals else None
