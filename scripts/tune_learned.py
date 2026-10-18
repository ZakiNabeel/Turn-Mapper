"""Phase C of docs/ML_IMPROVEMENT_PLAN.md: tune learned-segmenter v2 options on the dev set, pick the best by
a rule fixed in advance, then run the 12-case synthetic test once with classical, learned v1 and the pick.

Selection rule (declared before any result): dev score = mean(room recall, room precision, door recall,
door precision, routes) - 0.05 x mean wall crossings per floor. Ties go to the simpler config (earlier in
CONFIGS). Usage (needs TURN_SEG_WEIGHTS): python scripts/tune_learned.py --n 16 --out /kaggle/working/tune
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

CONFIG_SETS = {
    "learned": [
        ("v1", "learned", {}),
        ("doors", "learned", {"learned_doors": True}),
        ("doors+scales", "learned", {"learned_doors": True, "learned_scales": [0.7, 1.0, 1.4]}),
        ("doors+frag", "learned", {"learned_doors": True, "learned_min_wall_frag_t2": 6.0}),
        ("doors+thr0.35", "learned", {"learned_doors": True, "learned_wall_thr": 0.35}),
        (
            "doors+scales+thr0.35+frag",
            "learned",
            {
                "learned_doors": True,
                "learned_scales": [0.7, 1.0, 1.4],
                "learned_wall_thr": 0.35,
                "learned_min_wall_frag_t2": 6.0,
            },
        ),
    ],
    "hybrid": [
        ("hybrid0.75", "hybrid", {}),
        ("hybrid0.6", "hybrid", {"hybrid_wall_conf": 0.6}),
        ("hybrid0.9", "hybrid", {"hybrid_wall_conf": 0.9}),
        ("hybrid0.75+frag", "hybrid", {"learned_min_wall_frag_t2": 6.0}),
        ("hybrid0.75-nodoors", "hybrid", {"hybrid_doors": False}),
    ],
}
CONFIGS = CONFIG_SETS["learned"]  # kept for the first notebook run


def dev_score(s: dict) -> float:
    keys = ["room_recall", "room_precision", "door_recall", "door_precision", "routes"]
    return sum(s.get(k) or 0.0 for k in keys) / len(keys) - 0.05 * (s.get("wall_crossings") or 0.0)


def sh(cmd: list[str], env: dict | None = None) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **(env or {})})
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-3000:], flush=True)
    return r.stdout


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--out", default="runs/tune")
    ap.add_argument("--set", default="learned", choices=sorted(CONFIG_SETS))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    results = {}
    configs = CONFIG_SETS[args.set]
    runs = [("classical", "classical", {})] + configs
    for name, seg, params in runs:
        d = out / f"dev_{name}"
        sh(
            [
                py,
                "eval/evaluate_dev.py",
                "--segmenter",
                seg,
                "--params",
                json.dumps(params),
                "--n",
                str(args.n),
                "--out",
                str(d),
            ]
        )
        summ = json.loads((d / "dev_metrics.json").read_text())["summary"]
        results[name] = {
            "segmenter": seg,
            "params": params,
            "dev": summ,
            "dev_score": round(dev_score(summ), 4),
        }
        print(name, json.dumps(results[name]), flush=True)
    learned = [n for n, _, _ in configs]
    best = max(learned, key=lambda n: (results[n]["dev_score"], -learned.index(n)))
    print("BEST (by the declared rule):", best, flush=True)
    # one test run on the 12 synthetic cases
    test = {}
    for name, seg, params in [
        ("classical", "classical", {}),
        ("v1", "learned", {}),
        (best, "learned", results[best]["params"]),
    ]:
        d = out / f"synth_{name}"
        env = {"TURN_PARAMS_JSON": json.dumps(params)} if params else {}
        sh([py, "eval/evaluate_synthetic.py", "--segmenter", seg, "--out", str(d)], env=env)
        test[name] = json.loads((d / "metrics.json").read_text())
    (out / "tune_results.json").write_text(json.dumps({"dev": results, "best": best, "test": test}, indent=1))
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
