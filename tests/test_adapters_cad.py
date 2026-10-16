"""DXF / vector-PDF / SVG adapters: real drawing units give a measured (``cad_units``) scale."""

from dataclasses import replace

import numpy as np
import pytest

from turn_mapper.api import process_floor
from turn_mapper.config import single_image_config
from turn_mapper.ingest import inspect_file, load_floor
from turn_mapper.synthetic import make_plan

ezdxf = pytest.importorskip("ezdxf")


@pytest.mark.parametrize("units", ["mm", "m"])
def test_dxf_gives_cad_scale_and_skips_annotation_layers(tmp_path, units):
    from turn_mapper.synthetic import plan_to_dxf

    path = plan_to_dxf(make_plan("basic"), str(tmp_path / "plan.dxf"), units=units)
    layers = {x["name"]: x["default_on"] for x in inspect_file(path)["layers"]}
    assert layers == {"A-ANNO-DIMS": False, "A-AREA-IDEN": True, "A-WALL": True}
    cfg = single_image_config(path)
    fr = process_floor(cfg.floors[0], cfg)
    assert fr.scale_source == "cad_units"
    assert fr.scale_m_per_px == pytest.approx(0.02, rel=1e-6)
    rooms = [r for r in fr.geom.regions if r.kind == "room"]
    assert len(rooms) == 7 and len(fr.geom.doors) == 6  # R-107 has no door by design
    walk = fr.geom.walkable.bounds
    assert (walk[2] - walk[0]) * fr.scale_m_per_px == pytest.approx(29.7, abs=0.5)  # 30 m corridor


def test_dxf_without_units_needs_override(tmp_path):
    from turn_mapper.synthetic import plan_to_dxf

    path = plan_to_dxf(make_plan("basic"), str(tmp_path / "plan.dxf"))
    doc = ezdxf.readfile(path)
    doc.header["$INSUNITS"] = 0
    doc.saveas(path)
    spec = single_image_config(path).floors[0]
    assert "cad_m_per_px" not in load_floor(spec).source_meta
    meta = load_floor(replace(spec, options={"units": "mm"})).source_meta
    assert meta["cad_m_per_px"] == pytest.approx(0.02, rel=1e-6)


def test_vector_pdf_with_drawing_scale(tmp_path):
    import cv2
    import pymupdf

    p = make_plan("basic")
    wall = (np.abs(p.rgb[:, :, 0].astype(int) - 191) < 3).astype(np.uint8)
    cs, _ = cv2.findContours(wall, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    k = p.m_per_px / 100 / (0.0254 / 72)  # points per pixel at 1:100
    doc = pymupdf.open()
    page = doc.new_page(width=p.rgb.shape[1] * k + 20, height=p.rgb.shape[0] * k + 20)
    for c in cs:
        pts = [pymupdf.Point(10 + x * k, 10 + y * k) for x, y in c[:, 0, :]]
        page.draw_polyline([*pts, pts[0]], color=(0, 0, 0), width=0.25)
    path = str(tmp_path / "vec.pdf")
    doc.save(path)
    cfg = single_image_config(path)
    spec = replace(cfg.floors[0], page=1, options={"drawing_scale": 100})
    img = load_floor(spec)
    assert img.source_meta["adapter"] == "pdf_render" and img.source_meta["vector_only"]
    fr = process_floor(spec, cfg)
    assert fr.scale_source == "cad_units"
    assert len([r for r in fr.geom.regions if r.kind == "room"]) == 7
    assert len(fr.geom.doors) == 6


def test_dwg_gets_a_clear_message(tmp_path):
    f = tmp_path / "plan.dwg"
    f.write_bytes(b"AC1032")
    with pytest.raises(ValueError, match="DXF"):
        inspect_file(str(f))
