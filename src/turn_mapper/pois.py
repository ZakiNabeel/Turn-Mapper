"""Room labels (OCR per room) and destinations (POIs attached to door nodes)."""

from __future__ import annotations

import re

import cv2
import numpy as np

from .config import PipelineParams
from .ir import GeometryPx, Issue, NavGraph, Poi

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


def label_rooms(geom: GeometryPx, gray: np.ndarray, params: PipelineParams, patterns: list[str]) -> None:
    regs = [re.compile(p.strip("^$")) for p in (patterns or [DEFAULT_LABEL_PATTERN])]
    for r in geom.regions:
        if r.kind == "circulation":
            continue
        text, conf = _ocr_room(gray, geom.debug["region_masks"][r.id], params)
        r.ocr_conf = conf if text else None
        if not text:
            continue
        label = None
        for rg in regs:
            m = rg.search(text.replace(" ", "")) or rg.search(text)
            if m:
                label = m.group(0)
                break
        r.label = label
        rest = text.replace(label, "").strip(" -") if label else text
        r.name = rest or label
        cat = _category(text)
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
