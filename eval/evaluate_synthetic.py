"""Level B/C evaluation (docs/EVALUATION_PROTOCOL.md) on synthetic plans, where the ground truth is exact.

For every layout x drawing style it runs the pipeline and compares the output (metres) with the truth:

  walkable IoU      area overlap of the predicted walkable area with the true one
  room P / R        rooms matched at IoU >= 0.5
  label acc         matched rooms whose OCR label equals the true label
  door P / R        predicted door centres within 0.75 m of a true door centre
  scale err %       estimated m/px vs true m/px
  route found       fraction of destination pairs connected in the graph
  route ratio       predicted route length / true shortest walking distance (median)
  wall crossings    route edges that pass through a true wall (must be 0)

    python eval/evaluate_synthetic.py --out runs/eval_synth [--segmenter classical]

Writes <out>/metrics.json and <out>/METRICS.md. Every number in docs comes from this script.
"""

from __future__ import annotations

import argparse
import itertools
import json
import time
from pathlib import Path

import cv2
import networkx as nx
import numpy as np
from skimage.graph import MCP_Geometric

from turn_mapper.api import convert
from turn_mapper.synthetic import DOOR_M, PX_PER_M, STYLES, _px, make_plan, render_style

TRUE_M_PER_PX = 1.0 / PX_PER_M


def truth(plan, style):
    g = plan.rgb[:, :, 0]
    h, w = g.shape
    ox, oy = plan.extra["origin_px"]
    walk = ((g != 191) & (g != 255)).astype(np.uint8)
    wall = (g == 191).astype(np.uint8)
    rooms = {}
    for r in plan.rooms:
        m = np.zeros((h, w), np.uint8)
        m[oy + _px(r.y0) : oy + _px(r.y1), ox + _px(r.x0) : ox + _px(r.x1)] = 1
        rooms[r.label] = m & walk
    doors = {}
    for r in plan.rooms:
        if not r.door:
            continue
        side, off = r.door
        if side in ("top", "bottom"):
            c = (ox + _px(r.x0 + off + DOOR_M / 2), oy + _px(r.y0 if side == "top" else r.y1))
        else:
            c = (ox + _px(r.x0 if side == "left" else r.x1), oy + _px(r.y0 + off + DOOR_M / 2))
        doors[r.label] = np.array(c, float)
    M = None
    if style == "scanned":  # the scanned style is rotated 1.5 deg about the centre: rotate the truth too
        M = cv2.getRotationMatrix2D((w / 2, h / 2), 1.5, 1.0)
        warp = lambda m: cv2.warpAffine(m, M, (w, h), flags=cv2.INTER_NEAREST)  # noqa: E731
        walk, wall = warp(walk), warp(wall)
        rooms = {k: warp(v) for k, v in rooms.items()}
        doors = {k: M @ np.r_[v, 1.0] for k, v in doors.items()}
    return walk.astype(bool), wall.astype(bool), {k: v.astype(bool) for k, v in rooms.items()}, doors


def raster(polys_m, s, shape):
    m = np.zeros(shape, np.uint8)
    for poly in polys_m:
        pts = np.round(np.array(poly) / s).astype(np.int32)
        cv2.fillPoly(m, [pts], 1)
    return m.astype(bool)


def iou(a, b):
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 0.0


