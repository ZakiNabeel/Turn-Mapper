"""OCR engine choice and room labelling from page-level text boxes."""

import numpy as np

from turn_mapper import ocr
from turn_mapper.ir import TextBox
from turn_mapper.pois import _text_in_room


def _reset(monkeypatch, **env):
    for k in ("TURN_OCR", "TESSERACT_CMD"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    ocr.engine_name.cache_clear()


def test_engine_none_is_reported_not_silent(monkeypatch):
    _reset(monkeypatch, TURN_OCR="none")
    st = ocr.status()
    assert st["engine"] == "none" and not st["available"] and "rapidocr" in st["detail"]
    assert ocr.page_text(np.full((50, 50), 255, np.uint8)) == []
    ocr.engine_name.cache_clear()


def test_ocr_unavailable_warning_in_pipeline(monkeypatch, tmp_path):
    import cv2

    from turn_mapper.api import process_floor
    from turn_mapper.config import single_image_config
    from turn_mapper.synthetic import make_plan, render_style

    _reset(monkeypatch, TURN_OCR="none")
    p = tmp_path / "p.png"
    cv2.imwrite(str(p), render_style(make_plan("basic"), "blackwalls"))
    cfg = single_image_config(str(p))
    fr = process_floor(cfg.floors[0], cfg)
    assert any(w.code == "OCR_UNAVAILABLE" for w in fr.warnings)
    ocr.engine_name.cache_clear()


def test_text_boxes_are_joined_per_room_in_reading_order():
    mask = np.zeros((100, 200), bool)
    mask[10:90, 10:110] = True
    boxes = [
        TextBox("Lab", 0.99, (60, 50, 80, 60)),
        TextBox("B-215A", 0.99, (20, 20, 70, 32)),
        TextBox("Maker", 0.99, (20, 50, 55, 60)),
        TextBox("B-300", 0.99, (150, 20, 190, 30)),  # other room
    ]
    text, conf = _text_in_room(mask, boxes, 0.45)
    assert text == "B-215A Maker Lab" and conf > 0.9


def test_rapidocr_reads_a_rendered_label():
    import cv2
    import pytest

    pytest.importorskip("rapidocr")
    img = np.full((600, 1200), 255, np.uint8)  # a label is small on a plan
    cv2.putText(img, "B-215A", (40, 75), cv2.FONT_HERSHEY_SIMPLEX, 1.6, 0, 3)
    ocr.engine_name.cache_clear()
    import os

    old = os.environ.get("TURN_OCR")
    os.environ["TURN_OCR"] = "rapidocr"
    try:
        ocr.engine_name.cache_clear()
        got = " ".join(t.text for t in ocr.page_text(img))
    finally:
        if old is None:
            os.environ.pop("TURN_OCR")
        else:
            os.environ["TURN_OCR"] = old
        ocr.engine_name.cache_clear()
    assert "B-215A" in got.replace(" ", "")
