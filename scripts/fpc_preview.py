"""Look at real FloorPlanCAD tiles: which drawn symbols carry which semantic id.

Downloads the test archive (research use only, nothing kept in git), counts semantic ids per tile and writes
a contact sheet: the ids given with --ids in colour, the --walls ids black, everything else light grey.

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

COL: dict[int, tuple] = {}
WALLS: tuple = ()
PALETTE = [(40, 40, 230), (230, 90, 30), (40, 170, 40), (200, 40, 200), (0, 160, 220)]  # BGR


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
            elif sem in WALLS and wall_pass:
                cv2.polylines(img, [p], False, (0, 0, 0), 2, cv2.LINE_AA, shift=4)
            elif not wall_pass and sem not in COL and sem not in WALLS:
                cv2.polylines(
                    img, [p], False, (190, 190, 190) if sem == 0 else (150, 170, 200), 1, cv2.LINE_AA, shift=4
                )
    return img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--svg-dir", default=None)
    ap.add_argument("--scan", type=int, default=1500)
    ap.add_argument(
        "--ids", type=int, nargs="+", default=[30, 31, 32], help="ids to colour (red, blue, green ...)"
    )
    ap.add_argument("--walls", type=int, nargs="+", default=[35], help="ids drawn black")
    ap.add_argument("--ids2", type=int, nargs="+", default=[35, 1, 9, 3, 23], help="second sheet, no black")
    a = ap.parse_args()
    global WALLS
    WALLS = tuple(a.walls)
    d = a.svg_dir or fetch("/tmp/fpc_preview")
    files = sorted(glob.glob(f"{d}/**/*.svg", recursive=True))[: a.scan]
    print("FILES", len(files))
    head = Path(files[0]).read_text()[:1500]
    print("HEAD", head.replace("\n", " ")[:1500])
    tiles = collections.Counter()
    strokes = collections.Counter()
    picks_all: dict[int, list[str]] = {s: [] for s in [*a.ids, *a.ids2]}
    for f in files:
        try:
            els, _ = read_svg(f)
        except Exception:  # noqa: BLE001
            continue
        c = collections.Counter(e["sem"] for e in els)
        strokes.update(c)
        for s in c:
            tiles[s] += 1
        for s in picks_all:
            if c.get(s, 0) >= 4 and len(picks_all[s]) < 8:
                picks_all[s].append(f)
    print("TILES_WITH_ID", dict(sorted(tiles.items())))
    print("STROKES_BY_ID", dict(sorted(strokes.items())))

    def sheet(out_path: str, ids: list[int]) -> None:
        COL.clear()
        COL.update({s: PALETTE[i % len(PALETTE)] for i, s in enumerate(ids)})
        rows = []
        for s in ids:
            fs = [f for f in picks_all.get(s, [])][:8]
            ims = [draw(f) for f in fs] + [np.full((420, 420, 3), 255, np.uint8)] * (8 - len(fs))
            row = np.hstack(ims[:8])
            cv2.putText(row, f"id {s}", (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, COL[s], 2)
            rows.append(row)
        cv2.imwrite(out_path, np.vstack(rows))

    sheet(a.out, a.ids)
    WALLS = ()
    sheet(a.out.replace(".png", "_b.png"), a.ids2)
    print("WROTE", a.out)


if __name__ == "__main__":
    main()
