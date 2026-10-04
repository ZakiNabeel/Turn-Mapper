"""Navigation graph from the walkable area (pixel space).

skeleton -> traced polylines -> spur pruning / node merging -> containment-checked
simplification -> nodes every <= max_edge -> door nodes linked with wall-safe edges.
"""

from __future__ import annotations

import cv2
import networkx as nx
import numpy as np
from scipy import ndimage
from shapely.geometry import LineString, Point
from shapely.prepared import prep
from skimage.morphology import skeletonize

from .ir import Door, GeometryPx, GraphEdge, GraphNode, Issue, NavGraph

_OFFS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def skeleton_polylines(sk: np.ndarray, with_nodes: bool = False):
    """Trace a 1-px skeleton into polylines between node clusters (endpoints / junctions).

    Returns a list of point lists ``[(x, y), ...]``; with ``with_nodes`` returns
    ``(polylines, node_centroids)`` where each polyline is ``(a_id, b_id, pts)``.
    """
    sk = sk.astype(bool)
    h, w = sk.shape
    nb = ndimage.convolve(sk.astype(np.uint8), np.ones((3, 3), np.uint8), mode="constant") - sk
    node_px = sk & (nb != 2)
    nlab, nn = ndimage.label(node_px, structure=np.ones((3, 3)))
    cents = {}
    if nn:
        for i, c in enumerate(ndimage.center_of_mass(node_px, nlab, range(1, nn + 1)), start=1):
            cents[i] = (float(c[1]), float(c[0]))
    visited = np.zeros_like(sk)
    lines = []

    def neighbors(y, x):
        for dy, dx in _OFFS:
            yy, xx = y + dy, x + dx
            if 0 <= yy < h and 0 <= xx < w and sk[yy, xx]:
                yield yy, xx

    done_pairs = set()
    ys, xs = np.nonzero(node_px)
    for y, x in zip(ys, xs, strict=False):
        a = nlab[y, x]
        for qy, qx in neighbors(y, x):
            b = nlab[qy, qx]
            if b:
                if b != a and (min(a, b), max(a, b)) not in done_pairs:
                    done_pairs.add((min(a, b), max(a, b)))
                    lines.append((a, b, [cents[a], cents[b]]))
                continue
            if visited[qy, qx]:
                continue
            path = [cents[a], (float(qx), float(qy))]
            visited[qy, qx] = True
            py, px_, cy, cx = y, x, qy, qx
            end = None
            while True:
                nxt = None
                for ny, nx_ in neighbors(cy, cx):
                    if (ny, nx_) == (py, px_):
                        continue
                    if nlab[ny, nx_] and nlab[ny, nx_] != 0:
                        if not (ny == y and nx_ == x and len(path) < 3):
                            end = nlab[ny, nx_]
                            break
                    elif not visited[ny, nx_]:
                        nxt = (ny, nx_)
                if end is not None or nxt is None:
                    break
                py, px_, cy, cx = cy, cx, nxt[0], nxt[1]
                visited[cy, cx] = True
                path.append((float(cx), float(cy)))
            if end is not None:
                path.append(cents[end])
                lines.append((a, end, path))
            else:
                lines.append((a, None, path))
    # pure cycles without nodes
    rest = sk & ~node_px & ~visited
    while rest.any():
        y, x = map(int, np.argwhere(rest)[0])
        path = [(float(x), float(y))]
        rest[y, x] = False
        cy, cx = y, x
        while True:
            nxt = next(((ny, nx_) for ny, nx_ in neighbors(cy, cx) if rest[ny, nx_]), None)
            if nxt is None:
                break
            cy, cx = nxt
            rest[cy, cx] = False
            path.append((float(cx), float(cy)))
        path.append(path[0])
        lines.append((None, None, path))
    if with_nodes:
        return lines, cents
    return [p for _, _, p in lines]


def _plen(pts) -> float:
    a = np.asarray(pts)
    return float(np.sum(np.linalg.norm(np.diff(a, axis=0), axis=1))) if len(a) > 1 else 0.0


def _to_nx(lines, cents) -> nx.MultiGraph:
    g = nx.MultiGraph()
    nid = max(cents) if cents else 0
    for k, v in cents.items():
        g.add_node(k, xy=v)
    for a, b, pts in lines:
        if a is None:
            nid += 1
            a = nid
            g.add_node(a, xy=pts[0])
        if b is None:
            nid += 1
            b = nid
            g.add_node(b, xy=pts[-1])
        if a == b and _plen(pts) < 3:
            continue
        g.add_edge(a, b, pts=list(pts), length=_plen(pts))
    return g


