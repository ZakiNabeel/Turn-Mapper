"""Learned segmenter v2 pieces that do not need weights: network doors in vectorize, fragment removal,
scale selection by confidence (with a stand-in model)."""

from dataclasses import replace

import cv2
import numpy as np
import pytest

from turn_mapper.api import process_floor
from turn_mapper.config import single_image_config
from turn_mapper.synthetic import make_plan, render_style


@pytest.fixture(scope="module")
def basic(tmp_path_factory):
    p = tmp_path_factory.mktemp("v2") / "b.png"
    cv2.imwrite(str(p), render_style(make_plan("basic"), "blackwalls"))
    cfg = single_image_config(str(p))
    return cfg, process_floor(cfg.floors[0], cfg)


def _rooms(fr):
    return len([r for r in fr.geom.regions if r.kind == "room"])


def _widen_first_door(seg, door, extra_px=30):
    """Remove wall around a door so the opening is far wider than a door (gap closing will not close it)."""
    x0, y0, x1, y1 = (int(v) for v in door.segment.bounds)
    wall = seg.wall.copy()
    band = slice(max(y0 - 8, 0), y1 + 9), slice(max(x0 - extra_px, 0), x1 + extra_px)
    rows = np.nonzero(wall[band[0], band[1].start].ravel() | wall[band[0], band[1].stop - 1].ravel())[0]
    opening = np.zeros_like(
        wall
    )  # the whole opening (wall band thickness x width), as a network would mark it
    opening[band[0].start + rows.min() : band[0].start + rows.max() + 1, band[1]] = True
    wall[band] = False
    return replace(seg, wall=wall, floor=seg.floor | opening), opening


def test_network_doors_close_wide_openings(basic):
    cfg, fr = basic
    seg_wide, opening = _widen_first_door(fr.seg, fr.geom.doors[0])
    wide = process_floor(cfg.floors[0], cfg, seg_override=seg_wide)
    assert _rooms(wide) == _rooms(fr) - 1  # without door evidence the room merges into the corridor
    fixed = process_floor(cfg.floors[0], cfg, seg_override=replace(seg_wide, doors=opening))
    assert _rooms(fixed) == _rooms(fr) and len(fixed.geom.doors) >= len(fr.geom.doors)


def test_doors_none_leaves_classical_unchanged(basic):
    cfg, fr = basic
    again = process_floor(cfg.floors[0], cfg, seg_override=replace(fr.seg, doors=None))
    assert _rooms(again) == _rooms(fr) and len(again.geom.doors) == len(fr.geom.doors)


def test_drop_small_fragments_keeps_wall_network():
    from turn_mapper.learned.segmenter import drop_small_fragments

    w = np.zeros((200, 200), bool)
    w[20:26, 10:190] = True  # main wall
    w[20:180, 10:16] = True
    w[100:104, 100:106] = True  # stray stroke inside a room
    out = drop_small_fragments(w, 4.0)
    assert out[22, 100] and out[100, 12] and not out[101, 102]


def test_scale_choice_by_confidence(monkeypatch, basic):
    """A stand-in network that is only confident at one image size: v2 must pick that size."""
    import turn_mapper.learned.model as model_mod
    import turn_mapper.learned.segmenter as seg_mod
    from turn_mapper.learned.classes import BG, CLASSES, ROOM, WALL

    cfg, fr = basic
    target_w = int(round(fr.image.rgb.shape[1] * 1.4))

    def fake_predict(model, gs, tile, device):
        prob = np.full((len(CLASSES), *gs.shape), 0.01, np.float32)
        conf = 0.95 if abs(gs.shape[1] - target_w) <= 2 else 0.4
        dark = gs < 128
        prob[WALL][dark] = conf
        prob[ROOM][~dark] = conf
        prob[BG][:2, :] = 1.0
        return prob

    monkeypatch.setattr(seg_mod, "_model", lambda device: (None, {"wall_px_median": None, "crop": 512}, "x"))
    monkeypatch.setattr(model_mod, "predict_proba", fake_predict)
    params = replace(cfg.params, learned_scales=(0.7, 1.0, 1.4))
    seg = seg_mod.LearnedSegmenter(device="cpu").segment(_pre(fr, params), params)
    assert seg.levels["learned"]["scale"] == pytest.approx(1.4, abs=0.01)
    assert seg.wall.shape == fr.seg.wall.shape


def _pre(fr, params):
    from turn_mapper.preprocess import preprocess

    return preprocess(fr.image, params)
