"""Export for the live-positioning app (venue package v1 + TURN Floor GeoJSON v1)."""

import json

import pytest

from turn_mapper.positioning_export import export, to_floor_geojson, to_venue_package


@pytest.fixture()
def venue(converted):
    res, _ = converted["lshape"]
    return json.loads(res.package.read_text()), res.package


def test_package_shape_and_frame(venue):
    v, _ = venue
    pkg, rep = to_venue_package(v)
    assert pkg["schemaVersion"] == 1 and pkg["frame"]["axes"] == "x-right-y-up"
    fl = pkg["floors"][0]
    fd = v["floors"][0]["floor"]
    h = fd["image"]["height_px"] * fd["transform"]["scale_m_per_px"]
    assert fl["heightMetres"] == pytest.approx(h, abs=0.01)
    # y is flipped: a node at TURN-Mapper y has app y = height - y
    n0 = fd["graph"]["nodes"][0]
    a0 = next(n for n in pkg["nodes"] if n["id"].endswith(":" + n0["id"]))
    assert a0["y"] == pytest.approx(h - n0["y"], abs=0.01)
    for kind in ("nodes", "edges", "pois", "anchors", "connectors"):
        ids = [x["id"] for x in pkg[kind]]
        assert len(ids) == len(set(ids)), kind
    assert all(0 <= n["x"] <= fl["widthMetres"] and 0 <= n["y"] <= fl["heightMetres"] for n in pkg["nodes"])
    assert any(r["kind"] == "circulation" for r in fl["rooms"])


def test_edges_never_shorter_than_geometry_and_references_resolve(venue):
    v, _ = venue
    pkg, _ = to_venue_package(v)
    nodes = {n["id"]: n for n in pkg["nodes"]}
    for e in pkg["edges"]:
        a, b = nodes[e["from"]], nodes[e["to"]]
        assert e["distanceMetres"] + 0.001 >= ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5
    assert all(p["nodeId"] in nodes for p in pkg["pois"])
    for a in pkg["anchors"]:
        n = nodes[a["nodeId"]]
        assert a["venueId"] == pkg["venueId"] and (n["x"], n["y"]) == (a["position"]["x"], a["position"]["y"])
    assert pkg["anchors"], "a package needs at least one start anchor"


def test_destinations_are_reachable_from_every_anchor(venue):
    import networkx as nx

    v, _ = venue
    pkg, _ = to_venue_package(v)
    g = nx.Graph([(e["from"], e["to"]) for e in pkg["edges"]])
    for a in pkg["anchors"]:
        for p in pkg["pois"]:
            assert nx.has_path(g, a["nodeId"], p["nodeId"])


def test_geojson_and_export_files(venue, tmp_path):
    v, path = venue
    gj = to_floor_geojson(v, v["floors"][0]["id"])
    kinds = {f["properties"]["kind"] for f in gj["features"]}
    assert {"room", "circulation", "door", "wall"} <= kinds and gj["turn"]["units"] == "metres"
    rep = export(path, tmp_path)
    fid = v["floors"][0]["id"]
    assert (tmp_path / "floors" / fid / "venue.package.json").exists()
    assert (tmp_path / "floors" / fid / f"{fid}.turn-floor.geojson").exists()
    assert (tmp_path / "export_report.json").exists() and rep
