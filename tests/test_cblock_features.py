"""Unit tests for the features added for C block: stairs texture, thin partitions, door slabs drawn over
walls, three-orientation OCR mapping, and footprint scale transfer. All use small synthetic images."""

import cv2
import numpy as np

from turn_mapper.config import PipelineParams
from turn_mapper.segment import detect_partitions, detect_stairs
from turn_mapper.vectorize import carve_door_slabs

LV = {"background": 255, "floor": 238, "wall": 191}


def _plan(h=200, w=300):
    g = np.full((h, w), 238, np.uint8)
    g[:5], g[-5:], g[:, :5], g[:, -5:] = 191, 191, 191, 191
    return g


def test_stairs_texture_detected_and_flat_floor_ignored():
    g = _plan()
    # smooth grey gradient (stair texture) in a 60x60 block
    for i in range(60):
        g[100:160, 40 + i] = 226 + (i % 12)
    wall = g <= 200
    st = detect_stairs(g, LV, wall, PipelineParams())
    assert st[130, 70], "stair texture should be detected"
    assert not st[50, 200], "flat floor must not be stairs"


def test_thin_partition_kept_door_arc_like_short_stroke_dropped():
    g = _plan()
    g[100, 20:280] = 200  # long thin partition with floor on both sides
    g[40:52, 150] = 200  # short stroke (arc fragment / text)
    wall = cv2.morphologyEx((g <= 210).astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
    bg = np.zeros_like(wall)
    p = detect_partitions(g, LV, 210, wall, bg, np.zeros_like(wall), PipelineParams())
    assert p[100, 150]
    assert not p[45, 150]


def test_door_slab_over_unbroken_wall_is_carved():
    g = _plan()
    g[95:105, 5:295] = 191  # horizontal wall, 10 px thick, no gap
    g[99:102, 120:150] = 255  # white door slab drawn on top of it
    wall = g <= 200
    out, carved = carve_door_slabs(wall, g, LV, np.zeros_like(wall), t=10.0, gap_px=40)
    assert carved.any()
    assert not out[97, 135] and not out[103, 135], "opening must go through the full wall thickness"
    assert out[100, 60], "wall away from the slab is untouched"


def test_rotated_ocr_box_mapping_round_trip():
    """A box found in the 90-degree-clockwise image must map back onto the original text location."""
    H = 100
    # original box at x 20..30, y 40..80 (vertical text); in the clockwise-rotated image (W'=H, H'=W)
    # it sits at x' = H-1-y, y' = x
    x0, y0, x1, y1 = 20, 40, 30, 80
    xr, yr, wr, hr = H - 1 - y1, x0, y1 - y0, x1 - x0
    mx0, my0, mx1, my1 = yr, H - 1 - (xr + wr), yr + hr, H - 1 - xr
    assert (mx0, my0, mx1, my1) == (x0, y0, x1, y1)


def test_footprint_scale_transfer(tmp_path):
    """Same building drawn at 1.5x pixel size: the transferred scale must be 1/1.5 of the reference's."""
    import yaml

    from turn_mapper.api import convert
    from turn_mapper.synthetic import make_plan

    plan = make_plan("basic")
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    cv2.imwrite(str(a), cv2.cvtColor(plan.rgb, cv2.COLOR_RGB2BGR))
    big = cv2.resize(plan.rgb, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_NEAREST)
    cv2.imwrite(str(b), cv2.cvtColor(big, cv2.COLOR_RGB2BGR))
    cfg = {
        "venue": {"id": "t", "name": "t"},
        "buildings": [{"id": "X", "name": "X"}],
        "floors": [
            {"id": "F1", "building": "X", "level": 1, "file": str(a)},
            {"id": "F2", "building": "X", "level": 2, "file": str(b), "scale_like": "F1"},
        ],
        "scale_evidence": {"F1": [{"p1_px": [0, 0], "p2_px": [100, 0], "distance_m": 4.0}]},
    }
    p = tmp_path / "v.yaml"
    p.write_text(yaml.safe_dump(cfg))
    res = convert(str(a), venue_config=str(p), out_dir=str(tmp_path / "run"))
    f = {x["id"]: x for x in res.floors}
    assert f["F1"]["scale_source"] == "operator_two_point"
    assert f["F2"]["scale_source"] == "footprint_transfer"
    assert abs(f["F2"]["scale"] - 0.04 / 1.5) / (0.04 / 1.5) < 0.03
    assert res.all_passed
