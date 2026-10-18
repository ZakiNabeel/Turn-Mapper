"""Real-floor evaluation against Studio-corrected ground truth (docs/ML_IMPROVEMENT_PLAN.md phase F).

Ground truth: a floor JSON saved by TURN Studio after a person corrected it (rooms, doors, places, graph), in
the same image frame as the plan. Any segmenter's automatic map of the same plan image is compared with it:

- rooms: matched by polygon IoU ≥ 0.5 → recall / precision
- doors: matched by centre distance ≤ 0.75 m → recall / precision
- places: share of ground-truth places whose room was found (matched room) → place recall
- routes: share of ground-truth place pairs (up to 50) that are connected in the automatic graph, between the
  nodes nearest to the ground-truth place nodes; plus the median ratio of automatic to true route length
- wall crossings: automatic graph edges whose segment crosses a ground-truth room boundary more than twice
  (a cheap proxy; true walls are the room outlines)

Usage:
    python eval/evaluate_real.py --truth gt/A-F1.floor.json --pred runs/x/floors/A-F1.json
The FAST A block is a frozen test set (ADR-009): run each method on it once, never tune on it.
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import networkx as nx
import numpy as np
from shapely.geometry import LineString, Point, Polygon


def _poly(r: dict) -> Polygon:
    p = Polygon(r["polygon"])
    return p if p.is_valid else p.buffer(0)


def _graph(fd: dict) -> tuple[nx.Graph, dict]:
    nodes = {n["id"]: (n["x"], n["y"]) for n in fd["graph"]["nodes"]}
    g = nx.Graph()
    g.add_nodes_from(nodes)
    for e in fd["graph"]["edges"]:
        if e["from"] in nodes and e["to"] in nodes:
            g.add_edge(e["from"], e["to"], w=float(np.hypot(*np.subtract(nodes[e["from"]], nodes[e["to"]]))))
    return g, nodes


def to_pixels(fd: dict) -> dict:
    """Same floor with every coordinate in image pixels (truth and prediction may use different scales)."""
    import copy

    s = float(fd["transform"]["scale_m_per_px"])
    out = copy.deepcopy(fd)
    for r in out["rooms"]:
        r["polygon"] = [[x / s, y / s] for x, y in r["polygon"]]
    for d in out["doors"]:
        d["a"] = [v / s for v in d["a"]]
        d["b"] = [v / s for v in d["b"]]
    for n in out["graph"]["nodes"]:
        n["x"], n["y"] = n["x"] / s, n["y"] / s
    out["_px_per_m"] = 1.0 / s
    return out


def compare(truth: dict, pred: dict) -> dict:
    """Both floors in metres of their own scale; compared in the truth's metres via the image pixel frame."""
    k = float(truth["transform"]["scale_m_per_px"])  # truth metres per pixel
    truth, pred = to_pixels(truth), to_pixels(pred)
    for fd in (truth, pred):  # back to metres, all at the truth's scale
        for r in fd["rooms"]:
            r["polygon"] = [[x * k, y * k] for x, y in r["polygon"]]
        for d in fd["doors"]:
            d["a"] = [v * k for v in d["a"]]
            d["b"] = [v * k for v in d["b"]]
        for n in fd["graph"]["nodes"]:
            n["x"], n["y"] = n["x"] * k, n["y"] * k
    tr = [(r["id"], _poly(r)) for r in truth["rooms"]]
    pr = [(r["id"], _poly(r)) for r in pred["rooms"]]
    match, used = {}, set()
    for tid, tp in tr:
        best, bid = 0.0, None
        for pid, pp in pr:
            if pid in used or not tp.intersects(pp):
                continue
            iou = tp.intersection(pp).area / max(tp.union(pp).area, 1e-9)
            if iou > best:
                best, bid = iou, pid
        if best >= 0.5:
            match[tid] = bid
            used.add(bid)

    def centre(d):
        return np.array([(d["a"][0] + d["b"][0]) / 2, (d["a"][1] + d["b"][1]) / 2])

    td, pd = [centre(d) for d in truth["doors"]], [centre(d) for d in pred["doors"]]
    hit_t = sum(any(np.linalg.norm(a - b) <= 0.75 for b in pd) for a in td)
    hit_p = sum(any(np.linalg.norm(a - b) <= 0.75 for a in td) for b in pd)

    places = [p for p in truth["pois"] if p.get("room_id")]
    place_hit = sum(1 for p in places if p["room_id"] in match)

    gt_g, gt_n = _graph(truth)
    pg, pn = _graph(pred)
    pts = {p["id"]: gt_n[p["node_id"]] for p in truth["pois"] if p["node_id"] in gt_n}
    ids = sorted(pts)
    pairs = list(itertools.combinations(ids, 2))
    if len(pairs) > 50:
        rng = np.random.default_rng(0)
        pairs = [pairs[i] for i in rng.choice(len(pairs), 50, replace=False)]

    def nearest(xy):
        if not pn:
            return None, np.inf
        k = min(pn, key=lambda n: np.hypot(pn[n][0] - xy[0], pn[n][1] - xy[1]))
        return k, float(np.hypot(pn[k][0] - xy[0], pn[k][1] - xy[1]))

    ok, ratios = 0, []
    for a, b in pairs:
        na, da = nearest(pts[a])
        nb, db = nearest(pts[b])
        if na is None or nb is None or max(da, db) > 2.0 or not nx.has_path(pg, na, nb):
            continue
        ok += 1
        ga = next(p["node_id"] for p in truth["pois"] if p["id"] == a)
        gb = next(p["node_id"] for p in truth["pois"] if p["id"] == b)
        if nx.has_path(gt_g, ga, gb):
            lt = nx.shortest_path_length(gt_g, ga, gb, weight="w")
            lp = nx.shortest_path_length(pg, na, nb, weight="w")
            if lt > 0:
                ratios.append(lp / lt)

    bounds = [tp.exterior for _, tp in tr]
    cross = 0
    for e in pred["graph"]["edges"]:
        if e["from"] not in pn or e["to"] not in pn:
            continue
        seg = LineString([pn[e["from"]], pn[e["to"]]])
        hits = 0
        for b in bounds:
            x = seg.intersection(b)
            hits += 0 if x.is_empty else len(getattr(x, "geoms", [x]))
        if hits > 2:
            cross += 1
    _ = Point  # kept for callers extending the metric set
    return {
        "room_recall": round(len(match) / max(len(tr), 1), 3),
        "room_precision": round(len(match) / max(len(pr), 1), 3),
        "door_recall": round(hit_t / max(len(td), 1), 3),
        "door_precision": round(hit_p / max(len(pd), 1), 3),
        "place_recall": round(place_hit / max(len(places), 1), 3),
        "routes": round(ok / len(pairs), 3) if pairs else None,
        "route_ratio_median": round(float(np.median(ratios)), 3) if ratios else None,
        "wall_crossings": cross,
        "n_rooms_truth": len(tr),
        "n_rooms_pred": len(pr),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", required=True)
    ap.add_argument("--pred", required=True)
    args = ap.parse_args()
    t = json.loads(Path(args.truth).read_text())
    p = json.loads(Path(args.pred).read_text())
    print(json.dumps(compare(t, p), indent=1))


if __name__ == "__main__":
    main()
