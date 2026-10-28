"""Vector-PDF plans (CAD exports): read the drawing's own lines and text instead of a picture of them.

Industry tools work from the vector data (Esri builds rooms from CAD polylines; Pointr's patent first strips
text, hatching and leader lines and keeps the text as a database). This adapter does the same for PDFs:

- **door swings**: a quarter arc whose centre is the hinge, plus the leaf from the hinge to one arc end, is a
  door. Arc and leaf are left out of the drawing (they close the wall gap otherwise) and the closed-door
  position, hinge to the other arc end, is kept as a *known opening*;
- **hatching**: a stroke style whose segments are mostly parallel, oblique and many is fill pattern, not wall;
- **text** is not drawn (it punches holes in spaces) but kept, with exact positions, as the room-label source
  (no OCR needed);
- light or coloured fills (room colours) are not drawn; dark fills (solid walls, columns) are.

What remains is rendered as clean black strokes for the usual raster stages.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import cv2
import numpy as np

from .ir import FloorImage, TextBox


def _pt(p) -> np.ndarray:
    return np.array([p.x, p.y], float)


def _bezier(p0, p1, p2, p3, n: int = 10) -> np.ndarray:
    t = np.linspace(0, 1, n)[:, None]
    return ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * t * t * p2 + t**3 * p3


def _circle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> tuple[np.ndarray, float] | None:
    """Circle through three points (centre, radius)."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return None
    ux = (
        (ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)
    ) / d
    uy = (
        (ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)
    ) / d
    centre = np.array([ux, uy])
    return centre, float(np.linalg.norm(a - centre))


def _is_dark(color) -> bool:
    if color is None:
        return False
    r, g, b = color[:3]
    # walls are near-black; grey and colour fills (wayfinding maps) are room fills, not walls
    return 0.299 * r + 0.587 * g + 0.114 * b < 0.2


