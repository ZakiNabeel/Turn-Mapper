"""Floor registration, scale correction, optimal matching, shafts and config connections (link.py)."""

import pytest

from turn_mapper.link import (
    _apply,
    building_frames,
    link_floors,
    link_venue,
    register_floors,
    resolve_place,
)

# an asymmetric wall layout (metres): outer box, a corridor wall, a few partitions
WALLS = [
    ((0, 0), (40, 0)),
    ((40, 0), (40, 16)),
    ((40, 16), (0, 16)),
    ((0, 16), (0, 0)),
    ((0, 6), (28, 6)),
    ((8, 0), (8, 6)),
    ((19, 0), (19, 6)),
    ((28, 6), (28, 16)),
    ((12, 6), (12, 16)),
    ((33, 0), (33, 3)),
]


def _floor(k=1.0, dx=0.0, dy=0.0, source="operator_two_point", tnodes=()):
    """The layout drawn at scale ``k`` (a floor whose metres are off by 1/k) and shifted by (dx, dy)."""

    def p(q):
        return [q[0] * k + dx, q[1] * k + dy]

    walls = [{"a": p(a), "b": p(b), "thickness_m": 0.2} for a, b in WALLS]
    nodes = [{"id": "c0", "x": p((2, 3))[0], "y": p((2, 3))[1]}]
    for nid, kind, q in tnodes:
        x, y = p(q)
        nodes.append({"id": nid, "x": x, "y": y, "transition": kind})
    edges = [
        {"id": f"e{i}", "from": "c0", "to": n["id"], "length_m": abs(n["x"] - nodes[0]["x"])}
        for i, n in enumerate(nodes[1:])
    ]
    xs = [v for w in walls for v in (w["a"][0], w["b"][0])]
    ys = [v for w in walls for v in (w["a"][1], w["b"][1])]
    return {
        "bounds_m": {"min_x": min(xs), "min_y": min(ys), "max_x": max(xs), "max_y": max(ys)},
        "walls": walls,
        "doors": [],
        "rooms": [],
        "walkable": {"type": "Polygon", "coordinates": []},
        "transform": {
            "px_to_m": [[0.04, 0, 0], [0, 0.04, 0]],
            "scale_m_per_px": 0.04,
            "scale_source": source,
        },
        "graph": {"nodes": nodes, "edges": edges},
    }


def test_registration_recovers_shift_and_scale():
    fa = _floor()
    fb = _floor(k=1 / 1.2, dx=3.0, dy=-2.0)  # fb's metres are 1.2x too small and shifted
    r = register_floors(fa, fb)
    assert r["method"] == "walls" and r["score"] > 0.6
    assert r["scale"] == pytest.approx(1.2, rel=0.03)
    for _a, b in WALLS[:5]:  # fb's wall corners land on fa's
        x, y = _apply(r["matrix"], b[0] / 1.2 + 3.0, b[1] / 1.2 - 2.0)
        assert abs(x - b[0]) < 0.6 and abs(y - b[1]) < 0.6


def test_no_walls_falls_back_to_bounds():
    fa, fb = _floor(), _floor()
    fb["walls"] = []
    meta = [
        ({"id": "X0", "building_id": "X", "level": 0}, fa),
        ({"id": "X1", "building_id": "X", "level": 1}, fb),
    ]
    frames, _ = building_frames(meta)
    assert frames["X0"]["method"] == "reference" and frames["X1"]["method"] in ("bounds", "none")


def _venue(k1=1.0, src1="operator_two_point"):
    stairs = [("s", "stairs", (5, 3)), ("l", "lift", (36, 10))]
    f0 = _floor(tnodes=stairs)
    f1 = _floor(k=k1, dx=4.0, dy=1.0, source=src1, tnodes=stairs)
    f2 = _floor(dx=-2.0, tnodes=stairs)
    return [
        ({"id": "T0", "building_id": "T", "level": 0}, f0),
        ({"id": "T1", "building_id": "T", "level": 1}, f1),
        ({"id": "T2", "building_id": "T", "level": 2}, f2),
    ]


