"""Validators. Work on the metric JSON (floor.json / venue.json), so they can check any package —
ours, or one exported by the Android app — exactly as the consumer sees it."""

from __future__ import annotations

import json
from importlib import resources

import networkx as nx
import numpy as np
from jsonschema import Draft202012Validator
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import unary_union
from shapely.prepared import prep

from .ir import Issue


def load_schema() -> dict:
    return json.loads(resources.files("turn_mapper").joinpath("schema/turnmap.schema.json").read_text())


def _validator(defname: str) -> Draft202012Validator:
    schema = load_schema()
    sub = {"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": f"#/$defs/{defname}"}
    return Draft202012Validator(sub)


def schema_errors(obj: dict, defname: str) -> list[Issue]:
    return [
        Issue("SCHEMA", f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}")
        for e in _validator(defname).iter_errors(obj)
    ]


def walkable_geom(fd: dict) -> MultiPolygon:
    polys = []
    for p in fd["walkable"]["coordinates"]:
        poly = Polygon(p[0], p[1:])
        polys.append(poly if poly.is_valid else poly.buffer(0))
    u = unary_union(polys) if polys else MultiPolygon()
    return u if isinstance(u, MultiPolygon) else MultiPolygon([u]) if not u.is_empty else MultiPolygon()


def validate_floor(fd: dict, inside_tol_m: float = 0.05) -> tuple[list[Issue], list[Issue]]:
    errors = schema_errors(fd, "floor")
    warnings: list[Issue] = []
    if errors:
        return errors, warnings
    walk = walkable_geom(fd)
    if walk.is_empty:
        errors.append(Issue("WALKABLE_EMPTY", "walkable area is empty"))
        return errors, warnings
    region = prep(walk.buffer(inside_tol_m))
    nodes = {n["id"]: n for n in fd["graph"]["nodes"]}
    if len(nodes) != len(fd["graph"]["nodes"]):
        errors.append(Issue("NODE_ID_DUPLICATE", "duplicate node ids"))
    walls = [
        LineString([w["a"], w["b"]]).buffer(max(w.get("thickness_m", 0.1), 0.02) * 0.35) for w in fd["walls"]
    ]
    wall_u = prep(unary_union(walls)) if walls else None
    g = nx.Graph()
    g.add_nodes_from(nodes)
    for e in fd["graph"]["edges"]:
        if e["from"] not in nodes or e["to"] not in nodes:
            errors.append(Issue("EDGE_DANGLING", "edge references a missing node", e["id"]))
            continue
        a, b = nodes[e["from"]], nodes[e["to"]]
        seg = LineString([(a["x"], a["y"]), (b["x"], b["y"])])
        if abs(seg.length - e["length_m"]) > 0.011:
            errors.append(
                Issue("EDGE_LENGTH_MISMATCH", f"length_m {e['length_m']} != {seg.length:.3f}", e["id"])
            )
        if not region.contains(seg):
            errors.append(Issue("EDGE_OUTSIDE_WALKABLE", "edge leaves the walkable area", e["id"]))
        elif wall_u is not None and e["type"] != "door" and wall_u.intersects(seg):
            errors.append(Issue("EDGE_CROSSES_WALL", "edge intersects a wall", e["id"]))
        g.add_edge(e["from"], e["to"])
    comps = sorted(nx.connected_components(g), key=len, reverse=True) if len(g) else []
    if len(comps) > 1:
        sizes = [len(c) for c in comps]
        warnings.append(Issue("GRAPH_DISCONNECTED", f"{len(comps)} components, node counts {sizes[:8]}"))
    main = comps[0] if comps else set()
    for p in fd["pois"]:
        if p["node_id"] not in nodes:
            errors.append(Issue("POI_BAD_NODE", "POI references a missing node", p["id"]))
        elif p["node_id"] not in main:
            warnings.append(
                Issue("POI_NOT_IN_MAIN_COMPONENT", f"'{p['name']}' not reachable from main graph", p["id"])
            )
        if p.get("needs_review"):
            warnings.append(Issue("POI_NEEDS_REVIEW", f"label '{p['name']}' needs human review", p["id"]))
    b = fd["bounds_m"]
    xs = [n["x"] for n in nodes.values()]
    ys = [n["y"] for n in nodes.values()]
    if xs and (
        min(xs) < b["min_x"] - 1e-6
        or max(xs) > b["max_x"] + 1e-6
        or min(ys) < b["min_y"] - 1e-6
        or max(ys) > b["max_y"] + 1e-6
    ):
        errors.append(Issue("NODE_OUT_OF_BOUNDS", "graph node outside floor bounds"))
    if not fd["graph"]["edges"]:
        errors.append(Issue("GRAPH_EMPTY", "no graph edges"))
    return errors, warnings


def route_lengths(fd: dict, pairs: int = 20, seed: int = 0) -> list[tuple[str, str, float | None, list[str]]]:
    """A* between random POI pairs (sanity check for the QA report)."""
    nodes = {n["id"]: (n["x"], n["y"]) for n in fd["graph"]["nodes"]}
    g = nx.Graph()
    for e in fd["graph"]["edges"]:
        g.add_edge(e["from"], e["to"], weight=e["length_m"])
    pois = fd["pois"]
    rng = np.random.default_rng(seed)
    out = []
    if len(pois) < 2:
        return out

    def h(u, v):
        return float(np.hypot(nodes[u][0] - nodes[v][0], nodes[u][1] - nodes[v][1]))

    for _ in range(pairs):
        i, j = rng.choice(len(pois), 2, replace=False)
        a, b = pois[i], pois[j]
        try:
            path = nx.astar_path(g, a["node_id"], b["node_id"], heuristic=h, weight="weight")
            length = sum(g[u][v]["weight"] for u, v in zip(path[:-1], path[1:], strict=False))
            out.append((a["name"], b["name"], round(length, 2), path))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            out.append((a["name"], b["name"], None, []))
    return out
