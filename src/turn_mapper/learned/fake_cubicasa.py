"""A tiny dataset in CubiCasa5K's on-disk format, made from the synthetic plans.

Used to test the whole ML path (SVG parsing -> masks -> training -> inference) offline and in CI, without
downloading the real dataset. Not useful for actually training a model.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..synthetic import DOOR_M, STYLES, WALL_M, _px, make_plan, render_style


def _poly(pts, dx, dy) -> str:
    return " ".join(f"{x - dx:.1f},{y - dy:.1f}" for x, y in pts)


def _rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def plan_svg(plan, shift=(5.0, 7.0)) -> str:
    g = plan.rgb[:, :, 0]
    h, w = g.shape
    ox, oy = plan.extra["origin_px"]
    dx, dy = shift  # coordinates are written shifted and undone by a group transform (tests transforms)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">']
    out.append(f'<g id="Model" transform="translate({dx},{dy})"><g class="Floorplan Floor-1">')
    wall = (g == 191).astype(np.uint8)
    for kern in (np.ones((1, 15), np.uint8), np.ones((15, 1), np.uint8)):
        part = cv2.morphologyEx(wall, cv2.MORPH_OPEN, kern)
        n, _, st, _ = cv2.connectedComponentsWithStats(part)
        for i in range(1, n):
            x, y, ww, hh = st[i, :4]
            pts = _poly(_rect(x, y, x + ww, y + hh), dx, dy)
            out.append(f'<g id="Wall" class="Wall "><polygon points="{pts}"/></g>')
    rooms = np.zeros_like(wall)
    for r in plan.rooms:
        q = _rect(ox + _px(r.x0), oy + _px(r.y0), ox + _px(r.x1), oy + _px(r.y1))
        cv2.fillPoly(rooms, [np.array(q, np.int32)], 1)
        out.append(f'<g class="Space Bedroom"><polygon points="{_poly(q, dx, dy)}"/></g>')
    hall = (g != 191) & (g != 255) & (rooms == 0)
    n, lab = cv2.connectedComponents(hall.astype(np.uint8))
    for i in range(1, n):
        m = (lab == i).astype(np.uint8)
        if m.sum() < 200:
            continue
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        c = max(cs, key=cv2.contourArea)[:, 0, :]
        out.append(f'<g class="Space Hall"><polygon points="{_poly(c, dx, dy)}"/></g>')
    for r in plan.rooms:
        if not r.door:
            continue
        side, off = r.door
        if side in ("top", "bottom"):
            y = r.y0 if side == "top" else r.y1
            q = _rect(
                _px(1 + r.x0 + off), _px(1 + y - WALL_M), _px(1 + r.x0 + off + DOOR_M), _px(1 + y + WALL_M)
            )
        else:
            x = r.x0 if side == "left" else r.x1
            q = _rect(
                _px(1 + x - WALL_M), _px(1 + r.y0 + off), _px(1 + x + WALL_M), _px(1 + r.y0 + off + DOOR_M)
            )
        out.append(
            f'<g id="Door" class="Door Swing Beside"><polygon points="{_poly(q, dx, dy)}"/>'
            f'<g class="Panel"><polygon points="0,0 1,0 1,1"/></g></g>'
        )
    out.append("</g></g></svg>")
    return "\n".join(out)


def make(root: str | Path, styles=STYLES) -> Path:
    root = Path(root)
    ids = []
    for variant in ("basic", "lshape"):
        plan = make_plan(variant)
        svg = plan_svg(plan)
        for style in styles:
            d = root / "synthetic" / f"{variant}_{style}"
            d.mkdir(parents=True, exist_ok=True)
            img = render_style(plan, style)
            if img.shape[:2] != plan.rgb.shape[:2]:
                img = cv2.resize(img, (plan.rgb.shape[1], plan.rgb.shape[0]))
            cv2.imwrite(str(d / "F1_scaled.png"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
            (d / "model.svg").write_text(svg)
            ids.append(f"/synthetic/{variant}_{style}/")
    (root / "train.txt").write_text("\n".join(i for i in ids if "scanned" not in i) + "\n")
    (root / "val.txt").write_text("\n".join(i for i in ids if "scanned" in i) + "\n")
    (root / "test.txt").write_text("")
    return root
