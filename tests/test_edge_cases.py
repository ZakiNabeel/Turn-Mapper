"""Edge and failure cases: the module must reject bad input clearly, never crash or emit an unusable map."""

import time

import cv2
import numpy as np
from click.testing import CliRunner

from turn_mapper.api import convert
from turn_mapper.cli import main
from turn_mapper.synthetic import make_plan


def test_blank_page_is_rejected_not_crashed(tmp_path):
    p = tmp_path / "blank.png"
    cv2.imwrite(str(p), np.full((400, 600), 255, np.uint8))
    res = convert(str(p), out_dir=str(tmp_path / "out"))
    f = res.floors[0]
    assert not f["passed"]
    assert "WALKABLE_EMPTY" in {e["code"] for e in f["errors"]}


def test_random_noise_is_rejected(tmp_path):
    p = tmp_path / "noise.png"
    cv2.imwrite(str(p), (np.random.default_rng(0).random((300, 400)) * 255).astype(np.uint8))
    res = convert(str(p), out_dir=str(tmp_path / "out"))
    assert not res.all_passed


def test_unsupported_file_gives_clear_cli_error(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("not a floor plan")
    r = CliRunner().invoke(main, ["run", str(p), "--out", str(tmp_path / "out")])
    assert r.exit_code != 0
    assert "no adapter can read" in r.output and "Traceback" not in r.output


def test_missing_learned_weights_gives_clear_cli_error(tmp_path, monkeypatch):
    monkeypatch.setenv("TURN_SEG_WEIGHTS", str(tmp_path / "missing.pt"))
    p = tmp_path / "plan.png"
    cv2.imwrite(str(p), cv2.cvtColor(make_plan("basic").rgb, cv2.COLOR_RGB2BGR))
    r = CliRunner().invoke(main, ["run", str(p), "--segmenter", "learned", "--out", str(tmp_path / "o")])
    assert r.exit_code != 0
    assert ("no segmentation weights" in r.output) or ("ML extra" in r.output)


def test_floor_runtime_under_budget(tmp_path):
    """NFR-01: one floor in well under 2 minutes on a laptop CPU (synthetic floor: < 30 s)."""
    p = tmp_path / "plan.png"
    cv2.imwrite(str(p), cv2.cvtColor(make_plan("lshape").rgb, cv2.COLOR_RGB2BGR))
    t0 = time.time()
    res = convert(str(p), out_dir=str(tmp_path / "out"))
    assert res.all_passed and time.time() - t0 < 30
