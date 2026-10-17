"""TURN Studio backend: upload -> floor -> run -> edit -> scale -> masks re-run -> export."""

import base64
import io
import json
import zipfile

import cv2
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from turn_mapper.api import validate_package  # noqa: E402
from turn_mapper.studio.project import rescale_floor, tidy_floor, walkable_edit  # noqa: E402
from turn_mapper.studio.server import create_app  # noqa: E402
from turn_mapper.synthetic import make_plan, render_style  # noqa: E402


@pytest.fixture(scope="module")
def studio(tmp_path_factory):
    c = TestClient(create_app(tmp_path_factory.mktemp("studio")))
    pid = c.post("/api/projects", json={"name": "Test Venue"}).json()["id"]
    ok, buf = cv2.imencode(".png", render_style(make_plan("basic"), "blackwalls"))
    r = c.post(f"/api/projects/{pid}/files", files={"file": ("plan.png", buf.tobytes(), "image/png")})
    assert r.status_code == 200
    r = c.post(
        f"/api/projects/{pid}/floors", json={"source": "plan.png", "id": "F1", "building": "C", "level": 1}
    )
    assert r.status_code == 200, r.text
    r = c.post(f"/api/projects/{pid}/floors/F1/run", json={})
    assert r.status_code == 200, r.text
    return c, pid


def test_run_gives_a_valid_floor(studio):
    c, pid = studio
    s = c.get(f"/api/projects/{pid}/floors/F1").json()["record"]["summary"]
    assert s["passed"] and s["rooms"] == 7 and s["doors"] == 6 and s["components"] == 1
    assert s["routes_ok"] == s["routes_tried"]


def test_manual_edit_is_kept_and_validated(studio):
    c, pid = studio
    fd = c.get(f"/api/projects/{pid}/floors/F1").json()["floor"]
    gone = fd["graph"]["nodes"][0]["id"]
    fd["graph"]["nodes"] = fd["graph"]["nodes"][1:]
    fd["_edited"] = True
    r = c.put(f"/api/projects/{pid}/floors/F1/floor", json=fd).json()
    assert r["record"]["status"] == "edited"
    assert all(
        gone not in (e["from"], e["to"]) for e in r["floor"]["graph"]["edges"]
    )  # dangling edges dropped
    r = c.post(f"/api/projects/{pid}/floors/F1/revert").json()
    assert any(n["id"] == gone for n in r["floor"]["graph"]["nodes"])


def test_scale_rescales_the_floor(studio):
    c, pid = studio
    pairs = [{"p1_px": [25, 25], "p2_px": [775, 25], "distance_m": 30.0}]  # plan is 25 px/m
    r = c.post(f"/api/projects/{pid}/floors/F1/scale", json={"pairs": pairs}).json()
    t = r["floor"]["transform"]
    assert t["scale_source"] == "operator_two_point" and t["scale_m_per_px"] == pytest.approx(0.04)
    assert r["floor"]["bounds_m"]["max_x"] == pytest.approx(800 * 0.04, abs=0.01)


def test_masks_roundtrip_and_rerun(studio):
    c, pid = studio
    png = c.get(f"/api/projects/{pid}/floors/F1/image/masks").content
    assert (
        c.put(
            f"/api/projects/{pid}/floors/F1/masks", json={"png": base64.b64encode(png).decode()}
        ).status_code
        == 200
    )
    r = c.post(f"/api/projects/{pid}/floors/F1/run", json={"from_masks": True}).json()
    assert r["record"]["status"] == "corrected" and r["floor"]["validation"]["passed"]
    assert r["floor"]["walls"][0]["provenance"]["source"] == "corrected"


def test_exports(studio, tmp_path):
    c, pid = studio
    r = c.get(f"/api/projects/{pid}/export/venue.json")
    assert r.status_code == 200
    zipfile.ZipFile(io.BytesIO(r.content)).extractall(tmp_path)
    assert validate_package(str(tmp_path / "venue.json"))["passed"]
    gj = json.loads(c.get(f"/api/projects/{pid}/export/geojson").content)
    assert {f["properties"]["layer"] for f in gj["features"]} >= {
        "walkable",
        "wall",
        "door",
        "room",
        "node",
        "edge",
    }
    assert c.get(f"/api/projects/{pid}/export/svg").content.startswith(b"<svg")
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/projects/{pid}/export/annotations").content))
    assert any(n.startswith("masks/") for n in z.namelist())
    assert c.get(f"/api/projects/{pid}/export/turnmap").status_code == 200


def test_dwg_upload_is_refused_clearly(studio):
    c, pid = studio
    r = c.post(f"/api/projects/{pid}/files", files={"file": ("x.dwg", b"AC1032", "application/octet-stream")})
    assert r.status_code == 400 and "DXF" in r.json()["detail"]


def test_pure_helpers():
    fd = {
        "walkable": {
            "type": "MultiPolygon",
            "coordinates": [[[[0, 0], [10, 0], [10, 4], [0, 4], [0, 0]]]],
            "provenance": {"source": "auto"},
        },
        "walls": [{"id": "w1", "a": [0, 0], "b": [10, 0], "thickness_m": 0.2}],
        "doors": [],
        "rooms": [],
        "graph": {
            "nodes": [
                {"id": "a", "x": 1, "y": 2, "kind": "corridor", "door_id": "gone"},
                {"id": "b", "x": 9, "y": 2, "kind": "door", "door_id": "gone"},
            ],
            "edges": [
                {"id": "e1", "from": "a", "to": "b", "length_m": 0},
                {"id": "e2", "from": "b", "to": "a", "length_m": 0},
                {"id": "e3", "from": "a", "to": "zz", "length_m": 0},
            ],
        },
        "pois": [{"id": "p", "node_id": "zz", "room_id": None}],
        "bounds_m": {"min_x": 0, "min_y": 0, "max_x": 10, "max_y": 4},
    }
    t = tidy_floor(fd)
    assert [e["id"] for e in t["graph"]["edges"]] == ["e1"] and t["graph"]["edges"][0]["length_m"] == 8
    assert t["graph"]["nodes"][1]["kind"] == "junction" and not t["pois"]
    assert rescale_floor(t, 2)["graph"]["nodes"][1]["x"] == 18
    cut = walkable_edit(t, [[8, 1], [10.5, 1], [10.5, 3], [8, 3]], "remove")
    assert [n["id"] for n in cut["graph"]["nodes"]] == ["a"]


def test_export_editable_dxf(studio):
    ezdxf = pytest.importorskip("ezdxf")
    c, pid = studio
    r = c.get(f"/api/projects/{pid}/export/dxf")
    assert r.status_code == 200 and "dxf" in r.headers["content-disposition"]
    doc = ezdxf.read(io.StringIO(r.content.decode("utf-8", "ignore")))
    assert doc.header["$INSUNITS"] == 6
    assert any(e.dxf.layer == "A-WALL" for e in doc.modelspace())
