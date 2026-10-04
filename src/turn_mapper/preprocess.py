"""Preprocess: grayscale, OCR text boxes, erase text so it does not punch holes in spaces."""

from __future__ import annotations

import cv2
import numpy as np

from .config import PipelineParams
from .ir import FloorImage, Preprocessed, TextBox


def run_ocr(gray: np.ndarray, params: PipelineParams) -> list[TextBox]:
    """Word boxes from Tesseract (sparse-text mode) on an upscaled image. Empty if unavailable."""
    if not params.ocr:
        return []
    try:
        import pytesseract
    except ImportError:  # pragma: no cover
        return []
    k = params.ocr_upscale
    big = cv2.resize(gray, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    try:
        data = pytesseract.image_to_data(big, config="--psm 11", output_type=pytesseract.Output.DICT)
    except Exception:  # tesseract binary missing or failed
        return []
    out: list[TextBox] = []
    for i, txt in enumerate(data["text"]):
        txt = (txt or "").strip()
        conf = float(data["conf"][i])
        if not txt or conf < 0:
            continue
        x, y, w, h = (data[key][i] / k for key in ("left", "top", "width", "height"))
        if h > gray.shape[0] * 0.2:  # absurdly tall "text" is usually a wall/edge misread
            continue
        out.append(TextBox(text=txt, conf=conf / 100.0, box=(int(x), int(y), int(x + w + 1), int(y + h + 1))))
    return out


def _dominant_light_gray(gray: np.ndarray) -> int:
    hist = np.bincount(gray.ravel(), minlength=256)
    hist[250:] = 0  # ignore paper white
    hist[:150] = 0
    return int(np.argmax(hist))


def erase_text(gray: np.ndarray, boxes: list[TextBox], min_conf: float) -> np.ndarray:
    """Paint text boxes with the surrounding floor grey, only where the box sits on floor."""
    out = gray.copy()
    floor_level = _dominant_light_gray(gray)
    for tb in boxes:
        if tb.conf < min_conf * 0.5 and len(tb.text) < 2:
            continue
        x0, y0, x1, y1 = tb.box
        x0, y0 = max(x0 - 1, 0), max(y0 - 1, 0)
        x1, y1 = min(x1 + 1, gray.shape[1]), min(y1 + 1, gray.shape[0])
        if x1 <= x0 or y1 <= y0:
            continue
        ring = np.concatenate([gray[y0, x0:x1], gray[y1 - 1, x0:x1], gray[y0:y1, x0], gray[y0:y1, x1 - 1]])
        # only erase if the border of the box is mostly floor (text inside a space, not across walls)
        if np.mean(np.abs(ring.astype(int) - floor_level) <= 10) > 0.8:
            out[y0:y1, x0:x1] = floor_level
    return out


def preprocess(img: FloorImage, params: PipelineParams) -> Preprocessed:
    gray = cv2.cvtColor(img.rgb, cv2.COLOR_RGB2GRAY)
    boxes = run_ocr(gray, params)
    clean = erase_text(gray, boxes, params.ocr_min_conf)
    return Preprocessed(gray=clean, gray_raw=gray, text=boxes)
