"""Room labels (OCR per room) and destinations (POIs attached to door nodes)."""

from __future__ import annotations

import re

import cv2
import numpy as np

from .config import PipelineParams
from .ir import GeometryPx, Issue, NavGraph, Poi, TextBox

# generic room code (e.g. A-104, B-215A, C509, LAB-02) used when a venue gives no pattern
DEFAULT_LABEL_PATTERN = r"\b[A-Z]{1,3}-?\d{2,4}[A-Z]?\b"

_CATEGORY_WORDS = [
    ("lift", ("elevator", "lift")),
    ("stairs", ("stair",)),
    ("washroom", ("w.c", "wc", "washroom", "toilet")),
    ("lab", ("lab",)),
    ("office", ("office",)),
    ("classroom", ("classroom", "class room")),
]


def _ocr_room(gray: np.ndarray, mask: np.ndarray, params: PipelineParams) -> tuple[str, float]:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return "", 0.0
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    crop = gray[y0:y1, x0:x1].copy()
    crop[~mask[y0:y1, x0:x1]] = 255
    if crop.shape[0] < 8 or crop.shape[1] < 8:
        return "", 0.0
    try:
        import pytesseract

        big = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        big = cv2.copyMakeBorder(big, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)
        data = pytesseract.image_to_data(big, config="--psm 6", output_type=pytesseract.Output.DICT)
    except Exception:
        return "", 0.0
    words, confs = [], []
    for txt, conf in zip(data["text"], data["conf"], strict=False):
        txt = (txt or "").strip()
        if txt and float(conf) >= params.ocr_min_conf * 100 and re.search(r"[A-Za-z0-9]", txt):
            words.append(txt)
            confs.append(float(conf) / 100)
    return " ".join(words), (float(np.mean(confs)) if confs else 0.0)


def _category(text: str) -> str | None:
    t = text.lower()
    for cat, keys in _CATEGORY_WORDS:
        if any(k in t for k in keys):
            return cat
    return None


def _text_in_room(mask: np.ndarray, boxes: list[TextBox], min_conf: float) -> tuple[str, float]:
    """Join the page-level text boxes whose centre lies in the room (reading order: top-to-bottom, left-right;
    vertical labels by x)."""
    inside = []
    h, w = mask.shape
    for tb in boxes:
        x0, y0, x1, y1 = tb.box
        cx, cy = int(min(max((x0 + x1) // 2, 0), w - 1)), int(min(max((y0 + y1) // 2, 0), h - 1))
        if mask[cy, cx] and tb.conf >= min_conf and re.search(r"[A-Za-z0-9]", tb.text):
            inside.append(tb)
    if not inside:
        return "", 0.0
    vertical = sum((b.box[3] - b.box[1]) > (b.box[2] - b.box[0]) for b in inside) > len(inside) / 2
    line_h = float(np.median([min(b.box[3] - b.box[1], b.box[2] - b.box[0]) for b in inside])) or 1.0
    if vertical:  # labels turned clockwise (read top to bottom): lines run right to left, words downwards
        inside.sort(key=lambda b: (-round(b.box[0] / line_h), b.box[1]))
    else:
        inside.sort(key=lambda b: (round(b.box[1] / line_h), b.box[0]))
    return " ".join(b.text for b in inside), float(np.mean([b.conf for b in inside]))


def label_rooms(
    geom: GeometryPx,
    gray: np.ndarray,
    params: PipelineParams,
    patterns: list[str],
    text: list[TextBox] | None = None,
    page_level: bool | None = None,
) -> None:
    """Room label (code such as B-215A) and name (the rest, e.g. "Maker Lab") from the text drawn in it.

    With RapidOCR the page-level boxes from preprocessing are assigned to rooms (fast, reads small and rotated
    labels); with Tesseract each room is cropped and read on its own (the historic path)."""
    from .ocr import engine_name

    regs = [re.compile(p.strip("^$")) for p in (patterns or [DEFAULT_LABEL_PATTERN])]
    if page_level is None:
        page_level = engine_name() == "rapidocr" and text is not None
    for r in geom.regions:
        if r.kind == "circulation":
            continue
        mask = geom.debug["region_masks"][r.id]
        if page_level:
            text_, conf = _text_in_room(mask, text, params.ocr_min_conf)
        else:
            text_, conf = _ocr_room(gray, mask, params)
        text_room = text_
        r.ocr_conf = conf if text_room else None
        if not text_room:
            continue
        label = None
        for rg in regs:
            m = rg.search(text_room) or rg.search(text_room.replace(" ", ""))
            if m:
                label = m.group(0)
                break
        r.label = label
        rest = text_room.replace(label, "").strip(" -") if label else text_room
        r.name = rest or label
        cat = _category(text_room)
        if cat in ("lift", "stairs"):
            r.kind = "transition"


def make_pois(geom: GeometryPx, graph: NavGraph) -> tuple[list[Poi], list[Issue]]:
    issues: list[Issue] = []
    door_node = {n.door_id: n.id for n in graph.nodes.values() if n.door_id}
    pois: list[Poi] = []
    for r in geom.regions:
        if r.kind in ("circulation", "transition"):
            continue
        node = next((door_node[d.id] for d in geom.doors if r.id in d.regions and d.id in door_node), None)
        if node is None:
            issues.append(Issue("ROOM_NOT_REACHABLE", "room has no door linked to the corridor graph", r.id))
            continue
        name = r.label or r.name
        needs_review = not name or (r.ocr_conf or 0) < 0.6
        if r.label and r.name and r.name != r.label:
            name = f"{r.label} {r.name}"
        pois.append(
            Poi(
                id=f"p{len(pois) + 1}",
                name=name or f"Unlabelled room {r.id}",
                label=r.label,
                node_id=node,
                room_id=r.id,
                needs_review=needs_review,
                ocr_conf=r.ocr_conf,
                category=_category(f"{r.label or ''} {r.name or ''}"),
            )
        )
    tnodes = geom.debug.get("transition_nodes", {})
    counts: dict[str, int] = {}
    for t in geom.transitions:
        if t.id not in tnodes:
            continue
        counts[t.type] = counts.get(t.type, 0) + 1
        name = f"{'Stairs' if t.type == 'stairs' else 'Lift'} {counts[t.type]}"
        pois.append(
            Poi(
                id=f"p{len(pois) + 1}",
                name=name,
                label=None,
                node_id=tnodes[t.id],
                room_id=t.region_id,
                needs_review=False,
                ocr_conf=None,
                category=t.type,
            )
        )
    return pois, issues
