"""Multi-floor linking (FR-18): a shared frame per building, then stairs/lift pairing across adjacent levels.

Fills ``venue.transitions`` and each floor's ``building_frame`` (docs/MAP_PACKAGE_SCHEMA.md section 3).

1. **Building frame.** Floors of one building are drawn separately (other crop, sometimes another scale), so
   positions can't be compared directly. Each pair of adjacent levels is registered by aligning their wall
   drawings (similarity: scale + translation; phase correlation on rasterised walls over a range of scales,
   scored by the share of wall pixels that land within 0.5 m of the other floor's walls). The transforms
   are chained from a reference floor (measured scale first, then the lowest level). A pair that does not
   register well falls back to aligning the floors' bounds and is reported. A registered scale far from 1
   means one of the two floors has a wrong scale: reported, not changed.
2. **Pairing.** Stairs/lift/escalator nodes of adjacent levels are paired by type with an optimal assignment
   (Hungarian) on their distance in the building frame, with a distance cap. Unmatched nodes are reported,
   never guessed. Linked nodes form **shafts** (one stair core through several levels) with one id.
3. **Manual links** (Studio) and venue **connections** (config: walkways between buildings, ramps) are added
   with provenance ``manual`` / ``config`` and win over auto links on the same node.

Lengths are flagged estimates (``length_estimated``) unless given: stairs 6 m per level, lift 4 m, escalator
8 m; a venue can set ``stairs_m_per_level`` etc.
"""

from __future__ import annotations

import math
import re

import numpy as np

DEFAULT_LEN = {"stairs": 6.0, "lift": 4.0, "escalator": 8.0}
MAX_DIST_M = 8.0  # stair feet move between levels (the flight arrives on the other side)
MEASURED = {"operator_two_point", "measured_room_size", "cad_units"}
REG_RES_M = 0.25  # raster resolution for wall registration
REG_MIN_SCORE = 0.35  # share of wall pixels within 0.5 m after alignment
LINK_TYPES = ("stairs", "lift", "escalator", "ramp", "walkway")


def _w(code: str, message: str) -> dict:
    return {"code": code, "message": message}


def _tnodes(fl: dict) -> list[dict]:
    return [n for n in fl["graph"]["nodes"] if n.get("transition") in DEFAULT_LEN]


def _size(fl: dict) -> tuple[float, float]:
    b = fl["bounds_m"]
    return b["max_x"] - b["min_x"], b["max_y"] - b["min_y"]


def _footprint_gap(a: dict, b: dict) -> float:
    wa, ha = _size(a)
    wb, hb = _size(b)
    return max(abs(wa - wb) / max(wa, wb, 1e-6), abs(ha - hb) / max(ha, hb, 1e-6))


def _apply(t: list[list[float]], x: float, y: float) -> tuple[float, float]:
    return t[0][0] * x + t[0][1] * y + t[0][2], t[1][0] * x + t[1][1] * y + t[1][2]


def _compose(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    """a ∘ b (apply b first)."""
    A = np.vstack([np.asarray(a, float), [0, 0, 1]])
    B = np.vstack([np.asarray(b, float), [0, 0, 1]])
    return (A @ B)[:2].round(6).tolist()


IDENTITY = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]


# ---- registration ---------------------------------------------------------------------------------------
def _wall_raster(fl: dict, scale: float = 1.0, res: float = REG_RES_M) -> np.ndarray:
    import cv2

    w, h = _size(fl)
    b = fl["bounds_m"]
    W, H = int(math.ceil(w * scale / res)) + 4, int(math.ceil(h * scale / res)) + 4
    img = np.zeros((H, W), np.uint8)
    for wl in fl.get("walls", []):
        p = [((wl["a"][0] - b["min_x"]) * scale / res + 2, (wl["a"][1] - b["min_y"]) * scale / res + 2)]
        p.append(((wl["b"][0] - b["min_x"]) * scale / res + 2, (wl["b"][1] - b["min_y"]) * scale / res + 2))
        t = max(1, int(round(float(wl.get("thickness_m") or 0.2) * scale / res)))
        cv2.line(img, tuple(int(round(v)) for v in p[0]), tuple(int(round(v)) for v in p[1]), 1, t)
    return img


