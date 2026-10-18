"""Run segmenters on Studio-corrected floors and compare each automatic map with the correction
(docs/ML_IMPROVEMENT_PLAN.md phase F).

A floor counts as ground truth when its Studio record status is "edited" (a person saved corrections). Each
method runs on the exact image Studio prepared for that floor (after crop/rotate/erase), so frames match.

    python scripts/eval_real_block.py --studio studio_projects/fast --floors A-GF A-F1 --methods hybrid
The FAST A block is a frozen test set: run once per method, never tune on it.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import cv2

from turn_mapper.api import process_floor
from turn_mapper.config import single_image_config
from turn_mapper.export import floor_to_dict

_spec = importlib.util.spec_from_file_location(
    "evaluate_real", Path(__file__).parents[1] / "eval/evaluate_real.py"
)
er = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(er)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--studio", required=True, help="a Studio project folder (studio_projects/<id>)")
    ap.add_argument("--floors", nargs="*", help="floor ids (default: every edited floor)")
    ap.add_argument("--methods", nargs="+", default=["classical", "learned", "hybrid"])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    proj = Path(args.studio)
    meta = json.loads((proj / "project.json").read_text())
    floors = [
        f
        for f in meta["floors"]
        if f.get("status") == "edited" and (not args.floors or f["id"] in args.floors)
    ]
    from turn_mapper.studio.project import Studio

    st = Studio(proj.parent)
    results = {}
    for rec in floors:
        fdir = st.fdir(meta["id"], rec["id"])
        truth = json.loads((fdir / "floor.json").read_text())
        img = fdir / "_eval_plan.png"
        cv2.imwrite(str(img), cv2.cvtColor(st.plan_rgb(meta["id"], rec["id"]), cv2.COLOR_RGB2BGR))
        for m in args.methods:
            cfg = single_image_config(str(img))
            try:
                pred = floor_to_dict(process_floor(cfg.floors[0], cfg, m))
                results.setdefault(rec["id"], {})[m] = er.compare(truth, pred)
            except Exception as e:
                results.setdefault(rec["id"], {})[m] = {"error": f"{type(e).__name__}: {e}"[:200]}
            print(rec["id"], m, json.dumps(results[rec["id"]][m]), flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
