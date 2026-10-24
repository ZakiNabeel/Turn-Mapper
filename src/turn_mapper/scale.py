"""Metric scale per floor.

Preferred: operator two-point evidence from the venue config (measured on site). Fallback:
median detected door width = ``door_width_prior_m`` — an *estimate*, always flagged with a warning.
"""

from __future__ import annotations

import numpy as np

from .ir import GeometryPx, Issue


def _two_point_scale(e: dict) -> float:
    d_px = float(np.hypot(*np.subtract(e["p2_px"], e["p1_px"])))
    if d_px <= 0:
        raise ValueError("scale evidence points are identical")
    return float(e["distance_m"]) / d_px


def scale_from_evidence(evidence: list[dict]) -> tuple[float, list[dict]]:
    """Scale from evidence. A ``cad_units`` entry (document units of a DXF/vector file, ``m_per_px``) wins;
    otherwise the first two-point measurement fits the scale. Every other two-point entry is a held-out check
    and gets a ``residual_m``."""
    cad = [e for e in evidence if e.get("method") == "cad_units"]
    if cad:
        first = cad[0]
        s = float(first["m_per_px"])
    else:
        used = [e for e in evidence if e.get("used_for_fit", True)] or evidence[:1]
        first = used[0]
        s = _two_point_scale(first)
    out = []
    for e in evidence:
        e2 = dict(e)
        e2["used_for_fit"] = e is first
        if e is not first and "p1_px" in e:
            dpx = float(np.hypot(*np.subtract(e["p2_px"], e["p1_px"])))
            e2["residual_m"] = round(dpx * s - float(e["distance_m"]), 3)
        out.append(e2)
    return s, out


def estimate_scale(
    geom: GeometryPx, evidence: list[dict], door_prior_m: float
) -> tuple[float, str, list[dict], list[Issue]]:
    issues: list[Issue] = []
    if evidence:
        s, ev = scale_from_evidence(evidence)
        big = [e for e in ev if abs(e.get("residual_m", 0)) > 0.5]
        for e in big:
            issues.append(Issue("SCALE_RESIDUAL_HIGH", f"held-out distance off by {e['residual_m']} m", None))
        src = "cad_units" if any(e.get("method") == "cad_units" for e in evidence) else "operator_two_point"
        return s, src, ev, issues
    circ = {r.id for r in geom.regions if r.kind == "circulation"}
    widths = [d.width_px for d in geom.doors if len(d.regions) == 2 and circ & set(d.regions)]
    widths = widths or [d.width_px for d in geom.doors]
    if not widths:
        issues.append(
            Issue("SCALE_MISSING", "no scale evidence and no doors to estimate from; using 0.05 m/px")
        )
        return 0.05, "door_width_prior", [], issues
    med = float(np.median(widths))
    s = door_prior_m / med
    issues.append(
        Issue(
            "SCALE_ESTIMATED",
            f"no measured distances; scale estimated from median door width {med:.1f}px = "
            f"{door_prior_m} m -> {s:.4f} m/px. Measure on site before trusting distances.",
        )
    )
    return (
        s,
        "door_width_prior",
        [
            {
                "method": "door_width_prior",
                "median_door_px": med,
                "assumed_door_m": door_prior_m,
                "n_doors": len(widths),
            }
        ],
        issues,
    )


# ----------------------------------------------------------------------------------------------------
# Scale from measured room / corridor sizes (site measurements of whole spaces rather than two picked points).
# Evidence entries (venue config ``scale_evidence``, per floor id or per building id):
#   {method: room_size,      label: B-227A, size_ft: [35.78, 25.11]}   one named room, inside dimensions
#   {method: typical_room,   size_ft: [30, 25]}                          the common room size on this floor
#   {method: corridor_width, width_ft: 12}                               check only: median corridor width
# ``size_m`` / ``width_m`` may be used instead of feet. ``check_only: true`` never fits, only reports.
# ----------------------------------------------------------------------------------------------------

