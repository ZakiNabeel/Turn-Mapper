"""FloorResult (pixels) -> floor.json (metres); writing and reading .turnmap packages."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import cv2
import numpy as np
from shapely.geometry import MultiPolygon, Polygon

from . import __version__
from .ingest import sha256_file
from .ir import FloorResult

SCHEMA_VERSION = "0.1.0"


def _r(v: float) -> float:
    return round(float(v), 3)


def _pt(xy, s) -> list[float]:
    return [_r(xy[0] * s), _r(xy[1] * s)]


def _ring(coords, s) -> list[list[float]]:
    pts = [_pt(c, s) for c in coords]
    if pts and pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts


def _poly_m(p: Polygon, s: float) -> list[list[list[float]]]:
    return [_ring(p.exterior.coords, s)] + [_ring(i.coords, s) for i in p.interiors]


def floor_to_dict(fr: FloorResult) -> dict:
    s = fr.scale_m_per_px
    h, w = fr.image.rgb.shape[:2]
    g = fr.geom
    walk = g.walkable if isinstance(g.walkable, MultiPolygon) else MultiPolygon([g.walkable])
    rooms = []
    for r in g.regions:
        if r.kind == "circulation":
            continue
        prov = {"source": "auto", "confidence": 0.6}
        if r.ocr_conf is not None:
            prov["ocr_confidence"] = _r(min(max(r.ocr_conf, 0), 1))
        rooms.append(
            {
                "id": r.id,
                "polygon": _ring(r.polygon.exterior.coords, s),
                "label": r.label,
                "name": r.name,
                "category": "stairs_or_lift" if r.kind == "transition" else None,
                "provenance": prov,
            }
        )
    door_room = {}
    circ = {r.id for r in g.regions if r.kind == "circulation"}
    for d in g.doors:
        others = [x for x in d.regions if x not in circ]
        door_room[d.id] = others[0] if others else None
    nodes = [
        {
            "id": n.id,
            "x": _r(n.x * s),
            "y": _r(n.y * s),
            "kind": n.kind,
            "door_id": n.door_id,
            "provenance": {"source": "auto"},
        }
        for n in fr.graph.nodes.values()
    ]
    edges = []
    for e in fr.graph.edges:
        a, b = fr.graph.nodes[e.a], fr.graph.nodes[e.b]
        length = float(np.hypot((a.x - b.x) * s, (a.y - b.y) * s))
        edges.append(
            {
                "id": e.id,
                "from": e.a,
                "to": e.b,
                "length_m": _r(length),
                "type": e.type,
                "bidirectional": True,
                "accessible": None,
                "provenance": {"source": "auto"},
            }
        )
    return {
        "floor_id": fr.image.spec.id,
        "image": {"file": "floorplan.png", "width_px": int(w), "height_px": int(h)},
        "transform": {
            "px_to_m": [[s, 0.0, 0.0], [0.0, s, 0.0]],
            "scale_m_per_px": s,
            "scale_source": fr.scale_source,
            "scale_evidence": fr.scale_evidence,
        },
        "bounds_m": {"min_x": 0.0, "min_y": 0.0, "max_x": _r(w * s), "max_y": _r(h * s)},
        "walkable": {
            "type": "MultiPolygon",
            "coordinates": [_poly_m(p, s) for p in walk.geoms],
            "provenance": {"source": "auto", "confidence": 0.7},
        },
        "walls": [
            {
                "id": f"w{i + 1}",
                "a": _pt(a, s),
                "b": _pt(b, s),
                "thickness_m": _r(t * s),
                "provenance": {"source": "auto", "confidence": 0.9},
            }
            for i, (a, b, t) in enumerate(g.wall_segments)
        ],
        "doors": [
            {
                "id": d.id,
                "a": _pt(d.segment.coords[0], s),
                "b": _pt(d.segment.coords[-1], s),
                "room_id": door_room[d.id],
                "provenance": {"source": "auto", "confidence": 0.7},
            }
            for d in g.doors
        ],
        "rooms": rooms,
        "graph": {"nodes": nodes, "edges": edges},
        "pois": [
            {
                "id": p.id,
                "name": p.name,
                "label": p.label,
                "node_id": p.node_id,
                "room_id": p.room_id,
                "category": None,
                "needs_review": p.needs_review,
                "provenance": {"source": "auto"},
            }
            for p in fr.pois
        ],
        "validation": {"passed": True, "forced": False, "errors": [], "warnings": []},
    }


def png_bytes(rgb: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert ok
    return buf.tobytes()


def venue_dict(
    venue_id: str,
    venue_name: str,
    buildings: list[dict],
    floors: list[dict],
    run_id: str | None,
    git_commit: str | None,
    method: str,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {
            "name": "turn-mapper",
            "version": __version__,
            "git_commit": git_commit,
            "run_id": run_id,
            "model": {"name": method, "checksum": None},
        },
        "venue": {"id": venue_id, "name": venue_name},
        "buildings": buildings,
        "floors": floors,
        "transitions": [],
    }


def write_package(
    path: str | Path,
    venue: dict,
    floors: dict[str, tuple[dict, bytes]],
    qa_files: dict[str, bytes] | None = None,
) -> Path:
    """floors: floor_id -> (floor_dict, floorplan_png_bytes)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("venue.json", json.dumps(venue, indent=2))
        for fid, (fd, png) in floors.items():
            z.writestr(f"floors/{fid}/floor.json", json.dumps(fd, indent=1))
            z.writestr(f"floors/{fid}/floorplan.png", png)
        for name, data in (qa_files or {}).items():
            z.writestr(f"qa/{name}", data)
    return path


def read_package(path: str | Path) -> dict:
    """Returns {'venue': dict, 'floors': {floor_id: dict}, 'images': {floor_id: bytes}}."""
    out: dict = {"floors": {}, "images": {}}
    with zipfile.ZipFile(path) as z:
        out["venue"] = json.loads(z.read("venue.json"))
        for f in out["venue"]["floors"]:
            out["floors"][f["id"]] = json.loads(z.read(f["path"]))
            img = str(Path(f["path"]).parent / out["floors"][f["id"]]["image"]["file"])
            out["images"][f["id"]] = z.read(img)
    return out


def file_sha(path: str | Path) -> str:
    return sha256_file(path)


__all__ = [
    "floor_to_dict",
    "write_package",
    "read_package",
    "venue_dict",
    "png_bytes",
    "SCHEMA_VERSION",
    "io",
]
