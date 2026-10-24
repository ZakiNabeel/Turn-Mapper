"""Export a TURN-Mapper ``venue.json`` for the live-positioning app (SMR202/turn-indoor-navigation).

Two targets, both defined in that repository:

- **Venue package v1** (``packages/venue-model/src/schema.ts``, ``schemaVersion: 1``): the complete map the
  app loads with ``npm run venue:load -- venue.package.json``. Rooms, corridors, walls, doors, our navigation
  graph, destinations, stairs/lift connectors between floors and manual start anchors.
- **TURN Floor GeoJSON v1** (``docs/MAP_IMPORT_FORMAT.md``): one file per floor, the documented hand-off for
  floor-plan conversion tools; the app derives its own walk graph from rooms and doors on import.

Frames differ: TURN-Mapper uses metres with the origin at the image's top-left and y pointing down; the app
uses metres with x right and y **up**. Every y is flipped about the floor's height (image height x scale).

The positioning app's own validator (``npm run venue:validate``) requires a route from every anchor to every
destination. Destinations whose node is not connected to the anchors are therefore left out by default and
listed in the report (``reachable_only=False`` keeps them).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import networkx as nx
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import unary_union

ID_RE = re.compile(r"[^A-Za-z0-9_.:-]+")


def _id(*parts: str) -> str:
    return ID_RE.sub("-", ":".join(str(p) for p in parts))[:120]


def _r(v: float) -> float:
    return round(float(v), 3)


def _floor_frame(fd: dict) -> tuple[float, float]:
    s = float(fd["transform"]["scale_m_per_px"])
    return fd["image"]["width_px"] * s, fd["image"]["height_px"] * s


def _flip(p, h: float) -> dict:
    return {"x": _r(p[0]), "y": _r(h - p[1])}


def _ring(poly: Polygon, h: float) -> list[dict]:
    pts = [_flip(p, h) for p in list(poly.exterior.coords)[:-1]]
    return pts


def _polys(geom) -> list[Polygon]:
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]


def _clean(poly: Polygon) -> Polygon:
    return poly if poly.is_valid else poly.buffer(0)


def _room_kind(r: dict) -> str:
    return "stairs" if (r.get("category") or "") in ("stairs_or_lift", "stairs", "lift") else "room"


def _room_name(r: dict, i: int) -> str:
    label, name = r.get("label"), r.get("name")
    if label and name and name != label:
        return f"{label} {name}"
    return label or name or f"Room {i + 1}"


def _circulation(fd: dict, min_area_m2: float = 2.0) -> list[Polygon]:
    """Walkable area that is not a room: corridors, halls and lobbies."""
    walk = _clean(shape(fd["walkable"])) if fd.get("walkable") else None
    if walk is None or walk.is_empty:
        return []
    rooms = unary_union([_clean(Polygon(r["polygon"])) for r in fd["rooms"] if len(r["polygon"]) >= 3])
    rest = walk.difference(rooms.buffer(0.05)) if not rooms.is_empty else walk
    return [p.simplify(0.05) for p in _polys(rest) if p.area >= min_area_m2]


def to_venue_package(
    venue: dict,
    floors: list[str] | None = None,
    venue_id: str | None = None,
    name: str | None = None,
    revision: str | None = None,
    rights: str = "Private venue plan: use only with the venue owner's permission; do not redistribute.",
    reachable_only: bool = True,
) -> tuple[dict, dict]:
    """Venue package v1 (dict) and a report. ``floors``: floor ids to include (default: all valid floors)."""
    gen = venue.get("generator", {})
    vid = _id(venue_id or venue["venue"]["id"])
    rev = revision or gen.get("run_id") or gen.get("git_commit") or "1"
    report: dict = {"floors": {}, "dropped_pois": [], "connectors": 0, "anchors": 0, "notes": []}
    out_floors, nodes, edges, pois, connectors = [], [], [], [], []
    node_floor: dict[str, str] = {}
    entries = [f for f in venue["floors"] if (not floors or f["id"] in floors)]
    if not entries:
        raise ValueError("no floors selected")
    notes = []
    for f in entries:
        fd = f["floor"]
        fid = f["id"]
        width, height = _floor_frame(fd)
        t = fd["transform"]
        src = t["scale_source"]
        notes.append(
            f"{fid}: scale {t['scale_m_per_px']:.4f} m/px from {src}"
            + ("" if src in ("measured_room_size", "operator_two_point", "cad_units") else " (estimate)")
            + ("" if f.get("validation_passed", True) else "; floor FAILED validation")
        )
        rooms = []
        for i, r in enumerate(fd["rooms"]):
            poly = _clean(Polygon(r["polygon"]))
            for k, p in enumerate(_polys(poly)):
                if p.area <= 0:
                    continue
                rooms.append(
                    {
                        "id": _id(fid, r["id"] if k == 0 else f"{r['id']}-{k}"),
                        "name": _room_name(r, i),
                        "polygon": _ring(p, height),
                        "labelPosition": _flip(p.representative_point().coords[0], height),
                        "kind": _room_kind(r),
                    }
                )
        for j, p in enumerate(_circulation(fd)):
            rooms.append(
                {
                    "id": _id(fid, f"corridor-{j + 1}"),
                    "name": "Corridor",
                    "polygon": _ring(p, height),
                    "labelPosition": _flip(p.representative_point().coords[0], height),
                    "kind": "circulation",
                }
            )
        walk = _clean(shape(fd["walkable"])) if fd.get("walkable") else None
        walkable = [_ring(p, height) for p in (_polys(walk) if walk is not None else []) if p.area > 0.5]
        if not walkable:
            walkable = [r["polygon"] for r in rooms]
        doors = []
        for d in fd["doors"]:
            a, b = d["a"], d["b"]
            w = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
            if w <= 0:
                continue
            doors.append(
                {
                    "id": _id(fid, d["id"]),
                    "position": _flip(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), height),
                    "widthMetres": _r(w),
                }
            )
        out_floors.append(
            {
                "id": fid,
                "label": f.get("name") or fid,
                "level": int(f.get("level", 0)),
                "widthMetres": _r(width),
                "heightMetres": _r(height),
                "windows": [],
                "rooms": rooms,
                "walkablePolygons": walkable,
                "walls": [{"from": _flip(w["a"], height), "to": _flip(w["b"], height)} for w in fd["walls"]],
                "doors": doors,
            }
        )
        ids = {}
        for n in fd["graph"]["nodes"]:
            nid = _id(fid, n["id"])
            ids[n["id"]] = nid
            p = _flip((n["x"], n["y"]), height)
            nodes.append(
                {
                    "id": nid,
                    "floorId": fid,
                    "x": min(max(p["x"], 0.0), _r(width)),
                    "y": min(max(p["y"], 0.0), _r(height)),
                }
            )
            node_floor[nid] = fid
        for e in fd["graph"]["edges"]:
            if e["from"] not in ids or e["to"] not in ids:
                continue
            na = next(n for n in nodes if n["id"] == ids[e["from"]])
            nb = next(n for n in nodes if n["id"] == ids[e["to"]])
            straight = ((na["x"] - nb["x"]) ** 2 + (na["y"] - nb["y"]) ** 2) ** 0.5
            edges.append(
                {
                    "id": _id(fid, e["id"]),
                    "from": ids[e["from"]],
                    "to": ids[e["to"]],
                    # never shorter than the straight line (the app's schema rejects that)
                    "distanceMetres": _r(max(float(e.get("length_m") or 0.0), straight + 0.001, 0.01)),
                    "bidirectional": bool(e.get("bidirectional", True)),
                    "stepFree": e.get("accessible") is not False,
                }
            )
        for p in fd["pois"]:
            if p["node_id"] not in ids:
                continue
            pois.append(
                {
                    "id": _id(fid, p["id"]),
                    "name": p["name"],
                    "category": p.get("category") or "room",
                    "nodeId": ids[p["node_id"]],
                }
            )
        report["floors"][fid] = {
            "rooms": len(rooms),
            "doors": len(doors),
            "nodes": len(ids),
            "pois": len([p for p in pois if node_floor.get(p["nodeId"]) == fid]),
            "scale_source": src,
        }
    # stairs / lifts between floors (from multi-floor linking)
    node_ids = {n["id"] for n in nodes}
    for t in venue.get("transitions", []) or []:
        a = _id(t["from"]["floor_id"], t["from"]["node_id"])
        b = _id(t["to"]["floor_id"], t["to"]["node_id"])
        if a not in node_ids or b not in node_ids or a == b:
            continue
        kind = t.get("type") if t.get("type") in ("stairs", "lift", "escalator", "ramp") else "stairs"
        cid = _id("conn", t["id"])
        connectors.append({"id": cid, "kind": kind, "nodeIds": [a, b]})
        edges.append(
            {
                "id": _id("conn", t["id"], "edge"),
                "from": a,
                "to": b,
                "distanceMetres": _r(max(float(t.get("length_m") or 6.0), 0.01)),
                "bidirectional": True,
                "stepFree": kind in ("lift", "ramp"),
                "connectorId": cid,
            }
        )
    report["connectors"] = len(connectors)
    # manual start anchors: one at every stairs/lift node (a person can stand there and confirm it)
    g = nx.Graph()
    g.add_nodes_from(n["id"] for n in nodes)
    g.add_edges_from((e["from"], e["to"]) for e in edges)
    trans_nodes = []
    for f in entries:
        for n in f["floor"]["graph"]["nodes"]:
            if n.get("kind") == "transition":
                trans_nodes.append((f["id"], n, _id(f["id"], n["id"])))
    # the component holding the most destinations is the one routes are guaranteed in
    comps = sorted(nx.connected_components(g), key=lambda c: -sum(1 for p in pois if p["nodeId"] in c))
    main = comps[0] if comps else set()
    anchors = []
    by_floor = defaultdict(int)
    node_by_id = {n["id"]: n for n in nodes}
    for fid, n, nid in trans_nodes:
        if nid not in main:
            continue
        by_floor[fid] += 1
        nn = node_by_id[nid]
        anchors.append(
            {
                "id": _id("anchor", nid),
                "venueId": vid,
                "floorId": fid,
                "kind": "manual",
                "position": {"x": nn["x"], "y": nn["y"]},
                "label": f"{(n.get('transition') or 'stairs').capitalize()} landing, {fid} ({by_floor[fid]})",
                "nodeId": nid,
            }
        )
    if not anchors and main:
        # no stairs/lift node reachable: one manual start at the busiest junction of the main graph
        sub = g.subgraph(main)
        nid = max(sub.nodes, key=lambda k: (sub.degree(k), k))
        nn = node_by_id[nid]
        anchors.append(
            {
                "id": _id("anchor", nid),
                "venueId": vid,
                "floorId": nn["floorId"],
                "kind": "manual",
                "position": {"x": nn["x"], "y": nn["y"]},
                "label": f"Corridor junction, {nn['floorId']}",
                "nodeId": nid,
            }
        )
    report["anchors"] = len(anchors)
    if reachable_only:
        keep = [p for p in pois if p["nodeId"] in main]
        report["dropped_pois"] = [
            f"{node_floor[p['nodeId']]}: {p['name']}" for p in pois if p["nodeId"] not in main
        ]
        pois = keep
    for fid in report["floors"]:
        report["floors"][fid]["pois_exported"] = len([p for p in pois if node_floor[p["nodeId"]] == fid])
    if report["dropped_pois"]:
        notes.append(
            f"{len(report['dropped_pois'])} destinations not connected to the main graph were left out; "
            "see the TURN-Mapper QA report and correct the map to include them."
        )
    pkg = {
        "schemaVersion": 1,
        "venueId": vid,
        "revision": _id(rev),
        "name": name or venue["venue"]["name"],
        "provenance": {
            "kind": "plan-derived",
            "rights": rights,
            "description": (
                f"Generated by TURN-Mapper {gen.get('version', '?')} "
                f"(commit {gen.get('git_commit')}, run {rev}) "
                "from raster floor plans. Automatic map: verify in TURN Studio before relying on it."
            ),
            "notes": notes,
        },
        "frame": {
            "units": "metres",
            "axes": "x-right-y-up",
            "originDescription": "Per floor: bottom-left corner of that floor's plan image (TURN-Mapper's "
            "top-left/y-down frame flipped about the image height).",
        },
        "floors": out_floors,
        "nodes": nodes,
        "edges": edges,
        "pois": pois,
        "anchors": anchors,
        "testCourses": [],
        "connectors": connectors,
        "assets": [],
    }
    report["notes"] = notes
    return pkg, report


def to_floor_geojson(venue: dict, floor_id: str) -> dict:
    """TURN Floor GeoJSON v1 for one floor, in metres (x right, y up)."""
    f = next((x for x in venue["floors"] if x["id"] == floor_id), None)
    if f is None:
        raise ValueError(f"no floor {floor_id}")
    fd = f["floor"]
    _, height = _floor_frame(fd)

    def ring(poly: Polygon) -> list[list[float]]:
        pts = [[_r(x), _r(height - y)] for x, y in poly.exterior.coords]
        return pts

    feats = []
    for i, r in enumerate(fd["rooms"]):
        for k, p in enumerate(_polys(_clean(Polygon(r["polygon"])))):
            feats.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [ring(p)]},
                    "properties": {
                        "kind": _room_kind(r),
                        "name": _room_name(r, i),
                        "id": _id(r["id"] if k == 0 else f"{r['id']}-{k}"),
                        **({"category": r["category"]} if r.get("category") else {}),
                    },
                }
            )
    for j, p in enumerate(_circulation(fd)):
        feats.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring(p)]},
                "properties": {"kind": "circulation", "name": "Corridor", "id": f"corridor-{j + 1}"},
            }
        )
    # the importer sizes the floor from the space polygons; a door outside them cannot connect anything
    xs = [c[0] for ft in feats for c in ft["geometry"]["coordinates"][0]]
    ys = [c[1] for ft in feats for c in ft["geometry"]["coordinates"][0]]
    xmax, ymax = (max(xs), max(ys)) if xs else (0.0, 0.0)
    for d in fd["doors"]:
        a, b = d["a"], d["b"]
        w = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
        cx, cy = (a[0] + b[0]) / 2, height - (a[1] + b[1]) / 2
        if not (0 <= cx <= xmax and 0 <= cy <= ymax):
            continue
        feats.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [_r((a[0] + b[0]) / 2), _r(height - (a[1] + b[1]) / 2)],
                },
                "properties": {"kind": "door", "id": _id(d["id"]), "width": _r(w)},
            }
        )
    for w in fd["walls"]:
        feats.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [_r(w["a"][0]), _r(height - w["a"][1])],
                        [_r(w["b"][0]), _r(height - w["b"][1])],
                    ],
                },
                "properties": {"kind": "wall", "id": _id(w["id"])},
            }
        )
    return {"type": "FeatureCollection", "turn": {"units": "metres"}, "features": feats}


def export(venue_path: str | Path, out_dir: str | Path, floors: list[str] | None = None, **kw) -> dict:
    """App venues: ``<out>/<building>/venue.package.json`` (floors joined by matched stairs/lifts;
    destinations
    on floors that are not linked are left out) and ``<out>/floors/<floor>/venue.package.json`` (one floor,
    always fully routable), each with ``<floor>.turn-floor.geojson``; plus ``<out>/export_report.json``.
    With ``floors``, one package of exactly those floors in ``<out>/``."""
    venue = json.loads(Path(venue_path).read_text())
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    groups: dict[str, list[str]] = defaultdict(list)
    if floors:
        groups[""] = list(floors)
    else:
        for f in venue["floors"]:
            groups[f.get("building_id") or ""].append(f["id"])
            groups[f"floors/{f['id']}"] = [f["id"]]  # every floor alone: always fully routable
    names = {b["id"]: b.get("name", b["id"]) for b in venue.get("buildings", [])}
    full: dict = {}
    for b, fids in groups.items():
        d = out / b if b else out
        d.mkdir(parents=True, exist_ok=True)
        tag = b.split("/")[-1]
        vid = f"{venue['venue']['id']}-{tag}" if b else None
        nm = f"{venue['venue']['name']} - {names.get(tag, tag)}" if b else None
        pkg, rep = to_venue_package(venue, fids, venue_id=vid, name=nm, **kw)
        (d / "venue.package.json").write_text(json.dumps(pkg, indent=1))
        for f in pkg["floors"]:
            (d / f"{f['id']}.turn-floor.geojson").write_text(json.dumps(to_floor_geojson(venue, f["id"])))
        full[b or "selection"] = rep
    (out / "export_report.json").write_text(json.dumps(full, indent=1))
    return full
