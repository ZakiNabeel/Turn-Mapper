"""Extracted map -> editable DXF -> loaded back as a measured CAD input."""

import cv2
import pytest

pytest.importorskip("ezdxf")
from turn_mapper.api import process_floor  # noqa: E402
from turn_mapper.config import single_image_config  # noqa: E402
from turn_mapper.export import floor_to_dict  # noqa: E402
from turn_mapper.studio.project import _orthogonal_walls, floor_dxf  # noqa: E402
from turn_mapper.synthetic import make_plan, render_style  # noqa: E402


def test_png_to_dxf_and_back_keeps_rooms_doors_and_labels(tmp_path):
    png = tmp_path / "p.png"
    cv2.imwrite(str(png), render_style(make_plan("basic"), "blackwalls"))
    cfg = single_image_config(str(png))
    fd = floor_to_dict(process_floor(cfg.floors[0], cfg))
    dxf = floor_dxf(fd, str(tmp_path / "p.dxf"))
    import ezdxf

    layers = {e.dxf.layer for e in ezdxf.readfile(dxf).modelspace()}
    assert {"A-WALL", "A-AREA-IDEN", "TURN-DOORS", "TURN-GRAPH"} <= layers
    cfg2 = single_image_config(dxf)
    fr = process_floor(cfg2.floors[0], cfg2)
    assert fr.scale_source == "cad_units"  # a measured scale, no site visit
    g = floor_to_dict(fr)
    assert (len(g["rooms"]), len(g["doors"]), len(g["pois"])) == (
        len(fd["rooms"]),
        len(fd["doors"]),
        len(fd["pois"]),
    )


def test_cad_edit_is_picked_up(tmp_path):
    """Delete one wall in the DXF (as a CAD user would): two rooms merge."""
    import ezdxf

    png = tmp_path / "p.png"
    cv2.imwrite(str(png), render_style(make_plan("basic"), "blackwalls"))
    cfg = single_image_config(str(png))
    fd = floor_to_dict(process_floor(cfg.floors[0], cfg))
    dxf = floor_dxf(fd, str(tmp_path / "p.dxf"))
    doc = ezdxf.readfile(dxf)
    msp = doc.modelspace()
    walls = [e for e in msp if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "A-WALL"]
    vertical = [
        e for e in walls if abs(e.get_points()[0][0] - e.get_points()[-1][0]) < 1e-6 and e.dxf.const_width
    ]
    inner = [e for e in vertical if 2 < e.get_points()[0][0] < 29]  # a partition between two rooms
    assert inner
    msp.delete_entity(inner[0])
    doc.saveas(dxf)
    cfg2 = single_image_config(dxf)
    g = floor_to_dict(process_floor(cfg2.floors[0], cfg2))
    assert len(g["rooms"]) == len(fd["rooms"]) - 1


def test_orthogonal_snap_aligns_door_gap_ends():
    walls = [
        {"a": [0.0, 5.00], "b": [4.0, 5.03]},
        {"a": [5.0, 5.06], "b": [9.0, 5.00]},
        {"a": [0.0, 0.0], "b": [3.0, 3.0]},  # diagonal: untouched
    ]
    segs = _orthogonal_walls(walls)
    assert segs[0][0][1] == segs[0][1][1] == segs[1][0][1] == segs[1][1][1]
    assert segs[2] == [[0.0, 0.0], [3.0, 3.0]]