def test_link_venue_aligns_shifted_floors_and_builds_shafts():
    floors = _venue()
    out = link_venue(floors)
    vert = [t for t in out["transitions"] if t["type"] in ("stairs", "lift")]
    assert len(vert) == 4  # stairs and lift, T0-T1 and T1-T2: the middle node links both ways
    assert {t["shaft"] for t in vert if t["type"] == "stairs"} != {
        t["shaft"] for t in vert if t["type"] == "lift"
    }
    assert len({t["shaft"] for t in vert if t["type"] == "stairs"}) == 1
    assert all(t["match_distance_m"] < 1.0 for t in vert)  # in the building frame they coincide
    assert floors[1][1]["building_frame"]["method"] == "walls"
    assert not out["rescaled"]


def test_estimated_scale_is_corrected_from_a_measured_floor():
    floors = _venue(k1=1 / 1.25, src1="door_width_prior")  # T1's estimate is 25 % short
    out = link_venue(floors)
    assert out["rescaled"]["T1"] == pytest.approx(1.25, rel=0.03)
    t = floors[1][1]["transform"]
    assert t["scale_source"] == "footprint_transfer"
    assert t["scale_evidence"][-1]["method"] == "wall_registration"
    assert floors[1][1]["building_frame"]["scale_corrected"]
    assert any(w["code"] == "SCALE_FROM_REGISTRATION" for w in out["warnings"])
    off = link_venue(_venue(k1=1 / 1.25, src1="door_width_prior"), correct_scales=False)
    assert not off["rescaled"]


def test_a_measured_floor_is_never_rescaled():
    floors = _venue(k1=1 / 1.25)  # both measured but disagreeing: warn, don't change
    out = link_venue(floors)
    assert not out["rescaled"]
    assert any(w["code"] == "LINK_SCALE_DISAGREES" for w in out["warnings"])


def test_hungarian_beats_greedy():
    # two stair nodes per floor; greedy nearest-first would pair a0-b0 (0.9 m) and leave a1-b1 at 9 m
    def fl(nodes):
        return {
            "bounds_m": {"min_x": 0, "min_y": 0, "max_x": 30, "max_y": 10},
            "graph": {
                "nodes": [{"id": i, "x": x, "y": 5, "transition": "stairs"} for i, x in nodes],
                "edges": [],
            },
        }

    fa, fb = fl([("a0", 10.0), ("a1", 4.0)]), fl([("b0", 10.9), ("b1", 13.0)])
    meta = [
        ({"id": "P0", "building_id": "P", "level": 0}, fa),
        ({"id": "P1", "building_id": "P", "level": 1}, fb),
    ]
    links, _ = link_floors(meta)
    pairs = {(k["from"]["node_id"], k["to"]["node_id"]) for k in links}
    assert pairs == {("a0", "b1"), ("a1", "b0")}  # both matched, within the cap


def test_resolve_place_and_connections():
    floors = _venue()
    by_id = {m["id"]: fl for m, fl in floors}
    by_id["T0"]["pois"] = [{"id": "p1", "label": "R-101", "name": "Room 101", "node_id": "s"}]
    assert resolve_place(by_id, "T0:s") == ("T0", "s")
    assert resolve_place(by_id, "T0:R-101") == ("T0", "s")
    assert resolve_place(by_id, "T0:36.2,10.1") == ("T0", "l")
    with pytest.raises(KeyError):
        resolve_place(by_id, "T9:s")
    out = link_venue(
        floors, connections=[{"from": "T0:c0", "to": "T2:c0", "type": "walkway", "length_m": 12}]
    )
    w = [t for t in out["transitions"] if t["type"] == "walkway"]
    assert len(w) == 1 and w[0]["length_m"] == 12 and w[0]["provenance"]["source"] == "manual"
    bad = link_venue(_venue(), connections=[{"from": "T0:nowhere", "to": "T2:c0"}])
    assert any(x["code"] == "LINK_CONNECTION_UNRESOLVED" for x in bad["warnings"])


