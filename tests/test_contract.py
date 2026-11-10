"""Contract tests: the schema copy shipped in the package equals contract/, and every fixture in
contract/fixtures validates (valid ones pass, invalid ones fail)."""

import json
from pathlib import Path

import pytest

from turn_mapper.api import validate_package
from turn_mapper.validate import schema_errors, validate_floor

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "contract" / "fixtures"


def test_schema_copy_in_sync():
    a = json.loads((ROOT / "contract" / "turnmap.schema.json").read_text())
    b = json.loads((ROOT / "src" / "turn_mapper" / "schema" / "turnmap.schema.json").read_text())
    assert a == b, "run: cp contract/turnmap.schema.json src/turn_mapper/schema/"


@pytest.mark.parametrize("pkg", sorted(FIX.glob("valid_*.turnmap")), ids=lambda p: p.name)
def test_valid_fixtures(pkg):
    r = validate_package(str(pkg))
    assert r["passed"], r


@pytest.mark.parametrize("path", sorted(FIX.glob("invalid_*.floor.json")), ids=lambda p: p.name)
def test_invalid_fixtures(path):
    fd = json.loads(path.read_text())
    expected = fd.pop("_expect_error")
    errs = schema_errors(fd, "floor") or validate_floor(fd)[0]
    assert expected in {e.code for e in errs}


def test_fixtures_exist():
    assert list(FIX.glob("valid_*.turnmap")), "run: python scripts/make_fixtures.py"
    assert list(FIX.glob("invalid_*.floor.json"))


@pytest.mark.parametrize("pkg", sorted(FIX.glob("json_*/venue.json")), ids=lambda p: p.parent.name)
def test_valid_json_fixtures(pkg):
    r = validate_package(str(pkg))
    assert r["passed"], r


MF = FIX / "json_synthetic_multifloor" / "venue.json"


def test_multifloor_fixture_has_typed_links_and_frames():
    from turn_mapper.api import load_package
    from turn_mapper.route import VenueGraph

    pkg = load_package(str(MF))
    assert pkg["venue"]["schema_version"] == "0.1.3"
    types = {t["type"] for t in pkg["venue"]["transitions"]}
    assert {"stairs", "lift", "walkway"} <= types
    assert all("building_frame" in fd for fd in pkg["floors"].values())
    r = VenueGraph.from_package(str(MF)).route("T2:R-103", "W0:R-106", step_free=True)
    assert r is not None and r.floors[0] == "T2" and r.floors[-1] == "W0"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t.update({"type": "teleport"}),
        lambda t: t.pop("length_m"),
        lambda t: t["from"].pop("node_id"),
        lambda t: t.update({"length_m": -1}),
    ],
    ids=["bad_type", "no_length", "no_node", "negative_length"],
)
def test_bad_transitions_fail_the_schema(mutate):
    from turn_mapper.api import load_package

    venue = load_package(str(MF))["venue"]
    mutate(venue["transitions"][0])
    assert any(e.code == "SCHEMA" for e in schema_errors(venue, "venue"))


def test_bad_building_frame_fails_the_schema():
    from turn_mapper.api import load_package

    fd = next(iter(load_package(str(MF))["floors"].values()))
    fd["building_frame"]["matrix"] = [[1, 0], [0, 1]]
    assert any(e.code == "SCHEMA" for e in schema_errors(fd, "floor"))