FT = 0.3048
ROOM_METHODS = ("room_size", "typical_room", "corridor_width")
# acceptance rules for a typical-room fit, fixed before looking at the FAST results they gate
TYPICAL_ASPECT_TOL = 0.15  # room side ratio within 15% of the measured ratio
TYPICAL_CLUSTER_TOL = 0.06  # rooms agreeing on scale within 6%
TYPICAL_MIN_ROOMS = 5  # at least five agreeing rooms
DOOR_WIDTH_RANGE_M = (0.6, 2.5)  # a fit implying doors outside this range is physically implausible


def _metres(e: dict, key: str) -> list[float]:
    if f"{key}_m" in e:
        v = e[f"{key}_m"]
    elif f"{key}_ft" in e:
        v = e[f"{key}_ft"]
        v = [x * FT for x in v] if isinstance(v, list | tuple) else v * FT
    else:
        raise ValueError(f"scale evidence {e.get('method')} needs {key}_m or {key}_ft")
    return [float(x) for x in v] if isinstance(v, list | tuple) else [float(v)]


def _norm_label(s: str | None) -> str:
    return "".join(ch for ch in (s or "").upper() if ch.isalnum())


def room_rects(geom: GeometryPx) -> list[dict]:
    """Minimum-area rectangle of every room region (long side L, short side W, in px), with how well the
    rectangle is filled (1.0 = the room is a rectangle)."""
    import cv2

    out = []
    masks = geom.debug.get("region_masks", {})
    for r in geom.regions:
        m = masks.get(r.id)
        if m is None or r.kind != "room":
            continue
        m8 = m.astype(np.uint8)
        cs, _ = cv2.findContours(m8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cs:
            continue
        (_, _), (w, h), _ = cv2.minAreaRect(max(cs, key=cv2.contourArea))
        if min(w, h) < 1:
            continue
        out.append(
            {
                "id": r.id,
                "label": r.label,
                "L": float(max(w, h)),
                "W": float(min(w, h)),
                "fill": float(m8.sum()) / float(w * h),
                "area": float(m8.sum()),
            }
        )
    return out


def _named_room_fit(rects: list[dict], e: dict) -> dict:
    L, W = sorted(_metres(e, "size"), reverse=True)
    want = _norm_label(e.get("label"))
    hit = [r for r in rects if _norm_label(r["label"]) == want]
    if not hit:
        return {"ok": False, "reason": f"room {e.get('label')} not found among OCR-labelled rooms"}
    r = max(hit, key=lambda r: r["area"])
    sL, sW = L / r["L"], W / r["W"]
    return {
        "ok": True,
        "m_per_px": (sL + sW) / 2,
        "room": r["id"],
        "room_px": [round(r["L"], 1), round(r["W"], 1)],
        "side_disagreement": round(abs(sL / sW - 1), 3),
    }


def _typical_room_fit(rects: list[dict], e: dict) -> dict:
    L, W = sorted(_metres(e, "size"), reverse=True)
    cand = [
        ((L / r["L"] + W / r["W"]) / 2, r)
        for r in rects
        if 0.9 <= r["fill"] <= 1.1
        and r["W"] >= 10
        and abs((r["L"] / r["W"]) / (L / W) - 1) < TYPICAL_ASPECT_TOL
    ]
    best = None
    for s, _ in cand:
        group = [(t, r) for t, r in cand if abs(t / s - 1) < TYPICAL_CLUSTER_TOL]
        score = sum(r["area"] for _, r in group)  # big rooms count more than many small ones
        if best is None or score > best[0]:
            best = (score, group)
    if best is None or len(best[1]) < TYPICAL_MIN_ROOMS:
        n = len(best[1]) if best else 0
        return {
            "ok": False,
            "reason": f"only {n} rooms agree on a scale for {L / FT:.0f} x {W / FT:.0f} ft "
            f"(need {TYPICAL_MIN_ROOMS})",
            "n_candidates": len(cand),
        }
    scales = np.array([t for t, _ in best[1]])
    return {
        "ok": True,
        "m_per_px": float(np.median(scales)),
        "n_rooms": len(scales),
        "rooms": [r["label"] or r["id"] for _, r in best[1]],
        "spread": round(float(scales.max() / scales.min() - 1), 3),
    }


def corridor_width_px(geom: GeometryPx) -> float | None:
    """Median width of the largest circulation space (2x distance to its edge, along its centre line)."""
    import cv2
    from skimage.morphology import skeletonize

    masks = geom.debug.get("region_masks", {})
    circ = [masks[r.id] for r in geom.regions if r.kind == "circulation" and r.id in masks]
    if not circ:
        return None
    m = max(circ, key=lambda a: int(a.sum())).astype(np.uint8)
    dt = cv2.distanceTransform(m, cv2.DIST_L2, 5)
    sk = skeletonize(m > 0)
    return float(np.median(2 * dt[sk])) if sk.any() else None


def room_evidence_scale(
    geom: GeometryPx, evidence: list[dict], door_widths_px: list[float]
) -> tuple[float | None, list[dict], list[Issue]]:
    """Fit the scale from the first accepted room-size evidence; every other entry is reported as a check
    (``implied_m_per_px`` and ``residual_pct`` against the fit). Returns (scale or None, evidence, issues)."""
    rects = room_rects(geom)
    issues: list[Issue] = []
    out: list[dict] = []
    fitted: float | None = None
    door_med = float(np.median(door_widths_px)) if door_widths_px else None
    for e in evidence:
        m = e.get("method")
        if m not in ROOM_METHODS:
            continue
        if m == "corridor_width":
            w_px = corridor_width_px(geom)
            res = (
                {"ok": True, "m_per_px": _metres(e, "width")[0] / w_px, "corridor_width_px": round(w_px, 1)}
                if w_px
                else {"ok": False, "reason": "no corridor found"}
            )
        elif m == "room_size":
            res = _named_room_fit(rects, e)
        else:
            res = _typical_room_fit(rects, e)
        if res["ok"] and door_med:
            res["implied_door_m"] = round(door_med * res["m_per_px"], 2)
            lo, hi = DOOR_WIDTH_RANGE_M
            if not lo <= res["implied_door_m"] <= hi:
                res = {
                    **res,
                    "ok": False,
                    "reason": f"implies {res['implied_door_m']} m doors (outside {lo}-{hi} m)",
                }
        rec = {**e, **{k: v for k, v in res.items() if k != "ok"}, "accepted": res["ok"]}
        can_fit = res["ok"] and not e.get("check_only") and m != "corridor_width"
        if fitted is None and can_fit:
            fitted = res["m_per_px"]
            rec["used_for_fit"] = True
        else:
            rec["used_for_fit"] = False
        if not res["ok"]:
            issues.append(
                Issue("SCALE_EVIDENCE_REJECTED", f"{m} {e.get('label', '')}: {res['reason']}".strip())
            )
        out.append(rec)
    if fitted:
        for rec in out:
            if not rec["used_for_fit"] and "m_per_px" in rec:
                rec["residual_pct"] = round(100 * (rec["m_per_px"] / fitted - 1), 1)
                if abs(rec["residual_pct"]) > 10:
                    issues.append(
                        Issue(
                            "SCALE_RESIDUAL_HIGH",
                            f"check {rec['method']} {rec.get('label', '')} differs by {rec['residual_pct']}%",
                        )
                    )
    for rec in out:
        if "m_per_px" in rec:
            rec["m_per_px"] = round(rec["m_per_px"], 5)
    return fitted, out, issues


def point_evidence(evidence: list[dict]) -> list[dict]:
    """Evidence that fixes the scale before segmentation (CAD units, two measured points)."""
    return [e for e in evidence if e.get("method") not in ROOM_METHODS]
