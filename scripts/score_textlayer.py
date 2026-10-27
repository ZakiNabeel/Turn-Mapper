"""Objective score for vector-PDF plans without annotation: the room numbers printed in the PDF text layer.

Every printed room number is a point inside its room, so it can check a map automatically:

- ``separated``: the number lies in a space the map calls a room, and that space holds no other printed number
  (the room was split off from its neighbours and the corridor)
- ``reachable``: that room is a destination attached to the main route graph
- ``named``: the destination carries that number as its label

    python scripts/score_textlayer.py RUN_DIR PLAN.pdf            # RUN_DIR = convert() output for one plan
    python scripts/score_textlayer.py --batch RUNS_DIR INPUT_DIR  # every RUNS_DIR/<id> with floors/F1.json

Numbers in title blocks or legends also count, so scores are a lower bound; they are identical across
pipeline variants, so comparisons between variants are fair.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import networkx as nx
from shapely.geometry import Point, Polygon

ROOM_NO = re.compile(r"^(?:[A-Z]{1,3}[-.]?)?\d{2,4}(?:\.\d)?[A-Z]?$")


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def printed_numbers(pdf: Path, page: int = 0) -> tuple[list[tuple[str, float, float]], float]:
    import pymupdf

    pg = pymupdf.open(str(pdf))[page]
    words = []
    for w in pg.get_text("words"):
        t = w[4].strip().upper()
        if ROOM_NO.match(t) and not re.fullmatch(r"(19|20)\d\d", t):
            words.append((norm(t), (w[0] + w[2]) / 2, (w[1] + w[3]) / 2, w[3] - w[1]))
    # numbers stacked on one spot (two numbering systems, or a number repeated on two layers) are one label
    words.sort(key=lambda w: -w[3])
    out: list[tuple[str, float, float]] = []
    kept: list[tuple[float, float, float]] = []
    for t, x, y, h in words:
        if any(abs(x - kx) < 1.5 * kh and abs(y - ky) < 1.5 * kh for kx, ky, kh in kept):
            continue
        kept.append((x, y, h))
        out.append((t, x, y))
    return out, pg.rect.width


def score(run_dir: Path, pdf: Path) -> dict | None:
    fd = json.loads((run_dir / "floors" / "F1.json").read_text())
    pts, page_w = printed_numbers(pdf)
    if len(pts) < 10:
        return None
    s_img = fd["image"]["width_px"] / page_w  # px per pt (whole page rendered)
    m = fd["transform"]["scale_m_per_px"]
    rooms = [(r["id"], Polygon(r["polygon"]).buffer(0)) for r in fd["rooms"] if len(r["polygon"]) >= 3]
    g = nx.Graph()
    g.add_nodes_from(n["id"] for n in fd["graph"]["nodes"])
    g.add_edges_from((e["from"], e["to"]) for e in fd["graph"]["edges"])
    main = max(nx.connected_components(g), key=len) if len(g) else set()
    poi_by_room = {p["room_id"]: p for p in fd["pois"] if p.get("room_id")}
    hits = []
    for t, x, y in pts:
        q = Point(x * s_img * m, y * s_img * m)
        # exported room outlines carry no holes, so a ring-shaped space contains the rooms it surrounds;
        # the smallest outline that contains the point is the space the point is in
        inside = [(poly.area, rid) for rid, poly in rooms if poly.is_valid and poly.contains(q)]
        rid = min(inside)[1] if inside else None
        hits.append((t, rid))
    count: dict = {}
    for _, rid in hits:
        if rid:
            count[rid] = count.get(rid, 0) + 1
    sep = reach = named = 0
    for t, rid in hits:
        if not rid or count[rid] != 1:
            continue
        sep += 1
        p = poi_by_room.get(rid)
        if p and p["node_id"] in main:
            reach += 1
            if p.get("label") and norm(p["label"]) == t:
                named += 1
    n = len(hits)
    return {
        "printed": n,
        "separated": round(sep / n, 3),
        "reachable": round(reach / n, 3),
        "named": round(named / n, 3),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--batch", action="store_true")
    a = ap.parse_args()
    if not a.batch:
        print(json.dumps(score(Path(a.a), Path(a.b))))
        return
    rows = {}
    for d in sorted(Path(a.a).iterdir()):
        pdf = Path(a.b) / f"{d.name}.pdf"
        if (d / "floors" / "F1.json").exists() and pdf.exists():
            r = score(d, pdf)
            if r:
                rows[d.name] = r
    for k, r in rows.items():
        print(
            f"{k:14s} n={r['printed']:4d} separated={r['separated']:.3f}"
            f" reachable={r['reachable']:.3f} named={r['named']:.3f}"
        )
    if rows:
        mean = {
            k: round(sum(r[k] for r in rows.values()) / len(rows), 3)
            for k in ("separated", "reachable", "named")
        }
        print("MEAN", json.dumps(mean), f"over {len(rows)} plans")
    (Path(a.a) / "textlayer_scores.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
