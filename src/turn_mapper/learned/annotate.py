"""Bootstrap annotations: turn the classical pipeline's result into a starting mask that a person corrects.

Drawing masks from scratch takes hours per floor; correcting a mostly right one takes minutes. Output is the
mask-dataset format (``images/``, ``masks/``) plus ``previews/`` (colour overlay to check, or edit in any
paint program using the palette in ``classes.PALETTE``).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..ir import FloorResult
from .classes import BG, DOOR, PALETTE, ROOM, STAIRS, WALKABLE, WALL


def mask_from_result(fr: FloorResult) -> np.ndarray:
    seg, geom = fr.seg, fr.geom
    mask = np.full(seg.wall.shape, BG, np.uint8)
    masks = geom.debug.get("region_masks", {})
    for r in geom.regions:
        m = masks.get(r.id)
        if m is not None:
            mask[m] = WALKABLE if r.kind == "circulation" else ROOM
    if seg.stairs is not None:
        mask[seg.stairs & (mask != BG)] = STAIRS
    mask[seg.wall] = WALL
    t = max(int(round(geom.debug.get("wall_thickness_px", 4))), 2)
    for d in geom.doors:
        (x0, y0), (x1, y1) = list(d.segment.coords)[:2]
        cv2.line(mask, (int(x0), int(y0)), (int(x1), int(y1)), int(DOOR), t + 2)
    return mask


def colorize(mask: np.ndarray, gray: np.ndarray | None = None) -> np.ndarray:
    pal = np.array(PALETTE + ((0, 0, 0),) * (256 - len(PALETTE)), np.uint8)
    rgb = pal[mask]
    if gray is not None:
        rgb = (0.55 * rgb + 0.45 * gray[..., None]).astype(np.uint8)
    return rgb


def export_dataset(results: dict[str, FloorResult], out: str | Path) -> list[str]:
    out = Path(out)
    for sub in ("images", "masks", "previews"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    ids = []
    for fid, fr in results.items():
        g = fr.pre.gray_raw
        m = mask_from_result(fr)
        cv2.imwrite(str(out / "images" / f"{fid}.png"), g)
        cv2.imwrite(str(out / "masks" / f"{fid}.png"), m)
        cv2.imwrite(str(out / "previews" / f"{fid}.png"), cv2.cvtColor(colorize(m, g), cv2.COLOR_RGB2BGR))
        ids.append(fid)
    return ids
