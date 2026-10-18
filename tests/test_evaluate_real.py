"""Real-floor evaluator: a map compared with itself is perfect; a degraded map scores lower."""

import copy
import importlib.util
from pathlib import Path

import cv2
import pytest

from turn_mapper.api import process_floor
from turn_mapper.config import single_image_config
from turn_mapper.export import floor_to_dict
from turn_mapper.synthetic import make_plan, render_style

spec = importlib.util.spec_from_file_location(
    "evaluate_real", Path(__file__).parents[1] / "eval/evaluate_real.py"
)
er = importlib.util.module_from_spec(spec)
spec.loader.exec_module(er)


@pytest.fixture(scope="module")
def fd(tmp_path_factory):
    p = tmp_path_factory.mktemp("er") / "p.png"
    cv2.imwrite(str(p), render_style(make_plan("basic"), "blackwalls"))
    cfg = single_image_config(str(p))
    return floor_to_dict(process_floor(cfg.floors[0], cfg))


def test_identical_maps_score_perfectly(fd):
    m = er.compare(fd, fd)
    assert m["room_recall"] == m["room_precision"] == m["door_recall"] == m["place_recall"] == 1.0
    assert m["routes"] == 1.0 and m["wall_crossings"] == 0


def test_missing_room_and_door_lower_the_scores(fd):
    worse = copy.deepcopy(fd)
    worse["rooms"] = worse["rooms"][1:]
    worse["doors"] = worse["doors"][1:]
    m = er.compare(fd, worse)
    assert m["room_recall"] < 1.0 and m["door_recall"] < 1.0 and m["room_precision"] == 1.0
