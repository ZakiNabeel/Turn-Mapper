"""Look at real FloorPlanCAD tiles: which drawn symbols carry semantic ids 28 / 29 / 30 and the wall ids.

Downloads the test archive (research use only, nothing kept in git), counts semantic ids per tile and writes
a contact sheet where id 28 is red, 29 blue, 30 green, walls (33-35) black and everything else light grey.

    python scripts/fpc_preview.py --out /kaggle/working/fpc_preview.png [--svg-dir DIR]
"""

from __future__ import annotations

import argparse
import collections
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from turn_mapper.learned.floorplancad import read_svg  # noqa: E402

COL = {28: (40, 40, 230), 29: (230, 90, 30), 30: (40, 170, 40)}  # BGR: red, blue, green


def fetch(dest: str) -> str:
    os.makedirs(dest, exist_ok=True)
    out = f"{dest}/test.archive"
    subprocess.run(
        [
            "gdown",
            "-q",
            "--fuzzy",
            "https://drive.google.com/file/d/1jxpYgxnLUbXEzMOsjaMPQFSuvmvHimiZ/view",
            "-O",
            out,
        ]
    )
    for fmt in ("zip", "gztar", "xztar", "tar"):
        try:
            shutil.unpack_archive(out, dest, fmt)
            break
        except Exception:  # noqa: BLE001
            continue
    os.remove(out)
    return dest


def draw(path: str, size: int = 420) -> np.ndarray:
    els, (x0, y0, w, h) = read_svg(path)
    k = size / max(w, h)
    img = np.full((size, size, 3), 255, np.uint8)
    for wall_pass in (False, True):
        for e in els:
            sem = e["sem"]
            p = np.round([[(x - x0) * k * 16, (y - y0) * k * 16] for x, y in e["pts"]]).astype(np.int32)
            if sem in COL and wall_pass:
                cv2.polylines(img, [p], False, COL[sem], 2, cv2.LINE_AA, shift=4)
            elif sem in (33, 34, 35) and wall_pass:
                cv2.polylines(img, [p], False, (0, 0, 0), 2, cv2.LINE_AA, shift=4)
            elif not wall_pass and sem not in COL and sem not in (33, 34, 35):
                cv2.polylines(
                    img, [p], False, (190, 190, 190) if sem == 0 else (150, 170, 200), 1, cv2.LINE_AA, shift=4
                )
    return img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--svg-dir", default=None)
    ap.add_argument("--scan", type=int, default=1500)
    a = ap.parse_args()
    d = a.svg_dir or fetch("/tmp/fpc_preview")
    files = sorted(glob.glob(f"{d}/**/*.svg", recursive=True))[: a.scan]
    print("FILES", len(files))
    head = Path(files[0]).read_text()[:1500]
    print("HEAD", head.replace("\n", " ")[:1500])
    tiles = collections.Counter()
    strokes = collections.Counter()
    picks: dict[int, list[str]] = {28: [], 29: [], 30: []}
    for f in files:
        try:
            els, _ = read_svg(f)
        except Exception:  # noqa: BLE001
            continue
        c = collections.Counter(e["sem"] for e in els)
        strokes.update(c)
        for s in c:
            tiles[s] += 1
        for s in picks:
            if c.get(s, 0) >= 4 and len(picks[s]) < 8:
                picks[s].append(f)
    print("TILES_WITH_ID", dict(sorted(tiles.items())))
    print("STROKES_BY_ID", dict(sorted(strokes.items())))
    rows = []
    for s, fs in picks.items():
        ims = [draw(f) for f in fs] + [np.full((420, 420, 3), 255, np.uint8)] * (8 - len(fs))
        row = np.hstack(ims[:8])
        cv2.putText(row, f"id {s}", (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, COL[s], 2)
        rows.append(row)
    cv2.imwrite(a.out, np.vstack(rows))
    print("WROTE", a.out)


if __name__ == "__main__":
    main()