def register_floors(fa: dict, fb: dict, res: float = REG_RES_M) -> dict:
    """Similarity transform mapping fb's metric frame onto fa's: {'matrix', 'scale', 'score', 'method'}.

    Searches scales 0.67-1.5; for each, phase correlation gives the shift; the score is the share of fb's wall
    pixels within 0.5 m of fa's walls after the shift (both shift signs tried)."""
    import cv2

    A = _wall_raster(fa, 1.0, res)
    if A.sum() == 0 or not fb.get("walls"):
        return {"matrix": None, "scale": None, "score": 0.0, "method": "none"}
    dist = cv2.distanceTransform((A == 0).astype(np.uint8), cv2.DIST_L2, 3)
    near = dist <= 0.5 / res
    best = None
    for s in np.geomspace(0.67, 1.5, 41):
        B = _wall_raster(fb, float(s), res)
        if B.sum() == 0:
            continue
        H, W = max(A.shape[0], B.shape[0]), max(A.shape[1], B.shape[1])
        H, W = cv2.getOptimalDFTSize(H * 2), cv2.getOptimalDFTSize(W * 2)
        pa = np.zeros((H, W), np.float32)
        pb = np.zeros((H, W), np.float32)
        pa[: A.shape[0], : A.shape[1]] = cv2.GaussianBlur(A.astype(np.float32), (0, 0), 2)
        pb[: B.shape[0], : B.shape[1]] = cv2.GaussianBlur(B.astype(np.float32), (0, 0), 2)
        # cross-correlation of the blurred wall drawings (FFT); the strongest peaks are candidate shifts
        corr = np.fft.irfft2(np.fft.rfft2(pa) * np.conj(np.fft.rfft2(pb)), s=pa.shape)
        flat = np.argpartition(corr.ravel(), -5)[-5:]
        ys, xs = np.nonzero(B)
        for k in flat:
            py, px = divmod(int(k), W)
            sy = py - H if py > H // 2 else py
            sx = px - W if px > W // 2 else px
            u = xs + sx
            v = ys + sy
            ok = (u >= 0) & (v >= 0) & (u < A.shape[1]) & (v < A.shape[0])
            score = float(near[v[ok], u[ok]].sum()) / len(xs)
            if best is None or score > best[0]:
                best = (score, float(s), float(sx), float(sy))
    if best is None:
        return {"matrix": None, "scale": None, "score": 0.0, "method": "none"}
    score, s, sx, sy = best
    ba, bb = fa["bounds_m"], fb["bounds_m"]
    # B raster px -> fa metres: x_a = (xb_px + sx - 2) * res + minx_a; xb_px = (x_b - minx_b) * s / res + 2
    tx = sx * res + ba["min_x"] - bb["min_x"] * s
    ty = sy * res + ba["min_y"] - bb["min_y"] * s
    return {
        "matrix": [[round(s, 6), 0.0, round(tx, 4)], [0.0, round(s, 6), round(ty, 4)]],
        "scale": round(s, 4),
        "score": round(score, 3),
        "method": "walls",
    }


def _bounds_transform(fa: dict, fb: dict) -> list[list[float]]:
    ba, bb = fa["bounds_m"], fb["bounds_m"]
    return [[1.0, 0.0, ba["min_x"] - bb["min_x"]], [0.0, 1.0, ba["min_y"] - bb["min_y"]]]


