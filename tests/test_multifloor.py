"""Multi-floor and multi-building routing, end to end on synthetic plans with known answers.

Tower: the same plan on 3 levels with a stair core (STAIRS) and a lift (LIFT). Annex: a one-floor
building joined to the tower's ground floor by a configured walkway.
"""

import json
import subprocess
import sys

import cv2
import pytest

from turn_mapper.api import convert, load_package, validate_package
from turn_mapper.route import VenueGraph, venue_checks
from turn_mapper.synthetic import make_plan

VENUE_YAML = """venue: {id: synth-campus, name: Synthetic campus}
buildings:
  - {id: T, name: Tower}
  - {id: W, name: Annex}
floors:
  - {id: T0, building: T, level: 0, file: tower.png}
  - {id: T1, building: T, level: 1, file: tower.png}
  - {id: T2, building: T, level: 2, file: tower.png}
  - {id: W0, building: W, level: 0, file: annex.png}
scale_evidence:
  T: [{p1_px: [25, 25], p2_px: [775, 25], distance_m: 30.0}]
  W: [{p1_px: [25, 25], p2_px: [775, 25], distance_m: 30.0}]
multifloor:
  connections:
    - {from: "T0:R-101", to: "W0:R-104", type: walkway, length_m: 25}
"""


@pytest.fixture(scope="module")
def campus(tmp_path_factory):
    d = tmp_path_factory.mktemp("campus")
    for name, variant in (("tower", "tower"), ("annex", "basic")):
        cv2.imwrite(str(d / f"{name}.png"), cv2.cvtColor(make_plan(variant).rgb, cv2.COLOR_RGB2BGR))
    (d / "venue.yaml").write_text(VENUE_YAML)
    out = d / "run"
    convert(str(d / "tower.png"), venue_config=str(d / "venue.yaml"), out_dir=str(out))
    return out / "venue.json"


def test_links_join_every_tower_level(campus):
    pkg = load_package(str(campus))
    tr = pkg["venue"]["transitions"]
    kinds = {(t["type"], t["from"]["floor_id"], t["to"]["floor_id"]) for t in tr}
    for a, b in (("T0", "T1"), ("T1", "T2")):
        assert ("stairs", a, b) in kinds or ("stairs", b, a) in kinds
        assert ("lift", a, b) in kinds or ("lift", b, a) in kinds
    assert any(t["type"] == "walkway" and t["length_m"] == 25 for t in tr)
    # every link carries provenance; identical plans register with scale ~1
    assert all(t["provenance"]["source"] in ("auto", "manual", "corrected") for t in tr)
    for fid in ("T1", "T2"):
        bf = pkg["floors"][fid]["building_frame"]
        assert bf["reference_floor_id"] == "T0" and abs(bf["registered_scale"] - 1) < 0.02


def test_route_across_floors_and_step_free(campus):
    vg = VenueGraph.from_package(str(campus))
    r = vg.route("T0:R-102", "T2:R-106")
    assert r is not None and r.floors == ["T0", "T1", "T2"]
    assert any("stairs up 2 floors" in s for s in r.instructions)
    sf = vg.route("T0:R-102", "T2:R-106", step_free=True)
    assert sf is not None and sf.step_free
    assert {c.type for c in sf.changes} == {"lift"}
    assert sf.time_s >= r.time_s  # lift wait makes it slower here
    # across buildings: stairs down then the walkway
    x = vg.route("T2:R-103", "W0:R-106")
    assert x is not None and [c.type for c in x.changes][-1] == "walkway"
    assert x.floors[-1] == "W0"


def test_find_place_ambiguity_and_misses(campus):
    vg = VenueGraph.from_package(str(campus))
    assert {p.floor_id for p in vg.find_place("R-102")} >= {"T0", "T1", "T2"}
    with pytest.raises(KeyError, match="T0"):
        vg._one("R-102")  # ambiguous: the error lists the floors
    assert len(vg.find_place("R-102", floor_id="T1")) == 1
    with pytest.raises(KeyError):
        vg._one("no such room")


def test_venue_checks_and_validate(campus):
    vg = VenueGraph.from_package(str(campus))
    v = venue_checks(vg, samples=50)
    assert v["floor_pairs_connected"] == v["floor_pairs_total"] == 12
    assert v["routed"] == v["sampled_cross_floor_routes"] > 0
    assert v["routed_step_free"] == v["routed"]
    assert not [w for w in v["warnings"] if w["code"] in ("W_BUILDINGS_SEPARATE", "W_FLOOR_UNLINKED")]
    res = validate_package(str(campus))
    assert res["passed"] and res["multifloor"]["floor_pairs_connected"] == 12


def test_cli_route(campus):
    def run(*a):
        return subprocess.run(
            [sys.executable, "-m", "turn_mapper.cli", "route", str(campus), *a],
            capture_output=True,
            text=True,
        )

    p = run("--from", "T0:R-102", "--to", "T2:R-106", "--step-free", "--json")
    assert p.returncode == 0, p.stderr
    d = json.loads(p.stdout)
    assert d["step_free"] and d["floors"] == ["T0", "T1", "T2"]
    p = run("--from", "R-102", "--to", "T2:R-106")
    assert p.returncode == 2 and "R-102" in (p.stdout + p.stderr)


