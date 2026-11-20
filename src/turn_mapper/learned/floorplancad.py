"""FloorPlanCAD -> TURN mask dataset (real CAD drawings: offices, schools, hospitals, malls, homes).

FloorPlanCAD (Fan et al., ICCV 2021) is about 15,000 CAD floor-plan tiles as SVG; every drawn element
carries a ``semantic-id`` (1-35) and an ``instance-id``. Annotations are CC BY-NC 4.0 and the drawings are
not owned by the dataset authors: use for research only, keep data and weights out of git.

What it gives the segmenter that CubiCasa and ResPlan (homes) do not: **real stair, lift and escalator
symbols and real institutional wall drawings**. What it does not give: rooms and corridors. So the masks are
*partial* (see ``classes.OPEN``):

    wall (1), curtain wall (2), windows (9-11)                  -> WALL  (double lines closed into a band)
    stairs (30) / elevator (31) / escalator (32)                -> STAIRS / LIFT / ESCALATOR (instance hull)
    doors (3-8), opening symbol (12), furniture and fixtures
    (13-29), 33, 34, parking spots (35)                         -> IGNORE (our door class is the opening in
                                                                   the wall, not the swing symbol)
    unlabelled linework (dimensions, axes, hatching)            -> IGNORE in a thin band
    everything else                                             -> OPEN  (not wall, not a transition)

**Semantic ids.** The numbers above are the ones in the SVG release on the authors' Google Drive (attribute
``semantic-id``), checked by eye on 2026-11-15 with ``scripts/fpc_preview.py``: 1 = walls, 3 = door swings,
9 = windows, 28/29 = urinals and toilets, 30 = stairs, 31 = lifts, 32 = escalators, 35 = parking spots. That
is the published class list with wall and curtain wall moved to the front and everything else **plus two**
(published: stairs 28, elevator 29, escalator 30, wall 33). Using the published numbers trains toilets as
lifts and parking spots as walls. Ids 2, 10-12, 33 and 34 were not looked at: 2 and 10-11 are taken from the
shifted list (curtain wall, bay / blind window); 12, 33 and 34 get no loss.

The image is the drawing itself: every element stroked dark on light paper at a random resolution.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import cv2
import numpy as np

from .classes import ESCALATOR, IGNORE, LIFT, OPEN, STAIRS, WALL

TILE_M = 14.0  # FloorPlanCAD tiles are 14 m x 14 m squares
WALL_IDS = {1, 2, 9, 10, 11}
TRANSITION = {30: STAIRS, 31: LIFT, 32: ESCALATOR}
IGNORE_IDS = set(range(3, 9)) | set(range(12, 30)) | {33, 34, 35}
_NUM = re.compile(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _f(v, default: float = 0.0) -> float:
    m = _NUM.search(str(v)) if v is not None else None
    return float(m.group(0)) if m else default


def _viewbox(root) -> tuple[float, float, float, float]:
    vb = [float(x) for x in _NUM.findall(root.get("viewBox") or "")]
    if len(vb) == 4 and vb[2] > 0 and vb[3] > 0:
        return vb[0], vb[1], vb[2], vb[3]
    return 0.0, 0.0, _f(root.get("width"), 100.0), _f(root.get("height"), 100.0)


def _arc_points(p0, rx, ry, phi_deg, large, sweep, p1, n=12) -> list[tuple[float, float]]:
    """SVG elliptical arc (endpoint form) -> polyline."""
    if rx == 0 or ry == 0:
        return [p0, p1]
    phi = math.radians(phi_deg)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1, y1 = cp * dx + sp * dy, -sp * dx + cp * dy
    rx, ry = abs(rx), abs(ry)
    lam = x1 * x1 / (rx * rx) + y1 * y1 / (ry * ry)
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    k = math.sqrt(max(num / den, 0.0)) if den else 0.0
    if bool(large) == bool(sweep):
        k = -k
    cx1, cy1 = k * rx * y1 / ry, -k * ry * x1 / rx
    cx = cp * cx1 - sp * cy1 + (p0[0] + p1[0]) / 2
    cy = sp * cx1 + cp * cy1 + (p0[1] + p1[1]) / 2
    a0 = math.atan2((y1 - cy1) / ry, (x1 - cx1) / rx)
    a1 = math.atan2((-y1 - cy1) / ry, (-x1 - cx1) / rx)
    da = a1 - a0
    if sweep and da < 0:
        da += 2 * math.pi
    elif not sweep and da > 0:
        da -= 2 * math.pi
    out = []
    for i in range(n + 1):
        a = a0 + da * i / n
        ex, ey = rx * math.cos(a), ry * math.sin(a)
        out.append((cp * ex - sp * ey + cx, sp * ex + cp * ey + cy))
    return out


def path_polylines(d: str) -> list[list[tuple[float, float]]]:
    """A small SVG path reader (M L H V C Q A Z, absolute and relative): enough for CAD exports."""
    toks = re.findall(r"[MmLlHhVvCcQqAaZzSsTt]|-?\d*\.?\d+(?:[eE][-+]?\d+)?", d or "")
    out: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    pos, start, i, cmd = (0.0, 0.0), (0.0, 0.0), 0, ""

    def nums(k):
        nonlocal i
        v = [float(t) for t in toks[i : i + k]]
        i += k
        return v

    while i < len(toks):
        if toks[i].isalpha():
            cmd = toks[i]
            i += 1
            if cmd in "Zz":
                if cur:
                    cur.append(start)
                    out.append(cur)
                    cur = []
                pos = start
                continue
        try:
            rel = cmd.islower()
            c = cmd.upper()
            if c == "M":
                x, y = nums(2)
                pos = (pos[0] + x, pos[1] + y) if rel else (x, y)
                if len(cur) > 1:
                    out.append(cur)
                cur, start = [pos], pos
                cmd = "l" if rel else "L"
            elif c == "L":
                x, y = nums(2)
                pos = (pos[0] + x, pos[1] + y) if rel else (x, y)
                cur.append(pos)
            elif c == "H":
                (x,) = nums(1)
                pos = (pos[0] + x if rel else x, pos[1])
                cur.append(pos)
            elif c == "V":
                (y,) = nums(1)
                pos = (pos[0], pos[1] + y if rel else y)
                cur.append(pos)
            elif c in "CSQT":
                k = {"C": 6, "S": 4, "Q": 4, "T": 2}[c]
                v = nums(k)
                pts = [
                    (v[j] + (pos[0] if rel else 0), v[j + 1] + (pos[1] if rel else 0)) for j in range(0, k, 2)
                ]
                ctrl = [pos, *pts]
                for t in np.linspace(0, 1, 9)[1:]:  # de Casteljau on whatever control points there are
                    q = ctrl
                    while len(q) > 1:
                        q = [
                            (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                            for a, b in zip(q[:-1], q[1:], strict=False)
                        ]
                    cur.append(q[0])
                pos = pts[-1]
            elif c == "A":
                rx, ry, phi, large, sweep, x, y = nums(7)
                end = (pos[0] + x, pos[1] + y) if rel else (x, y)
                cur.extend(_arc_points(pos, rx, ry, phi, large, sweep, end)[1:])
                pos = end
            else:
                i += 1
        except ValueError:
            break  # malformed tail: keep what was read
    if len(cur) > 1:
        out.append(cur)
    return out


def read_svg(path: str | Path) -> tuple[list[dict], tuple[float, float, float, float]]:
    """-> ([{'pts': [(x, y), ...], 'sem': int, 'inst': int, 'width': float}], viewBox)."""
    import xml.etree.ElementTree as ET

    root = ET.parse(str(path)).getroot()
    vb = _viewbox(root)
    els: list[dict] = []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        polys: list[list[tuple[float, float]]] = []
        if tag == "path":
            polys = path_polylines(el.get("d", ""))
        elif tag == "line":
            polys = [[(_f(el.get("x1")), _f(el.get("y1"))), (_f(el.get("x2")), _f(el.get("y2")))]]
        elif tag in ("polyline", "polygon"):
            v = [float(x) for x in _NUM.findall(el.get("points") or "")]
            pts = list(zip(v[0::2], v[1::2], strict=False))
            if tag == "polygon" and pts:
                pts.append(pts[0])
            polys = [pts]
        elif tag in ("circle", "ellipse"):
            cx, cy = _f(el.get("cx")), _f(el.get("cy"))
            rx = _f(el.get("r")) if tag == "circle" else _f(el.get("rx"))
            ry = rx if tag == "circle" else _f(el.get("ry"))
            polys = [
                [(cx + rx * math.cos(a), cy + ry * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 25)]
            ]
        elif tag == "rect":
            x, y, w, h = (_f(el.get(k)) for k in ("x", "y", "width", "height"))
            polys = [[(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]]
        for pts in polys:
            if len(pts) >= 2:
                els.append(
                    {
                        "pts": pts,
                        "sem": int(_f(el.get("semantic-id"), 0)),
                        "inst": int(_f(el.get("instance-id"), -1)),
                        "width": _f(el.get("stroke-width"), 0.1),
                    }
                )
    return els, vb


def rasterize(
    els: list[dict], vb: tuple[float, float, float, float], size: int, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """-> (grey image, mask) of ``size`` x ``size`` px for one tile."""
    x0, y0, w, h = vb
    k = size / max(w, h)
    m_per_px = TILE_M / size

    def px(pts):
        return np.round([[(x - x0) * k * 16, (y - y0) * k * 16] for x, y in pts]).astype(np.int32)

    paper = int(rng.integers(238, 256))
    ink = int(rng.integers(0, 90))
    img = np.full((size, size), paper, np.uint8)
    wall = np.zeros((size, size), np.uint8)
    other = np.zeros((size, size), np.uint8)
    hulls: dict[tuple[int, int], list] = {}
    base_w = float(rng.uniform(0.9, 1.6))
    for n, e in enumerate(els):
        p = px(e["pts"])
        lw = max(1, int(round(base_w if e["width"] <= 0.15 else base_w * 1.6)))
        cv2.polylines(img, [p], False, ink, lw, cv2.LINE_AA, shift=4)
        sem = e["sem"]
        if sem in WALL_IDS:
            cv2.polylines(wall, [p], False, 1, 2, cv2.LINE_8, shift=4)
        elif sem in TRANSITION or sem in IGNORE_IDS:
            hulls.setdefault((sem, e["inst"] if e["inst"] >= 0 else -(n + 2)), []).append(p)
        else:
            cv2.polylines(other, [p], False, 1, 3, cv2.LINE_8, shift=4)
    mask = np.full((size, size), OPEN, np.uint8)
    mask[other > 0] = IGNORE
    for (sem, _), parts in hulls.items():
        if sem in IGNORE_IDS:
            hull = cv2.convexHull(np.concatenate(parts))
            cv2.fillConvexPoly(mask, hull, IGNORE, cv2.LINE_8, shift=4)
    # the two outline strokes of a wall -> one band (gaps up to ~0.35 m closed)
    kk = max(3, int(round(0.35 / m_per_px)) | 1)
    band = cv2.morphologyEx(wall, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (kk, kk)))
    mask[band > 0] = WALL
    for (sem, _), parts in hulls.items():
        if sem in TRANSITION:
            hull = cv2.convexHull(np.concatenate(parts))
            cv2.fillConvexPoly(mask, hull, TRANSITION[sem], cv2.LINE_8, shift=4)
    return img, mask


def prepare(
    train_dirs: list[str | Path],
    out: str | Path,
    test_dirs: list[str | Path] | None = None,
    limit: int | None = None,
    size_m_per_px: tuple[float, float] = (0.018, 0.035),
    val_share: float = 0.05,
    seed: int = 0,
    min_wall_share: float = 0.004,
    boost_transitions: int = 3,
) -> dict:
    """Write ``images/``, ``masks/``, ``{train,val,test}.txt`` from FloorPlanCAD SVG folders.

    Tiles with almost no wall are skipped (legends, site plans). Training tiles that contain a stair, lift or
    escalator are listed ``boost_transitions`` times: they are a few percent of the tiles."""
    rng = np.random.default_rng(seed)
    out = Path(out)
    for sub in ("images", "masks"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    lists: dict[str, list[str]] = {"train": [], "val": [], "test": []}
    stats = {"read": 0, "kept": 0, "skipped_no_wall": 0, "failed": 0, "with_stairs": 0, "with_lift": 0}
    stats["with_escalator"] = 0
    # strokes per semantic id: a wrong id table (e.g. the published list instead of the numbers in the files)
    # shows up here as stairs rarer than lifts, or no wall strokes at all
    per_id: dict[int, int] = {}

    def run(dirs, split):
        files = sorted(f for d in dirs for f in Path(d).rglob("*.svg"))
        if limit:
            files = files[:limit]
        for f in files:
            stats["read"] += 1
            try:
                els, vb = read_svg(f)
                for e in els:
                    per_id[e["sem"]] = per_id.get(e["sem"], 0) + 1
                size = int(round(TILE_M / float(rng.uniform(*size_m_per_px))))
                img, mask = rasterize(els, vb, size, rng)
            except Exception:  # noqa: BLE001  a malformed drawing must not stop a 15,000-file conversion
                stats["failed"] += 1
                continue
            if (mask == WALL).mean() < min_wall_share:
                stats["skipped_no_wall"] += 1
                continue
            name = f"fpc_{split[0]}_{f.stem}"
            cv2.imwrite(str(out / "images" / f"{name}.png"), img)
            cv2.imwrite(str(out / "masks" / f"{name}.png"), mask)
            has = {c: bool((mask == c).any()) for c in (STAIRS, LIFT, ESCALATOR)}
            stats["with_stairs"] += has[STAIRS]
            stats["with_lift"] += has[LIFT]
            stats["with_escalator"] += has[ESCALATOR]
            stats["kept"] += 1
            sp = split
            if split == "train" and rng.random() < val_share:
                sp = "val"
            reps = boost_transitions if sp == "train" and any(has.values()) else 1
            lists[sp] += [name] * reps

    run(train_dirs, "train")
    run(test_dirs or [], "test")
    for s, ids in lists.items():
        (out / f"{s}.txt").write_text("\n".join(ids) + ("\n" if ids else ""))
    info = {
        "source": "FloorPlanCAD (annotations CC BY-NC 4.0; research use only)",
        **stats,
        "splits": {k: len(v) for k, v in lists.items()},
        "m_per_px": list(size_m_per_px),
        "boost_transitions": boost_transitions,
        "strokes_per_semantic_id": {str(k): v for k, v in sorted(per_id.items())},
        "strokes_mapped": {
            "wall": sum(v for k, v in per_id.items() if k in WALL_IDS),
            "stairs": per_id.get(30, 0),
            "lift": per_id.get(31, 0),
            "escalator": per_id.get(32, 0),
        },
    }
    (out / "dataset.json").write_text(json.dumps(info, indent=1))
    return info


def fake_tile(path: str | Path, seed: int = 0, lift: bool = True) -> None:
    """A tiny SVG in the FloorPlanCAD convention (for tests; not real data)."""
    rng = np.random.default_rng(seed)
    o = float(rng.uniform(0, 4))
    s = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">']

    def line(x1, y1, x2, y2, sem, inst=-1, w=0.1):
        s.append(
            f'<path d="M {x1},{y1} L {x2},{y2}" semantic-id="{sem}" instance-id="{inst}" '
            f'stroke-width="{w}" stroke="black" fill="none"/>'
        )

    for y in (10 + o, 11.6 + o, 60 + o, 61.6 + o):  # two double-line walls
        line(5, y, 95, y, 1)
    for x in (5, 6.6, 93.4, 95):
        line(x, 10 + o, x, 61.6 + o, 1)
    for i in range(8):  # a stair: treads
        line(20 + 2 * i, 20 + o, 20 + 2 * i, 34 + o, 30, 1)
    line(20, 20 + o, 34, 20 + o, 30, 1)
    line(20, 34 + o, 34, 34 + o, 30, 1)
    if lift:
        for a, b, c, d in ((60, 20, 72, 20), (72, 20, 72, 32), (72, 32, 60, 32), (60, 32, 60, 20)):
            line(a, b + o, c, d + o, 31, 2)
        line(60, 20 + o, 72, 32 + o, 31, 2)
        line(72, 20 + o, 60, 32 + o, 31, 2)
    s.append(
        f'<path d="M 45,{61.6 + o} L 45,{55 + o} A 6.6,6.6 0 0 1 51.6,{61.6 + o}" semantic-id="3" '
        'instance-id="3" stroke-width="0.1" stroke="black" fill="none"/>'
    )
    s.append(f'<circle cx="80" cy="{48 + o}" r="3" semantic-id="20" instance-id="4" stroke-width="0.1"/>')
    line(0, 80, 100, 80, 0)  # a dimension line: unlabelled
    s.append("</svg>")
    Path(path).write_text("\n".join(s))