def _merge_degree2(g: nx.MultiGraph) -> None:
    changed = True
    while changed:
        changed = False
        for n in list(g.nodes):
            if n not in g or g.degree(n) != 2:
                continue
            es = list(g.edges(n, keys=True, data=True))
            if len(es) != 2:
                continue
            (u1, v1, k1, d1), (u2, v2, k2, d2) = es
            o1 = v1 if u1 == n else u1
            o2 = v2 if u2 == n else u2
            if o1 == n or o2 == n:
                continue
            p1 = d1["pts"] if _close(d1["pts"][-1], g.nodes[n]["xy"]) else d1["pts"][::-1]
            p2 = d2["pts"] if _close(d2["pts"][0], g.nodes[n]["xy"]) else d2["pts"][::-1]
            pts = p1 + p2[1:]
            g.remove_node(n)
            g.add_edge(o1, o2, pts=pts, length=_plen(pts))
            changed = True


def _close(p, q, tol=3.0) -> bool:
    return abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol


def prune_spurs(g: nx.MultiGraph, min_len: float, keep_xy: list[tuple[float, float]] | None = None) -> None:
    for _ in range(20):
        removed = False
        for u, v, k, d in list(g.edges(keys=True, data=True)):
            if not g.has_edge(u, v, k):
                continue
            du, dv = g.degree(u), g.degree(v)
            if d["length"] < min_len and (du == 1) != (dv == 1) and max(du, dv) >= 3:
                leaf = u if du == 1 else v
                g.remove_edge(u, v, k)
                g.remove_node(leaf)
                removed = True
        _merge_degree2(g)
        if not removed:
            break
    g.remove_nodes_from([n for n in list(g.nodes) if g.degree(n) == 0])


def merge_close_nodes(g: nx.MultiGraph, radius: float) -> None:
    for _ in range(10):
        short = [(u, v, k) for u, v, k, d in g.edges(keys=True, data=True) if u != v and d["length"] < radius]
        if not short:
            break
        u, v, k = short[0]
        g.remove_edge(u, v, k)
        xy = tuple(np.mean([g.nodes[u]["xy"], g.nodes[v]["xy"]], axis=0))
        g.nodes[u]["xy"] = xy
        for _a, b, d in list(g.edges(v, data=True)):
            other = b if _a == v else _a
            other = u if other == v else other
            g.add_edge(
                u,
                other,
                pts=[xy] + d["pts"][1:-1] + [g.nodes[other]["xy"]] if other != u else d["pts"],
                length=d["length"],
            )
        g.remove_node(v)
    for u, v, k in [(u, v, k) for u, v, k in g.edges(keys=True) if u == v]:
        g.remove_edge(u, v, k)


def _segment_ok(a, b, region_prep, wall_mask: np.ndarray) -> bool:
    seg = LineString([a, b])
    if not region_prep.contains(seg):
        return False
    n = max(int(seg.length), 2)
    xs = np.clip(np.linspace(a[0], b[0], n).round().astype(int), 0, wall_mask.shape[1] - 1)
    ys = np.clip(np.linspace(a[1], b[1], n).round().astype(int), 0, wall_mask.shape[0] - 1)
    return not wall_mask[ys, xs].any()


def simplify_checked(pts, tol: float, region_prep, wall_mask) -> list:
    """Douglas-Peucker where every output segment must stay inside the region and off walls."""
    pts = [tuple(p) for p in pts]
    if len(pts) <= 2:
        return pts
    t = tol
    while t >= 0.5:
        out = list(LineString(pts).simplify(t, preserve_topology=False).coords)
        if all(_segment_ok(a, b, region_prep, wall_mask) for a, b in zip(out[:-1], out[1:], strict=False)):
            return out
        t /= 2
    return pts


