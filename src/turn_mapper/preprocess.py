"""Preprocess: grayscale, OCR text boxes, erase text so it does not punch holes in spaces."""

from __future__ import annotations

import cv2
import numpy as np

from .config import PipelineParams
from .ir import FloorImage, Preprocessed, TextBox


def _ocr_boxes(gray: np.ndarray, k: float) -> list[tuple[str, float, tuple[float, float, float, float]]]:
    import pytesseract

    big = cv2.resize(gray, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    data = pytesseract.image_to_data(big, config="--psm 11", output_type=pytesseract.Output.DICT)
    out = []
    for i, txt in enumerate(data["text"]):
        txt = (txt or "").strip()
        conf = float(data["conf"][i])
        if not txt or conf < 0:
            continue
        x, y, w, h = (data[key][i] / k for key in ("left", "top", "width", "height"))
        out.append((txt, conf / 100.0, (x, y, w, h)))
    return out


def run_ocr(gray: np.ndarray, params: PipelineParams) -> list[TextBox]:
    """Word boxes from Tesseract (sparse-text mode) on an upscaled image, in three orientations (0, 90, 270
    degrees) so vertical labels are found too. Boxes are mapped back to image coordinates."""
    if not params.ocr:
        return []
    try:
        import pytesseract  # noqa: F401
    except ImportError:  # pragma: no cover
        return []
    H, W = gray.shape
    out: list[TextBox] = []
    try:
        variants = [
            (0, gray),
            (90, cv2.rotate(gray, cv2.ROTATE_90_CLOCKWISE)),
            (270, cv2.rotate(gray, cv2.ROTATE_90_COUNTERCLOCKWISE)),
        ]
        for ang, img in variants:
            for txt, conf, (x, y, w, h) in _ocr_boxes(img, params.ocr_upscale):
                if ang != 0 and (conf < params.ocr_min_conf or len(txt) < 2):
                    continue  # rotated passes: keep only confident words
                if ang == 0:
                    x0, y0, x1, y1 = x, y, x + w, y + h
                elif ang == 90:  # rotated clockwise: (x', y') = (H-1-y, x)
                    x0, y0, x1, y1 = y, H - 1 - (x + w), y + h, H - 1 - x
                else:  # counter-clockwise: (x', y') = (y, W-1-x)
                    x0, y0, x1, y1 = W - 1 - (y + h), x, W - 1 - y, x + w
                if (y1 - y0) > H * 0.2 and (x1 - x0) > W * 0.2:
                    continue
                out.append(TextBox(text=txt, conf=conf, box=(int(x0), int(y0), int(x1 + 1), int(y1 + 1))))
    except Exception:  # tesseract binary missing or failed
        return out
    return out


def _dominant_light_gray(gray: np.ndarray) -> int:
    hist = np.bincount(gray.ravel(), minlength=256)
    hist[250:] = 0  # ignore paper white
    hist[:150] = 0
    return int(np.argmax(hist))


def erase_text(gray: np.ndarray, boxes: list[TextBox], min_conf: float) -> np.ndarray:
    """Paint each text box with the colour around it, only where that surround is uniform and light
    (text sitting inside a space, not across walls). Works for any floor colour (grey, white, tinted)."""
    out = gray.copy()
    for tb in boxes:
        if tb.conf < min_conf * 0.5 and len(tb.text) < 2:
            continue
        x0, y0, x1, y1 = tb.box
        x0, y0 = max(x0 - 1, 0), max(y0 - 1, 0)
        x1, y1 = min(x1 + 1, gray.shape[1]), min(y1 + 1, gray.shape[0])
        if x1 <= x0 or y1 <= y0:
            continue
        ring = np.concatenate([gray[y0, x0:x1], gray[y1 - 1, x0:x1], gray[y0:y1, x0], gray[y0:y1, x1 - 1]])
        fill = int(np.median(ring))
        if fill > 150 and np.mean(np.abs(ring.astype(int) - fill) <= 10) > 0.8:
            out[y0:y1, x0:x1] = fill
    return out


def preprocess(img: FloorImage, params: PipelineParams) -> Preprocessed:
    gray = cv2.cvtColor(img.rgb, cv2.COLOR_RGB2GRAY)
    boxes = run_ocr(gray, params)
    clean = erase_text(gray, boxes, params.ocr_min_conf)
    sat = cv2.cvtColor(img.rgb, cv2.COLOR_RGB2HSV)[:, :, 1] > 80
    color = cv2.dilate(sat.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0 if sat.any() else None
    return Preprocessed(gray=clean, gray_raw=gray, text=boxes, color_mask=color)