def evaluate(plan, style, fd):
    s = fd["transform"]["scale_m_per_px"]
    walk_t, wall_t, rooms_t, doors_t = truth(plan, style)
    shape = walk_t.shape
    wk = fd["walkable"]
    polys = [ring for poly in wk["coordinates"] for ring in poly[:1]] if wk["type"] == "MultiPolygon" else []
    walk_p = raster(polys, s, shape)
    for poly in wk["coordinates"]:  # cut holes
        for hole in poly[1:]:
            walk_p &= ~raster([hole], s, shape)
    rooms_any_t = np.zeros(shape, bool)
    for m_t in rooms_t.values():
        rooms_any_t |= m_t
    corr_t = walk_t & ~rooms_any_t
    rooms_any_p = raster([r["polygon"] for r in fd["rooms"]], s, shape)
    # walkable in the package = circulation (corridors + door openings); rooms are separate polygons
    out = {
        "free_space_iou": round(iou(walk_p | rooms_any_p, walk_t), 3),
        "corridor_iou": round(iou(walk_p, corr_t), 3),
    }

    # rooms: greedy one-to-one matching at IoU >= 0.5
    pred_rooms = [(r, raster([r["polygon"]], s, shape)) for r in fd["rooms"]]
    used, matched, label_ok, match_of = set(), 0, 0, {}
    for lbl, m_t in rooms_t.items():
        best, bi = 0.0, None
        for i, (_, m_p) in enumerate(pred_rooms):
            if i not in used:
                v = iou(m_p, m_t)
                if v > best:
                    best, bi = v, i
        if bi is not None and best >= 0.5:
            used.add(bi)
            match_of[lbl] = pred_rooms[bi][0]["id"]
            matched += 1
            label_ok += pred_rooms[bi][0].get("label") == lbl
    out.update(
        room_precision=round(matched / max(len(pred_rooms), 1), 3),
        room_recall=round(matched / len(rooms_t), 3),
        label_acc=round(label_ok / max(matched, 1), 3),
    )

    # doors: centre within 0.75 m (true metres)
    tol_px = 0.75 / TRUE_M_PER_PX
    pc = [(np.array(d["a"]) + np.array(d["b"])) / 2 / s for d in fd["doors"]]
    tc = list(doors_t.values())
    hit_t = sum(any(np.linalg.norm(p - t) <= tol_px for p in pc) for t in tc)
    hit_p = sum(any(np.linalg.norm(p - t) <= tol_px for t in tc) for p in pc)
    out.update(
        door_precision=round(hit_p / max(len(pc), 1), 3),
        door_recall=round(hit_t / max(len(tc), 1), 3),
        scale_err_pct=round(100 * (s - TRUE_M_PER_PX) / TRUE_M_PER_PX, 1),
    )

    # routes between destinations (POIs whose label is a true room with a door)
    G = nx.Graph()
    nodes = {n["id"]: np.array([n["x"], n["y"]]) / s for n in fd["graph"]["nodes"]}
    for e in fd["graph"]["edges"]:
        G.add_edge(e["from"], e["to"], w=float(np.linalg.norm(nodes[e["from"]] - nodes[e["to"]])))
    # destinations: the POI of the predicted room matched to each true room (independent of OCR labels)
    poi_by_room = {p["room_id"]: p["node_id"] for p in fd["pois"] if p.get("room_id")}
    poi = {lbl: poi_by_room[rid] for lbl, rid in match_of.items() if lbl in doors_t and rid in poi_by_room}
    cost = np.where(walk_t, 1.0, np.inf)
    found, ratios, pairs = 0, [], list(itertools.combinations(sorted(doors_t), 2))
    for a, b in pairs:
        if a not in poi or b not in poi or not nx.has_path(G, poi[a], poi[b]):
            continue
        found += 1
        path = nx.shortest_path(G, poi[a], poi[b], weight="w")
        lp = sum(G[u][v]["w"] for u, v in itertools.pairwise(path))
        mcp = MCP_Geometric(cost)
        ta, tb = doors_t[a][::-1].round().astype(int), doors_t[b][::-1].round().astype(int)
        dist, _ = mcp.find_costs([tuple(ta)], [tuple(tb)])
        lt = dist[tuple(tb)]
        if np.isfinite(lt) and lt > 0:
            ratios.append(lp / lt)
    crossings = 0
    for e in fd["graph"]["edges"]:
        p, q = nodes[e["from"]], nodes[e["to"]]
        n = max(int(np.linalg.norm(q - p)), 2)
        pts = (p[None] + (q - p)[None] * np.linspace(0.1, 0.9, n)[:, None]).round().astype(int)
        pts = pts[(pts[:, 0] >= 0) & (pts[:, 1] >= 0) & (pts[:, 0] < shape[1]) & (pts[:, 1] < shape[0])]
        # a crossing = the edge runs through >= 3 consecutive true-wall pixels (a door gap is not a wall)
        on = wall_t[pts[:, 1], pts[:, 0]].astype(int)
        run = max((len(list(g)) for k, g in itertools.groupby(on) if k), default=0)
        crossings += run >= 3
    out.update(
        route_found=round(found / max(len(pairs), 1), 3),
        route_ratio_median=round(float(np.median(ratios)), 3) if ratios else None,
        wall_crossing_edges=int(crossings),
        n_pairs=len(pairs),
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="runs/eval_synth")
    ap.add_argument("--segmenter", default="classical")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for variant in ("basic", "lshape"):
        plan = make_plan(variant)
        for style in STYLES:
            p = out / f"{variant}_{style}.png"
            cv2.imwrite(str(p), cv2.cvtColor(render_style(plan, style), cv2.COLOR_RGB2BGR))
            t0 = time.time()
            res = convert(str(p), out_dir=str(out / f"{variant}_{style}"), method=args.segmenter, force=True)
            secs = time.time() - t0
            fd = json.loads((out / f"{variant}_{style}" / "floors" / "F1.json").read_text())
            m = evaluate(plan, style, fd)
            m.update(layout=variant, style=style, valid=bool(res.floors[0]["passed"]), seconds=round(secs, 1))
            rows.append(m)
            print(json.dumps(m), flush=True)
    (out / "metrics.json").write_text(json.dumps(rows, indent=1))
    cols = [
        ("layout", "layout"),
        ("style", "style"),
        ("valid", "valid"),
        ("free_space_iou", "free-space IoU"),
        ("corridor_iou", "corridor IoU"),
        ("room_precision", "room P"),
        ("room_recall", "room R"),
        ("label_acc", "label acc"),
        ("door_precision", "door P"),
        ("door_recall", "door R"),
        ("scale_err_pct", "scale err %"),
        ("route_found", "routes found"),
        ("route_ratio_median", "route/true"),
        ("wall_crossing_edges", "wall crossings"),
        ("seconds", "s"),
    ]
    lines = ["| " + " | ".join(c[1] for c in cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        lines.append("| " + " | ".join(str(r[c[0]]) for c in cols) + " |")
    num = [c[0] for c in cols[3:-1] if c[0] != "valid"]
    # mean of |scale error| (signed errors would cancel out)
    mean = {
        k: np.mean(
            [abs(r[k]) if k == "scale_err_pct" else r[k] for r in rows if isinstance(r[k], int | float)]
        )
        for k in num
    }
    lines.append(
        "| **mean** | | "
        + f"{sum(r['valid'] for r in rows)}/{len(rows)} | "
        + " | ".join(f"{mean[k]:.3f}" for k in num)
        + " | |"
    )
    lines.append(f"\nsegmenter: {args.segmenter}; command: `python eval/evaluate_synthetic.py --out {out}`")
    (out / "METRICS.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
