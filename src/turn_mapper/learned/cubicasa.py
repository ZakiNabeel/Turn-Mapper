"""CubiCasa5K reader: model.svg -> TURN class mask, and conversion to a plain mask dataset.

CubiCasa5K (Kalervo et al. 2019, CC BY-NC 4.0, https://zenodo.org/record/2613548) has ~5000 plans, each a
folder with ``F1_original.png``, ``F1_scaled.png`` and ``model.svg``. The SVG holds labelled polygons:
``<g class="Wall">``, ``<g class="Window">``, ``<g class="Door ...">``, ``<g class="Railing">`` and
``<g class="Space <Type>">`` (Kitchen, Bedroom, Hall, StairWell, ...). We rasterise those into TURN classes.

Licence: non-commercial. Fine for an FYP; the dataset and anything derived from it stay out of git.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np

from .classes import BG, DOOR, WALL, cubicasa_space_class

_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _parse_transform(s: str | None) -> np.ndarray:
    m = np.eye(3)
    if not s:
        return m
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", s):
        v = [float(x) for x in _NUM.findall(args)]
        t = np.eye(3)
        if name == "matrix" and len(v) == 6:
            t[0, :] = [v[0], v[2], v[4]]
            t[1, :] = [v[1], v[3], v[5]]
        elif name == "translate":
            t[0, 2], t[1, 2] = v[0], (v[1] if len(v) > 1 else 0.0)
        elif name == "scale":
            t[0, 0], t[1, 1] = v[0], (v[1] if len(v) > 1 else v[0])
        elif name == "rotate":
            a = math.radians(v[0])
            r = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
            if len(v) == 3:
                c, d = np.eye(3), np.eye(3)
                c[:2, 2], d[:2, 2] = (v[1], v[2]), (-v[1], -v[2])
                r = c @ r @ d
            t = r
        m = m @ t
    return m


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _label_of(el: ET.Element) -> tuple[str, str] | None:
    """(kind, subtype) for a labelled group, kind in Wall/Window/Door/Railing/Space."""
    cls = (el.get("class") or "").split()
    ident = (el.get("id") or "").strip()
    first = cls[0] if cls else ident
    if first in ("Wall", "Window", "Door", "Railing"):
        return first, ""
    if first == "Space":
        return "Space", (cls[1] if len(cls) > 1 else "Undefined")
    return None


def parse_svg(path: str | Path) -> tuple[list[tuple[str, str, np.ndarray]], tuple[float, float] | None]:
    """All labelled polygons as (kind, subtype, Nx2 points in SVG user units), plus the SVG (w, h)."""
    root = ET.parse(str(path)).getroot()
    size = None
    try:
        size = (float(_NUM.findall(root.get("width", ""))[0]), float(_NUM.findall(root.get("height", ""))[0]))
    except (IndexError, ValueError):
        vb = root.get("viewBox")
        if vb:
            p = [float(x) for x in _NUM.findall(vb)]
            size = (p[2], p[3]) if len(p) == 4 else None
    out: list[tuple[str, str, np.ndarray]] = []

    def walk(el: ET.Element, m: np.ndarray, label: tuple[str, str] | None, depth_in_label: int):
        m = m @ _parse_transform(el.get("transform"))
        tag = _local(el.tag)
        own = _label_of(el) if tag == "g" else None
        if own:
            label, depth_in_label = own, 0
        if tag == "polygon" and label and depth_in_label == 1:  # direct child of the labelled group
            pts = np.array(_NUM.findall(el.get("points", "")), float).reshape(-1, 2)
            if len(pts) >= 3:
                h = np.c_[pts, np.ones(len(pts))] @ m.T
                out.append((label[0], label[1], h[:, :2]))
        for ch in el:
            walk(ch, m, label, depth_in_label + 1 if label else 0)

    walk(root, np.eye(3), None, 0)
    return out, size


def rasterize(polys: list[tuple[str, str, np.ndarray]], shape: tuple[int, int], sx=1.0, sy=1.0) -> np.ndarray:
    """Paint polygons in navigation priority order: spaces < railings < walls/windows < doors."""
    mask = np.full(shape, BG, np.uint8)
    order = {"Space": 0, "Railing": 1, "Wall": 2, "Window": 2, "Door": 3}
    for kind, sub, pts in sorted(polys, key=lambda p: order[p[0]]):
        cls = cubicasa_space_class(sub) if kind == "Space" else (DOOR if kind == "Door" else WALL)
        q = np.round(pts * [sx, sy]).astype(np.int32)
        cv2.fillPoly(mask, [q], int(cls))
    return mask


def load_sample(folder: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """(grey image HxW uint8, class mask HxW uint8) for one CubiCasa folder.

    The polygon coordinates are pixel coordinates of ``F1_scaled.png``, used as they are (this is what the
    official CubiCasa loader does). The SVG's width/height attributes are only the drawing's bounding box
    and must NOT be used to rescale: doing so stretched the labels off the walls (measured on Kaggle,
    2026-10-12: wall pixels averaged grey 220 with rescaling vs 146 without; see docs/RESULTS_ML)."""
    folder = Path(folder)
    polys, _ = parse_svg(folder / "model.svg")
    for name in ("F1_scaled.png", "F1_original.png"):
        if (folder / name).exists():
            img = cv2.imread(str(folder / name), cv2.IMREAD_GRAYSCALE)
            return img, rasterize(polys, img.shape)
    raise FileNotFoundError(f"no F1_*.png in {folder}")


def _list_split(root: Path, split: str) -> list[Path]:
    f = root / f"{split}.txt"
    if f.exists():
        return [root / ln.strip().strip("/") for ln in f.read_text().splitlines() if ln.strip()]
    return []


def prepare(root: str | Path, out: str | Path, max_side: int = 2048, limit: int | None = None) -> dict:
    """Convert a CubiCasa5K folder into a mask dataset: out/{images,masks}/<id>.png + out/<split>.txt.

    Parsing SVGs every epoch is slow; this is done once (≈ 10-20 min for the full set on Colab)."""
    root, out = Path(root), Path(out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "masks").mkdir(parents=True, exist_ok=True)
    splits = {s: _list_split(root, s) for s in ("train", "val", "test")}
    if not any(splits.values()):  # no split files: every folder with a model.svg, 90/10
        allf = sorted(p.parent for p in root.rglob("model.svg"))
        k = max(1, len(allf) // 10)
        splits = {"train": allf[k:], "val": allf[:k], "test": []}
    stats = {"written": 0, "failed": 0}
    for split, folders in splits.items():
        ids = []
        for folder in folders[:limit] if limit else folders:
            sid = "_".join(folder.relative_to(root).parts)
            try:
                img, mask = load_sample(folder)
            except Exception as e:  # a handful of CubiCasa SVGs are broken; skip and count them
                stats["failed"] += 1
                print(f"skip {folder}: {e!r}"[:160])
                continue
            s = min(1.0, max_side / max(img.shape))
            if s < 1.0:
                img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
                mask = cv2.resize(mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
            cv2.imwrite(str(out / "images" / f"{sid}.png"), img)
            cv2.imwrite(str(out / "masks" / f"{sid}.png"), mask)
            ids.append(sid)
            stats["written"] += 1
        (out / f"{split}.txt").write_text("\n".join(ids) + ("\n" if ids else ""))
        stats[split] = len(ids)
    return stats
