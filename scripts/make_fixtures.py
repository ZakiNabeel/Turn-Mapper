"""Regenerate contract/fixtures from the synthetic plans.

valid_*.turnmap         -> must pass validation (Python and the Android importer)
invalid_*.floor.json    -> must be rejected; `_expect_error` names the expected error code
"""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
from pathlib import Path

import cv2

from turn_mapper.api import convert, load_package
from turn_mapper.synthetic import make_plan

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "contract" / "fixtures"


def main() -> None:
    FIX.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    for v in ("basic", "lshape"):
        p = tmp / f"{v}.png"
        cv2.imwrite(str(p), cv2.cvtColor(make_plan(v).rgb, cv2.COLOR_RGB2BGR))
        res = convert(str(p), out_dir=str(tmp / v))
        assert res.all_passed, res.floors[0]["errors"]
        shutil.copy(res.package, FIX / f"valid_synthetic_{v}.turnmap")
    fd = load_package(str(FIX / "valid_synthetic_basic.turnmap"))["floors"]["F1"]

    def bad(name, code, mutate):
        d = copy.deepcopy(fd)
        mutate(d)
        d["_expect_error"] = code
        (FIX / f"invalid_{name}.floor.json").write_text(json.dumps(d, indent=1))

    bad("edge_dangling", "EDGE_DANGLING", lambda d: d["graph"]["edges"][0].update({"to": "nope"}))
    bad("edge_length", "EDGE_LENGTH_MISMATCH", lambda d: d["graph"]["edges"][0].update({"length_m": 99.0}))
    bad("poi_bad_node", "POI_BAD_NODE", lambda d: d["pois"][0].update({"node_id": "nope"}))
    bad("schema_missing_graph", "SCHEMA", lambda d: d.pop("graph"))
    bad("schema_bad_scale_source", "SCHEMA", lambda d: d["transform"].update({"scale_source": "guess"}))
    print("fixtures written to", FIX)


if __name__ == "__main__":
    main()
