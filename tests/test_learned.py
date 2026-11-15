"""ML plumbing, offline: CubiCasa SVG parsing -> masks -> 2 training iterations -> pipeline with the learned
segmenter. Checks that the path works end to end, not accuracy (that needs real GPU training)."""

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("segmentation_models_pytorch")


@pytest.fixture(scope="module")
def mask_ds(tmp_path_factory):
    from turn_mapper.learned.cubicasa import prepare
    from turn_mapper.learned.fake_cubicasa import make

    root = tmp_path_factory.mktemp("cc")
    make(root / "raw", styles=("greyfill", "blackwalls", "scanned"))
    stats = prepare(root / "raw", root / "masks")
    assert stats["failed"] == 0 and stats["train"] == 4 and stats["val"] == 2
    return root / "masks"


def test_svg_masks_match_drawing(mask_ds):
    import cv2

    from turn_mapper.learned.classes import DOOR, ROOM, WALKABLE, WALL
    from turn_mapper.synthetic import make_plan

    m = cv2.imread(str(mask_ds / "masks" / "synthetic_basic_greyfill.png"), cv2.IMREAD_UNCHANGED)
    g = make_plan("basic").rgb[:, :, 0]
    wall = g == 191
    iou = (wall & (m == WALL)).sum() / (wall | (m == WALL)).sum()
    assert iou > 0.75  # the group transform was applied (else everything is shifted by 5/7 px)
    assert (m == ROOM).sum() > (m == WALKABLE).sum() > 0
    assert (m == DOOR).sum() > 0


def test_train_and_run_learned(mask_ds, tmp_path, monkeypatch):
    import cv2

    from turn_mapper.api import convert
    from turn_mapper.learned.train import train
    from turn_mapper.synthetic import make_plan

    ck = tmp_path / "turn_seg.pt"
    r = train(
        [str(mask_ds)],
        str(ck),
        epochs=1,
        batch=2,
        crop=128,
        encoder="resnet18",
        encoder_weights=None,
        max_iters=2,
        val_items=1,
        workers=0,
        device="cpu",
    )
    assert ck.exists() and ck.with_suffix(".json").exists()
    assert r["log"][0]["mIoU"] is not None

    monkeypatch.setenv("TURN_SEG_WEIGHTS", str(ck))
    p = tmp_path / "plan.png"
    cv2.imwrite(str(p), cv2.cvtColor(make_plan("basic").rgb, cv2.COLOR_RGB2BGR))
    res = convert(str(p), out_dir=str(tmp_path / "out"), method="learned", force=True)
    assert res.floors[0]["id"] == "F1"  # an untrained net gives a poor map; the point is that it runs


def test_bootstrap_masks(tmp_path):
    import cv2

    from turn_mapper.api import process_floor
    from turn_mapper.config import single_image_config
    from turn_mapper.learned.annotate import export_dataset
    from turn_mapper.synthetic import make_plan

    p = tmp_path / "plan.png"
    cv2.imwrite(str(p), cv2.cvtColor(make_plan("basic").rgb, cv2.COLOR_RGB2BGR))
    cfg = single_image_config(str(p))
    export_dataset({"F1": process_floor(cfg.floors[0], cfg)}, tmp_path / "ds")
    m = cv2.imread(str(tmp_path / "ds" / "masks" / "F1.png"), cv2.IMREAD_UNCHANGED)
    assert set(np.unique(m)) >= {0, 1, 2, 3, 4}


def test_svg_size_attribute_does_not_rescale_labels(tmp_path):
    """Regression (Kaggle run 2026-10-12): the SVG width/height is the drawing's bounding box, not the
    image size. Labels must be painted at raw pixel coordinates of F1_scaled.png."""
    import cv2

    from turn_mapper.learned.classes import WALL
    from turn_mapper.learned.cubicasa import load_sample

    d = tmp_path / "s"
    d.mkdir()
    img = np.full((200, 300), 255, np.uint8)
    img[50:60, 40:240] = 30  # one dark wall
    cv2.imwrite(str(d / "F1_scaled.png"), img)
    (d / "model.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="250" height="120">'
        '<g id="Wall" class="Wall "><polygon points="40,50 240,50 240,60 40,60"/></g></svg>'
    )
    g, m = load_sample(d)
    assert g.shape == m.shape == (200, 300)
    wall = m == WALL
    assert wall.sum() > 0 and g[wall].mean() < 60  # labels sit on the dark wall


def test_open_space_loss_rewards_any_allowed_class():
    from turn_mapper.learned.classes import BG, CLASSES, OPEN, ROOM, WALKABLE, WALL
    from turn_mapper.learned.train import confusion, open_space_loss

    y = torch.full((1, 4, 4), OPEN, dtype=torch.long)

    def logits_for(c):
        z = torch.full((1, len(CLASSES), 4, 4), -8.0)
        z[:, c] = 8.0
        return z

    as_wall, as_room, as_corr = (float(open_space_loss(logits_for(c), y)) for c in (WALL, ROOM, WALKABLE))
    assert as_wall > 10 and as_room < 1e-3 and as_corr < 1e-3  # only "wall" (or a transition) is wrong
    assert float(open_space_loss(logits_for(WALL), torch.zeros((1, 4, 4), dtype=torch.long))) == 0.0
    # OPEN and IGNORE pixels are not scored
    gt = np.array([[OPEN, 255, WALL, BG]])
    assert confusion(np.array([[WALL, WALL, WALL, BG]]), gt).sum() == 2


def test_train_on_partial_floorplancad_masks(mask_ds, tmp_path):
    """Stage S4 plumbing: partial masks (OPEN / IGNORE) train together with full masks, without NaN."""
    from turn_mapper.learned.floorplancad import fake_tile, prepare
    from turn_mapper.learned.train import evaluate, train

    raw = tmp_path / "fpc_raw"
    raw.mkdir()
    for i in range(6):
        fake_tile(raw / f"t{i}.svg", i)
    info = prepare([raw], tmp_path / "fpc", [raw], limit=3)
    assert info["splits"]["test"] == 3
    ck = tmp_path / "s4.pt"
    r = train(
        [str(tmp_path / "fpc"), str(mask_ds)],
        str(ck),
        epochs=1,
        batch=2,
        crop=128,
        encoder="resnet18",
        encoder_weights=None,
        max_iters=4,
        val_items=1,
        workers=0,
        device="cpu",
    )
    assert ck.exists() and np.isfinite(r["log"][0]["loss"])
    # FloorPlanCAD-only batches (no fully labelled pixel in some crops) must also give a finite loss
    r2 = train(
        [str(tmp_path / "fpc")],
        str(tmp_path / "s4b.pt"),
        epochs=1,
        batch=2,
        crop=96,
        encoder="resnet18",
        encoder_weights=None,
        max_iters=3,
        val_items=1,
        workers=0,
        device="cpu",
    )
    assert np.isfinite(r2["log"][0]["loss"])
    from turn_mapper.learned.model import load_checkpoint

    model, _ = load_checkpoint(str(ck), "cpu")
    m = evaluate(model, [str(tmp_path / "fpc")], "test", "cpu", 128)
    assert set(m["per_class"]) >= {"wall", "stairs", "lift"} and m["per_class"]["room"] is None
