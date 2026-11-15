"""FloorPlanCAD -> partial masks (real CAD drawings; the test uses tiny fake tiles in the same convention)."""

import cv2
import numpy as np
import pytest

from turn_mapper.learned.classes import ESCALATOR, IGNORE, LIFT, OPEN, STAIRS, WALL
from turn_mapper.learned.floorplancad import fake_tile, path_polylines, prepare, rasterize, read_svg


@pytest.fixture(scope="module")
def fpc(tmp_path_factory):
    d = tmp_path_factory.mktemp("fpc")
    (d / "train").mkdir()
    (d / "test").mkdir()
    for i in range(6):
        fake_tile(d / "train" / f"t{i}.svg", i, lift=i % 2 == 0)
    fake_tile(d / "test" / "x0.svg", 99)
    (d / "train" / "empty.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"/>')
    (d / "train" / "broken.svg").write_text("<svg")
    info = prepare([d / "train"], d / "out", [d / "test"], seed=0)
    return d / "out", info


def test_prepare_counts_and_splits(fpc):
    out, info = fpc
    assert info["read"] == 9 and info["kept"] == 7 and info["failed"] == 1 and info["skipped_no_wall"] == 1
    assert info["with_stairs"] == 7 and info["with_lift"] == 4 and info["with_escalator"] == 0
    assert info["splits"]["test"] == 1
    train = (out / "train.txt").read_text().split()
    assert len(train) == 3 * len(set(train))  # tiles with a stair or lift are listed three times


def test_masks_are_partial_and_aligned(fpc):
    out, _ = fpc
    m = cv2.imread(str(out / "masks" / "fpc_t_t0.png"), cv2.IMREAD_UNCHANGED)
    img = cv2.imread(str(out / "images" / "fpc_t_t0.png"), cv2.IMREAD_GRAYSCALE)
    assert m.shape == img.shape and set(np.unique(m)) == {WALL, STAIRS, LIFT, OPEN, IGNORE}
    k = m.shape[0] / 100.0
    o = np.random.default_rng(0).uniform(0, 4)  # fake_tile's vertical offset for seed 0

    def at(x, y):
        return int(m[int(round((y + o) * k)), int(round(x * k))])

    assert at(27, 27) == STAIRS and at(66, 26) == LIFT
    assert at(50, 10.8) == WALL  # between the two strokes of the double-line wall: closed into a band
    assert at(50, 45) == OPEN  # empty floor: known not to be a wall, use unknown
    assert at(80, 48) == IGNORE  # furniture
    assert int(m[int(round(80 * k)), int(round(50 * k))]) == IGNORE  # unlabelled dimension line
    # the drawing has dark ink where the stair treads are
    ys, xs = np.nonzero(m == STAIRS)
    assert img[ys, xs].min() < 120


def test_escalator_and_plain_elements():
    els = [
        {"pts": [(10, 10), (30, 10), (30, 20), (10, 20), (10, 10)], "sem": 30, "inst": 5, "width": 0.1},
        {"pts": [(0, 50), (100, 50)], "sem": 33, "inst": -1, "width": 0.1},
        {"pts": [(0, 51.5), (100, 51.5)], "sem": 33, "inst": -1, "width": 0.1},
    ]
    _, m = rasterize(els, (0, 0, 100, 100), 400, np.random.default_rng(0))
    assert m[60, 80] == ESCALATOR and m[203, 200] == WALL and m[300, 200] == OPEN


def test_path_reader_handles_arcs_relative_moves_and_curves(tmp_path):
    (a,) = path_polylines("M 0,0 A 10,10 0 0 1 10,10")
    assert a[0] == (0, 0) and a[-1] == pytest.approx((10, 10)) and len(a) > 5
    mid = a[len(a) // 2]
    assert np.hypot(mid[0] - 0, mid[1] - 10) == pytest.approx(10, abs=0.2)  # on the circle centred at (0, 10)
    r = path_polylines("m 5,5 l 10,0 v 5 h -10 z M 50 50 C 50 60 60 60 60 50")
    assert r[0][:4] == [(5, 5), (15, 5), (15, 10), (5, 10)] and r[0][-1] == (5, 5)
    assert r[1][0] == (50, 50) and r[1][-1] == pytest.approx((60, 50))
    f = tmp_path / "e.svg"
    f.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
        '<line x1="0" y1="0" x2="5" y2="5" semantic-id="33"/><circle cx="9" cy="9" r="2" semantic-id="29" '
        'instance-id="7"/><rect x="1" y="1" width="2" height="2"/><polyline points="0,0 1,1 2,0"/></svg>'
    )
    els, vb = read_svg(f)
    assert vb == (0.0, 0.0, 200.0, 100.0)
    assert [(e["sem"], e["inst"]) for e in els] == [(33, -1), (29, 7), (0, -1), (0, -1)]
