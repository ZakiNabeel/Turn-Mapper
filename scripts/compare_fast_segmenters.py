"""Classical vs learned vs hybrid on a whole venue, without ground truth (map-quality proxies).

For each method the venue is converted once and every floor is reported with: passed validation, rooms, doors,
destinations, graph pieces, share of destinations on the main graph piece, map grade (route.floor_quality) and
the venue's cross-floor route checks. These are not accuracy numbers (no answer key): they show whether a
method makes routable maps. Accuracy against a person's corrections is `scripts/eval_real_block.py`.

    set TURN_SEG_WEIGHTS=C:\\path\\to\\turn_seg_s4.pt          (Windows; `export` on Linux/macOS)
    python scripts/compare_fast_segmenters.py samples/private/fast_blocks.pdf \\
        --venue configs/venues/fast_isb.yaml --out runs/compare_s4

Writes <out>/<method>/ (normal run output) and <out>/COMPARISON.md + comparison.json.
The FAST A block is the frozen test split (ADR-009): run once per model, never tune on it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import networkx as nx

from turn_mapper.api import convert, load_package
from turn_mapper.route import VenueGraph, venue_checks


def floor_row(fd: dict) -> dict:
    g = nx.Graph()
    g.add_nodes_from(n["id"] for n in fd["graph"]["nodes"])
    g.add_edges_from((e["from"], e["to"]) for e in fd["graph"]["edges"])
    comps = list(nx.connected_components(g)) if len(g) else []
    big = max(comps, key=len) if comps else set()
    pois = fd.get("pois", [])
    return {
        "valid": bool(fd.get("validation", {}).get("passed")),
        "rooms": len(fd.get("rooms", [])),
        "doors": len(fd.get("doors", [])),
        "destinations": len(pois),
        "pieces": len(comps),
        "reachable": round(sum(p["node_id"] in big for p in pois) / len(pois), 3) if pois else None,
    }


def run_method(plan: str, venue: str | None, out: Path, method: str, samples: int) -> dict:
    t0 = time.time()
    convert(plan, venue_config=venue, out_dir=str(out), method=method)
    secs = round(time.time() - t0, 1)
    pkg = load_package(str(out / "venue.json"))
    vc = venue_checks(VenueGraph.from_package(str(out / "venue.json")), samples=samples)
    floors = {}
    for fid, fd in pkg["floors"].items():
        r = floor_row(fd)
        r["grade"] = vc["floors"].get(fid, {}).get("quality", {}).get("grade")
        floors[fid] = r
    keys = (
        "floor_pairs_connected",
        "floor_pairs_total",
        "sampled_cross_floor_routes",
        "routed",
        "routed_step_free",
    )
    return {"seconds": secs, "floors": floors, "venue": {k: vc[k] for k in keys}}


def sha256(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def table(res: dict) -> str:
    methods = list(res["methods"])
    fids = sorted({f for m in methods for f in res["methods"][m]["floors"]})
    head = "| floor | " + " | ".join(methods) + " |"
    lines = [
        "Per floor: valid · rooms / doors / destinations · graph pieces · destinations reachable · grade",
        "",
        head,
        "|---|" + "---|" * len(methods),
    ]
    for fid in fids:
        cells = []
        for m in methods:
            r = res["methods"][m]["floors"].get(fid)
            if not r:
                cells.append("—")
                continue
            reach = "—" if r["reachable"] is None else f"{r['reachable']:.0%}"
            ok = "ok" if r["valid"] else "FAIL"
            cells.append(
                f"{ok} · {r['rooms']}/{r['doors']}/{r['destinations']} · {r['pieces']} · {reach} · "
                f"{r['grade']}"
            )
        lines.append(f"| {fid} | " + " | ".join(cells) + " |")
    lines += ["", "| venue | " + " | ".join(methods) + " |", "|---|" + "---|" * len(methods)]
    for label, fn in (
        ("floors valid", lambda v, f: f"{sum(x['valid'] for x in f.values())}/{len(f)}"),
        ("floor pairs connected", lambda v, f: f"{v['floor_pairs_connected']}/{v['floor_pairs_total']}"),
        ("cross-floor routes found", lambda v, f: f"{v['routed']}/{v['sampled_cross_floor_routes']}"),
        ("… step-free", lambda v, f: f"{v['routed_step_free']}/{v['sampled_cross_floor_routes']}"),
        ("rooms (sum)", lambda v, f: str(sum(x["rooms"] for x in f.values()))),
        ("doors (sum)", lambda v, f: str(sum(x["doors"] for x in f.values()))),
        (
            "floors graded ready/usable/needs work",
            lambda v, f: "/".join(
                str(sum(x["grade"] == g for x in f.values())) for g in ("ready", "usable", "needs work")
            ),
        ),
    ):
        cells = [fn(res["methods"][m]["venue"], res["methods"][m]["floors"]) for m in methods]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    secs = " · ".join(f"{m} {res['methods'][m]['seconds']} s" for m in methods)
    lines += [
        "",
        f"Run time: {secs}. Weights: {res.get('weights')} (sha256 {res.get('weights_sha256', '—')[:12]}…).",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan")
    ap.add_argument("--venue", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--methods", nargs="+", default=["classical", "learned", "hybrid"])
    ap.add_argument("--samples", type=int, default=200, help="sampled cross-floor routes per method")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    w = os.environ.get("TURN_SEG_WEIGHTS")
    if any(m != "classical" for m in a.methods) and not (w and Path(w).exists()):
        raise SystemExit("set TURN_SEG_WEIGHTS to the .pt file (learned and hybrid need it)")
    res = {"plan": a.plan, "venue": a.venue, "weights": w, "methods": {}}
    if w and Path(w).exists():
        res["weights_sha256"] = sha256(w)
    for m in a.methods:
        print(f"== {m}", flush=True)
        res["methods"][m] = run_method(a.plan, a.venue, out / m, m, a.samples)
    (out / "comparison.json").write_text(json.dumps(res, indent=1))
    (out / "COMPARISON.md").write_text(table(res))
    print(table(res))


if __name__ == "__main__":
    main()
