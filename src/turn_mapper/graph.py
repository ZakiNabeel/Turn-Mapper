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
from shapely.ops import unary_union
from shapely.prepared import prep
from skimage.morphology import skeletonize

from .ir import GeometryPx, GraphEdge, GraphNode, Issue, NavGraph

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


def oriented(pts: list, start_xy) -> list:
    """Return ``pts`` running from the end nearest ``start_xy`` (networkx does not keep edge direction)."""
    d0 = (pts[0][0] - start_xy[0]) ** 2 + (pts[0][1] - start_xy[1]) ** 2
    d1 = (pts[-1][0] - start_xy[0]) ** 2 + (pts[-1][1] - start_xy[1]) ** 2
    return list(pts) if d0 <= d1 else list(pts)[::-1]


def merge_close_nodes(g: nx.MultiGraph, radius: float) -> None:
    for _ in range(10):
        short = [(u, v, k) for u, v, k, d in g.edges(keys=True, data=True) if u != v and d["length"] < radius]
        if not short:
            break
        u, v, k = short[0]
        g.remove_edge(u, v, k)
        v_xy = g.nodes[v]["xy"]
        xy = tuple(np.mean([g.nodes[u]["xy"], v_xy], axis=0))
        g.nodes[u]["xy"] = xy
        for _a, b, d in list(g.edges(v, data=True)):
            other = b if _a == v else _a
            if other in (u, v):
                continue
            pts = oriented(d["pts"], v_xy)
            g.add_edge(u, other, pts=[xy] + pts[1:-1] + [g.nodes[other]["xy"]], length=d["length"])
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


def simplify_checked(pts, tol: float, region_prep, wall_mask) -> list | None:
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
    return greedy_visible(pts, region_prep, wall_mask)


