"""Run TURN-Mapper on real public floor plans from other institutions and record what it produced.

    python scripts/eval_public_plans.py INPUT_DIR SOURCES_TSV --out runs/public_eval [--segmenter classical]

INPUT_DIR holds one file per plan as downloaded (<id>.pdf, or <id>.png for image plans). Each goes through
the normal input adapters (vector PDFs: page 1 rendered by the CAD-aware renderer, as in Studio), with one
generic venue config for all plans: room-number pattern GENERIC_LABEL and a render resolution capped at
MAX_SIDE_PX on the long side. Nothing is set per plan. For vector PDFs the text layer gives the room
numbers printed on the plan, used as a label reference (how many printed room numbers ended up as named
destinations in the map).

These plans have no annotated ground truth, so the numbers are what the pipeline produced (valid map,
counts, connectivity, routes, label recall vs printed numbers, runtime). Correctness of rooms/doors is
judged separately by looking at the overlays (see docs/RESULTS_PUBLIC_PLANS_*.md).
The plans themselves are third-party material: keep them out of the repository.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path

import networkx as nx

from turn_mapper.api import convert

ROOM_NO = re.compile(r"^(?:[A-Z]{1,3}[-.]?)?\d{2,4}(?:\.\d)?[A-Z]?$")
GENERIC_LABEL = r"\b(?:[A-Z]{1,3}[-.]?)?\d{2,4}(?:\.\d)?[A-Z]?\b"
MAX_SIDE_PX = 5000


def venue_yaml(path: Path, out: Path) -> Path:
    floor = {"id": "F1", "building": "B1", "level": 0, "file": str(path.resolve())}
    if path.suffix.lower() == ".pdf":
        import pymupdf

        r = pymupdf.open(str(path))[0].rect
        floor["page"] = 1
        floor["options"] = {"dpi": int(min(300, MAX_SIDE_PX * 72 / max(r.width, r.height)))}
    cfg = {
        "venue": {"id": path.stem, "name": path.stem},
        "label_patterns": {"B1": GENERIC_LABEL},
        "buildings": [{"id": "B1", "name": "Building"}],
        "floors": [floor],
    }
    out.mkdir(parents=True, exist_ok=True)
    y = out / "venue.yaml"
    y.write_text(json.dumps(cfg, indent=1))  # JSON is valid YAML
    return y


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def printed_room_numbers(raw: Path) -> set[str] | None:
    """Room-number tokens in a PDF's first-page text layer (None for images / no text)."""
    if raw.suffix.lower() != ".pdf":
        return None
    import pymupdf

    words = pymupdf.open(str(raw))[0].get_text("words")
    toks = {norm(w[4]) for w in words if ROOM_NO.match(w[4].strip().upper())}
    toks = {t for t in toks if not re.fullmatch(r"(19|20)\d\d", t)}  # years in title blocks
    return toks or None


def floor_metrics(fd: dict, summary: dict) -> dict:
    g = nx.Graph()
    g.add_nodes_from(n["id"] for n in fd["graph"]["nodes"])
    g.add_edges_from((e["from"], e["to"]) for e in fd["graph"]["edges"])
    pois = fd["pois"]
    comp = max(nx.connected_components(g), key=len) if len(g) else set()
    in_main = sum(p["node_id"] in comp for p in pois)
    routes = summary["routes"]
    ok_routes = sum(r[2] is not None for r in routes)
    codes = [e.get("code", "") for e in summary["errors"]]
    return {
        "valid": summary["passed"],
        "rooms": summary["n_rooms"],
        "doors": summary["n_doors"],
        "pois": summary["n_pois"],
        "labelled_pois": sum(bool(p.get("label")) for p in pois),
        "graph_nodes": summary["n_nodes"],
        "components": summary["n_components"],
        "pois_in_main_component": in_main,
        "routes_ok": ok_routes,
        "routes_tried": len(routes),
        "wall_crossings": sum("cross" in c.lower() for c in codes),
        "error_codes": codes,
        "scale_source": summary["scale_source"],
        "seconds": round(summary["seconds"], 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_dir")
    ap.add_argument("sources")
    ap.add_argument("--out", default="runs/public_eval")
    ap.add_argument("--segmenter", default="classical")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = {r["id"]: r for r in csv.DictReader(open(a.sources, encoding="utf-8"), delimiter="\t")}
    only = set(filter(None, a.only.split(",")))
    rows = []
    for src in sorted(p for p in Path(a.input_dir).iterdir() if p.suffix.lower() in (".pdf", ".png", ".jpg")):
        pid = src.stem
        if only and pid not in only:
            continue
        m = meta.get(pid, {})
        row = {
            "id": pid,
            "institution": m.get("institution", ""),
            "kind": m.get("kind", ""),
            "floor": m.get("floor", ""),
            "segmenter": a.segmenter,
        }
        t0 = time.perf_counter()
        try:
            y = venue_yaml(src, out / pid)
            res = convert(
                [str(src)], venue_config=str(y), out_dir=str(out / pid), method=a.segmenter, force=True
            )
            s = res.floors[0]
            fd = json.loads((out / pid / "floors" / f"{s['id']}.json").read_text())
            row.update(floor_metrics(fd, s))
            truth = printed_room_numbers(src)
            if truth:
                got = {norm(p["label"]) for p in fd["pois"] if p.get("label")}
                row["printed_room_numbers"] = len(truth)
                row["printed_found_as_destinations"] = len(truth & got)
                row["label_recall"] = round(len(truth & got) / len(truth), 3)
                row["labels_not_printed"] = len(got - truth)
            row["overlay"] = str(out / pid / "qa" / s["overlay"])
        except Exception as e:  # record the failure; it is a result too
            row.update({"valid": False, "crash": f"{type(e).__name__}: {e}"[:300]})
        row["wall_seconds"] = round(time.perf_counter() - t0, 2)
        rows.append(row)
        print(
            json.dumps(
                {
                    k: row.get(k)
                    for k in (
                        "id",
                        "valid",
                        "rooms",
                        "doors",
                        "pois",
                        "components",
                        "label_recall",
                        "wall_seconds",
                        "crash",
                    )
                }
            ),
            flush=True,
        )
    (out / f"results_{a.segmenter}.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
