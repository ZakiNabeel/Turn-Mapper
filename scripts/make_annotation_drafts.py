"""Draft ground truth for review: one TURN Studio project per plan, with the automatic map already run.

The team opens each project in Studio, corrects walls, doors, corridors and room names, and saves; the
corrected floor.json is then the reference for scoring (docs/DATA_AND_ANNOTATION.md, "Correcting a draft").
Plans stay where they are on disk and in the Studio folder (both gitignored); nothing is committed.

    python scripts/make_annotation_drafts.py PLANS_DIR SOURCES_TSV --studio studio_projects --set heldout
    python scripts/make_annotation_drafts.py samples/private --files fast_blocks.pdf:3 --studio studio_projects
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from turn_mapper.studio.project import Studio


def draft(studio: Studio, name: str, path: Path, page: int | None) -> dict:
    pid = studio.create_project(f"annotate {name}")["id"]
    studio.add_file(pid, path.name, path.read_bytes())
    body = {"source": path.name, "id": "F1", "name": name}
    if path.suffix.lower() == ".pdf":
        body["page"] = page or 1
    studio.add_floor(pid, body)
    studio.run(pid, "F1")
    rec = studio.floor(pid, "F1")
    return {"plan": name, "project": pid, "status": rec.get("status"), **rec.get("stats", {})}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("plans", help="folder holding the plan files")
    ap.add_argument("sources", nargs="?", help="sources.tsv (id, set, ...); plans are <id>.pdf / <id>.png")
    ap.add_argument("--studio", default="studio_projects")
    ap.add_argument("--set", default="heldout", help="rows of this set in sources.tsv (all: every row)")
    ap.add_argument("--files", default="", help="comma list of FILE[:PAGE] instead of sources.tsv")
    a = ap.parse_args()
    studio = Studio(a.studio)
    plans = Path(a.plans)
    todo: list[tuple[str, Path, int | None]] = []
    if a.files:
        for item in a.files.split(","):
            fname, _, page = item.partition(":")
            todo.append((Path(fname).stem + (f"_p{page}" if page else ""), plans / fname, int(page or 0) or None))
    else:
        rows = csv.DictReader(open(a.sources, encoding="utf-8"), delimiter="\t")
        seen = set()
        for r in rows:
            if r["id"] in seen or (a.set != "all" and r["set"] != a.set):
                continue
            seen.add(r["id"])
            hits = sorted(plans.glob(r["id"] + ".*"))
            if hits:
                todo.append((r["id"], hits[0], 1))  # downloaded plans are already cut to the floor's page
            else:
                print("MISSING", r["id"])
    for name, path, page in todo:
        try:
            print(json.dumps(draft(studio, name, path, page)), flush=True)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"plan": name, "error": repr(e)[:200]}), flush=True)


if __name__ == "__main__":
    main()
