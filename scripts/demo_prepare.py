"""Prepare the inputs for the live mid-evaluation demo (docs/mideval/06_DEMO_SCRIPT.md).

    python scripts/demo_prepare.py [--out demo_inputs]

Writes: plans in 6 drawing styles (two layouts), edge cases (blank page, noise, unsupported file) and a
deliberately broken map for the validator demo. Nothing here is hardcoded into the pipeline: these are
ordinary input files.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

from turn_mapper.api import convert
from turn_mapper.synthetic import STYLES, make_plan, render_style


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="demo_inputs")
    out = Path(ap.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    for variant in ("basic", "lshape"):
        plan = make_plan(variant)
        for style in STYLES:
            cv2.imwrite(
                str(out / f"{variant}_{style}.png"),
                cv2.cvtColor(render_style(plan, style), cv2.COLOR_RGB2BGR),
            )
    cv2.imwrite(str(out / "edge_blank.png"), np.full((500, 700), 255, np.uint8))
    cv2.imwrite(
        str(out / "edge_noise.png"), (np.random.default_rng(0).random((500, 700)) * 255).astype(np.uint8)
    )
    (out / "edge_not_a_plan.txt").write_text("this is not a floor plan\n")

    # a valid map, then the same map with an edge forced through walls + a dangling edge -> must be rejected
    convert(str(out / "basic_greyfill.png"), out_dir=str(out / "_valid"))
    venue = json.loads((out / "_valid" / "venue.json").read_text())
    fd = venue["floors"][0]["floor"]
    nodes = fd["graph"]["nodes"]
    # two door nodes in the same wall line, far apart: the straight edge between them runs along the wall
    doors = sorted((n for n in nodes if n["kind"] == "door"), key=lambda n: (round(n["y"], 0), n["x"]))
    a, b = doors[0], next(n for n in reversed(doors) if abs(n["y"] - doors[0]["y"]) < 0.5)
    length = round(((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5, 3)
    bad = {"id": "e_bad", "from": a["id"], "to": b["id"], "length_m": length, "type": "corridor"}
    bad.update({"bidirectional": True, "accessible": None, "provenance": {"source": "manual"}})
    fd["graph"]["edges"].append(bad)
    fd["graph"]["edges"].append(dict(fd["graph"]["edges"][0], id="e_dangling", to="does_not_exist"))
    broken = out / "broken_map"
    shutil.rmtree(broken, ignore_errors=True)
    shutil.copytree(out / "_valid" / "images", broken / "images")
    (broken / "venue.json").write_text(json.dumps(venue, indent=1))
    print(f"demo inputs written to {out}/")


if __name__ == "__main__":
    main()
