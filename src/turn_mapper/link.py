"""Multi-floor linking (FR-18): pair stair/lift graph nodes on adjacent levels of one building.

Fills the reserved ``venue.transitions`` slot (docs/MAP_PACKAGE_SCHEMA.md section 3); no schema change.
Matching is a proposal: same transition type, adjacent level, nearest position after aligning the floors'
bounds (floors of one block share a footprint), with a distance cap. Unmatched nodes are reported, never
guessed. Manual links (from Studio) override auto ones and carry provenance ``manual``.

Default lengths are flagged estimates (``length_estimated``): stairs 6 m, lift 4 m; replace by measurement.
"""

from __future__ import annotations

import math


def _w(code: str, message: str) -> dict:
    return {"code": code, "message": message}


DEFAULT_LEN = {"stairs": 6.0, "lift": 4.0, "escalator": 8.0}
MAX_DIST_M = 4.0


def _tnodes(fl: dict) -> list[dict]:
    return [n for n in fl["graph"]["nodes"] if n.get("transition") in DEFAULT_LEN]


def _aligned(fl: dict, n: dict) -> tuple[float, float]:
    b = fl["bounds_m"]
    return n["x"] - b["min_x"], n["y"] - b["min_y"]


def _footprint_gap(a: dict, b: dict) -> float:
    wa, ha = a["bounds_m"]["max_x"] - a["bounds_m"]["min_x"], a["bounds_m"]["max_y"] - a["bounds_m"]["min_y"]
    wb, hb = b["bounds_m"]["max_x"] - b["bounds_m"]["min_x"], b["bounds_m"]["max_y"] - b["bounds_m"]["min_y"]
    return max(abs(wa - wb) / max(wa, wb, 1e-6), abs(ha - hb) / max(ha, hb, 1e-6))


def _link(tid: str, kind: str, f1: str, n1: str, f2: str, n2: str, source: str, conf: float, d: float | None):
    return {
        "id": tid,
        "type": kind,
        "from": {"floor_id": f1, "node_id": n1},
        "to": {"floor_id": f2, "node_id": n2},
        "length_m": DEFAULT_LEN[kind],
        "length_estimated": True,
        "accessible": True if kind == "lift" else (False if kind == "stairs" else None),
        "provenance": {"source": source, "confidence": round(conf, 2)},
        **({"match_distance_m": round(d, 2)} if d is not None else {}),
    }


def link_floors(
    floors: list[tuple[dict, dict]], manual: list[dict] | None = None, max_dist_m: float = MAX_DIST_M
) -> tuple[list[dict], list[dict]]:
    """floors: [(meta{id,building_id|building,level}, floor_dict)] -> (transitions, warnings)."""
    manual = manual or []
    by_id = {m["id"]: fl for m, fl in floors}
    warns: list[dict] = []
    links: list[dict] = []
    used: set[tuple[str, str]] = set()

    for m in manual:  # manual first: they win
        a, b = m["from"], m["to"]
        try:
            na = next(n for n in by_id[a["floor_id"]]["graph"]["nodes"] if n["id"] == a["node_id"])
            next(n for n in by_id[b["floor_id"]]["graph"]["nodes"] if n["id"] == b["node_id"])
        except (KeyError, StopIteration):
            warns.append(_w("LINK_DANGLING", f"manual link {m} points at a missing node"))
            continue
        kind = m.get("type") or na.get("transition") or "stairs"
        links.append(
            _link(
                f"t{len(links) + 1}",
                kind,
                a["floor_id"],
                a["node_id"],
                b["floor_id"],
                b["node_id"],
                "manual",
                1.0,
                None,
            )
        )
        used |= {(a["floor_id"], a["node_id"]), (b["floor_id"], b["node_id"])}

    blds: dict[str, list[tuple[dict, dict]]] = {}
    for m, fl in floors:
        blds.setdefault(m.get("building_id") or m.get("building"), []).append((m, fl))
    for bid, fs in blds.items():
        fs.sort(key=lambda t: t[0]["level"])
        for (ma, fa), (mb, fb) in zip(fs, fs[1:], strict=False):
            if mb["level"] - ma["level"] != 1:
                warns.append(
                    _w(
                        "LINK_LEVEL_GAP",
                        f"{bid}: no floor between level {ma['level']} and {mb['level']}; not linked",
                    )
                )
                continue
            gap = _footprint_gap(fa, fb)
            if gap > 0.25:
                warns.append(
                    _w(
                        "LINK_FOOTPRINT_MISMATCH",
                        f"{ma['id']}/{mb['id']}: footprints differ by {gap:.0%}; check links by hand",
                    )
                )
            for kind in DEFAULT_LEN:
                A = [n for n in _tnodes(fa) if n["transition"] == kind and (ma["id"], n["id"]) not in used]
                B = [n for n in _tnodes(fb) if n["transition"] == kind and (mb["id"], n["id"]) not in used]
                cand = sorted(
                    (math.dist(_aligned(fa, a), _aligned(fb, b)), a["id"], b["id"]) for a in A for b in B
                )
                ua: set[str] = set()
                ub: set[str] = set()
                for d, ia, ib in cand:
                    if d > max_dist_m:
                        break
                    if ia in ua or ib in ub:
                        continue
                    ua.add(ia)
                    ub.add(ib)
                    conf = max(0.2, 1 - d / max_dist_m) * (0.6 if gap > 0.25 else 1.0)
                    links.append(
                        _link(f"t{len(links) + 1}", kind, ma["id"], ia, mb["id"], ib, "auto", conf, d)
                    )
                for n in A:
                    if n["id"] not in ua:
                        warns.append(
                            _w(
                                "LINK_UNMATCHED",
                                f"{ma['id']}:{n['id']} ({kind}) has no partner on {mb['id']}",
                            )
                        )
                for n in B:
                    if n["id"] not in ub:
                        warns.append(
                            _w(
                                "LINK_UNMATCHED",
                                f"{mb['id']}:{n['id']} ({kind}) has no partner on {ma['id']}",
                            )
                        )
    return links, warns


def cross_floor_path_m(
    floors: dict[str, dict], links: list[dict], src: tuple[str, str], dst: tuple[str, str]
) -> float | None:
    """Shortest path length in metres between (floor_id, node_id) pairs across floors, or None."""
    import networkx as nx

    g = nx.Graph()
    for fid, fl in floors.items():
        for e in fl["graph"]["edges"]:
            g.add_edge((fid, e["from"]), (fid, e["to"]), weight=e["length_m"])
    for k in links:
        g.add_edge(
            (k["from"]["floor_id"], k["from"]["node_id"]),
            (k["to"]["floor_id"], k["to"]["node_id"]),
            weight=k["length_m"],
        )
    try:
        return float(nx.shortest_path_length(g, src, dst, weight="weight"))
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None
