"""Metric scale per floor.

Preferred: operator two-point evidence from the venue config (measured on site). Fallback:
median detected door width = ``door_width_prior_m`` — an *estimate*, always flagged with a warning.
"""

from __future__ import annotations

import numpy as np

from .ir import GeometryPx, Issue


def scale_from_evidence(evidence: list[dict]) -> tuple[float, list[dict]]:
    used = [e for e in evidence if e.get("used_for_fit", True)] or evidence[:1]
    first = used[0]
    d_px = float(np.hypot(*np.subtract(first["p2_px"], first["p1_px"])))
    if d_px <= 0:
        raise ValueError("scale evidence points are identical")
    s = float(first["distance_m"]) / d_px
    out = []
    for e in evidence:
        e2 = dict(e)
        e2["used_for_fit"] = e is first
        if e is not first:
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
        return s, "operator_two_point", ev, issues
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