def test_studio_route_across_floors(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from turn_mapper.studio.server import create_app

    c = TestClient(create_app(tmp_path))
    pid = c.post("/api/projects", json={"name": "Tower"}).json()["id"]
    _, buf = cv2.imencode(".png", cv2.cvtColor(make_plan("tower").rgb, cv2.COLOR_RGB2BGR))
    c.post(f"/api/projects/{pid}/files", files={"file": ("t.png", buf.tobytes(), "image/png")})
    for lvl in range(3):
        fid = f"T{lvl}"
        c.post(
            f"/api/projects/{pid}/floors", json={"source": "t.png", "id": fid, "building": "T", "level": lvl}
        )
        assert c.post(f"/api/projects/{pid}/floors/{fid}/run", json={}).status_code == 200
    q = c.get(f"/api/projects/{pid}/links").json()["quality"]
    assert set(q) == {"T0", "T1", "T2"} and all(v["pieces"] == 1 for v in q.values())
    places = c.get(f"/api/projects/{pid}/places").json()
    assert {p["floor_id"] for p in places} == {"T0", "T1", "T2"}
    r = c.post(f"/api/projects/{pid}/route", json={"from": "T0:R-102", "to": "T2:R-106"}).json()
    assert r["found"] and r["floors"] == ["T0", "T1", "T2"] and r["legs"][0]["nodes"]
    r = c.post(f"/api/projects/{pid}/route", json={"from": "T0:R-102", "to": "T2:R-106", "step_free": True})
    assert r.json()["found"] and {ch["type"] for ch in r.json()["changes"]} == {"lift"}
    assert c.post(f"/api/projects/{pid}/route", json={"from": "R-102", "to": "T2:R-106"}).status_code == 404


def test_floor_quality_grades(campus):
    from turn_mapper.route import floor_quality

    v = venue_checks(VenueGraph.from_package(str(campus)), samples=10)
    q = {f: d["quality"] for f, d in v["floors"].items()}
    assert q["T1"]["grade"] == "ready" and q["T1"]["transitions_linked"] == "2/2"
    base = dict(
        pieces=1,
        destinations=10,
        destinations_on_main=10,
        scale_source="operator_two_point",
        transitions=1,
        transitions_linked=1,
        multi_floor_building=True,
        reaches_building=True,
    )
    assert floor_quality(**base)["grade"] == "ready"
    est = floor_quality(**{**base, "scale_source": "door_width_prior"})
    assert est["grade"] == "usable" and "estimate" in est["reasons"][0]
    assert floor_quality(**{**base, "destinations_on_main": 8, "pieces": 2})["grade"] == "needs work"
    assert floor_quality(**{**base, "reaches_building": False})["grade"] == "needs work"
    empty = floor_quality(**{**base, "destinations": 0, "destinations_on_main": 0})
    assert empty["grade"] == "needs work" and "no destinations found" in empty["reasons"]


def test_studio_connection_between_buildings(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from turn_mapper.studio.server import create_app

    c = TestClient(create_app(tmp_path))
    pid = c.post("/api/projects", json={"name": "Two blocks"}).json()["id"]
    _, buf = cv2.imencode(".png", cv2.cvtColor(make_plan("tower").rgb, cv2.COLOR_RGB2BGR))
    c.post(f"/api/projects/{pid}/files", files={"file": ("t.png", buf.tobytes(), "image/png")})
    for fid, b in (("T0", "T"), ("W0", "W")):
        c.post(f"/api/projects/{pid}/floors", json={"source": "t.png", "id": fid, "building": b, "level": 0})
        assert c.post(f"/api/projects/{pid}/floors/{fid}/run", json={}).status_code == 200
    r = c.post(f"/api/projects/{pid}/route", json={"from": "T0:R-102", "to": "W0:R-106"}).json()
    assert not r["found"]  # two buildings, nothing joins them yet
    body = {
        "manual": [],
        "connections": [{"from": "T0@right", "to": "W0@left", "type": "walkway", "length_m": 12}],
    }
    L = c.put(f"/api/projects/{pid}/links", json=body).json()
    w = [t for t in L["links"] if t["type"] == "walkway"]
    assert len(w) == 1 and w[0]["length_m"] == 12 and w[0]["provenance"]["source"] == "auto"
    assert L["connections"] == body["connections"] and set(L["floors"]) == {"T0", "W0"}
    assert any(x["code"] == "LINK_ENDPOINT_ESTIMATED" for x in L["warnings"])
    r = c.post(f"/api/projects/{pid}/route", json={"from": "T0:R-102", "to": "W0:R-106"}).json()
    assert r["found"] and r["floors"] == ["T0", "W0"] and r["changes"][0]["type"] == "walkway"
    bad = {"manual": [], "connections": [{"from": "T0@right", "to": "W0@left", "type": "teleport"}]}
    assert c.put(f"/api/projects/{pid}/links", json=bad).status_code == 400


def test_compare_segmenters_script_classical(tmp_path):
    """compare_fast_segmenters.py: per-floor table and venue rows (classical only: no weights needed)."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "cmp", Path(__file__).parents[1] / "scripts" / "compare_fast_segmenters.py"
    )
    cmp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cmp)
    for name, variant in (("tower", "tower"), ("annex", "basic")):
        cv2.imwrite(str(tmp_path / f"{name}.png"), cv2.cvtColor(make_plan(variant).rgb, cv2.COLOR_RGB2BGR))
    (tmp_path / "venue.yaml").write_text(VENUE_YAML)
    r = cmp.run_method(
        str(tmp_path / "tower.png"), str(tmp_path / "venue.yaml"), tmp_path / "c", "classical", 10
    )
    assert set(r["floors"]) == {"T0", "T1", "T2", "W0"}
    assert all(f["valid"] and f["pieces"] == 1 and f["reachable"] == 1.0 for f in r["floors"].values())
    assert r["venue"]["floor_pairs_connected"] == r["venue"]["floor_pairs_total"] == 12
    md = cmp.table({"methods": {"classical": r}, "weights": None})
    assert "| T1 | ok · 8/7/7 · 1 · 100% · ready |" in md and "| floors valid | 4/4 |" in md
