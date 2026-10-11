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
