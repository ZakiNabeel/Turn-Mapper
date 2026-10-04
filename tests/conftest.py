from pathlib import Path

import cv2
import pytest

from turn_mapper.synthetic import make_plan

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def synth_paths(tmp_path_factory):
    d = tmp_path_factory.mktemp("synth")
    out = {}
    for v in ("basic", "lshape"):
        plan = make_plan(v)
        p = d / f"{v}.png"
        cv2.imwrite(str(p), cv2.cvtColor(plan.rgb, cv2.COLOR_RGB2BGR))
        out[v] = (p, plan)
    return out


@pytest.fixture(scope="session")
def converted(synth_paths, tmp_path_factory):
    from turn_mapper.api import convert

    res = {}
    for v, (p, plan) in synth_paths.items():
        out = tmp_path_factory.mktemp(f"run_{v}")
        res[v] = (convert(str(p), out_dir=str(out)), plan)
    return res