def parse_page(page) -> dict:
    """Primitives of one PDF page: strokes, dark fills, arcs (quarter-circle Béziers)."""
    strokes, fills, arcs = [], [], []
    for pi, d in enumerate(page.get_drawings()):
        width = float(d.get("width") or 0.0)
        style = (round(width, 2), tuple(round(c, 2) for c in (d.get("color") or (0, 0, 0))))
        is_fill = d.get("fill") is not None
        polys: list[np.ndarray] = []
        for it in d["items"]:
            k = it[0]
            if k == "l":
                seg = np.array([_pt(it[1]), _pt(it[2])])
                if d.get("color") is not None:
                    strokes.append({"pts": seg, "style": style, "path": pi, "kind": "l"})
            elif k == "c":
                p0, p1, p2, p3 = (_pt(q) for q in it[1:5])
                seg = _bezier(p0, p1, p2, p3)
                circ = _circle(p0, seg[len(seg) // 2], p3)
                arc = {"pts": seg, "style": style, "path": pi, "kind": "c", "p0": p0, "p3": p3}
                if circ is not None:
                    centre, r = circ
                    chord = float(np.linalg.norm(p3 - p0))
                    sweep = 2 * math.degrees(math.asin(min(1.0, chord / (2 * r)))) if r > 0 else 0
                    arc.update(centre=centre, r=r, sweep=sweep)
                    arcs.append(arc)
                if d.get("color") is not None:
                    strokes.append(arc)
            elif k == "re":
                r = it[1]
                seg = np.array([[r.x0, r.y0], [r.x1, r.y0], [r.x1, r.y1], [r.x0, r.y1], [r.x0, r.y0]], float)
                if d.get("color") is not None:
                    strokes.append({"pts": seg, "style": style, "path": pi, "kind": "re"})
            elif k == "qu":
                q = it[1]
                seg = np.array([_pt(q.ul), _pt(q.ur), _pt(q.lr), _pt(q.ll), _pt(q.ul)])
                if d.get("color") is not None:
                    strokes.append({"pts": seg, "style": style, "path": pi, "kind": "qu"})
            else:
                continue
            polys.append(seg)
        if is_fill and _is_dark(d.get("fill")) and polys:
            # chain consecutive items into closed sub-paths; filled together they keep their holes
            subs: list[np.ndarray] = []
            for seg in polys:
                if subs and np.allclose(subs[-1][-1], seg[0], atol=0.05):
                    subs[-1] = np.vstack([subs[-1], seg[1:]])
                else:
                    subs.append(seg)
            fills.append(subs)
    return {"strokes": strokes, "fills": fills, "arcs": arcs}


def merge_arcs(arcs: list[tuple[int, dict]]) -> list[tuple[int, dict]]:
    """Join Bézier pieces of one circle that meet end to end (CAD exports often draw a 90 degree swing as
    two 45 degree curves)."""
    if not arcs:
        return arcs
    parent = list(range(len(arcs)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    grid: dict = {}
    for k, (_, a) in enumerate(arcs):
        for e in (a["p0"], a["p3"]):
            grid.setdefault((round(e[0], 1), round(e[1], 1)), []).append(k)
    for ks in grid.values():
        for x in ks:
            for y in ks:
                ax, ay = arcs[x][1], arcs[y][1]
                if x < y and abs(ax["r"] - ay["r"]) <= 0.05 * ax["r"]:
                    if np.linalg.norm(ax["centre"] - ay["centre"]) <= 0.1 * ax["r"]:
                        parent[find(x)] = find(y)
    groups: dict = {}
    for k in range(len(arcs)):
        groups.setdefault(find(k), []).append(k)
    out = []
    for ks in groups.values():
        if len(ks) == 1:
            out.append(arcs[ks[0]])
            continue
        ends: dict = {}
        for k in ks:
            for e in (arcs[k][1]["p0"], arcs[k][1]["p3"]):
                key = (round(e[0], 1), round(e[1], 1))
                ends[key] = (ends.get(key, (0, e))[0] + 1, e)
        free = [e for n, e in ends.values() if n == 1]
        if len(free) != 2:
            out.extend(arcs[k] for k in ks)
            continue
        a0 = dict(arcs[ks[0]][1])
        a0.update(
            p0=free[0],
            p3=free[1],
            sweep=sum(arcs[k][1]["sweep"] for k in ks),
            members=[arcs[k][0] for k in ks],
        )
        out.append((arcs[ks[0]][0], a0))
    return out


def polyline_arcs(strokes: list[dict]) -> list[tuple[int, dict]]:
    """Arcs exported as chains of short straight segments (some CAD/PDF writers flatten curves).
    Returns arc records like parse_page's, with the chain's stroke ids as members."""
    out: list[tuple[int, dict]] = []
    chain: list[int] = []

    def fit(ids: list[int]) -> None:
        if len(ids) < 5:
            return
        pts = np.vstack([strokes[ids[0]]["pts"][:1]] + [strokes[k]["pts"][1:] for k in ids])
        circ = _circle(pts[0], pts[len(pts) // 2], pts[-1])
        if circ is None:
            return
        centre, r = circ
        d = np.linalg.norm(pts - centre, axis=1)
        seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        if r <= 0 or np.abs(d - r).max() > 0.05 * r or seg.max() > 0.35 * r:
            return
        ang = np.unwrap(np.arctan2(pts[:, 1] - centre[1], pts[:, 0] - centre[0]))
        rec = dict(
            pts=pts,
            style=strokes[ids[0]]["style"],
            kind="c",
            p0=pts[0].copy(),
            p3=pts[-1].copy(),
            centre=centre,
            r=r,
            sweep=abs(math.degrees(ang[-1] - ang[0])),
            members=list(ids),
        )
        out.append((ids[0], rec))

    def flush():
        if len(chain) >= 5:
            # a leaf or a wall drawn in the same path continues the chain; arc pieces are all about equally
            # long, so split where the length jumps
            lens = np.array([np.linalg.norm(strokes[k]["pts"][1] - strokes[k]["pts"][0]) for k in chain])
            med = float(np.median(lens))
            run: list[int] = []
            for k, ln in zip(chain, lens, strict=True):
                if med > 0 and 0.2 * med <= ln <= 2 * med:
                    run.append(k)
                else:
                    fit(run)
                    run = []
            fit(run)
        chain.clear()

    for i, s in enumerate(strokes):
        if s["kind"] == "l":
            if chain:
                prev = strokes[chain[-1]]
                if prev["style"] == s["style"] and np.allclose(prev["pts"][1], s["pts"][0], atol=0.05):
                    chain.append(i)
                    continue
                flush()
            chain.append(i)
        else:
            flush()
    flush()
    return out


def find_doors(prim: dict) -> tuple[list[tuple[np.ndarray, np.ndarray]], set[int]]:
    """Door swings: a 60-100 degree arc plus a straight leaf from the arc centre to one arc end.
    Returns the closed-door segments (hinge, far end) and the ids of the strokes to leave out."""
    # straight things a door leaf can be: a line, or a thin rectangle (leaf drawn with its thickness)
    cands: list[tuple[int, np.ndarray]] = []
    for i, s in enumerate(prim["strokes"]):
        if s["kind"] == "l":
            cands.append((i, s["pts"]))
        elif s["kind"] in ("re", "qu") and len(s["pts"]) >= 4:
            q = s["pts"][:4]
            e01, e12 = np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[2] - q[1])
            if min(e01, e12) > 0 and max(e01, e12) / min(e01, e12) >= 3:
                if e01 < e12:  # short sides 0-1 and 2-3
                    cands.append((i, np.array([(q[0] + q[1]) / 2, (q[2] + q[3]) / 2])))
                else:
                    cands.append((i, np.array([(q[1] + q[2]) / 2, (q[3] + q[0]) / 2])))
    arcs = merge_arcs([(i, s) for i, s in enumerate(prim["strokes"]) if s["kind"] == "c" and "r" in s])
    arcs += polyline_arcs(prim["strokes"])
    radii = [s["r"] for _, s in arcs if 60 <= s["sweep"] <= 100]
    if not radii:
        return [], set()
    cell = max(float(np.percentile(radii, 75)) * 0.25, 0.5)
    grid: dict = {}
    for ci, (_i, pts) in enumerate(cands):
        for e in (0, 1):
            key = tuple(np.floor(pts[e] / cell).astype(int))
            grid.setdefault(key, []).append((ci, e))
    drop: set[int] = set()
    doors = []

    def near(pt, tol, exclude):
        k = np.floor(pt / cell).astype(int)
        reach = int(math.ceil(tol / cell))
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                for ci, e in grid.get((k[0] + dx, k[1] + dy), []):
                    if ci not in exclude and np.linalg.norm(cands[ci][1][e] - pt) <= tol:
                        yield ci, e

    for ai, a in arcs:
        if not 60 <= a["sweep"] <= 100:
            continue
        c, r = a["centre"], a["r"]
        tol = 0.2 * r
        # leaves from the hinge to an arc end (to the open position; in closed wedge symbols also the line
        # to the closed position)
        spokes: dict[int, int] = {}
        for ci, e in near(c, tol, set()):
            tip = cands[ci][1][1 - e]
            for k_end, end in enumerate((a["p0"], a["p3"])):
                if np.linalg.norm(tip - end) <= tol:
                    spokes[ci] = k_end
        if not spokes:
            continue
        ends = (a["p0"], a["p3"])
        # the closed position meets the opposite jamb: an end that touches another (wall) line
        touching = [k for k in (0, 1) if any(True for _ in near(ends[k], tol, set(spokes)))]
        if len(touching) == 1:
            closed_end = ends[touching[0]]
        else:
            closed_end = ends[1 - next(iter(spokes.values()))]
        drop.update(a.get("members", [ai]))
        drop.update(cands[ci][0] for ci in spokes)
        doors.append((c.copy(), closed_end.copy()))
    return doors, drop


def find_hatching(prim: dict, skip: set[int]) -> set[int]:
    """Stroke styles that are mostly many parallel oblique segments (hatch fill)."""
    by_style: dict = {}
    for i, s in enumerate(prim["strokes"]):
        if i in skip or s["kind"] != "l":
            continue
        v = s["pts"][1] - s["pts"][0]
        if np.hypot(*v) < 1e-6:
            continue
        ang = math.degrees(math.atan2(v[1], v[0])) % 180
        by_style.setdefault(s["style"], []).append((i, ang))
    out: set[int] = set()
    for _style, items in by_style.items():
        angs = np.array([a for _, a in items])
        hist = np.histogram(angs, bins=180, range=(0, 180))[0]
        peak = int(np.argmax(hist))
        near = np.abs(((angs - (peak + 0.5)) + 90) % 180 - 90) <= 1.5
        oblique = min(abs(peak + 0.5 - 0), abs(peak + 0.5 - 90), abs(peak + 0.5 - 180)) > 5
        if oblique and near.sum() >= 15 and near.mean() >= 0.6:
            out.update(i for (i, _), keep in zip(items, near, strict=True) if keep)
    return out


def render(
    page, px_per_pt: float, min_line_px: int = 2, line_model: str | None = None
) -> tuple[np.ndarray, dict]:
    prim = parse_page(page)
    doors, drop = find_doors(prim)
    hatch = find_hatching(prim, drop)
    furniture: set[int] = set()
    if line_model:
        # learned line classes (FloorPlanCAD): furniture and fixtures drawn on the wall layer are left out
        from .primitives import load_classifier, stroke_groups

        groups = stroke_groups(prim["strokes"], load_classifier(line_model))
        furniture = {k for k, g in groups.items() if g == "furniture" and k not in drop}
    w, h = int(round(page.rect.width * px_per_pt)), int(round(page.rect.height * px_per_pt))
    img = np.full((h, w), 255, np.uint8)
    for subs in prim["fills"]:
        pts = [np.round(sp * px_per_pt).astype(np.int32) for sp in subs if len(sp) >= 3]
        if not pts:
            continue
        allp = np.vstack(pts)
        x0, y0 = np.maximum(allp.min(0), 0)
        x1, y1 = np.minimum(allp.max(0) + 1, [w, h])
        if x1 <= x0 or y1 <= y0:
            continue
        layer = np.zeros((y1 - y0, x1 - x0), np.uint8)
        for q in pts:  # even-odd: a sub-path inside another is a hole
            one = np.zeros_like(layer)
            cv2.fillPoly(one, [q - [x0, y0]], 1)
            layer ^= one
        img[y0:y1, x0:x1][layer > 0] = 0
    for i, s in enumerate(prim["strokes"]):
        if i in drop or i in hatch or i in furniture:
            continue
        lw = max(min_line_px, int(round(s["style"][0] * px_per_pt)))
        pts = np.round(s["pts"] * px_per_pt).astype(np.int32)
        cv2.polylines(img, [pts], False, 0, lw, lineType=cv2.LINE_8)
    known = [((a * px_per_pt).tolist(), (b * px_per_pt).tolist()) for a, b in doors]
    stats = {
        "strokes": len(prim["strokes"]),
        "door_swings": len(doors),
        "hatch_segments": len(hatch),
        "dark_fills": len(prim["fills"]),
        "furniture_strokes": len(furniture),
    }
    return np.dstack([img] * 3), {"known_doors": known, "vector_stats": stats}


def text_boxes(page, px_per_pt: float) -> list[TextBox]:
    """Words of the PDF text layer as text boxes in image pixels (confidence 1: no OCR involved)."""
    out = []
    for x0, y0, x1, y1, word, *_ in page.get_text("words"):
        word = word.strip()
        if word:
            b = tuple(int(round(v * px_per_pt)) for v in (x0, y0, x1, y1))
            out.append(TextBox(text=word, conf=1.0, box=b))  # type: ignore[arg-type]
    return out


class PdfVectorAdapter:
    """Vector-only PDF pages with a real drawing (CAD exports). ``options``: ``max_side_px`` (default 5000),
    ``dpi`` (overrides), ``vector_clean: false`` to fall back to plain page rendering."""

    name = "pdf_vector"

    def can_handle(self, spec) -> float:
        if not spec.source_file.lower().endswith(".pdf") or spec.image_index is not None:
            return 0.0
        if not spec.options.get("vector_clean", True):
            return 0.0
        forced = spec.options.get("vector_clean") is True  # asked for explicitly in the venue config
        try:
            import pymupdf

            page = pymupdf.open(spec.source_file)[(spec.page or 1) - 1]
            area = page.rect.width * page.rect.height
            img_area = sum(
                abs(r.width * r.height)
                for im in page.get_images(full=True)
                for r in page.get_image_rects(im[0])
            )
            if img_area > 0.2 * area:  # a scan or a picture of a plan, not a drawing (logos are fine)
                return 0.0
            return 0.95 if forced else (0.7 if len(page.get_drawings()) >= 200 else 0.0)
        except Exception:
            return 0.0

    def load(self, spec) -> FloorImage:
        import pymupdf

        from .ingest import _apply_crop, sha256_file

        page = pymupdf.open(spec.source_file)[(spec.page or 1) - 1]
        long_pt = max(page.rect.width, page.rect.height)
        dpi = float(
            spec.options.get("dpi") or min(300.0, float(spec.options.get("max_side_px", 5000)) * 72 / long_pt)
        )
        s = dpi / 72
        # optional learned line classifier: option ``line_model`` or env TURN_LINE_MODEL (a joblib path)
        line_model = spec.options.get("line_model") or os.environ.get("TURN_LINE_MODEL") or None
        rgb, meta = render(page, s, line_model=line_model)
        tb = text_boxes(page, s)
        if spec.crop:
            x0, y0 = spec.crop[0], spec.crop[1]
            tb = [
                TextBox(t.text, t.conf, (t.box[0] - x0, t.box[1] - y0, t.box[2] - x0, t.box[3] - y0))
                for t in tb
            ]
            meta["known_doors"] = [
                [[a[0] - x0, a[1] - y0], [b[0] - x0, b[1] - y0]] for a, b in meta["known_doors"]
            ]
        meta.update(
            {
                "adapter": self.name,
                "file": Path(spec.source_file).name,
                "sha256": sha256_file(spec.source_file),
                "page": spec.page,
                "dpi": round(dpi, 2),
                "vector_only": True,
                "text_boxes": tb,
            }
        )
        ratio = spec.options.get("drawing_scale")
        if ratio:
            from .ingest import PT_M

            meta["cad_m_per_px"] = PT_M * 72 / dpi * float(ratio)
            meta["units"] = f"paper 1:{ratio}"
        return FloorImage(spec=spec, rgb=_apply_crop(rgb, spec), source_meta=meta)