def greedy_visible(pts, region_prep, wall_mask) -> list | None:
    """From each kept point, jump to the farthest later point still reachable by a valid straight segment.
    Used when Douglas-Peucker can't satisfy containment (narrow passages); avoids one node per pixel."""
    out = [pts[0]]
    i, n = 0, len(pts)
    while i < n - 1:
        lo, hi = i + 1, n - 1
        best = i + 1
        while lo <= hi:  # binary search is a heuristic (validity isn't monotone); verified below
            mid = (lo + hi) // 2
            if _segment_ok(pts[i], pts[mid], region_prep, wall_mask):
                best, lo = mid, mid + 1
            else:
                hi = mid - 1
        while best > i + 1 and not _segment_ok(pts[i], pts[best], region_prep, wall_mask):
            best -= 1
        if best == i + 1 and not _segment_ok(pts[i], pts[best], region_prep, wall_mask):
            return None  # the traced path itself leaves the valid area (pinch narrower than tolerance)
        out.append(pts[best])
        i = best
    return out


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
    stairs = geom.debug.get("stairs_mask")
    if stairs is not None and stairs.any():
        # stairs are reached via a transition node, not traced: their texture makes the skeleton loop
        walk_s &= ~cv2.dilate(stairs.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    sk = skeletonize(walk_s)
    lines, cents = skeleton_polylines(sk, with_nodes=True)
    g = _to_nx(lines, cents)
    _merge_degree2(g)
    prune_spurs(g, params.spur_prune_m * px)
    merge_close_nodes(g, params.node_merge_m * px)
    _merge_degree2(g)

    # same geometry the exported-package validator uses (walkable + tolerance, minus wall bands), slightly
    # stricter, so an edge accepted here can't fail validation after export
    tol = params.inside_tolerance_m * px * 0.8
    wall_bands = unary_union(
        [
            LineString([a, b]).buffer(max(t * m_per_px, 0.02) * 0.35 * px + 0.5)
            for a, b, t in geom.wall_segments
        ]
    )
    region = (
        geom.walkable.buffer(tol).difference(wall_bands)
        if not wall_bands.is_empty
        else geom.walkable.buffer(tol)
    )
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
    dropped = 0
    for u, v, d in g.edges(data=True):
        pts = oriented(d["pts"], g.nodes[u]["xy"])
        pts[0], pts[-1] = g.nodes[u]["xy"], g.nodes[v]["xy"]
        simp = simplify_checked(pts, params.simplify_tol_m * px, rprep, wall_hard)
        pieces = [simp]
        if simp is None:
            # keep the valid stretches of the traced line; only the invalid steps are dropped
            dropped += 1
            pieces, run = [], [pts[0]]
            for a, b in zip(pts[:-1], pts[1:], strict=False):
                if _segment_ok(a, b, rprep, wall_hard):
                    run.append(b)
                else:
                    if len(run) >= 2:
                        pieces.append(greedy_visible(run, rprep, wall_hard))
                    run = [b]
            if len(run) >= 2:
                pieces.append(greedy_visible(run, rprep, wall_hard))
        for simp in pieces:
            if not simp or len(simp) < 2:
                continue
            dense = [simp[0]]
            for a, b in zip(simp[:-1], simp[1:], strict=False):
                seglen = float(np.hypot(b[0] - a[0], b[1] - a[1]))
                k = int(np.ceil(seglen / max_len)) if seglen > max_len else 1
                for i in range(1, k + 1):
                    dense.append((a[0] + (b[0] - a[0]) * i / k, a[1] + (b[1] - a[1]) * i / k))
            ids = [add_node(p) for p in dense]
            for a, b in zip(ids[:-1], ids[1:], strict=False):
                add_edge(a, b)

    if dropped:
        issues.append(
            Issue(
                "SKELETON_EDGE_SPLIT",
                f"{dropped} centre-line piece(s) pass through a gap narrower "
                "than the validator allows; dropped (bridging may reconnect)",
            )
        )
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
        did = add_node((door.center.x, door.center.y), kind="door", door_id=door.id)
        if not _link_point(
            did, nodes, edges, add_node, add_edge, rprep, wall_hard, params.door_link_max_m * px, "door"
        ):
            issues.append(
                Issue(
                    "DOOR_UNLINKED",
                    "door could not be linked to the corridor graph with a wall-safe edge",
                    door.id,
                )
            )
    for t in geom.transitions:
        tid = add_node((t.anchor.x, t.anchor.y), kind="transition", door_id=t.id)
        nodes[tid].door_id = None
        nodes[tid].transition = t.type
        geom.debug.setdefault("transition_nodes", {})[t.id] = tid
        if not _link_point(
            tid, nodes, edges, add_node, add_edge, rprep, wall_hard, params.door_link_max_m * px, "corridor"
        ):
            issues.append(Issue("TRANSITION_UNLINKED", f"{t.type} could not be linked to the graph", t.id))
    _bridge_components(
        nodes,
        edges,
        add_node,
        add_edge,
        rprep,
        wall_hard,
        params.door_link_max_m * px,
        issues,
        _region_mask(region, walk.shape),
    )
    return NavGraph(nodes=nodes, edges=edges), issues


def _region_mask(region, shape) -> np.ndarray:
    """Rasterise the validity region (walkable + tolerance - wall bands), shrunk 1 px for safety."""
    m = np.zeros(shape, np.uint8)
    geoms = getattr(region, "geoms", [region])
    for poly in geoms:
        if poly.is_empty or poly.geom_type != "Polygon":
            continue
        cv2.fillPoly(m, [np.round(np.asarray(poly.exterior.coords)).astype(np.int32)], 1)
        for hole in poly.interiors:
            cv2.fillPoly(m, [np.round(np.asarray(hole.coords)).astype(np.int32)], 0)
    return cv2.erode(m, np.ones((3, 3), np.uint8)) > 0


def _routed_path(mask: np.ndarray, a: tuple[float, float], b: tuple[float, float]) -> list | None:
    """Shortest raster path from a to b staying inside ``mask`` (None if impossible)."""
    from skimage.graph import route_through_array

    h, w = mask.shape

    def snap(p):
        x, y = int(round(p[0])), int(round(p[1]))
        if 0 <= y < h and 0 <= x < w and mask[y, x]:
            return y, x
        ys, xs = np.nonzero(mask[max(y - 6, 0) : y + 7, max(x - 6, 0) : x + 7])
        if len(xs) == 0:
            return None
        i = int(np.argmin((xs + max(x - 6, 0) - x) ** 2 + (ys + max(y - 6, 0) - y) ** 2))
        return int(ys[i] + max(y - 6, 0)), int(xs[i] + max(x - 6, 0))

    sa, sb = snap(a), snap(b)
    if sa is None or sb is None:
        return None
    cost = np.where(mask, 1.0, 1e6)
    path, total = route_through_array(cost, sa, sb, fully_connected=True, geometric=True)
    if total >= 1e5:
        return None
    return [a] + [(float(x), float(y)) for y, x in path] + [b]


def _bridge_components(nodes, edges, add_node, add_edge, rprep, wall_hard, max_d, issues, valid_mask) -> None:
    """Join small graph components to the largest: first with the shortest valid straight edge, else with
    a routed path through the valid area (repairs breaks at narrow passages, e.g. beside a stairwell).
    Components that can't be joined are reported."""
    unroutable: set[frozenset] = set()  # pieces whose routed fallback already failed: do not route them again
    for _ in range(20):
        g = nx.Graph([(e.a, e.b) for e in edges])
        g.add_nodes_from(nodes)
        comps = sorted(nx.connected_components(g), key=len, reverse=True)
        if len(comps) <= 1:
            return
        main = comps[0]
        main_xy = np.array([(nodes[n].x, nodes[n].y) for n in main])
        main_ids = list(main)
        joined = False
        for comp in comps[1:]:
            best = None
            for n in comp:
                d = np.hypot(main_xy[:, 0] - nodes[n].x, main_xy[:, 1] - nodes[n].y)
                for j in np.argsort(d)[:8]:
                    if d[j] > max_d:
                        break
                    m = main_ids[j]
                    if (best is None or d[j] < best[0]) and _segment_ok(
                        (nodes[n].x, nodes[n].y), (nodes[m].x, nodes[m].y), rprep, wall_hard
                    ):
                        best = (d[j], n, m)
                        break
            if best:
                add_edge(best[1], best[2])
                joined = True
                break
            # routed fallback: nearest node pair (by distance), path through the valid raster
            key = frozenset(comp)
            if key in unroutable:
                continue
            pairs = []
            hub = np.array([nodes[m].kind in ("corridor", "junction") for m in main_ids])
            for n in comp:
                d = np.hypot(main_xy[:, 0] - nodes[n].x, main_xy[:, 1] - nodes[n].y)
                d = np.where(hub, d, np.inf)  # bridge to corridor/junction nodes, not doors in wall gaps
                j = int(np.argmin(d))
                if np.isfinite(d[j]):
                    pairs.append((d[j], n, main_ids[j]))
            pairs.sort()
            for _d, n, m in pairs[:3]:
                path = _routed_path(valid_mask, (nodes[n].x, nodes[n].y), (nodes[m].x, nodes[m].y))
                if path is None:
                    continue
                simp = greedy_visible(path, rprep, wall_hard)
                if not simp:
                    continue
                ids = [n] + [add_node(p) for p in simp[1:-1]] + [m]
                for u, v in zip(ids[:-1], ids[1:], strict=False):
                    add_edge(u, v)
                joined = True
                break
            if joined:
                break
            unroutable.add(key)
        if not joined:
            for comp in comps[1:]:
                issues.append(
                    Issue(
                        "GRAPH_COMPONENT_ISOLATED",
                        f"{len(comp)} nodes could not be joined to the main graph",
                        sorted(comp)[0],
                    )
                )
            return


def _link_point(did: str, nodes, edges, add_node, add_edge, rprep, wall_hard, max_d, edge_type: str) -> bool:
    """Connect node ``did`` to the nearest corridor edge with a straight, wall-safe segment."""
    c = (nodes[did].x, nodes[did].y)
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
        add_edge(did, mid, edge_type)
        return True
    return False
