import json
import subprocess
import sys

import networkx as nx
import pytest

from turn_mapper.api import load_package, validate_package
from turn_mapper.validate import validate_floor


@pytest.mark.parametrize("variant", ["basic", "lshape"])
def test_chain_produces_valid_routable_package(converted, variant):
    res, plan = converted[variant]
    assert res.all_passed, res.floors[0]["errors"]
    v = validate_package(str(res.package))
    assert v["passed"], v
    fd = load_package(str(res.package))["floors"]["F1"]
    g = nx.Graph([(e["from"], e["to"]) for e in fd["graph"]["edges"]])
    assert nx.is_connected(g)
    # every room with a door becomes a reachable destination; the door-less room does not
    assert len(fd["pois"]) == len(plan.rooms_with_doors)
    codes = {w["code"] for w in fd["validation"]["warnings"]}
    assert "ROOM_NO_DOOR" in codes and "SCALE_ESTIMATED" in codes


def test_ocr_labels_rooms(converted):
    res, plan = converted["basic"]
    fd = load_package(str(res.package))["floors"]["F1"]
    labels = {p["label"] for p in fd["pois"]}
    expected = {r.label for r in plan.rooms_with_doors}
    assert len(labels & expected) >= len(expected) - 1  # allow one OCR miss


def test_door_prior_scale_close_to_truth(converted):
    res, plan = converted["basic"]
    s = res.floors[0]["scale"]
    assert abs(s - plan.m_per_px) / plan.m_per_px < 0.15


def test_metric_lengths_and_bounds(converted):
    res, plan = converted["basic"]
    fd = load_package(str(res.package))["floors"]["F1"]
    total = sum(e["length_m"] for e in fd["graph"]["edges"] if e["type"] == "corridor")
    assert 20 < total < 45  # 30 m corridor + small stubs, at estimated scale


def test_validator_catches_wall_crossing_and_dangling(converted):
    res, _ = converted["basic"]
    fd = load_package(str(res.package))["floors"]["F1"]
    bad = json.loads(json.dumps(fd))
    # edge straight through the building, from the first room POI node to a far node
    n0, n1 = bad["graph"]["nodes"][0], bad["graph"]["nodes"][-1]
    n_far = {"id": "x1", "x": 1.5, "y": 1.5, "kind": "corridor"}
    bad["graph"]["nodes"].append(n_far)
    bad["graph"]["edges"].append(
        {"id": "ex", "from": n0["id"], "to": "x1", "length_m": 0.0, "type": "corridor", "bidirectional": True}
    )
    bad["graph"]["edges"].append(
        {
            "id": "ey",
            "from": n1["id"],
            "to": "missing",
            "length_m": 1.0,
            "type": "corridor",
            "bidirectional": True,
        }
    )
    errs, _ = validate_floor(bad)
    codes = {e.code for e in errs}
    assert {"EDGE_DANGLING", "EDGE_LENGTH_MISMATCH", "EDGE_OUTSIDE_WALKABLE"} <= codes


def test_cli_inspect_and_validate(synth_paths, converted):
    p, _ = synth_paths["basic"]
    out = subprocess.run(
        [sys.executable, "-m", "turn_mapper.cli", "inspect", str(p)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(out.stdout)["kind"] == "image"
    res, _ = converted["basic"]
    r = subprocess.run(
        [sys.executable, "-m", "turn_mapper.cli", "validate", str(res.package)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0 and "PASSED" in r.stdout
