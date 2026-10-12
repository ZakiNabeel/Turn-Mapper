"""Acceptance tests for requirements not covered by a stage test (docs/mideval/03_REQUIREMENTS.md)."""

import json
import subprocess
from pathlib import Path

import cv2

from turn_mapper.api import convert, load_package
from turn_mapper.synthetic import make_plan

ROOT = Path(__file__).resolve().parents[1]


def _plan(tmp_path, variant="basic"):
    p = tmp_path / f"{variant}.png"
    cv2.imwrite(str(p), cv2.cvtColor(make_plan(variant).rgb, cv2.COLOR_RGB2BGR))
    return p


def test_qa_report_and_run_manifest(tmp_path):
    """FR-13 + NFR-05: every run writes a QA report and a manifest that pins inputs, params and code."""
    p = _plan(tmp_path)
    res = convert(str(p), out_dir=str(tmp_path / "out"))
    assert res.report.exists() and (tmp_path / "out" / "qa" / "F1_overlay.png").exists()
    m = json.loads(res.manifest.read_text())
    assert len(m["inputs"][p.name]) == 64  # sha256 of the input plan
    assert {"git_commit", "version"} <= set(m["generator"]) and m["params"]


def test_deterministic_output(tmp_path):
    """NFR-05: the same input and config give the same map (ignoring run id / timestamps)."""
    p = _plan(tmp_path, "lshape")
    a = convert(str(p), out_dir=str(tmp_path / "a"))
    b = convert(str(p), out_dir=str(tmp_path / "b"))
    fa = load_package(str(a.package))["floors"]["F1"]
    fb = load_package(str(b.package))["floors"]["F1"]
    for k in ("walkable", "walls", "doors", "rooms", "graph", "pois", "transform"):
        assert fa[k] == fb[k], k


def test_every_element_has_provenance(tmp_path):
    """NFR-10: AI output is a proposal: rooms, doors, nodes, edges, POIs all carry provenance."""
    res = convert(str(_plan(tmp_path)), out_dir=str(tmp_path / "out"))
    fd = load_package(str(res.package))["floors"]["F1"]
    items = fd["rooms"] + fd["doors"] + fd["pois"] + fd["graph"]["nodes"] + fd["graph"]["edges"]
    assert items and all(i.get("provenance", {}).get("source") == "auto" for i in items)


def test_no_private_data_in_git():
    """NFR-08: plans, datasets and weights never enter the repository."""
    files = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
    bad = [
        f
        for f in files
        if f.startswith(("samples/private/", "data/", "weights/", "runs/"))
        or f.endswith((".pt", ".pth", ".ckpt", ".pdf", ".zip"))
    ]
    assert not bad, bad
