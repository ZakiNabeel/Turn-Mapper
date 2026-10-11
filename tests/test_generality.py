"""Generality: the same known layout drawn in different conventions must give the same map.

Full matrix (2 layouts x 6 styles, with a report): scripts/style_stress.py. This keeps a fast subset in CI.
"""

import pytest

from turn_mapper.api import convert, load_package
from turn_mapper.synthetic import make_plan, render_style


@pytest.mark.parametrize("style", ["greyfill", "blackwalls", "thinlines", "doubleline", "colored"])
def test_style_basic(style, tmp_path):
    import cv2

    plan = make_plan("basic")
    p = tmp_path / f"{style}.png"
    cv2.imwrite(str(p), cv2.cvtColor(render_style(plan, style), cv2.COLOR_RGB2BGR))
    res = convert(str(p), out_dir=str(tmp_path / "out"))
    assert res.all_passed, res.floors[0]["errors"]
    fd = load_package(str(res.package))["floors"]["F1"]
    assert len(fd["rooms"]) == len(plan.rooms)
    assert len(fd["doors"]) == len(plan.rooms_with_doors)
    assert res.floors[0]["n_components"] == 1
