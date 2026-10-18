"""ResPlan (17K residential plans as metric vector geometry, CC BY 4.0) -> TURN mask dataset.

ResPlan ships polygons, not images, so every plan is drawn by us (``styles.render``) in a random drawing
convention at a random realistic resolution, with an exact mask. Source: https://github.com/m-agour/ResPlan
(cite: ResPlan, arXiv 2508.14006). The pickle is opened with a restricted unpickler that only allows
Shapely/NumPy objects, so a tampered file cannot run code.

Coordinates are in a 256-unit canvas per plan; metres per unit = sqrt(plan["area"] / area(inner)).
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import cv2
import numpy as np

from .classes import BG, DOOR, IGNORE, OTHER, ROOM, STAIRS, WALKABLE, WALL
from .styles import STYLES, Extras, render

ROOM_KEYS = ("bedroom", "bathroom", "kitchen", "living", "storage")
_ALLOWED = ("shapely.", "numpy", "networkx.")  # the Kaggle release adds a networkx graph


class _SafeUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if module.startswith(_ALLOWED):
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"ResPlan pickle wants {module}.{name}: refused")


def load_resplan(path: str | Path) -> list[dict]:
    with open(path, "rb") as f:
        return _SafeUnpickler(f).load()


def _polys(g):
    if g is None or g.is_empty:
        return []
    return [p for p in getattr(g, "geoms", [g]) if p.geom_type == "Polygon" and not p.is_empty]


def m_per_unit(plan: dict) -> float:
    from shapely.ops import unary_union

    inner = unary_union(_polys(plan.get("inner")))
    a = float(inner.area) if not inner.is_empty else 0.0
    return float(np.sqrt(float(plan["area"]) / a)) if a > 0 and plan.get("area") else 0.05


def rasterize(plan: dict, m_per_px: float, rng: np.random.Generator) -> tuple[np.ndarray, Extras, float]:
    """Plan -> (class mask, extras for drawing, metres per pixel)."""
    from shapely import minimum_rotated_rectangle
    from shapely.ops import unary_union

    k = m_per_unit(plan) / m_per_px  # px per unit
    allg = unary_union([g for key in ("inner", "wall") for g in _polys(plan.get(key))])
    x0, y0, x1, y1 = allg.bounds
    pad = 1.0 / m_per_px / k  # 1 m in units
    x0, y0 = x0 - pad, y0 - pad
    w, h = int(np.ceil((x1 - x0 + pad) * k)), int(np.ceil((y1 - y0 + pad) * k))

    def pts(poly):
        return [
            np.round((np.asarray(r.coords) - (x0, y0)) * k).astype(np.int32)
            for r in [poly.exterior, *poly.interiors]
        ]

    def fill(mask, geom, cls):
        for p in _polys(geom):
            rings = pts(p)
            if len(rings) == 1:
                cv2.fillPoly(mask, rings, int(cls))
                continue
            tmp = np.zeros(mask.shape, np.uint8)
            cv2.fillPoly(tmp, rings[:1], 1)
            cv2.fillPoly(tmp, rings[1:], 0)  # holes keep what is underneath
            mask[tmp > 0] = int(cls)

    mask = np.full((h, w), BG, np.uint8)
    fill(mask, plan.get("inner"), WALKABLE)  # interior not in a named room = circulation
    for key in ROOM_KEYS:
        fill(mask, plan.get(key), ROOM)
    fill(mask, plan.get("stair"), STAIRS)
    fill(mask, plan.get("balcony"), OTHER)
    fill(mask, plan.get("wall"), WALL)
    fill(mask, plan.get("window"), WALL)
    ex = Extras()
    for key in ("door", "front_door"):
        for p in _polys(plan.get(key)):
            fill(mask, p, DOOR)
            c = np.asarray(minimum_rotated_rectangle(p).exterior.coords)[:4]
            e = np.hypot(*np.diff(np.vstack([c, c[:1]]), axis=0).T)
            i = int(np.argmax(e[:2]))  # long side = the opening
            a, b = c[i], c[i + 1]
            a, b = (a - (x0, y0)) * k, (b - (x0, y0)) * k
            if rng.random() < 0.5:
                a, b = b, a
            ex.doors.append((tuple(a), tuple(b), int(rng.choice([-1, 1]))))
    names = {
        "bedroom": ["Bedroom", "Bed", "BR"],
        "bathroom": ["Bath", "WC", "Toilet"],
        "kitchen": ["Kitchen"],
        "living": ["Living", "Lounge", "Hall"],
        "storage": ["Store"],
    }
    for key in ROOM_KEYS:
        for p in _polys(plan.get(key)):
            if rng.random() < 0.7 and p.area * k * k > 900:
                c = p.representative_point()
                ex.labels.append((((c.x - x0) * k, (c.y - y0) * k), str(rng.choice(names[key]))))
                if rng.random() < 0.35:  # furniture: a box or two inside the room
                    bx0, by0, bx1, by1 = ((np.array(p.bounds) - (x0, y0, x0, y0)) * k).astype(int)
                    for _ in range(int(rng.integers(1, 3))):
                        fw, fh = int(rng.integers(8, 30)), int(rng.integers(8, 30))
                        if bx1 - bx0 > fw + 8 and by1 - by0 > fh + 8:
                            fx = int(rng.integers(bx0 + 4, bx1 - fw - 4))
                            fy = int(rng.integers(by0 + 4, by1 - fh - 4))
                            ex.furniture.append((fx, fy, fx + fw, fy + fh))
    return mask, ex, m_per_px


def prepare(
    pkl: str | Path,
    out: str | Path,
    split_json: str | Path | None = None,
    limit: int | None = None,
    variants: int = 1,
    m_per_px: tuple[float, float] = (0.02, 0.045),
    styles: tuple[str, ...] = STYLES,
    seed: int = 0,
    ignore_residual: bool = False,
) -> dict:
    """Write ``images/``, ``masks/``, ``{train,val,test}.txt``.

    ``variants`` drawings per plan (different style and resolution); the split follows ResPlan's canonical
    split by plan id, so variants of one plan never leak across splits."""
    rng = np.random.default_rng(seed)
    out = Path(out)
    for sub in ("images", "masks"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    plans = load_resplan(pkl)
    split_of: dict[int, str] = {}
    if split_json:
        sp = json.loads(Path(split_json).read_text())
        for name, ids in sp.items():
            for i in ids:
                split_of[int(i)] = {"train": "train", "val": "val", "test": "test"}.get(name, "train")
    lists: dict[str, list[str]] = {"train": [], "val": [], "test": []}
    counts = dict.fromkeys(styles, 0)
    n = 0
    for plan in plans:
        if limit and n >= limit:
            break
        pid = int(plan["id"])
        split = split_of.get(pid) or ("val" if rng.random() < 0.1 else "train")
        for v in range(variants):
            style = str(rng.choice(styles))
            mask, ex, _ = rasterize(plan, float(rng.uniform(*m_per_px)), rng)
            img = render(mask, ex, style, rng)
            if (
                ignore_residual
            ):  # ResPlan "inner minus named rooms" is not reliably circulation: no loss there
                mask = np.where(mask == WALKABLE, IGNORE, mask).astype(np.uint8)
            name = f"rp{pid}_{v}"
            cv2.imwrite(str(out / "images" / f"{name}.png"), cv2.cvtColor(img, cv2.COLOR_RGB2GRAY))
            cv2.imwrite(str(out / "masks" / f"{name}.png"), mask)
            lists[split].append(name)
            counts[style] += 1
        n += 1
    for s, ids in lists.items():
        (out / f"{s}.txt").write_text("\n".join(ids) + ("\n" if ids else ""))
    info = {
        "source": "ResPlan (CC BY 4.0)",
        "plans": n,
        "variants": variants,
        "splits": {k: len(v) for k, v in lists.items()},
        "styles": counts,
        "m_per_px": list(m_per_px),
        "ignore_residual": ignore_residual,
    }
    (out / "dataset.json").write_text(json.dumps(info, indent=1))
    return info
