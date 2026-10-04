import numpy as np
import pytest

from turn_mapper.config import PipelineParams
from turn_mapper.ir import FloorImage, FloorSpec
from turn_mapper.preprocess import preprocess
from turn_mapper.scale import scale_from_evidence
from turn_mapper.segment import ClassicalSegmenter, estimate_levels
from turn_mapper.synthetic import make_plan
from turn_mapper.vectorize import close_wall_gaps, vectorize, wall_thickness_px


def _seg(variant="basic"):
    plan = make_plan(variant)
    img = FloorImage(spec=FloorSpec("F1", "B", 0, "t", "x.png"), rgb=plan.rgb, source_meta={})
    p = PipelineParams()
    pre = preprocess(img, p)
    return plan, pre, ClassicalSegmenter().segment(pre, p), p


def test_levels_estimated_from_image():
    plan = make_plan()
    gray = plan.rgb[:, :, 0]
    lv = estimate_levels(gray)
    assert lv["background"] == 255 and lv["floor"] == 238 and lv["wall"] == 191


def test_levels_when_floor_outnumbers_paper():
    """Regression (B-GF): floor pixels more common than paper must not be read as background."""
    g = np.full((200, 200), 238, np.uint8)
    g[:4, :] = g[-4:, :] = g[:, :4] = g[:, -4:] = 255
    g[50:54, 20:180] = 191
    assert estimate_levels(g)["background"] == 255


def test_segmentation_masks():
    plan, pre, seg, _ = _seg()
    assert seg.wall.mean() > 0.01
    assert seg.floor.mean() > 0.5
    assert seg.background[0, 0] and not seg.background[seg.wall.shape[0] // 2, seg.wall.shape[1] // 2]


def test_gap_closing_closes_doors_but_not_narrow_rooms():
    w = np.zeros((120, 200), bool)
    w[20:24, 10:190] = True  # horizontal wall with a door gap
    w[20:24, 90:112] = False
    w[60:64, 10:190] = True  # two walls 14 px apart: a narrow room, must NOT be filled
    w[78:82, 10:190] = True
    out = close_wall_gaps(w, 30, 4.0)
    assert out[21, 100], "door gap should be closed"
    assert not out[71, 100], "narrow room between parallel walls must stay open"


def test_vectorize_finds_rooms_and_doors():
    plan, pre, seg, p = _seg()
    geom = vectorize(seg, pre.gray_raw, pre.text, p, plan.m_per_px)
    rooms = [r for r in geom.regions if r.kind != "circulation"]
    circ = [r for r in geom.regions if r.kind == "circulation"]
    assert len(rooms) == len(plan.rooms)
    assert len(circ) == 1
    assert len(geom.doors) == len(plan.rooms_with_doors)
    assert abs(wall_thickness_px(seg.wall) - 5) <= 1.5  # synthetic walls are drawn 5 px thick


def test_scale_from_two_points_and_residuals():
    ev = [
        {"p1_px": [0, 0], "p2_px": [100, 0], "distance_m": 5.0},
        {"p1_px": [0, 0], "p2_px": [0, 40], "distance_m": 2.1},
    ]
    s, out = scale_from_evidence(ev)
    assert s == pytest.approx(0.05)
    assert out[0]["used_for_fit"] and not out[1]["used_for_fit"]
    assert out[1]["residual_m"] == pytest.approx(-0.1, abs=1e-6)