def building_frames(floors: list[tuple[dict, dict]]) -> tuple[dict[str, dict], list[dict]]:
    """floors: [(meta{id, building_id|building, level}, floor)] -> ({floor_id: building_frame}, warnings).

    building_frame = {'matrix': 2x3 floor->building, 'reference_floor_id', 'method': reference|walls|bounds,
    'confidence', 'registered_scale'}."""
    frames: dict[str, dict] = {}
    warns: list[dict] = []
    blds: dict[str, list[tuple[dict, dict]]] = {}
    for m, fl in floors:
        blds.setdefault(m.get("building_id") or m.get("building"), []).append((m, fl))
    for fs in blds.values():
        fs.sort(key=lambda t: t[0]["level"])

        def rank(t):
            measured = t[1].get("transform", {}).get("scale_source") in MEASURED
            return (not measured, abs(t[0]["level"]), t[0]["level"])

        ref_i = min(range(len(fs)), key=lambda i: rank(fs[i]))
        ref_id = fs[ref_i][0]["id"]
        frames[ref_id] = {
            "matrix": IDENTITY,
            "reference_floor_id": ref_id,
            "method": "reference",
            "confidence": 1.0,
            "registered_scale": 1.0,
        }
        # walk outward from the reference in both directions, chaining pairwise transforms
        for step in (1, -1):
            i = ref_i
            while 0 <= i + step < len(fs):
                (ma, fa), (mb, fb) = fs[i], fs[i + step]
                reg = register_floors(fa, fb)
                if reg["matrix"] is not None and reg["score"] >= REG_MIN_SCORE:
                    t, method, conf = reg["matrix"], "walls", reg["score"]
                    if abs(reg["scale"] - 1) > 0.05:
                        warns.append(
                            _w(
                                "LINK_SCALE_DISAGREES",
                                f"{mb['id']} lines up with {ma['id']} only at {reg['scale']:.2f}x: one "
                                f"of the two scales ({fb.get('transform', {}).get('scale_source')} / "
                                f"{fa.get('transform', {}).get('scale_source')}) is off by about "
                                f"{abs(reg['scale'] - 1):.0%}",
                            )
                        )
                else:
                    t, method, conf = _bounds_transform(fa, fb), "bounds", 0.2
                    if reg["method"] != "none":  # floors without any wall drawing: nothing to check
                        warns.append(
                            _w(
                                "LINK_FRAME_BOUNDS",
                                f"{mb['id']}: walls do not line up with {ma['id']} "
                                f"(score {reg['score']:.2f}); floors aligned by their bounds, check links",
                            )
                        )
                frames[mb["id"]] = {
                    "matrix": _compose(frames[ma["id"]]["matrix"], t),
                    "reference_floor_id": ref_id,
                    "method": method,
                    "confidence": round(min(conf, frames[ma["id"]]["confidence"]), 3),
                    "registered_scale": reg["scale"] if method == "walls" else None,
                }
                i += step
    return frames, warns


ESTIMATED = {"door_width_prior", "door_width_calibrated", "footprint_transfer"}


def rescale_floor(fd: dict, k: float, evidence: dict | None = None) -> None:
    """Multiply every metric quantity of a floor dict by ``k`` (a corrected scale), in place."""

    def pt(p):
        return [round(p[0] * k, 3), round(p[1] * k, 3)]

    def deep(c):
        return [deep(x) for x in c] if isinstance(c[0], list) else pt(c)

    t = fd["transform"]
    t["px_to_m"] = [[v * k for v in row] for row in t["px_to_m"]]
    t["scale_m_per_px"] = t["scale_m_per_px"] * k
    b = fd["bounds_m"]
    for key in b:
        b[key] = round(b[key] * k, 3)
    if fd.get("walkable", {}).get("coordinates"):
        fd["walkable"]["coordinates"] = deep(fd["walkable"]["coordinates"])
    for w in fd.get("walls", []):
        w["a"], w["b"] = pt(w["a"]), pt(w["b"])
        if w.get("thickness_m") is not None:
            w["thickness_m"] = round(w["thickness_m"] * k, 3)
    for d in fd.get("doors", []):
        d["a"], d["b"] = pt(d["a"]), pt(d["b"])
    for r in fd.get("rooms", []):
        if r.get("polygon"):
            r["polygon"] = deep(r["polygon"])
    for n in fd["graph"]["nodes"]:
        n["x"], n["y"] = round(n["x"] * k, 3), round(n["y"] * k, 3)
    for e in fd["graph"]["edges"]:
        e["length_m"] = round(e["length_m"] * k, 3)
    if evidence:
        t.setdefault("scale_evidence", []).append(evidence)


