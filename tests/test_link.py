"""Multi-floor linking (FR-18)."""

from turn_mapper.link import cross_floor_path_m, link_floors


def _floor(nodes, w=30.0, h=12.0):
    edges = [
        {
            "id": f"e{i}",
            "from": a["id"],
            "to": b["id"],
            "length_m": abs(a["x"] - b["x"]) + abs(a["y"] - b["y"]),
        }
        for i, (a, b) in enumerate(zip(nodes, nodes[1:], strict=False))
    ]
    return {
        "bounds_m": {"min_x": 0.0, "min_y": 0.0, "max_x": w, "max_y": h},
        "graph": {"nodes": nodes, "edges": edges},
    }


def _n(i, x, y, t=None):
    return {"id": i, "x": x, "y": y, **({"transition": t} if t else {})}


def _two():
    f0 = _floor([_n("a", 2, 5), _n("s", 10, 5, "stairs"), _n("l", 20, 5, "lift"), _n("z", 28, 5)])
    f1 = _floor([_n("a", 2, 5), _n("s", 10.8, 5.2, "stairs"), _n("l", 20, 5.1, "lift"), _n("z", 28, 5)])
    meta = [
        ({"id": "C-GF", "building_id": "C", "level": 0}, f0),
        ({"id": "C-F1", "building_id": "C", "level": 1}, f1),
    ]
    return meta, {"C-GF": f0, "C-F1": f1}


def test_auto_links_pair_by_type_and_position():
    meta, fl = _two()
    links, warns = link_floors(meta)
    pairs = {(k["type"], k["from"]["node_id"], k["to"]["node_id"]) for k in links}
    assert pairs == {("stairs", "s", "s"), ("lift", "l", "l")}
    assert not warns
    assert all(k["provenance"]["source"] == "auto" and k["length_estimated"] for k in links)
    assert [k["accessible"] for k in links if k["type"] == "lift"] == [True]
    d = cross_floor_path_m(fl, links, ("C-GF", "a"), ("C-F1", "z"))
    assert d is not None and abs(d - 30.1) < 0.2  # 8 to stairs + 6 stairs + 16.1 across


def test_far_apart_stairs_are_not_linked_and_reported():
    meta, _ = _two()
    meta[1][1]["graph"]["nodes"][1]["x"] = 25.0  # stairs moved 15 m
    links, warns = link_floors(meta)
    assert {k["type"] for k in links} == {"lift"}
    assert sum(w["code"] == "LINK_UNMATCHED" for w in warns) == 2


def test_manual_link_wins_and_dangling_is_reported():
    meta, fl = _two()
    manual = [
        {
            "from": {"floor_id": "C-GF", "node_id": "s"},
            "to": {"floor_id": "C-F1", "node_id": "l"},
            "type": "stairs",
        },
        {"from": {"floor_id": "C-GF", "node_id": "nope"}, "to": {"floor_id": "C-F1", "node_id": "l"}},
    ]
    links, warns = link_floors(meta, manual)
    assert links[0]["provenance"]["source"] == "manual"
    assert any(w["code"] == "LINK_DANGLING" for w in warns)
    assert ("C-GF", "s") not in {(k["from"]["floor_id"], k["from"]["node_id"]) for k in links[1:]}


def test_level_gap_and_other_buildings_not_linked():
    meta, _ = _two()
    meta[1][0]["level"] = 3
    links, warns = link_floors(meta)
    assert links == [] and warns[0]["code"] == "LINK_LEVEL_GAP"
    meta, _ = _two()
    meta[1][0]["building_id"] = "B"
    assert link_floors(meta)[0] == []


def test_stairs_filter_drops_door_arc_keeps_flight():
    import cv2
    import numpy as np
    from shapely.geometry import MultiPolygon, box

    from turn_mapper.ir import GeometryPx, Segmentation
    from turn_mapper.transitions import find_transitions

    m = np.zeros((300, 300), bool)
    walk = np.ones((300, 300), bool)
    st = np.zeros((300, 300), np.uint8)
    cv2.ellipse(st, (60, 60), (40, 40), 0, 0, 90, 1, 3)  # door swing arc: 3 px line
    st[150:230, 150:200] = 1  # a real flight, 80x50 px
    scale = 0.02
    seg = Segmentation(wall=m, floor=walk, background=m, levels={}, method="t", stairs=st.astype(bool))
    geom = GeometryPx(
        regions=[],
        doors=[],
        walkable=MultiPolygon(),
        wall_segments=[],
        wall_mask_closed=m,
        debug={"walk_mask": walk},
    )
    issues = find_transitions(geom, seg, scale)
    assert len(geom.transitions) == 1
    assert box(150, 150, 200, 230).contains(geom.transitions[0].polygon.centroid)
    assert any(i.code == "STAIRS_TOO_SMALL" for i in issues)
