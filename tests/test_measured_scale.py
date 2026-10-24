"""Scale from measured room / corridor sizes and the venue door-width calibration."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from turn_mapper.api import calibrate_door_width, process_floor
from turn_mapper.config import load_venue_config, single_image_config
from turn_mapper.scale import FT, _typical_room_fit


def _rect(L, W, label=None):
    return {"id": label or f"s{L}x{W}", "label": label, "L": L, "W": W, "fill": 1.0, "area": L * W}


def test_typical_room_prefers_the_common_large_rooms():
    s = 0.05
    big = [_rect(30 * FT / s * k, 25 * FT / s * k) for k in (0.98, 1.0, 1.0, 1.01, 1.03, 0.99)]
    small = [_rect(30, 25) for _ in range(9)]  # same shape, much smaller: more of them, less area
    res = _typical_room_fit(big + small, {"method": "typical_room", "size_ft": [30, 25]})
    assert res["ok"] and res["n_rooms"] == 6
    assert res["m_per_px"] == pytest.approx(s, rel=0.02)


def test_typical_room_needs_five_agreeing_rooms():
    s = 0.05
    few = [_rect(30 * FT / s, 25 * FT / s) for _ in range(3)]
    res = _typical_room_fit(few, {"method": "typical_room", "size_ft": [30, 25]})
    assert not res["ok"] and "only 3 rooms" in res["reason"]


def test_named_room_size_sets_the_scale(synth_paths):
    p, plan = synth_paths["basic"]
    cfg = single_image_config(str(p))
    ev = [{"method": "room_size", "label": "R-105", "size_m": [10.0, 4.0]}]
    spec = replace(cfg.floors[0], scale_evidence=ev)
    fr = process_floor(spec, replace(cfg, floors=[spec]))
    assert fr.scale_source == "measured_room_size"
    # inside dimensions are a wall thickness smaller than the drawn rectangle: within 6 %
    assert fr.scale_m_per_px == pytest.approx(plan.m_per_px, rel=0.06)
    rec = fr.scale_evidence[0]
    assert rec["used_for_fit"] and rec["room_px"]


def test_missing_room_is_reported_not_guessed(synth_paths):
    p, _ = synth_paths["basic"]
    cfg = single_image_config(str(p))
    ev = [{"method": "room_size", "label": "R-999", "size_m": [10.0, 4.0]}]
    spec = replace(cfg.floors[0], scale_evidence=ev)
    fr = process_floor(spec, replace(cfg, floors=[spec]))
    assert fr.scale_source == "door_width_prior"
    assert any(w.code == "SCALE_EVIDENCE_REJECTED" for w in fr.warnings)


def test_door_width_calibration_uses_only_measured_floors():
    def fr(src, s, widths):
        return SimpleNamespace(
            scale_source=src,
            scale_m_per_px=s,
            geom=SimpleNamespace(doors=[SimpleNamespace(width_px=w) for w in widths]),
        )

    done = {
        "a": fr("measured_room_size", 0.05, [40, 40, 41]),  # 2.0 m
        "b": fr("measured_room_size", 0.1, [19, 20, 21]),  # 2.0 m
        "c": fr("door_width_prior", 0.03, [30]),
    }
    cal = calibrate_door_width(done)
    assert cal["door_width_m"] == pytest.approx(2.0, abs=0.03)
    assert set(cal["floors"]) == {"a", "b"}
    assert calibrate_door_width({"a": done["a"], "c": done["c"]}) is None


def test_building_level_evidence_applies_to_every_floor(tmp_path):
    y = tmp_path / "v.yaml"
    y.write_text(
        "venue: {id: v, name: V}\nsource: {file: x.pdf}\nbuildings: [{id: B, name: B}]\n"
        "floors:\n  - {id: B-GF, building: B, level: 0}\n  - {id: B-F1, building: B, level: 1}\n"
        "scale_evidence:\n  B: [{method: typical_room, size_ft: [30, 24]}]\n"
        "  B-F1: [{method: room_size, label: B-227A, size_ft: [35.78, 25.11]}]\n"
    )
    cfg = load_venue_config(y)
    ev = {f.id: [e["method"] for e in f.scale_evidence] for f in cfg.floors}
    assert ev == {"B-GF": ["typical_room"], "B-F1": ["room_size", "typical_room"]}
