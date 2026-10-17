"""Text reading for room labels: RapidOCR (pip only, models in the wheel) or Tesseract (a separate program).

Engine choice: env ``TURN_OCR`` = ``rapidocr`` | ``tesseract`` | ``none``; otherwise Tesseract if its program
is found (PATH, ``TESSERACT_CMD``, the usual Windows folders), else RapidOCR if installed, else none.
"No engine" is reported (``status()`` and an ``OCR_UNAVAILABLE`` warning), never silent: before this, a laptop
without Tesseract produced maps where every room was "Unlabelled".
"""

from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from .ir import TextBox

_WIN_TESSERACT = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    str(Path.home() / "AppData" / "Local" / "Programs" / "Tesseract-OCR" / "tesseract.exe"),
)


def find_tesseract() -> str | None:
    for c in (os.environ.get("TESSERACT_CMD"), shutil.which("tesseract"), *_WIN_TESSERACT):
        if c and Path(c).exists():
            try:
                import pytesseract

                pytesseract.pytesseract.tesseract_cmd = c
            except ImportError:
                return None
            return c
    return None


def _has_rapidocr() -> bool:
    try:
        import rapidocr  # noqa: F401
    except Exception:
        return False
    return True


@lru_cache(maxsize=1)
def engine_name() -> str:
    want = os.environ.get("TURN_OCR", "").strip().lower()
    if want in ("none", "off"):
        return "none"
    if want == "tesseract":
        return "tesseract" if find_tesseract() else "none"
    if want == "rapidocr":
        return "rapidocr" if _has_rapidocr() else "none"
    # Tesseract first: all recorded results (docs/RESULTS_*.md) were made with it, and RapidOCR's line boxes
    # change text erasure enough to move room shapes on some FAST floors (C-F5: 30 -> 23 rooms). RapidOCR is
    # the pip-only fallback that makes a laptop without Tesseract label rooms at all.
    if find_tesseract():
        return "tesseract"
    return "rapidocr" if _has_rapidocr() else "none"


def status() -> dict:
    name = engine_name()
    detail = {
        "rapidocr": "RapidOCR (built in)",
        "tesseract": f"Tesseract at {find_tesseract()}",
        "none": 'no text reader: rooms stay unlabelled. Fix: pip install "rapidocr" "onnxruntime" '
        "(or install Tesseract), then restart",
    }[name]
    return {"engine": name, "available": name != "none", "detail": detail}


@lru_cache(maxsize=1)
def _rapid():
    import logging

    from rapidocr import RapidOCR

    logging.getLogger("RapidOCR").setLevel(logging.WARNING)
    return RapidOCR()


def _rapid_boxes(img: np.ndarray) -> list[tuple[str, float, tuple[float, float, float, float]]]:
    rgb = img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    out = _rapid()(rgb)
    res = []
    if out.boxes is None:
        return res
    for quad, txt, score in zip(out.boxes, out.txts, out.scores, strict=False):
        q = np.asarray(quad, float)
        x0, y0 = q.min(0)
        x1, y1 = q.max(0)
        res.append((str(txt).strip(), float(score), (x0, y0, x1 - x0, y1 - y0)))
    return res


def _tess_boxes(gray: np.ndarray, k: float) -> list[tuple[str, float, tuple[float, float, float, float]]]:
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


def page_text(gray: np.ndarray, upscale: float = 2.0, min_conf: float = 0.45) -> list[TextBox]:
    """Text boxes over the whole floor image in three orientations (0, 90, 270 degrees, so vertical labels are
    found too), in image coordinates. Empty list when no engine is available."""
    name = engine_name()
    if name == "none":
        return []
    H, W = gray.shape
    out: list[TextBox] = []
    variants = [
        (0, gray),
        (90, cv2.rotate(gray, cv2.ROTATE_90_CLOCKWISE)),
        (270, cv2.rotate(gray, cv2.ROTATE_90_COUNTERCLOCKWISE)),
    ]
    taken = np.zeros((H, W), bool)
    try:
        for ang, img in variants:
            boxes = _rapid_boxes(img) if name == "rapidocr" else _tess_boxes(img, upscale)
            for txt, conf, (x, y, w, h) in boxes:
                if not txt:
                    continue
                if ang != 0 and (
                    conf < max(min_conf, 0.8 if name == "rapidocr" else min_conf) or len(txt) < 2
                ):
                    continue  # rotated passes: keep only confident words
                if ang == 0:
                    x0, y0, x1, y1 = x, y, x + w, y + h
                elif ang == 90:  # rotated clockwise: (x', y') = (H-1-y, x)
                    x0, y0, x1, y1 = y, H - 1 - (x + w), y + h, H - 1 - x
                else:  # counter-clockwise: (x', y') = (y, W-1-x)
                    x0, y0, x1, y1 = W - 1 - (y + h), x, W - 1 - y, x + w
                if (y1 - y0) > H * 0.2 and (x1 - x0) > W * 0.2:
                    continue
                bx = (int(max(x0, 0)), int(max(y0, 0)), int(min(x1 + 1, W)), int(min(y1 + 1, H)))
                if bx[2] <= bx[0] or bx[3] <= bx[1]:
                    continue
                if ang != 0 and name == "rapidocr":
                    # a rotated pass re-reads horizontal text as garbage: keep only boxes on unread pixels
                    if taken[bx[1] : bx[3], bx[0] : bx[2]].mean() > 0.3 or (bx[3] - bx[1]) < (bx[2] - bx[0]):
                        continue
                taken[bx[1] : bx[3], bx[0] : bx[2]] = True
                out.append(TextBox(text=txt, conf=conf, box=bx))
    except Exception:  # engine failed at run time: keep what we have
        return out
    return out
