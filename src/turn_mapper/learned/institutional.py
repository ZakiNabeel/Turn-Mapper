"""Procedural institutional floors (university / hospital / office style) with exact masks.

Residential datasets (CubiCasa5K, ResPlan) have no long double-loaded corridors, lecture halls, stair cores,
lifts, washroom blocks, lobbies or atrium voids, which is what our venues look like. This generator draws
them at a random realistic resolution; ``styles.render`` then draws them in any convention.

Everything is axis-aligned in metres and rasterised once; the data loader adds rotations/flips/crops.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .classes import BG, DOOR, LIFT, OTHER, ROOM, STAIRS, WALKABLE, WALL
from .styles import STYLES, Extras, render

LABELS = [
    "C-{n}",
    "B-{n}",
    "Lab {k}",
    "Room {n}",
    "Faculty Office",
    "CS Dept",
    "Seminar Hall",
    "Store",
    "Lecture Hall {k}",
    "Office {n}",
    "Server Room",
    "Library",
    "Lounge",
    "{n}",
]


@dataclass
class _Canvas:
    mask: np.ndarray
    s: float  # metres per pixel
    ex: Extras

    def px(self, v: float) -> int:
        return int(round(v / self.s))

    def rect(self, x0, y0, x1, y1, cls):
        a, b = (self.px(min(x0, x1)), self.px(min(y0, y1))), (self.px(max(x0, x1)), self.px(max(y0, y1)))
        cv2.rectangle(self.mask, a, (max(a[0], b[0] - 1), max(a[1], b[1] - 1)), int(cls), -1)


def generate(rng: np.random.Generator, m_per_px: float | None = None) -> tuple[np.ndarray, Extras]:
    s = m_per_px or float(rng.uniform(0.02, 0.045))
    W = float(rng.uniform(35, 85))
    r1, cw, r2 = float(rng.uniform(6, 10)), float(rng.uniform(2.2, 4.0)), float(rng.uniform(5, 10))
    te, ti = float(rng.uniform(0.25, 0.45)), float(rng.uniform(0.12, 0.25))
    wing = rng.random() < 0.55
    L2 = float(rng.uniform(15, 35)) if wing else 0.0
    m = 2.0
    H = r1 + cw + r2
    cv = _Canvas(
        np.full((int((H + L2 + 2 * m) / s) + 2, int((W + 2 * m) / s) + 2), BG, np.uint8), s, Extras()
    )
    ox, oy = m, m
    cy0, cy1 = oy + r1, oy + r1 + cw  # main corridor band
    cv.rect(ox, oy, ox + W, oy + H, ROOM)
    cv.rect(ox, cy0, ox + W, cy1, WALKABLE)
    wx0 = wx1 = 0.0
    if wing:
        wx0 = ox + float(rng.uniform(0.2, 0.7)) * W
        wwr = float(rng.uniform(5, 9))
        wx1 = wx0 + cw
        cv.rect(wx0 - wwr, oy + H, wx1 + wwr, oy + H + L2, ROOM)
        cv.rect(wx0, cy1, wx1, oy + H + L2, WALKABLE)
    walls: list[tuple[float, float, float, float, float]] = []  # x0, y0, x1, y1, thickness (centre lines)
    doors: list[tuple[float, float, float, float]] = []

    def band(xa, xb, ya, yb, horizontal_corr_y=None, vertical_corr_x=None):
        """Split a band of rooms into slots along its long axis; each slot gets a door onto the corridor."""
        along_x = horizontal_corr_y is not None
        lo, hi = (xa, xb) if along_x else (ya, yb)
        cuts = [lo]
        while cuts[-1] < hi - 3.5:
            cuts.append(
                min(
                    hi,
                    cuts[-1]
                    + float(
                        rng.choice(
                            [rng.uniform(3.5, 6), rng.uniform(7, 10), rng.uniform(10, 16)],
                            p=[0.35, 0.5, 0.15],
                        )
                    ),
                )
            )
        cuts[-1] = hi
        for a, b in zip(cuts[:-1], cuts[1:], strict=False):
            if along_x:
                walls.append((b, ya, b, yb, ti))
            else:
                walls.append((xa, b, xb, b, ti))
            kind = rng.random()
            span = b - a
            if kind < 0.08 and 5 < span < 8.5:  # stair core: open to the corridor, no door
                x0r, y0r, x1r, y1r = (a, ya, b, yb) if along_x else (xa, a, xb, b)
                cv.rect(x0r + ti, y0r + ti, x1r - ti, y1r - ti, STAIRS)
                if along_x:
                    doors.append((a + 0.6, horizontal_corr_y, b - 0.6, horizontal_corr_y))
                else:
                    doors.append((vertical_corr_x, a + 0.6, vertical_corr_x, b - 0.6))
                continue
            if kind < 0.14 and span > 4:  # lift + small lobby
                x0r, y0r = (a + 0.4, ya + 0.4) if along_x else (xa + 0.4, a + 0.4)
                cv.rect(x0r, y0r, x0r + 2.2, y0r + 2.4, LIFT)
            if kind > 0.92 and span > 6:  # washroom block: two small rooms
                mid = (a + b) / 2
                if along_x:
                    walls.append((mid, ya, mid, yb, ti))
                else:
                    walls.append((xa, mid, xb, mid, ti))
                parts = [(a, mid), (mid, b)]
            else:
                parts = [(a, b)]
            for pa, pb in parts:
                ndoor = 2 if pb - pa > 11 and rng.random() < 0.7 else 1
                for j in range(ndoor):
                    dw = float(rng.choice([rng.uniform(0.85, 1.1), rng.uniform(1.4, 1.8)], p=[0.8, 0.2]))
                    seg = (pb - pa) / ndoor
                    d0 = pa + j * seg + float(rng.uniform(0.4, max(0.5, seg - dw - 0.4)))
                    if along_x:
                        doors.append((d0, horizontal_corr_y, d0 + dw, horizontal_corr_y))
                    else:
                        doors.append((vertical_corr_x, d0, vertical_corr_x, d0 + dw))
                c = ((pa + pb) / 2, (ya + yb) / 2) if along_x else ((xa + xb) / 2, (pa + pb) / 2)
                if rng.random() < 0.8:
                    lab = str(rng.choice(LABELS)).format(
                        n=int(rng.integers(100, 420)), k=int(rng.integers(1, 9))
                    )
                    cv.ex.labels.append(((c[0] / s, c[1] / s), lab))
                if rng.random() < 0.4:  # desks/benches drawn as boxes
                    x0r, y0r, x1r, y1r = (pa, ya, pb, yb) if along_x else (xa, pa, xb, pb)
                    for _ in range(int(rng.integers(1, 6))):
                        fw, fh = float(rng.uniform(0.6, 2.0)), float(rng.uniform(0.5, 1.2))
                        if x1r - x0r > fw + 1.5 and y1r - y0r > fh + 1.5:
                            fx = float(rng.uniform(x0r + 0.7, x1r - fw - 0.7))
                            fy = float(rng.uniform(y0r + 0.7, y1r - fh - 0.7))
                            cv.ex.furniture.append((cv.px(fx), cv.px(fy), cv.px(fx + fw), cv.px(fy + fh)))

    # main wing: rooms above and below the corridor
    split_x = [ox, ox + W] if not wing else [ox, wx0, wx1, ox + W]
    band(ox, ox + W, oy, cy0, horizontal_corr_y=cy0)
    for xa, xb in zip(split_x[0::2], split_x[1::2], strict=False):
        if xb - xa > 3.5:
            band(xa, xb, cy1, oy + H, horizontal_corr_y=cy1)
    if wing:
        band(wx0 - wwr, wx0, oy + H, oy + H + L2, vertical_corr_x=wx0)
        band(wx1, wx1 + wwr, oy + H, oy + H + L2, vertical_corr_x=wx1)
    # lobby with an optional void (atrium / open to below): widen the corridor into the top band
    if rng.random() < 0.5:
        lx0 = ox + float(rng.uniform(0.1, 0.6)) * W
        lx1 = min(ox + W - 1, lx0 + float(rng.uniform(6, 14)))
        cv.rect(lx0, oy + 0.0, lx1, cy1, WALKABLE)
        walls[:] = [
            w for w in walls if not (w[0] == w[2] and lx0 - 0.1 < w[0] < lx1 + 0.1 and w[3] <= cy0 + 0.01)
        ]
        if rng.random() < 0.6:
            vx0, vy0 = lx0 + 1.5, oy + 1.5
            vx1, vy1 = lx1 - 1.5, cy0 - 0.5
            if vx1 - vx0 > 2 and vy1 - vy0 > 2:
                cv.rect(vx0, vy0, vx1, vy1, OTHER)
                for x0, y0, x1, y1 in (
                    (vx0, vy0, vx1, vy0),
                    (vx0, vy1, vx1, vy1),
                    (vx0, vy0, vx0, vy1),
                    (vx1, vy0, vx1, vy1),
                ):
                    walls.append((x0, y0, x1, y1, 0.08))  # balustrade
        doors.append(((lx0 + lx1) / 2 - 0.9, oy, (lx0 + lx1) / 2 + 0.9, oy))  # main entrance (double door)
    # corridor walls and outline
    walls += [(ox, cy0, ox + W, cy0, ti)]
    if wing:
        walls += [
            (ox, cy1, wx0, cy1, ti),
            (wx1, cy1, ox + W, cy1, ti),
            (wx0, cy1, wx0, oy + H + L2, ti),
            (wx1, cy1, wx1, oy + H + L2, ti),
        ]
        walls += [
            (ox, oy + H, wx0 - wwr, oy + H, te),
            (wx1 + wwr, oy + H, ox + W, oy + H, te),
            (wx0 - wwr, oy + H, wx0 - wwr, oy + H + L2, te),
            (wx1 + wwr, oy + H, wx1 + wwr, oy + H + L2, te),
            (wx0 - wwr, oy + H + L2, wx1 + wwr, oy + H + L2, te),
        ]
    else:
        walls += [(ox, cy1, ox + W, cy1, ti), (ox, oy + H, ox + W, oy + H, te)]
    walls += [(ox, oy, ox + W, oy, te), (ox, oy, ox, oy + H, te), (ox + W, oy, ox + W, oy + H, te)]
    for x0, y0, x1, y1, t in walls:
        cv.rect(x0 - t / 2, y0 - t / 2, x1 + t / 2, y1 + t / 2, WALL)
    if rng.random() < 0.5:  # columns along the outside walls
        step = float(rng.uniform(6, 8))
        c = float(rng.uniform(0.35, 0.6))
        for x in np.arange(ox, ox + W + 0.1, step):
            for y in (oy, oy + H):
                cv.rect(x - c / 2, y - c / 2, x + c / 2, y + c / 2, WALL)
    for x0, y0, x1, y1 in doors:
        t = te if y0 in (oy,) else ti
        if x0 == x1:
            cv.rect(x0 - t / 2 - 0.02, y0, x0 + t / 2 + 0.02, y1, DOOR)
        else:
            cv.rect(x0, y0 - t / 2 - 0.02, x1, y0 + t / 2 + 0.02, DOOR)
        if np.hypot(x1 - x0, y1 - y0) > 1.9:  # open archways (stair cores) and double doors: no swing drawn
            continue
        hinge, end = ((x0 / s, y0 / s), (x1 / s, y1 / s))
        if rng.random() < 0.5:
            hinge, end = end, hinge
        cv.ex.doors.append((hinge, end, int(rng.choice([-1, 1]))))
    return cv.mask, cv.ex


def prepare(
    out: str | Path, n: int = 2000, val_frac: float = 0.1, styles: tuple[str, ...] = STYLES, seed: int = 0
) -> dict:
    rng = np.random.default_rng(seed)
    out = Path(out)
    for sub in ("images", "masks"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    lists: dict[str, list[str]] = {"train": [], "val": []}
    counts = dict.fromkeys(styles, 0)
    for i in range(n):
        mask, ex = generate(rng)
        style = str(rng.choice(styles))
        img = render(mask, ex, style, rng)
        name = f"inst{i:05d}"
        cv2.imwrite(str(out / "images" / f"{name}.png"), cv2.cvtColor(img, cv2.COLOR_RGB2GRAY))
        cv2.imwrite(str(out / "masks" / f"{name}.png"), mask)
        lists["val" if i < int(n * val_frac) else "train"].append(name)
        counts[style] += 1
    for k, ids in lists.items():
        (out / f"{k}.txt").write_text("\n".join(ids) + "\n")
    (out / "test.txt").write_text("")
    info = {
        "source": "TURN procedural institutional floors",
        "n": n,
        "styles": counts,
        "splits": {k: len(v) for k, v in lists.items()},
    }
    (out / "dataset.json").write_text(json.dumps(info, indent=1))
    return info