def build_graph(
    geom: GeometryPx, m_per_px: float, params, walls_raw: np.ndarray
) -> tuple[NavGraph, list[Issue]]:
    issues: list[Issue] = []
    px = 1.0 / m_per_px
    walk = geom.debug["walk_mask"].copy()
    # fill small holes (residual text, door-arc fragments) so the skeleton has no loops around them
    holes = ndimage.binary_fill_holes(walk) & ~walk
    hl, hn = ndimage.label(holes)
    if hn:
        sizes = ndimage.sum(holes, hl, range(1, hn + 1))
        small = np.isin(hl, np.where(sizes < params.hole_fill_m2 * px * px)[0] + 1)
        walk |= small
    walk_s = cv2.morphologyEx(walk.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
    sk = skeletonize(walk_s)
    lines, cents = skeleton_polylines(sk, with_nodes=True)
    g = _to_nx(lines, cents)
    _merge_degree2(g)
    prune_spurs(g, params.spur_prune_m * px)
    merge_close_nodes(g, params.node_merge_m * px)
    _merge_degree2(g)

    tol = params.inside_tolerance_m * px + 1.5
    region = geom.walkable.buffer(tol)
    rprep = prep(region)
    wall_hard = walls_raw & ~geom.debug["walk_mask"]

    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    key_of: dict = {}

    def add_node(xy, kind="corridor", door_id=None) -> str:
        k = (round(xy[0], 1), round(xy[1], 1))
        if k in key_of and door_id is None:
            return key_of[k]
        nid = f"n{len(nodes) + 1}"
        nodes[nid] = GraphNode(id=nid, x=float(xy[0]), y=float(xy[1]), kind=kind, door_id=door_id)
        if door_id is None:
            key_of[k] = nid
        return nid

    def add_edge(a, b, typ="corridor"):
        if a == b:
            return
        na, nb_ = nodes[a], nodes[b]
        length = float(np.hypot(na.x - nb_.x, na.y - nb_.y))
        if length <= 0:
            return
        edges.append(GraphEdge(id=f"e{len(edges) + 1}", a=a, b=b, length=length, type=typ))

    max_len = params.max_edge_m * px
    for u, v, d in g.edges(data=True):
        pts = list(d["pts"])
        pts[0], pts[-1] = g.nodes[u]["xy"], g.nodes[v]["xy"]
        simp = simplify_checked(pts, params.simplify_tol_m * px, rprep, wall_hard)
        dense = [simp[0]]
        for a, b in zip(simp[:-1], simp[1:], strict=False):
            seglen = float(np.hypot(b[0] - a[0], b[1] - a[1]))
            k = int(np.ceil(seglen / max_len)) if seglen > max_len else 1
            for i in range(1, k + 1):
                dense.append((a[0] + (b[0] - a[0]) * i / k, a[1] + (b[1] - a[1]) * i / k))
        ids = [add_node(p) for p in dense]
        for a, b in zip(ids[:-1], ids[1:], strict=False):
            add_edge(a, b)

    # junction kinds
    deg: dict[str, int] = {}
    for e in edges:
        deg[e.a] = deg.get(e.a, 0) + 1
        deg[e.b] = deg.get(e.b, 0) + 1
    for nid, dval in deg.items():
        if dval >= 3:
            nodes[nid].kind = "junction"

    circ = {r.id for r in geom.regions if r.kind == "circulation"}
    for door in geom.doors:
        if not (circ & set(door.regions)):
            continue
        _link_door(
            door, nodes, edges, add_node, add_edge, rprep, wall_hard, params.door_link_max_m * px, issues
        )
    return NavGraph(nodes=nodes, edges=edges), issues


def _link_door(door: Door, nodes, edges, add_node, add_edge, rprep, wall_hard, max_d, issues) -> None:
    c = (door.center.x, door.center.y)
    did = add_node(c, kind="door", door_id=door.id)
    cands = []
    for e in edges:
        if e.type != "corridor":
            continue
        a, b = nodes[e.a], nodes[e.b]
        ls = LineString([(a.x, a.y), (b.x, b.y)])
        dist = ls.distance(Point(c))
        if dist <= max_d:
            cands.append((dist, e, ls))
    cands.sort(key=lambda t: t[0])
    for _dist, e, ls in cands[:6]:
        p = ls.interpolate(ls.project(Point(c)))
        tgt = (p.x, p.y)
        if not _segment_ok(c, tgt, rprep, wall_hard):
            continue
        a, b = nodes[e.a], nodes[e.b]
        if np.hypot(tgt[0] - a.x, tgt[1] - a.y) < 2:
            mid = e.a
        elif np.hypot(tgt[0] - b.x, tgt[1] - b.y) < 2:
            mid = e.b
        else:
            mid = add_node(tgt)
            old_b = e.b
            e.b = mid
            e.length = float(np.hypot(nodes[mid].x - a.x, nodes[mid].y - a.y))
            add_edge(mid, old_b)
        add_edge(did, mid, "door")
        return
    issues.append(
        Issue(
            "DOOR_UNLINKED", "door could not be linked to the corridor graph with a wall-safe edge", door.id
        )
    )
