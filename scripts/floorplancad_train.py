"""Train the CAD line classifier (src/turn_mapper/primitives.py) on FloorPlanCAD.

FloorPlanCAD: about 15,000 CAD floor plans as SVG with a `semantic-id` on every drawn element
(Fan et al., ICCV 2021; annotations CC BY-NC 4.0, drawings not owned by the authors). Run on Kaggle
(notebooks/floorplancad_kaggle.ipynb); the data and the model stay out of git.

    python scripts/floorplancad_train.py --train DIR [DIR ...] --test DIR --out fpc_lines.joblib
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from turn_mapper.primitives import FEATURES, FPC_GROUP, GROUPS, features  # noqa: E402


def _num(v, default=1.0) -> float:
    try:
        return float(str(v).replace("px", ""))
    except (TypeError, ValueError):
        return default


def svg_segments(path: Path):
    """One SVG -> (segs (N,2,2), info (N,4), labels (N,)) with labels as GROUPS indices."""
    from svgpathtools import Arc, CubicBezier, Line, QuadraticBezier, svg2paths2

    paths, attrs, _ = svg2paths2(str(path))
    segs, info, labels = [], [], []
    for p, a in zip(paths, attrs, strict=False):
        sid = int(_num(a.get("semantic-id"), 0))
        group = GROUPS.index(FPC_GROUP.get(sid, "other"))
        width = _num(a.get("stroke-width"), 1.0)
        for s in p:
            p0, p1 = s.start, s.end
            if abs(p1 - p0) < 1e-9 and not isinstance(s, Arc):
                continue
            if isinstance(s, Line):
                segs.append([[p0.real, p0.imag], [p1.real, p1.imag]])
                info.append([0.0, width, 0.0, 0.0])
            elif isinstance(s, (Arc, CubicBezier, QuadraticBezier)):
                pm = s.point(0.5)
                ax, ay, bx, by, cx, cy = p0.real, p0.imag, pm.real, pm.imag, p1.real, p1.imag
                dd = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
                if abs(dd) < 1e-9:
                    segs.append([[ax, ay], [cx, cy]])
                    info.append([0.0, width, 0.0, 0.0])
                else:
                    a2, b2, c2 = ax**2 + ay**2, bx**2 + by**2, cx**2 + cy**2
                    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / dd
                    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / dd
                    r = math.hypot(ax - ux, ay - uy)
                    a0 = math.atan2(ay - uy, ax - ux)
                    am = math.atan2(by - uy, bx - ux)
                    a1 = math.atan2(cy - uy, cx - ux)
                    sweep = abs((am - a0 + math.pi) % (2 * math.pi) - math.pi) + abs(
                        (a1 - am + math.pi) % (2 * math.pi) - math.pi
                    )
                    segs.append([[ax, ay], [cx, cy]])
                    info.append([1.0, width, r, math.degrees(sweep)])
            else:
                continue
            labels.append(group)
    if not segs:
        return None
    return np.asarray(segs, float), np.asarray(info, float), np.asarray(labels, int)


def build(files: list[Path], cap_per_drawing: int, seed: int):
    rng = np.random.default_rng(seed)
    xs, ys = [], []
    t0 = time.time()
    for k, f in enumerate(files):
        try:
            r = svg_segments(f)
        except Exception as e:  # noqa: BLE001
            print("SKIP", f.name, repr(e)[:80])
            continue
        if r is None:
            continue
        segs, info, lab = r
        x = features(segs, info)
        if cap_per_drawing and len(x) > cap_per_drawing:
            idx = rng.choice(len(x), cap_per_drawing, replace=False)
            x, lab = x[idx], lab[idx]
        xs.append(x)
        ys.append(lab)
        if (k + 1) % 200 == 0:
            print(f"  {k + 1}/{len(files)} drawings, {time.time() - t0:.0f}s", flush=True)
    return np.vstack(xs), np.concatenate(ys)


def report(y, p) -> dict:
    out = {}
    for g in range(len(GROUPS)):
        tp = int(((p == g) & (y == g)).sum())
        prec = tp / max(int((p == g).sum()), 1)
        rec = tp / max(int((y == g).sum()), 1)
        n = int((y == g).sum())
        out[GROUPS[g]] = {"precision": round(prec, 3), "recall": round(rec, 3), "support": n}
    out["accuracy"] = round(float((p == y).mean()), 3)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", nargs="+", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--out", default="fpc_lines.joblib")
    ap.add_argument("--max-train", type=int, default=4000)
    ap.add_argument("--max-test", type=int, default=1000)
    ap.add_argument("--cap", type=int, default=3000, help="segments sampled per training drawing")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    import joblib
    from sklearn.ensemble import HistGradientBoostingClassifier

    random.seed(a.seed)
    train = sorted(f for d in a.train for f in Path(d).rglob("*.svg"))
    test = sorted(Path(a.test).rglob("*.svg"))
    random.shuffle(train)
    random.shuffle(test)
    train, test = train[: a.max_train], test[: a.max_test]
    print(f"TRAIN drawings {len(train)}  TEST drawings {len(test)}", flush=True)
    xtr, ytr = build(train, a.cap, a.seed)
    counts = {GROUPS[g]: int((ytr == g).sum()) for g in range(len(GROUPS))}
    print("TRAIN segments", len(ytr), counts, flush=True)
    model = HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.1, max_leaf_nodes=63, class_weight="balanced", random_state=a.seed
    )
    model.fit(xtr, ytr)
    model.turn_features = list(FEATURES)
    xte, yte = build(test, 0, a.seed)
    rep = report(yte, model.predict(xte))
    rep["train_drawings"], rep["test_drawings"], rep["test_segments"] = len(train), len(test), int(len(yte))
    print("TEST", json.dumps(rep), flush=True)
    joblib.dump(model, a.out)
    Path(a.out).with_suffix(".json").write_text(json.dumps(rep, indent=1))
    print("SAVED", a.out)


if __name__ == "__main__":
    main()
