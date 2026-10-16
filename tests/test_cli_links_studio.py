"""CLI commands (D-09 coverage) and Studio floor links."""

import json

import cv2
import pytest
from click.testing import CliRunner

from turn_mapper.cli import main
from turn_mapper.synthetic import make_plan, render_style


@pytest.fixture(scope="module")
def plan_png(tmp_path_factory):
    p = tmp_path_factory.mktemp("cli") / "plan.png"
    cv2.imwrite(str(p), render_style(make_plan("basic"), "blackwalls"))
    return p


def test_cli_inspect_run_validate(plan_png, tmp_path):
    r = CliRunner().invoke(main, ["inspect", str(plan_png)])
    assert r.exit_code == 0 and "image" in r.output
    out = tmp_path / "run"
    r = CliRunner().invoke(main, ["run", str(plan_png), "--out", str(out)])
    assert r.exit_code == 0, r.output
    pkg = out / "venue.json"
    assert pkg.exists() and json.loads(pkg.read_text())["transitions"] == []
    assert json.loads((out / "run_manifest.json").read_text())["link_warnings"] == []
    r = CliRunner().invoke(main, ["validate", str(pkg)])
    assert r.exit_code == 0, r.output


def test_cli_make_institutional(tmp_path):
    r = CliRunner().invoke(main, ["ml", "make-institutional", "--out", str(tmp_path / "d"), "-n", "2"])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "d" / "dataset.json").exists()


def test_studio_two_floors_link_and_export(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from turn_mapper.studio.server import create_app

    c = TestClient(create_app(tmp_path))
    pid = c.post("/api/projects", json={"name": "Two"}).json()["id"]
    _, buf = cv2.imencode(".png", render_style(make_plan("basic"), "blackwalls"))
    c.post(f"/api/projects/{pid}/files", files={"file": ("p.png", buf.tobytes(), "image/png")})
    for fid, lvl in (("G", 0), ("F1", 1)):
        c.post(
            f"/api/projects/{pid}/floors", json={"source": "p.png", "id": fid, "building": "C", "level": lvl}
        )
        assert c.post(f"/api/projects/{pid}/floors/{fid}/run", json={}).status_code == 200
    # the synthetic plan has no stairs, so add a stairs node to both floors by hand (a manual edit)
    for fid in ("G", "F1"):
        fd = c.get(f"/api/projects/{pid}/floors/{fid}").json()["floor"]
        n = fd["graph"]["nodes"][0]
        n["transition"] = "stairs"
        fd["_edited"] = True
        assert c.put(f"/api/projects/{pid}/floors/{fid}/floor", json=fd).status_code == 200
    L = c.get(f"/api/projects/{pid}/links").json()
    assert {x["floor_id"] for x in L["manual"]} == set() and len(L["links"]) == 1  # auto proposal
    assert set(L["nodes"]) == {"G", "F1"}
    nid = L["nodes"]["G"][0]["id"]
    manual = [{"from": {"floor_id": "G", "node_id": nid}, "to": {"floor_id": "F1", "node_id": nid}}]
    L = c.put(f"/api/projects/{pid}/links", json={"manual": manual}).json()
    assert L["links"][0]["provenance"]["source"] == "manual"
    r = c.get(f"/api/projects/{pid}/export/venue.json")
    assert r.status_code == 200
