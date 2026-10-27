"""Kaggle runner: classical vs learned vs hybrid on the public plans in eval/public_plans/sources.tsv.

Downloads every plan from its institution's website (Kaggle has internet), runs
scripts/eval_public_plans.py once per configuration, scores each with
scripts/score_textlayer.py and writes small overlay contact sheets.
Plans are third-party material: they stay in /kaggle/working and are never committed.

    python scripts/kaggle_public_eval.py --weights .../turn_seg_s2.pt [--configs classical,learned,hybrid]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130"
CONFIGS = {
    "classical": {},
    "learned": {"learned_doors": True, "learned_scales": [0.7, 1.0, 1.4]},  # S2 tuned (RESULTS_ML_V2)
    "hybrid": {"hybrid_wall_conf": 0.6},  # hybrid0.6 (RESULTS_ML_V2)
}
METHOD = {"classical": "classical", "learned": "learned", "hybrid": "hybrid"}


def fetch(rows, out: Path) -> None:
    import pymupdf
    import requests
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    for r in rows:
        pid = r["id"]
        if list(out.glob(pid + ".*")):
            continue
        try:
            resp = requests.get(r["url"], headers={"User-Agent": UA}, timeout=120)
            data = resp.content
        except Exception as e:  # noqa: BLE001
            print("FETCH FAIL", pid, e)
            continue
        if data[:4] == b"%PDF":
            doc = pymupdf.open(stream=data, filetype="pdf")
            page = int(r.get("page") or 1)
            one = pymupdf.open()
            one.insert_pdf(doc, from_page=page - 1, to_page=page - 1)
            one.save(str(out / f"{pid}.pdf"))
        else:
            try:
                im = Image.open(io.BytesIO(data))
            except Exception:  # noqa: BLE001
                print("NOT A PLAN", pid, resp.status_code, data[:60])
                continue
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                bg = Image.new("RGB", im.size, "white")
                bg.paste(im, mask=im.split()[3])
                im = bg
            im.convert("RGB").save(out / f"{pid}.png")
        print("OK", pid, len(data))


def contact_sheet(run_dir: Path, ids: list[str], dest: Path) -> None:
    from PIL import Image, ImageDraw

    Image.MAX_IMAGE_PIXELS = None
    cell, cols = 520, 4
    ims = [(i, run_dir / i / "qa" / "F1_overlay.png") for i in ids]
    ims = [(i, p) for i, p in ims if p.exists()]
    if not ims:
        return
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), "white")
    d = ImageDraw.Draw(sheet)
    for k, (i, p) in enumerate(ims):
        im = Image.open(p).convert("RGB")
        im.thumbnail((cell - 10, cell - 30))
        x, y = (k % cols) * cell, (k // cols) * cell
        sheet.paste(im, (x + 5, y + 25))
        d.text((x + 8, y + 6), i, fill="red")
    sheet.save(dest, quality=80)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--configs", default="classical,learned,hybrid")
    ap.add_argument("--work", default="/kaggle/working/public_eval")
    a = ap.parse_args()
    work = Path(a.work)
    rows = list(
        csv.DictReader(open(ROOT / "eval/public_plans/sources.tsv", encoding="utf-8"), delimiter="\t")
    )
    fetch(rows, work / "inputs")
    summary = {}
    for name in a.configs.split(","):
        env = dict(os.environ, TURN_SEG_WEIGHTS=a.weights, TURN_PARAMS_JSON=json.dumps(CONFIGS[name]))
        out = work / f"runs_{name}"
        cmd = [
            sys.executable,
            str(ROOT / "scripts/eval_public_plans.py"),
            str(work / "inputs"),
            str(ROOT / "eval/public_plans/sources.tsv"),
            "--out",
            str(out),
            "--segmenter",
            METHOD[name],
        ]
        print("RUN", name, flush=True)
        subprocess.run(cmd, env=env, check=False)
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/score_textlayer.py"),
                "--batch",
                str(out),
                str(work / "inputs"),
            ],
            check=False,
        )
        scores = (
            json.loads((out / "textlayer_scores.json").read_text())
            if (out / "textlayer_scores.json").exists()
            else {}
        )
        res = json.loads((out / f"results_{METHOD[name]}.json").read_text())
        summary[name] = {
            "scores": scores,
            "runs": {
                r["id"]: {
                    k: r.get(k)
                    for k in ("valid", "rooms", "doors", "pois", "components", "wall_seconds", "crash")
                }
                for r in res
            },
        }
        for s in ("dev", "heldout"):
            ids = [r["id"] for r in rows if r["set"] == s]
            sc = [scores[i] for i in ids if i in scores]
            if sc:
                m = {
                    k: round(sum(x[k] for x in sc) / len(sc), 3) for k in ("separated", "reachable", "named")
                }
                print(f"SUMMARY {name} {s} n={len(sc)} {json.dumps(m)}", flush=True)
            contact_sheet(out, ids, work / f"sheet_{name}_{s}.jpg")
    (work / "summary.json").write_text(json.dumps(summary, indent=1))
    print("ALL DONE")


if __name__ == "__main__":
    main()
