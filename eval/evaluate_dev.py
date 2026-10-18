"""Dev-set evaluation for tuning segmenter options (docs/ML_IMPROVEMENT_PLAN.md phase C).

Floors come from the procedural institutional generator with seed 2026, which was never used for training
(training used seeds 0 and 1). Each floor is drawn in one of the 8 training styles and scored against exact
ground truth from the generator's mask:

- rooms: generator ROOM components ≥ 2 m², matched to predicted rooms by pixel IoU ≥ 0.5 → recall / precision
- doors: generator DOOR components, matched to predicted door centres within 0.75 m → recall / precision
- routes: share of pairs of matched rooms (up to 30) connected in the navigation graph
- wall crossings: graph edges whose straight line runs more than 1 m through generator walls

The scale is given (the dev set measures segmentation and geometry, not scale estimation).

Usage:
    python eval/evaluate_dev.py --segmenter learned --params '{"learned_doors": true}' --n 24 --out runs/dev
The 12 synthetic cases (eval/evaluate_synthetic.py) and the FAST A block are test sets: never tune on them.
"""

from __future__ import annotations

import argparse
import itertools
import json
import time
from dataclasses import replace
from pathlib import Path

import cv2
import networkx as nx
import numpy as np

from turn_mapper.api import process_floor
from turn_mapper.config import single_image_config
from turn_mapper.learned.classes import DOOR, ROOM, WALL
from turn_mapper.learned.institutional import generate
from turn_mapper.learned.styles import STYLES, render, thicken_walls

DEV_SEED = 2026
M_PER_PX = 0.04


def make_dev(n: int, out: Path) -> list[dict]:
    rng = np.random.default_rng(DEV_SEED)
    out.mkdir(parents=True, exist_ok=True)
    items = []
    for i in range(n):
        mask, ex = generate(rng, M_PER_PX)
        style = STYLES[i % len(STYLES)]
        if style == "doubleline":
            mask = thicken_walls(mask, rng)
        img = render(mask, ex, style, rng)
        p = out / f"dev{i:03d}_{style}.png"
        cv2.imwrite(str(p), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
        np.save(out / f"dev{i:03d}_mask.npy", mask)
        items.append({"id": i, "style": style, "image": str(p), "mask": str(out / f"dev{i:03d}_mask.npy")})
    return items


def score(fr, mask: np.ndarray) -> dict:
    s = M_PER_PX
    # rooms
    n, lab, st, _ = cv2.connectedComponentsWithStats((mask == ROOM).astype(np.uint8), connectivity=4)
    gt_rooms = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] * s * s >= 2.0]
    pred = [r for r in fr.geom.regions if r.kind == "room"]
    pm = fr.geom.debug["region_masks"]
    matched_gt, matched_pred, room_of_gt = set(), set(), {}
    for gi in gt_rooms:
        g = lab == gi
        best, bj = 0.0, None
        for r in pred:
            m = pm[r.id]
            inter = int((g & m).sum())
            if not inter:
                continue
            iou = inter / int((g | m).sum())
            if iou > best:
                best, bj = iou, r.id
        if best >= 0.5 and bj not in matched_pred:
            matched_gt.add(gi)
            matched_pred.add(bj)
            room_of_gt[gi] = bj
    # doors
    nd, dlab, dst, dcen = cv2.connectedComponentsWithStats((mask == DOOR).astype(np.uint8), connectivity=8)
    gt_d = [dcen[i] for i in range(1, nd) if dst[i, cv2.CC_STAT_AREA] >= 4]
    pr_d = [np.array([d.center.x, d.center.y]) for d in fr.geom.doors]
    tol = 0.75 / s
    hit_t = sum(any(np.linalg.norm(c - p) <= tol for p in pr_d) for c in gt_d)
    hit_p = sum(any(np.linalg.norm(c - p) <= tol for c in gt_d) for p in pr_d)
    # routes between matched rooms, via their POI node
    G = nx.Graph()
    G.add_nodes_from(fr.graph.nodes)
    for e in fr.graph.edges:
        G.add_edge(e.a, e.b)
    poi_room = {p.room_id: p.node_id for p in fr.pois if p.room_id}
    targets = [poi_room[r] for r in room_of_gt.values() if r in poi_room]
    pairs = list(itertools.combinations(targets, 2))
    rng = np.random.default_rng(0)
    if len(pairs) > 30:
        pairs = [pairs[i] for i in rng.choice(len(pairs), 30, replace=False)]
    ok = sum(1 for a, b in pairs if a in G and b in G and nx.has_path(G, a, b))
    # wall crossings against generator walls
    wall = mask == WALL
    cross = 0
    for e in fr.graph.edges:
        a, b = fr.graph.nodes[e.a], fr.graph.nodes[e.b]
        k = max(2, int(np.hypot(a.x - b.x, a.y - b.y)))
        xs = np.clip(np.linspace(a.x, b.x, k).round().astype(int), 0, wall.shape[1] - 1)
        ys = np.clip(np.linspace(a.y, b.y, k).round().astype(int), 0, wall.shape[0] - 1)
        if wall[ys, xs].sum() * s > 1.0:
            cross += 1
    return {
        "room_recall": round(len(matched_gt) / max(len(gt_rooms), 1), 3),
        "room_precision": round(len(matched_pred) / max(len(pred), 1), 3),
        "door_recall": round(hit_t / max(len(gt_d), 1), 3),
        "door_precision": round(hit_p / max(len(pr_d), 1), 3),
        "routes": round(ok / len(pairs), 3) if pairs else None,
        "wall_crossings": cross,
        "n_rooms_gt": len(gt_rooms),
        "n_rooms_pred": len(pred),
    }