def align_scales(
    floors: list[tuple[dict, dict]], frames: dict[str, dict], min_conf: float = 0.5, min_change: float = 0.02
) -> tuple[list[dict], dict[str, float]]:
    """Correct the scale of floors whose scale is an estimate (door width, footprint) when their walls line up
    with a floor of the same building whose scale was measured: the registered scale factor replaces the
    estimate. Changes floors and frames in place; returns (warnings, {floor_id: factor})."""
    by_id = {m["id"]: fl for m, fl in floors}
    warns: list[dict] = []
    changed: dict[str, float] = {}
    for fid, fr in frames.items():
        fd = by_id.get(fid)
        ref = by_id.get(fr["reference_floor_id"])
        if fd is None or ref is None or fid == fr["reference_floor_id"]:
            continue
        if (
            ref["transform"].get("scale_source") not in MEASURED
            or fd["transform"].get("scale_source") not in ESTIMATED
        ):
            continue
        if fr["method"] != "walls" or fr["confidence"] < min_conf:
            continue
        k = float(fr["matrix"][0][0])
        if abs(k - 1) < min_change:
            continue
        old = fd["transform"]["scale_source"]
        rescale_floor(
            fd,
            k,
            {
                "method": "wall_registration",
                "reference_floor_id": fr["reference_floor_id"],
                "factor": round(k, 4),
                "registration_confidence": fr["confidence"],
                "replaced": old,
            },
        )
        fd["transform"]["scale_source"] = "footprint_transfer"
        fr["matrix"] = [[1.0, 0.0, fr["matrix"][0][2]], [0.0, 1.0, fr["matrix"][1][2]]]
        fr["registered_scale"] = round(k, 4)
        fr["scale_corrected"] = True
        changed[fid] = round(k, 4)
        warns.append(
            _w(
                "SCALE_FROM_REGISTRATION",
                f"{fid}: scale ({old}) corrected by {k:.3f}x from wall alignment with measured floor "
                f"{fr['reference_floor_id']} (confidence {fr['confidence']:.2f})",
            )
        )
    return warns, changed


# ---- links ----------------------------------------------------------------------------------------------
def _link(
    tid: str,
    kind: str,
    f1: str,
    n1: str,
    f2: str,
    n2: str,
    source: str,
    conf: float,
    d: float | None,
    lengths: dict,
    length_m: float | None = None,
):
    est = length_m is None
    acc = {"lift": True, "ramp": True, "walkway": True, "stairs": False, "escalator": False}.get(kind)
    return {
        "id": tid,
        "type": kind,
        "from": {"floor_id": f1, "node_id": n1},
        "to": {"floor_id": f2, "node_id": n2},
        "length_m": float(length_m if length_m is not None else lengths.get(kind, 6.0)),
        "length_estimated": est,
        **({"accessible": acc} if acc is not None else {}),
        "provenance": {"source": source, "confidence": round(conf, 2)},
        **({"match_distance_m": round(d, 2)} if d is not None else {}),
    }


def _assign(cost: np.ndarray, cap: float) -> list[tuple[int, int, float]]:
    from scipy.optimize import linear_sum_assignment

    if cost.size == 0:
        return []
    big = cap * 1000 + 1
    c = np.where(cost <= cap, cost, big)
    rows, cols = linear_sum_assignment(c)
    return [
        (int(r), int(k), float(cost[r, k])) for r, k in zip(rows, cols, strict=False) if cost[r, k] <= cap
    ]


