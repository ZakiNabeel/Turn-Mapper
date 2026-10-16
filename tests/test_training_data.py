"""Stage-2 training data: styles, ResPlan rasterising (on a hand-made plan) and institutional floors."""

import pickle

import numpy as np
import pytest
from shapely.geometry import MultiPolygon, Polygon, box

from turn_mapper.learned.classes import BG, DOOR, ROOM, STAIRS, WALKABLE, WALL
from turn_mapper.learned.institutional import generate
from turn_mapper.learned.institutional import prepare as make_inst
from turn_mapper.learned.resplan import load_resplan, m_per_unit, prepare, rasterize
from turn_mapper.learned.styles import STYLES, render


def _plan(pid=1):
    # 200 x 100 units; 0.05 m/unit -> 10 m x 5 m = 50 m2 inner
    inner = MultiPolygon([box(0, 0, 200, 100)])
    walls = box(-4, -4, 204, 104).difference(box(0, 0, 200, 100)).union(box(98, 0, 102, 100))
    walls = walls.difference(box(98, 40, 102, 58))  # opening for the door
    return {
        "id": pid,
        "area": 50.0,
        "inner": inner,
        "wall": MultiPolygon(list(getattr(walls, "geoms", [walls]))),
        "bedroom": MultiPolygon([box(0, 0, 98, 100)]),
        "living": box(102, 0, 200, 100),
        "door": MultiPolygon([box(98, 40, 102, 58)]),
        "window": MultiPolygon([]),
    }


def test_rasterize_scale_and_classes():
    p = _plan()
    assert m_per_unit(p) == pytest.approx(0.05)
    mask, ex, s = rasterize(p, 0.025, np.random.default_rng(0))  # 2 px per unit
    assert mask.shape[1] == pytest.approx((208 + 2 * 20) * 2, abs=4)
    assert {BG, WALL, ROOM, DOOR} <= set(np.unique(mask))
    assert len(ex.doors) == 1
    hinge, end, _ = ex.doors[0]
    assert np.hypot(end[0] - hinge[0], end[1] - hinge[1]) == pytest.approx(36, abs=3)  # 18 units = 0.9 m


@pytest.mark.parametrize("style", STYLES)
def test_every_style_draws_walls_dark_or_outlined(style):
    rng = np.random.default_rng(1)
    mask, ex = generate(rng, m_per_px=0.04)
    img = render(mask, ex, style, rng)
    assert img.shape == (*mask.shape, 3) and img.dtype == np.uint8
    g = img.mean(axis=2)
    assert g[mask == WALL].mean() < g[mask == ROOM].mean() - 20  # walls are visible in every convention


def test_institutional_has_corridors_and_cores():
    rng = np.random.default_rng(5)
    seen = set()
    for _ in range(6):
        mask, _ = generate(rng)
        seen |= set(np.unique(mask).tolist())
    assert {WALL, ROOM, WALKABLE, DOOR} <= seen and STAIRS in seen


def test_prepare_writes_split_by_plan(tmp_path):
    pkl = tmp_path / "ResPlan.pkl"
    pkl.write_bytes(pickle.dumps([_plan(1), _plan(2), _plan(3)]))
    split = tmp_path / "split.json"
    split.write_text('{"train": [1, 2], "val": [3], "test": []}')
    info = prepare(pkl, tmp_path / "ds", split, variants=2)
    assert info["splits"] == {"train": 4, "val": 2, "test": 0}
    assert (tmp_path / "ds" / "masks" / "rp3_1.png").exists()
    inst = make_inst(tmp_path / "inst", n=4, val_frac=0.25)
    assert inst["splits"] == {"train": 3, "val": 1}


def test_unsafe_pickle_is_refused(tmp_path):
    class Evil:
        def __reduce__(self):
            import os

            return (os.system, ("echo pwned",))

    p = tmp_path / "bad.pkl"
    p.write_bytes(pickle.dumps([Evil()]))
    with pytest.raises(pickle.UnpicklingError):
        load_resplan(p)


def test_polygon_helper_ignores_empty():
    assert rasterize({**_plan(), "stair": Polygon()}, 0.05, np.random.default_rng(0))[0].size