def run(items: list[dict], segmenter: str, params: dict) -> list[dict]:
    rows = []
    for it in items:
        cfg = single_image_config(it["image"])
        spec = replace(cfg.floors[0], scale_evidence=[{"method": "cad_units", "m_per_px": M_PER_PX}])
        cfg = replace(cfg, floors=[spec], params=replace(cfg.params, **params))
        t0 = time.time()
        try:
            fr = process_floor(spec, cfg, segmenter)
            m = score(fr, np.load(it["mask"]))
        except Exception as e:  # a crash is a result too
            m = {"error": f"{type(e).__name__}: {e}"[:200]}
        m.update(id=it["id"], style=it["style"], seconds=round(time.time() - t0, 1))
        rows.append(m)
        print(json.dumps(m), flush=True)
    return rows


def summarise(rows: list[dict]) -> dict:
    ok = [r for r in rows if "error" not in r]
    keys = ["room_recall", "room_precision", "door_recall", "door_precision", "routes", "wall_crossings"]
    out = {k: round(float(np.mean([r[k] for r in ok if r.get(k) is not None])), 3) for k in keys if ok}
    out["errors"] = len(rows) - len(ok)

    def _m(vals):
        vals = [v for v in vals if v is not None]
        return round(float(np.mean(vals)), 3) if vals else None

    out["by_style"] = {
        st: {
            k: _m([r.get(k) for r in ok if r["style"] == st])
            for k in ("room_recall", "room_precision", "door_recall", "routes")
        }
        for st in sorted({r["style"] for r in ok})
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--segmenter", default="classical")
    ap.add_argument("--params", default="{}", help="JSON of PipelineParams overrides")
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--out", default="runs/dev")
    args = ap.parse_args()
    out = Path(args.out)
    items = make_dev(args.n, out / "data")
    params = json.loads(args.params)
    for k, v in list(params.items()):
        if isinstance(v, list):
            params[k] = tuple(v)
    rows = run(items, args.segmenter, params)
    summ = summarise(rows)
    (out / "dev_metrics.json").write_text(
        json.dumps(
            {"segmenter": args.segmenter, "params": args.params, "summary": summ, "rows": rows}, indent=1
        )
    )
    print("SUMMARY", json.dumps(summ))


if __name__ == "__main__":
    main()