def link_floors(
    floors: list[tuple[dict, dict]],
    manual: list[dict] | None = None,
    max_dist_m: float = MAX_DIST_M,
    frames: dict[str, dict] | None = None,
    lengths: dict | None = None,
    connections: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """floors: [(meta{id,building_id|building,level}, floor_dict)] -> (transitions, warnings)."""
    manual = manual or []
    lengths = {**DEFAULT_LEN, "ramp": 0.0, "walkway": 0.0, **(lengths or {})}
    by_id = {m["id"]: fl for m, fl in floors}
    warns: list[dict] = []
    if frames is None:
        frames, fw = building_frames(floors)
        warns += fw
    links: list[dict] = []
    used: set[tuple[str, str]] = set()

    def add(kind, a, b, source, conf, d=None, length_m=None):
        links.append(_link(f"t{len(links) + 1}", kind, *a, *b, source, conf, d, lengths, length_m))
        if source != "auto":  # a node joined by hand is not paired again automatically
            used.update({a, b})

    for m in manual:  # manual first: they win
        a, b = m["from"], m["to"]
        try:
            na = next(n for n in by_id[a["floor_id"]]["graph"]["nodes"] if n["id"] == a["node_id"])
            next(n for n in by_id[b["floor_id"]]["graph"]["nodes"] if n["id"] == b["node_id"])
        except (KeyError, StopIteration):
            warns.append(_w("LINK_DANGLING", f"manual link {m} points at a missing node"))
            continue
        kind = m.get("type") or na.get("transition") or "stairs"
        add(
            kind,
            (a["floor_id"], a["node_id"]),
            (b["floor_id"], b["node_id"]),
            "manual",
            1.0,
            length_m=m.get("length_m"),
        )

    for c in expand_connections(connections, floors):
        try:
            a = resolve_place(by_id, str(c["from"]))
            b = resolve_place(by_id, str(c["to"]))
        except KeyError as e:
            warns.append(_w("LINK_CONNECTION_UNRESOLVED", str(e.args[0])))
            continue
        kind = c.get("type") or "walkway"
        length = c.get("length_m")
        if length is None and kind in ("walkway", "ramp") and a[0] == b[0]:
            fl = by_id[a[0]]
            na = next(n for n in fl["graph"]["nodes"] if n["id"] == a[1])
            nb = next(n for n in fl["graph"]["nodes"] if n["id"] == b[1])
            length = math.dist((na["x"], na["y"]), (nb["x"], nb["y"]))
        if is_estimated_end(str(c["from"])) or is_estimated_end(str(c["to"])):
            # the connection is a site fact, but where it meets each floor is the tool's estimate
            add(kind, a, b, "auto", 0.5, length_m=length)
            warns.append(
                _w(
                    "LINK_ENDPOINT_ESTIMATED",
                    f"{c['from']} - {c['to']} ({kind}): joined at {a[0]}:{a[1]} and {b[0]}:{b[1]}, "
                    "the corridor nodes nearest those edges of the drawings; check the two ends (Studio) "
                    "or give exact nodes",
                )
            )
        else:
            add(kind, a, b, "manual", 1.0, length_m=length)  # operator-entered in the venue config

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
            ta = frames.get(ma["id"], {}).get("matrix") or IDENTITY
            tb = frames.get(mb["id"], {}).get("matrix") or IDENTITY
            conf_pair = min(
                frames.get(ma["id"], {}).get("confidence", 0.2),
                frames.get(mb["id"], {}).get("confidence", 0.2),
            )
            for kind in DEFAULT_LEN:
                A = [n for n in _tnodes(fa) if n["transition"] == kind and (ma["id"], n["id"]) not in used]
                B = [n for n in _tnodes(fb) if n["transition"] == kind and (mb["id"], n["id"]) not in used]
                pa = [_apply(ta, n["x"], n["y"]) for n in A]
                pb = [_apply(tb, n["x"], n["y"]) for n in B]
                cost = (
                    np.array([[math.dist(p, q) for q in pb] for p in pa]) if pa and pb else np.zeros((0, 0))
                )
                ua: set[str] = set()
                ub: set[str] = set()
                for i, j, d in _assign(cost, max_dist_m):
                    ua.add(A[i]["id"])
                    ub.add(B[j]["id"])
                    conf = max(0.2, 1 - d / max_dist_m) * (0.5 + 0.5 * min(conf_pair / 0.6, 1.0))
                    add(kind, (ma["id"], A[i]["id"]), (mb["id"], B[j]["id"]), "auto", conf, d)
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
        warns += _shaft_gaps(bid, fs, frames, max_dist_m, add)
    _shafts(links)
    return links, warns


INFER_REACH_M = 4.0  # an inferred lift stop must have a graph node this close
INFER_MIN_CONF = 0.35  # ... and every floor involved must be placed in the building frame at least this well


def _invert(t: list[list[float]]) -> list[list[float]] | None:
    (a, b, tx), (c, d, ty) = t
    det = a * d - b * c
    if abs(det) < 1e-9:
        return None
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    return [[ia, ib, -(ia * tx + ib * ty)], [ic, id_, -(ic * tx + id_ * ty)]]


def _placed(frames: dict, fid: str) -> bool:
    f = frames.get(fid, {})
    return f.get("method") == "reference" or (
        f.get("method") == "walls" and (f.get("confidence") or 0) >= INFER_MIN_CONF
    )


def _shaft_gaps(bid, fs, frames, max_dist_m, add=None) -> list[dict]:
    """A lift or escalator found on two non-adjacent levels at the same place in the building frame, but on no
    level between: it was missed on those levels.

    A **lift** passes through every floor between its stops, so when the floors are placed in the building
    frame by their walls, the stop on each missed floor is *proposed*: the graph node nearest the shaft
    (within ``INFER_REACH_M``) is linked, with low confidence, and reported as ``LINK_SHAFT_INFERRED``.
    Otherwise (an escalator, floors not aligned, no node near the shaft) nothing is linked and
    ``LINK_SHAFT_GAP`` names the floors to mark by hand: a link that skips floors would hide the floors
    in between."""
    out = []
    by_fid = {m["id"]: fl for m, fl in fs}
    for kind in ("lift", "escalator"):
        pos = []
        for m, fl in fs:
            t = frames.get(m["id"], {}).get("matrix") or IDENTITY
            pos += [
                (m["level"], m["id"], _apply(t, n["x"], n["y"]), n["id"])
                for n in _tnodes(fl)
                if n["transition"] == kind
            ]
        pos.sort(key=lambda p: (p[0], p[1], p[3]))
        levels = {m["level"]: m["id"] for m, _ in fs}
        for i, (la, fa_id, pa, na) in enumerate(pos):
            nxt = [q for q in pos[i + 1 :] if q[0] > la]
            if not nxt or nxt[0][0] == la + 1:
                continue
            lb, fb_id, pb, nb = nxt[0]
            if math.dist(pa, pb) > max_dist_m:
                continue
            missing = [levels[lv] for lv in range(la + 1, lb) if lv in levels]
            if not missing or len(missing) != lb - la - 1:
                continue
            x, y = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
            chain = [(fa_id, na)]
            ok = (
                kind == "lift"
                and add is not None
                and all(_placed(frames, f) for f in [fa_id, fb_id, *missing])
            )
            dists = []
            for fid in missing if ok else []:
                inv = _invert(frames.get(fid, {}).get("matrix") or IDENTITY)
                cand = _main_piece(by_fid[fid])
                if inv is None or not cand:
                    ok = False
                    break
                fx, fy = _apply(inv, x, y)
                n = min(cand, key=lambda n: math.dist((n["x"], n["y"]), (fx, fy)))
                d = math.dist((n["x"], n["y"]), (fx, fy))
                if d > INFER_REACH_M:
                    ok = False
                    break
                chain.append((fid, n["id"]))
                dists.append(d)
            if ok:
                chain.append((fb_id, nb))
                for u, v in zip(chain[:-1], chain[1:], strict=False):
                    add(kind, u, v, "auto", 0.4, d=max(dists))
                stops = ", ".join(f"{f}:{n}" for f, n in chain[1:-1])
                out.append(
                    _w(
                        "LINK_SHAFT_INFERRED",
                        f"{bid}: {kind} found on {fa_id} and {fb_id} at the same place but not on "
                        f"{', '.join(missing)}; a lift passes through, so a stop was proposed at {stops} "
                        "(nearest graph node to the shaft). Check it (Studio)",
                    )
                )
            else:
                out.append(
                    _w(
                        "LINK_SHAFT_GAP",
                        f"{bid}: {kind} on {fa_id} and {fb_id} at the same place (building frame "
                        f"{x:.1f}, {y:.1f} m) but not found on {', '.join(missing)}: "
                        "mark it there (Studio) to link these floors",
                    )
                )
    return out


def _shafts(links: list[dict]) -> None:
    """Give vertical links that chain through several levels (one stair core, one lift) a shared shaft id."""
    parent: dict = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    vert = [k for k in links if k["type"] in DEFAULT_LEN]
    for k in vert:
        a = (k["from"]["floor_id"], k["from"]["node_id"])
        b = (k["to"]["floor_id"], k["to"]["node_id"])
        parent[find(a)] = find(b)
    roots: dict = {}
    for k in vert:
        r = find((k["from"]["floor_id"], k["from"]["node_id"]))
        roots.setdefault(r, f"shaft{len(roots) + 1}")
        k["shaft"] = roots[r]


SIDES = ("left", "right", "top", "bottom")


def _main_piece(fl: dict) -> list[dict]:
    import networkx as nx

    g = nx.Graph()
    g.add_nodes_from(n["id"] for n in fl["graph"]["nodes"])
    g.add_edges_from((e["from"], e["to"]) for e in fl["graph"]["edges"])
    if not g:
        return []
    big = max(nx.connected_components(g), key=len)
    return [n for n in fl["graph"]["nodes"] if n["id"] in big]


def side_node(fl: dict, side: str) -> str:
    """The corridor node of the floor's main graph piece furthest towards one edge of the drawing.

    Used for a connection end written as ``FLOOR@side``: the place where a corridor leaves the floor towards a
    neighbouring building. The result is an estimate (the exact doorway is not known from the plan)."""
    cand = [n for n in _main_piece(fl) if n.get("kind") in ("corridor", "junction")] or _main_piece(fl)
    if not cand:
        raise KeyError("floor has no graph")
    key = {
        "left": lambda n: n["x"],
        "right": lambda n: -n["x"],
        "top": lambda n: n["y"],
        "bottom": lambda n: -n["y"],
    }[side]
    return min(cand, key=key)["id"]


def is_estimated_end(ref: str) -> bool:
    """True for ``FLOOR@side`` ends: the node is chosen by the tool, not given by a person."""
    return ":" not in ref and "@" in ref


def expand_connections(connections: list[dict] | None, floors: list[tuple[dict, dict]]) -> list[dict]:
    """Building-level connections -> one connection per level.

    ``{from: "A@right", to: "B@right", levels: [0, 1, 2]}`` (ends that name a *building*, not a floor) becomes
    one connection per listed level between the two buildings' floors on that level. Without ``levels`` every
    level both buildings have is used. Floor-level connections pass through unchanged."""
    fids = {m["id"] for m, _ in floors}
    by_bl = {(m.get("building_id") or m.get("building"), m["level"]): m["id"] for m, _ in floors}
    blds = {b for b, _ in by_bl}
    out: list[dict] = []
    for c in connections or []:
        ends = []
        for ref in (str(c.get("from", "")), str(c.get("to", ""))):
            head, sep, rest = re.match(r"^([^:@]*)([:@]?)(.*)$", ref).groups()
            ends.append((head, sep + rest, head in blds and head not in fids))
        if not (ends[0][2] and ends[1][2]):
            out.append(c)
            continue
        (ba, ra, _), (bb, rb, _) = ends
        common = sorted({lv for b, lv in by_bl if b == ba} & {lv for b, lv in by_bl if b == bb})
        levels = c.get("levels", common)
        for lv in levels:
            if (ba, lv) in by_bl and (bb, lv) in by_bl:
                rest_c = {k: v for k, v in c.items() if k not in ("from", "to", "levels")}
                out.append({**rest_c, "from": by_bl[(ba, lv)] + ra, "to": by_bl[(bb, lv)] + rb})
            else:
                out.append({**c, "from": f"{ba}[level {lv}]{ra}", "to": f"{bb}[level {lv}]{rb}"})  # reported
    return out


def resolve_place(floors: dict[str, dict], ref: str) -> tuple[str, str]:
    """'FLOOR:node_id', 'FLOOR:<label or name>', 'FLOOR:x,y' (metres) or 'FLOOR@side' -> (floor_id, node_id).

    Labels resolve to the destination's node; a point resolves to the nearest node on the floor's largest
    graph piece; a side (left/right/top/bottom of the drawing) to the corridor node furthest that way."""
    import networkx as nx

    if is_estimated_end(ref):
        fid, side = ref.split("@", 1)
        side = side.strip().lower()
        if fid not in floors:
            raise KeyError(f"connection end {ref!r}: no floor {fid!r}")
        if side not in SIDES:
            raise KeyError(f"connection end {ref!r}: side must be one of {', '.join(SIDES)}")
        try:
            return fid, side_node(floors[fid], side)
        except KeyError as e:
            raise KeyError(f"connection end {ref!r}: {e.args[0]}") from None
    if ":" not in ref:
        raise KeyError(f"connection end {ref!r}: use FLOOR:node, FLOOR:label, FLOOR:x,y or FLOOR@side")
    fid, rest = ref.split(":", 1)
    if fid not in floors:
        raise KeyError(f"connection end {ref!r}: no floor {fid!r}")
    fl = floors[fid]
    ids = {n["id"] for n in fl["graph"]["nodes"]}
    if rest in ids:
        return fid, rest
    m = re.fullmatch(r"\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*", rest)
    if m:
        x, y = float(m.group(1)), float(m.group(2))
        g = nx.Graph()
        g.add_nodes_from(ids)
        g.add_edges_from((e["from"], e["to"]) for e in fl["graph"]["edges"])
        big = max(nx.connected_components(g), key=len) if ids else set()
        cand = [n for n in fl["graph"]["nodes"] if n["id"] in big]
        if not cand:
            raise KeyError(f"connection end {ref!r}: floor has no graph")
        n = min(cand, key=lambda n: math.dist((n["x"], n["y"]), (x, y)))
        return fid, n["id"]
    q = re.sub(r"[^a-z0-9]", "", rest.lower())
    for p in fl.get("pois", []):
        if q in (
            re.sub(r"[^a-z0-9]", "", (p.get("label") or "").lower()),
            re.sub(r"[^a-z0-9]", "", p["name"].lower()),
        ):
            return fid, p["node_id"]
    raise KeyError(f"connection end {ref!r}: no node, point or destination matches")


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


def link_venue(
    floors: list[tuple[dict, dict]],
    manual: list[dict] | None = None,
    connections: list[dict] | None = None,
    lengths: dict | None = None,
    max_dist_m: float = MAX_DIST_M,
    correct_scales: bool = True,
) -> dict:
    """Everything multi-floor in one step: building frames, scale correction of estimated floors, links.

    Mutates the floor dicts (``building_frame``; rescaled geometry when corrected). Returns
    {'transitions', 'frames', 'warnings', 'rescaled'}."""
    frames, warns = building_frames(floors)
    rescaled: dict[str, float] = {}
    if correct_scales:
        sw, rescaled = align_scales(floors, frames)
        # a disagreement that was just corrected is no longer worth a warning
        warns = [
            w
            for w in warns
            if not (w["code"] == "LINK_SCALE_DISAGREES" and any(f in w["message"].split() for f in rescaled))
        ]
        warns += sw
    for m, fl in floors:
        if m["id"] in frames:
            fl["building_frame"] = frames[m["id"]]
    links, lw = link_floors(
        floors,
        manual=manual,
        max_dist_m=max_dist_m,
        frames=frames,
        lengths=lengths,
        connections=connections,
    )
    return {"transitions": links, "frames": frames, "warnings": warns + lw, "rescaled": rescaled}
