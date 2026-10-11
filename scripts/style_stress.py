"""Generality check: run the pipeline on the same known layouts drawn in different conventions and score
the result against ground truth (rooms, doors, destinations, labels, validity, scale).

    python scripts/style_stress.py [--out runs/style_stress] [--segmenter classical]

Writes a markdown table to <out>/RESULTS.md and the QA overlays per case.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

from turn_mapper.api import convert, load_package
from turn_mapper.synthetic import STYLES, make_plan, render_style


def score(plan, fd, summary) -> dict:
    rooms_true = len(plan.rooms)
    doors_true = len(plan.rooms_with_doors)
    labels_true = {r.label for r in plan.rooms_with_doors}
    labels_got = {p["label"] for p in fd["pois"] if p.get("label")}
    return {
        "valid": summary["passed"],
        "rooms": f"{len(fd['rooms'])}/{rooms_true}",
        "doors": f"{len(fd['doors'])}/{doors_true}",
        "pois": f"{len([p for p in fd['pois'] if p.get('category') not in ('stairs', 'lift')])}/{doors_true}",
        "labels": f"{len(labels_got & labels_true)}/{len(labels_true)}",
        "components": summary["n_components"],
        "scale_err_pct": round(100 * (summary["scale"] - plan.m_per_px) / plan.m_per_px, 1),
        "ok": (
            summary["passed"]
            and len(fd["rooms"]) == rooms_true
            and len(fd["doors"]) == doors_true
            and summary["n_components"] == 1
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="runs/style_stress")
    ap.add_argument("--segmenter", default="classical")
    ap.add_argument("--styles", default=",".join(STYLES))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for variant in ("basic", "lshape"):
        plan = make_plan(variant)
        for style in args.styles.split(","):
            img = render_style(plan, style)
            p = out / f"{variant}_{style}.png"
            cv2.imwrite(str(p), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
            try:
                res = convert(str(p), out_dir=str(out / f"{variant}_{style}"), method=args.segmenter)
                fd = load_package(str(res.package))["floors"]["F1"] if res.package.exists() else None
                if fd is None:  # failed validation -> not packaged; read the per-floor JSON
                    fd = json.loads((out / f"{variant}_{style}" / "floors" / "F1.json").read_text())
                s = score(plan, fd, res.floors[0])
            except Exception as e:  # report crashes as failures, never hide them
                s = {
                    "valid": False,
                    "rooms": "-",
                    "doors": "-",
                    "pois": "-",
                    "labels": "-",
                    "components": "-",
                    "scale_err_pct": "-",
                    "ok": False,
                    "error": repr(e)[:80],
                }
            rows.append((variant, style, s))
            print(variant, style, s)
    lines = [
        "| layout | style | valid | rooms | doors | destinations | labels | graph pieces "
        "| scale err % | all correct |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for v, st, s in rows:
        lines.append(
            f"| {v} | {st} | {'yes' if s['valid'] else 'NO'} | {s['rooms']} | {s['doors']} | {s['pois']} | "
            f"{s['labels']} | {s['components']} | {s['scale_err_pct']} | {'yes' if s['ok'] else 'NO'} |"
        )
    n_ok = sum(s["ok"] for *_, s in rows)
    lines.append(f"\n{n_ok}/{len(rows)} cases fully correct (segmenter: {args.segmenter}).")
    (out / "RESULTS.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
