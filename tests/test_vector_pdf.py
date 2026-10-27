"""Vector-PDF adapter: door swings become known openings, hatching and text are not drawn, labels come
from the text layer, and the pipeline finds the corridor and the rooms' destinations on a CAD-style sheet."""

from __future__ import annotations

import math

import numpy as np
import pymupdf

from turn_mapper.api import convert, load_package
from turn_mapper.vector_pdf import find_doors, find_hatching, parse_page, render

S = 10.0  # points per metre on the sheet (1:~280)


def _door(page, hinge, wall_dir, swing_dir, w=1.0):
    """Leaf (hinge -> open position) and the quarter arc back to the closed position, CAD-style."""
    hx, hy = hinge
    closed = (hx + wall_dir[0] * w * S, hy + wall_dir[1] * w * S)
    opened = (hx + swing_dir[0] * w * S, hy + swing_dir[1] * w * S)
    sh = page.new_shape()
    sh.draw_line(pymupdf.Point(hinge), pymupdf.Point(opened))
    # quarter circle centred on the hinge, from opened to closed (cubic Bézier, k = 0.5523)
    k = 0.5523 * w * S
    c1 = (opened[0] + wall_dir[0] * k, opened[1] + wall_dir[1] * k)
    c2 = (closed[0] + swing_dir[0] * k, closed[1] + swing_dir[1] * k)
    sh.draw_bezier(pymupdf.Point(opened), pymupdf.Point(c1), pymupdf.Point(c2), pymupdf.Point(closed))
    sh.finish(color=(0, 0, 0), width=0.3)
    sh.commit()


def make_sheet(path):
    """A sheet border, a corridor (y 20..23 m) with three rooms above it, doors drawn as swings, one hatched
    room, room numbers as text, and a title block."""
    doc = pymupdf.open()
    page = doc.new_page(width=700, height=500)
    sh = page.new_shape()
    sh.draw_rect(pymupdf.Rect(10, 10, 690, 490))  # sheet border
    sh.draw_rect(pymupdf.Rect(20, 430, 680, 480))  # title block
    sh.finish(color=(0, 0, 0), width=1.0)
    sh.commit()
    x0, x1, yt, yc, yb = 100.0, 400.0, 100.0, 200.0, 230.0  # rooms 100..200, corridor 200..230 (pt)
    walls = page.new_shape()
    walls.draw_line((x0, yt), (x1, yt))
    walls.draw_line((x0, yb), (x1, yb))
    walls.draw_line((x0, yt), (x0, yb))
    walls.draw_line((x1, yt), (x1, yb))
    for x in (200.0, 300.0):
        walls.draw_line((x, yt), (x, yc))
    # corridor wall with a 1 m (10 pt) gap per room
    gaps = [(140.0, 150.0), (240.0, 250.0), (340.0, 350.0)]
    xs = [x0] + [v for g in gaps for v in g] + [x1]
    for a, b in zip(xs[::2], xs[1::2], strict=True):
        walls.draw_line((a, yc), (b, yc))
    walls.finish(color=(0, 0, 0), width=1.2)
    walls.commit()
    for a, _ in gaps:
        _door(page, (a, yc), (1, 0), (0, -1))
    hatch = page.new_shape()
    for i in range(20):  # 45 degree hatch in the middle room
        x = 205 + i * 4.5
        hatch.draw_line((x, 190), (x + 10, 180))
    hatch.finish(color=(0.3, 0.3, 0.3), width=0.2)
    hatch.commit()
    for x, label in ((150, "101"), (250, "102"), (350, "103")):
        page.insert_text((x - 8, 150), label, fontsize=9)
    page.insert_text((30, 460), "ENGINEERING  FLOOR 1  SCALE 1:280", fontsize=8)
    doc.save(str(path))


def test_parse_finds_doors_and_hatch(tmp_path):
    pdf = tmp_path / "sheet.pdf"
    make_sheet(pdf)
    page = pymupdf.open(str(pdf))[0]
    prim = parse_page(page)
    doors, drop = find_doors(prim)
    assert len(doors) == 3
    for hinge, closed in doors:  # closed position lies along the corridor wall, 1 m long
        assert abs(hinge[1] - 200) < 0.5 and abs(closed[1] - 200) < 0.5
        assert math.isclose(np.linalg.norm(closed - hinge), 10, abs_tol=0.5)
    assert len(find_hatching(prim, drop)) >= 15
    img, meta = render(page, 4.0)
    assert len(meta["known_doors"]) == 3
    # the door gaps are open again in the rendering (no leaf, no arc)
    for a, _ in ((140.0, 150.0), (240.0, 250.0), (340.0, 350.0)):
        gap = img[int(200 * 4) - 1 : int(200 * 4) + 2, int((a + 3) * 4) : int((a + 7) * 4), 0]
        assert gap.min() == 255


def test_pipeline_on_cad_sheet(tmp_path):
    pdf = tmp_path / "sheet.pdf"
    make_sheet(pdf)
    cfg = tmp_path / "v.yaml"
    cfg.write_text(
        "venue: {id: t, name: t}\nlabel_patterns: {B1: '\\b\\d{3}\\b'}\nbuildings: [{id: B1, name: B}]\n"
        f"floors: [{{id: F1, building: B1, level: 0, file: '{pdf}', page: 1,"
        " options: {vector_clean: true}}]\n"
    )
    res = convert([str(pdf)], venue_config=str(cfg), out_dir=str(tmp_path / "out"))
    fd = load_package(str(res.package))["floors"]["F1"]
    assert {"101", "102", "103"} <= {r["label"] for r in fd["rooms"]}  # read from the text layer, no OCR
    reachable = {p["label"] for p in fd["pois"]} & {"101", "102", "103"}
    assert len(reachable) >= 2  # rooms linked to the corridor through their doors


def test_flattened_arc_door_is_found(tmp_path):
    """Some CAD exports write the swing as a chain of short straight segments; it is still a door."""
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=200)
    hinge = np.array([100.0, 100.0])
    sh = page.new_shape()
    sh.draw_line(pymupdf.Point(*hinge), pymupdf.Point(100, 90))  # leaf to the open position
    pts = [hinge + 10 * np.array([math.sin(a), -math.cos(a)]) for a in np.linspace(0, math.pi / 2, 13)]
    for p, q in zip(pts[:-1], pts[1:], strict=True):
        sh.draw_line(pymupdf.Point(*p), pymupdf.Point(*q))
    sh.draw_line(pymupdf.Point(110, 100), pymupdf.Point(140, 100))  # wall the closed door meets
    sh.finish(color=(0, 0, 0), width=0.3)
    sh.commit()
    doors, drop = find_doors(parse_page(page))
    assert len(doors) == 1
    a, b = doors[0]
    assert np.allclose(a, hinge, atol=0.5) and np.allclose(b, [110, 100], atol=0.5)
    assert len(drop) >= 13  # the leaf and every arc segment are left out of the wall drawing
