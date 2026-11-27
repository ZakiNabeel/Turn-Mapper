"""Venue routing: one route across floors and buildings, from a ``venue.json`` / ``.turnmap``.

The venue graph joins every floor's graph (nodes ``(floor_id, node_id)``) with the venue ``transitions``
(stairs, lifts, escalators, ramps and walkways from multi-floor linking, manual links and the venue
``connections``). Routes minimise estimated walking **time**, so a lift (waiting time) and stairs (time per
level) are compared fairly; the route also reports its length in metres.

``step_free=True`` leaves out stairs and escalators and any edge marked ``accessible: false``.

Everything a route reports is derived from the package: per-floor legs (node ids and metric points in that
floor's frame), floor changes and plain-language instructions. Stair/lift lengths are estimates unless the
link says ``length_estimated: false``.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import networkx as nx

# Walking speed and vertical-travel times (seconds). Typical values for indoor wayfinding; venue configs can
# override them. They only rank routes; the route length in metres is reported separately.
DEFAULT_COSTS = {
    "walk_mps": 1.3,
    "stairs_s_per_level": 20.0,
    "escalator_s_per_level": 15.0,
    "lift_wait_s": 30.0,
    "lift_s_per_level": 5.0,
    "ramp_mps": 1.1,
}
STEP_FREE_OK = {"lift", "ramp", "walkway"}
VERTICAL = {"stairs", "lift", "escalator"}


@dataclass
class Place:
    floor_id: str
    node_id: str
    name: str
    x: float
    y: float
    label: str | None = None
    kind: str = "poi"  # poi | node


@dataclass
class Leg:
    floor_id: str
    floor_name: str
    nodes: list[str]
    points: list[tuple[float, float]]
    length_m: float


@dataclass
class Change:
    link_id: str
    type: str
    from_floor: str
    to_floor: str
    levels: int  # signed: + up, - down
    length_m: float
    length_estimated: bool


@dataclass
class Route:
    start: Place
    end: Place
    legs: list[Leg]
    changes: list[Change]
    length_m: float
    time_s: float
    step_free: bool
    instructions: list[str] = field(default_factory=list)

    @property
    def floors(self) -> list[str]:
        return [leg.floor_id for leg in self.legs]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["floors"] = self.floors
        d["length_m"] = round(self.length_m, 1)
        d["time_s"] = round(self.time_s)
        return d


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


class VenueGraph:
    """All floors of a venue as one routable graph."""

    def __init__(
        self,
        venue: dict,
        floors: dict[str, dict],
        extra_links: list[dict] | None = None,
        costs: dict | None = None,
    ):
        self.venue = venue
        self.floors = floors
        self.costs = {**DEFAULT_COSTS, **(costs or {})}
        self.meta = {f["id"]: f for f in venue.get("floors", [])}
        self.links = list(venue.get("transitions") or []) + list(extra_links or [])
        self.g = nx.Graph()
        self.nodes: dict[tuple[str, str], tuple[float, float]] = {}
        walk = self.costs["walk_mps"]
        for fid, fl in floors.items():
            for n in fl["graph"]["nodes"]:
                self.nodes[(fid, n["id"])] = (float(n["x"]), float(n["y"]))
                self.g.add_node((fid, n["id"]))
            for e in fl["graph"]["edges"]:
                a, b = (fid, e["from"]), (fid, e["to"])
                if a not in self.nodes or b not in self.nodes:
                    continue
                length = float(e["length_m"])
                self.g.add_edge(
                    a,
                    b,
                    length=length,
                    time=length / walk,
                    kind="floor",
                    step_free=e.get("accessible") is not False,
                    link=None,
                )
        for k in self.links:
            a = (k["from"]["floor_id"], k["from"]["node_id"])
            b = (k["to"]["floor_id"], k["to"]["node_id"])
            if a not in self.nodes or b not in self.nodes or a == b:
                continue
            kind = k.get("type") or "stairs"
            length = float(k.get("length_m") or 0.0)
            levels = abs(self.level(b[0]) - self.level(a[0]))
            self.g.add_edge(
                a,
                b,
                length=length,
                time=self._link_time(kind, length, levels),
                kind=kind,
                step_free=(kind in STEP_FREE_OK) and k.get("accessible") is not False,
                link=k,
            )

    # ---- construction helpers -------------------------------------------------------------------
    @classmethod
    def from_package(cls, path: str | Path, **kw) -> VenueGraph:
        from .export import read_package

        pkg = read_package(str(path))
        return cls(pkg["venue"], pkg["floors"], **kw)

    def level(self, fid: str) -> int:
        return int(self.meta.get(fid, {}).get("level") or 0)

    def floor_name(self, fid: str) -> str:
        return self.meta.get(fid, {}).get("name") or fid

    def _link_time(self, kind: str, length: float, levels: int) -> float:
        c = self.costs
        if kind == "stairs":
            return max(levels, 1) * c["stairs_s_per_level"]
        if kind == "escalator":
            return max(levels, 1) * c["escalator_s_per_level"]
        if kind == "lift":
            return c["lift_wait_s"] + max(levels, 1) * c["lift_s_per_level"]
        if kind == "ramp":
            return length / c["ramp_mps"]
        return length / c["walk_mps"]  # walkway

    # ---- places -----------------------------------------------------------------------------------
    def places(self) -> list[Place]:
        out = []
        for fid, fl in self.floors.items():
            for p in fl.get("pois", []):
                xy = self.nodes.get((fid, p["node_id"]))
                if xy is None:
                    continue
                out.append(Place(fid, p["node_id"], p["name"], xy[0], xy[1], p.get("label")))
        return out

    def find_place(self, query: str, floor_id: str | None = None) -> list[Place]:
        """Places matching ``query``: ``FLOOR:node_id``, an exact room label/name, or a part of one."""
        if ":" in query:
            fid, rest = query.split(":", 1)
            if (fid, rest) in self.nodes:
                x, y = self.nodes[(fid, rest)]
                return [Place(fid, rest, f"{fid} {rest}", x, y, kind="node")]
            if fid in self.floors:  # FLOOR:label or FLOOR:name
                return self.find_place(rest, floor_id=fid)
        q = _norm(query)
        if not q:
            return []
        cand = [p for p in self.places() if floor_id in (None, p.floor_id)]
        exact = [p for p in cand if q in (_norm(p.label), _norm(p.name))]
        if exact:
            return exact
        return [p for p in cand if q in _norm(p.name) or (p.label and q in _norm(p.label))]

    # ---- routing ----------------------------------------------------------------------------------
    def route(self, start: Place | str, end: Place | str, step_free: bool = False) -> Route | None:
        a = start if isinstance(start, Place) else self._one(start)
        b = end if isinstance(end, Place) else self._one(end)
        g = self.g
        if step_free:
            g = nx.subgraph_view(self.g, filter_edge=lambda u, v: self.g[u][v]["step_free"])
        try:
            path = nx.shortest_path(g, (a.floor_id, a.node_id), (b.floor_id, b.node_id), weight="time")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
        legs: list[Leg] = []
        changes: list[Change] = []
        cur: list[tuple[str, str]] = [path[0]]
        length = time = 0.0
        for u, v in zip(path, path[1:], strict=False):
            ed = g[u][v]
            length += ed["length"]
            time += ed["time"]
            if ed["kind"] == "floor":
                cur.append(v)
                continue
            legs.append(self._leg(cur))
            k = ed["link"]
            changes.append(
                Change(
                    link_id=k.get("id", ""),
                    type=ed["kind"],
                    from_floor=u[0],
                    to_floor=v[0],
                    levels=self.level(v[0]) - self.level(u[0]),
                    length_m=ed["length"],
                    length_estimated=bool(k.get("length_estimated", True)),
                )
            )
            cur = [v]
        legs.append(self._leg(cur))
        r = Route(a, b, legs, changes, length, time, step_free)
        r.instructions = self._instructions(r)
        return r

    def _one(self, query: str) -> Place:
        found = self.find_place(query)
        if not found:
            raise KeyError(f"no place matches {query!r}")
        if len(found) > 1 and len({(p.floor_id, p.node_id) for p in found}) > 1:
            names = ", ".join(f"{p.name} ({p.floor_id})" for p in found[:6])
            raise KeyError(f"{query!r} is ambiguous: {names}")
        return found[0]

    def _leg(self, nodes: list[tuple[str, str]]) -> Leg:
        pts = [self.nodes[n] for n in nodes]
        length = sum(math.dist(p, q) for p, q in zip(pts, pts[1:], strict=False))
        fid = nodes[0][0]
        return Leg(fid, self.floor_name(fid), [n[1] for n in nodes], pts, length)

    # ---- instructions -----------------------------------------------------------------------------
    def _instructions(self, r: Route) -> list[str]:
        out = [f"Start at {r.start.name} ({self.floor_name(r.start.floor_id)})."]
        i = 0
        legs, changes = r.legs, r.changes
        while i < len(legs):
            out += _walk_steps(legs[i].points)
            if i >= len(changes):
                break
            # merge consecutive changes of one kind with no walking in between (one stair shaft, one lift)
            j = i
            while (
                j + 1 < len(changes) and changes[j + 1].type == changes[i].type and legs[j + 1].length_m < 0.5
            ):
                j += 1
            c0, c1 = changes[i], changes[j]
            levels = sum(c.levels for c in changes[i : j + 1])
            dest = self.floor_name(c1.to_floor)
            if c0.type in VERTICAL:
                verb = {
                    "stairs": "Take the stairs",
                    "lift": "Take the lift",
                    "escalator": "Take the escalator",
                }
                n = abs(levels)
                where = f"{'up' if levels > 0 else 'down'} {n} floor{'s' if n != 1 else ''} " if n else ""
                out.append(f"{verb[c0.type]} {where}to {dest}.")
            else:
                if c1.length_m < 0.5:  # the buildings meet: the corridor simply continues
                    out.append(f"Continue into {dest}.")
                else:
                    out.append(f"Follow the {c0.type} ({c1.length_m:.0f} m) to {dest}.")
            i = j + 1
        out.append(f"Arrive at {r.end.name}.")
        return out


def _walk_steps(
    pts: list[tuple[float, float]], turn_deg: float = 35.0, simplify_m: float = 1.0, min_seg_m: float = 3.0
) -> list[str]:
    """'Walk 12 m', 'Turn left and walk 8 m' along one floor's path (frame: x right, y down).

    The graph path zigzags through door and junction nodes, so it is simplified first (1 m tolerance) and
    segments shorter than 3 m are folded into their neighbours: only turns a person notices are announced."""
    from shapely.geometry import LineString

    p = [pts[0]] if pts else []
    for q in pts[1:]:
        if math.dist(p[-1], q) > 1e-6:
            p.append(q)
    if len(p) < 2:
        return []
    p = list(LineString(p).simplify(simplify_m).coords) if len(p) > 2 else p
    segs: list[list[float]] = []  # [heading, length]
    for a, b in zip(p, p[1:], strict=False):
        segs.append([math.atan2(b[1] - a[1], b[0] - a[0]), math.dist(a, b)])
    merged: list[list[float]] = []
    for h, d in segs:
        if merged and (abs(_angle(merged[-1][0], h)) < math.radians(turn_deg) or d < min_seg_m):
            ph, pd = merged[-1]
            merged[-1] = [ph if pd >= d else h, pd + d]
        else:
            merged.append([h, d])
    if len(merged) > 1 and merged[0][1] < min_seg_m:  # a short first step out of a doorway: no turn
        h, d = merged.pop(0)
        merged[0][1] += d
    steps = []
    for k, (h, d) in enumerate(merged):
        if k == 0:
            steps.append(f"Walk {d:.0f} m.")
            continue
        turn = _angle(merged[k - 1][0], h)  # + = clockwise on screen (y down) = right
        side = "right" if turn > 0 else "left"
        sharp = "sharp " if abs(turn) > math.radians(135) else ""
        steps.append(f"Turn {sharp}{side} and walk {d:.0f} m.")
    return steps


def _angle(h0: float, h1: float) -> float:
    return (h1 - h0 + math.pi) % (2 * math.pi) - math.pi


# ---- venue checks ---------------------------------------------------------------------------------
ESTIMATED_SCALES = ("door_width_prior", "door_width_calibrated", "footprint_transfer")


def floor_quality(
    pieces: int,
    destinations: int,
    destinations_on_main: int,
    scale_source: str | None,
    transitions: int,
    transitions_linked: int,
    multi_floor_building: bool,
    reaches_building: bool,
) -> dict:
    """A floor's readiness for routing.

    'ready': one graph piece, every destination on it, measured scale, every stair/lift linked.
    'usable': >= 90 % of destinations reachable and, in a multi-floor building, joined to another floor.
    Else 'needs work'.
    ``reasons`` says what keeps the floor from 'ready'."""
    reasons = []
    measured = bool(scale_source) and scale_source not in ESTIMATED_SCALES
    share = destinations_on_main / destinations if destinations else 1.0
    if destinations == 0:
        reasons.append("no destinations found")
    if pieces > 1:
        reasons.append(f"{pieces} graph pieces")
    if share < 1:
        reasons.append(
            f"{destinations - destinations_on_main} of {destinations} destinations off the main graph"
        )
    if not measured:
        reasons.append(f"scale is an estimate ({scale_source})")
    if transitions_linked < transitions:
        reasons.append(
            f"{transitions - transitions_linked} of {transitions} stairs/lifts not linked to another floor"
        )
    if multi_floor_building and not reaches_building:
        reasons.append("no route to another floor of its building")
    if not reasons:
        grade = "ready"
    elif destinations and share >= 0.9 and (reaches_building or not multi_floor_building):
        grade = "usable"
    else:
        grade = "needs work"
    return {
        "grade": grade,
        "pieces": pieces,
        "destinations_reachable": round(share, 3),
        "scale_measured": measured,
        "transitions_linked": f"{transitions_linked}/{transitions}",
        "reasons": reasons,
    }


def venue_checks(vg: VenueGraph, samples: int = 200, seed: int = 0) -> dict:
    """Multi-floor checks over destinations (POIs): which floors reach which, floors of a building that reach
    none of its other floors, buildings not joined to each other, stairs/lift nodes stranded off their floor's
    main graph piece, and a sample of cross-floor routes (all, and step-free)."""
    import random

    places = vg.places()
    by_floor: dict[str, list[Place]] = {}
    for p in places:
        by_floor.setdefault(p.floor_id, []).append(p)
    comp_of: dict[tuple[str, str], int] = {}
    for i, c in enumerate(nx.connected_components(vg.g)):
        for n in c:
            comp_of[n] = i
    comps_of_floor = {f: {comp_of[(p.floor_id, p.node_id)] for p in ps} for f, ps in by_floor.items()}
    floors_with = sorted(by_floor)
    reach = {a: {b: bool(comps_of_floor[a] & comps_of_floor[b]) for b in floors_with} for a in floors_with}
    bld = {fid: (vg.meta.get(fid, {}).get("building_id") or "") for fid in vg.floors}
    warnings = []
    per_floor = {}
    for fid in vg.floors:
        same = [b for b in floors_with if b != fid and bld[b] == bld[fid]]
        n_reach = sum(reach.get(fid, {}).get(b, False) for b in same)
        per_floor[fid] = {"destinations": len(by_floor.get(fid, [])), "reaches_floors_in_building": n_reach}
        if fid in by_floor and same and n_reach == 0:
            warnings.append(
                {
                    "code": "W_FLOOR_UNLINKED",
                    "message": f"{fid}: no destination on another floor of building {bld[fid]} is reachable",
                }
            )
    groups: list[set[str]] = []  # buildings joined by any route
    for b in sorted(set(bld.values())):
        fl_b = [f for f in floors_with if bld[f] == b]
        hit = [g for g in groups if any(reach[f][x] for f in fl_b for x in floors_with if bld[x] in g)]
        merged = {b}.union(*hit) if hit else {b}
        groups = [g for g in groups if g not in hit] + [merged]
    if len(groups) > 1:
        names = " | ".join(", ".join(sorted(g)) for g in groups)
        warnings.append(
            {
                "code": "W_BUILDINGS_SEPARATE",
                "message": f"no route between these building groups: {names}. Add walkways in the venue "
                "config (multifloor.connections) or links in Studio",
            }
        )
    linked = {(k["from"]["floor_id"], k["from"]["node_id"]) for k in vg.links}
    linked |= {(k["to"]["floor_id"], k["to"]["node_id"]) for k in vg.links}
    for fid, fl in vg.floors.items():
        fg = nx.Graph()
        fg.add_nodes_from(n["id"] for n in fl["graph"]["nodes"])
        fg.add_edges_from((e["from"], e["to"]) for e in fl["graph"]["edges"])
        if fg.number_of_nodes() == 0:
            continue
        comps = list(nx.connected_components(fg))
        big = max(comps, key=len)
        tnodes = [n for n in fl["graph"]["nodes"] if n.get("transition")]
        for n in tnodes:
            if n["id"] not in big:
                warnings.append(
                    {
                        "code": "W_TRANSITION_STRANDED",
                        "message": f"{fid}:{n['id']} ({n['transition']}) is off the floor's main graph piece",
                    }
                )
        pois = fl.get("pois", [])
        n_main = sum(p["node_id"] in big for p in pois)
        same = per_floor.get(fid, {}).get("reaches_floors_in_building")
        has_same = any(b != fid and bld[b] == bld[fid] for b in vg.floors)
        per_floor.setdefault(fid, {"destinations": len(pois), "reaches_floors_in_building": 0})
        per_floor[fid]["quality"] = floor_quality(
            pieces=len(comps),
            destinations=len(pois),
            destinations_on_main=n_main,
            scale_source=(fl.get("transform") or {}).get("scale_source"),
            transitions=len(tnodes),
            transitions_linked=sum((fid, n["id"]) in linked for n in tnodes),
            multi_floor_building=has_same,
            reaches_building=bool(same),
        )
    rng = random.Random(seed)
    tried = ok = ok_sf = 0
    if len(floors_with) > 1:
        for _ in range(samples):
            fa, fb = rng.sample(floors_with, 2)
            p, q = rng.choice(by_floor[fa]), rng.choice(by_floor[fb])
            tried += 1
            ok += vg.route(p, q) is not None
            ok_sf += vg.route(p, q, step_free=True) is not None
    pairs_total = len(floors_with) * (len(floors_with) - 1)
    pairs_ok = sum(reach[a][b] for a in floors_with for b in floors_with if a != b)
    in_bld = [(a, b) for a in floors_with for b in floors_with if a != b and bld[a] == bld[b]]
    return {
        "floors": per_floor,
        "floor_pairs_connected": pairs_ok,
        "floor_pairs_total": pairs_total,
        "floor_pairs_in_building_connected": sum(reach[a][b] for a, b in in_bld),
        "floor_pairs_in_building_total": len(in_bld),
        "building_groups": [sorted(g) for g in groups],
        "reach": reach,
        "sampled_cross_floor_routes": tried,
        "routed": ok,
        "routed_step_free": ok_sf,
        "transitions": len(vg.links),
        "warnings": warnings,
    }