def test_lift_missing_on_middle_floors_is_reported_not_linked():
    floors = [
        (
            {"id": f"T{lv}", "building_id": "T", "level": lv},
            _floor(tnodes=[("l", "lift", (36, 10))] if lv in (0, 3) else ()),
        )
        for lv in range(4)
    ]
    out = link_venue(floors)
    assert not [t for t in out["transitions"] if t["type"] == "lift"]
    gap = [w for w in out["warnings"] if w["code"] == "LINK_SHAFT_GAP"]
    assert len(gap) == 1 and "T1, T2" in gap[0]["message"]


def test_lift_stop_is_proposed_on_a_missed_floor_when_floors_are_aligned():
    lift = [("l", "lift", (36, 10))]
    near = [("c1", None, (35, 11))]  # an ordinary corridor node beside the shaft

    def fl(tn):
        f = _floor(tnodes=[t for t in tn if t[1]])
        for nid, kind, q in tn:
            if not kind:
                f["graph"]["nodes"].append({"id": nid, "x": q[0], "y": q[1], "kind": "corridor"})
                f["graph"]["edges"].append({"id": "ex", "from": "c0", "to": nid, "length_m": 30.0})
        return f

    floors = [
        ({"id": "T0", "building_id": "T", "level": 0}, fl(lift)),
        ({"id": "T1", "building_id": "T", "level": 1}, fl(near)),
        ({"id": "T2", "building_id": "T", "level": 2}, fl(lift)),
    ]
    out = link_venue(floors)
    lifts = [t for t in out["transitions"] if t["type"] == "lift"]
    assert [(t["from"]["floor_id"], t["to"]["floor_id"]) for t in lifts] == [("T0", "T1"), ("T1", "T2")]
    assert lifts[0]["to"]["node_id"] == "c1"
    assert all(t["provenance"] == {"source": "auto", "confidence": 0.4} for t in lifts)
    assert any(w["code"] == "LINK_SHAFT_INFERRED" for w in out["warnings"])


def test_side_ends_and_building_level_connections():
    from turn_mapper.link import expand_connections, side_node

    f0 = _venue()[0][1]
    assert side_node(f0, "left") == "c0" and side_node(f0, "right") == "l"  # extreme nodes of the graph
    two = [
        ({"id": "P0", "building_id": "P", "level": 0}, _floor()),
        ({"id": "P1", "building_id": "P", "level": 1}, _floor()),
        ({"id": "Q0", "building_id": "Q", "level": 0}, _floor()),
        ({"id": "Q1", "building_id": "Q", "level": 1}, _floor()),
        ({"id": "Q2", "building_id": "Q", "level": 2}, _floor()),
    ]
    ex = expand_connections([{"from": "P@right", "to": "Q@left", "type": "walkway"}], two)
    assert [(c["from"], c["to"]) for c in ex] == [("P0@right", "Q0@left"), ("P1@right", "Q1@left")]
    ex = expand_connections([{"from": "P@right", "to": "Q@left", "levels": [1]}], two)
    assert [(c["from"], c["to"]) for c in ex] == [("P1@right", "Q1@left")]
    keep = [{"from": "P0:c0", "to": "Q0:c0"}]
    assert expand_connections(keep, two) == keep
    out = link_venue(two, connections=[{"from": "P@right", "to": "Q@left", "levels": [0, 1]}])
    w = [t for t in out["transitions"] if t["type"] == "walkway"]
    assert len(w) == 2 and all(t["provenance"] == {"source": "auto", "confidence": 0.5} for t in w)
    assert sum(x["code"] == "LINK_ENDPOINT_ESTIMATED" for x in out["warnings"]) == 2
    bad = link_venue(
        two,
        connections=[
            {"from": "P0@sideways", "to": "Q0@left"},
            {"from": "P@left", "to": "Q@left", "levels": [7]},
        ],
    )
    assert sum(x["code"] == "LINK_CONNECTION_UNRESOLVED" for x in bad["warnings"]) == 2
