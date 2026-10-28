"""Which CAD line is a wall, a door, a window or furniture: a per-segment classifier for vector drawings.

Trained on FloorPlanCAD (line-level labels, CC BY-NC 4.0; `scripts/floorplancad_train.py`, Kaggle notebook
`notebooks/floorplancad_kaggle.ipynb`). The same features are computed for FloorPlanCAD SVGs and for the
strokes `vector_pdf.parse_page` reads from a PDF, so a model trained on one applies to the other.

Units are relative to the drawing: lengths in multiples of the drawing's median segment length, stroke widths
in multiples of its median width. That keeps the features independent of the sheet scale and of the CAD unit.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

# FloorPlanCAD semantic ids (1-35) -> TURN groups. 0/36 and anything else = other.
GROUPS = ["other", "wall", "door", "window", "furniture", "stairs"]
FPC_GROUP = {
    **{i: "door" for i in range(1, 7)},  # single, double, sliding, folding, revolving, rolling door
    **{i: "window" for i in range(7, 11)},  # window, bay window, blind window, opening symbol
    **{i: "furniture" for i in range(11, 28)},  # sofa .. toilet (fixtures and furniture)
    28: "stairs",
    29: "stairs",  # elevator
    30: "stairs",  # escalator
    31: "furniture",  # row chairs
    32: "furniture",  # parking spot
    33: "wall",
    34: "wall",  # curtain wall
    35: "wall",  # railing
}
FEATURES = [
    "is_curve",
    "len_u",
    "log_len_u",
    "cos2a",
    "sin2a",
    "axis",
    "width_w",
    "radius_u",
    "sweep_90",
    "deg0",
    "deg1",
    "n_r1",
    "n_r2",
    "par_r1",
    "curve_frac_r2",
    "mean_len_r2",
    "long_frac_r2",
]


def segments_from_strokes(strokes: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """PDF strokes (vector_pdf.parse_page) -> segments (N, 2, 2) endpoints, info (N, 4) =
    [is_curve, width, radius, sweep_deg], owner (N,) = index of the stroke each came from."""
    segs, info, owner = [], [], []
    for k, s in enumerate(strokes):
        w = float(s["style"][0])
        if s["kind"] == "c" and "r" in s:
            segs.append([s["pts"][0], s["pts"][-1]])
            info.append([1.0, w, float(s["r"]), float(s.get("sweep", 0.0))])
            owner.append(k)
            continue
        pts = s["pts"]
        for a, b in zip(pts[:-1], pts[1:], strict=False):
            if np.allclose(a, b):
                continue
            segs.append([a, b])
            info.append([0.0, w, 0.0, 0.0])
            owner.append(k)
    if not segs:
        return np.zeros((0, 2, 2)), np.zeros((0, 4)), np.zeros(0, int)
    return np.asarray(segs, float), np.asarray(info, float), np.asarray(owner, int)


def features(segs: np.ndarray, info: np.ndarray) -> np.ndarray:
    """Per-segment feature matrix (N, len(FEATURES))."""
    from scipy.spatial import cKDTree

    n = len(segs)
    if n == 0:
        return np.zeros((0, len(FEATURES)))
    d = segs[:, 1] - segs[:, 0]
    chord = np.hypot(d[:, 0], d[:, 1])
    is_curve = info[:, 0] > 0
    # a curve's length is its arc length
    length = np.where(is_curve, info[:, 2] * np.radians(info[:, 3]), chord)
    length = np.maximum(length, 1e-9)
    u = float(np.median(length)) or 1.0
    widths = info[:, 1]
    w0 = float(np.median(widths[widths > 0])) if (widths > 0).any() else 1.0
    ang = np.arctan2(d[:, 1], d[:, 0])
    deg = np.degrees(ang) % 90
    axis = (np.minimum(deg, 90 - deg) < 2).astype(float)
    mid = segs.mean(axis=1) / u
    ends = np.vstack([segs[:, 0], segs[:, 1]]) / u
    etree = cKDTree(ends)
    deg_e = np.array([len(x) - 1 for x in etree.query_ball_point(ends, 0.02)], float)
    deg0, deg1 = deg_e[:n], deg_e[n:]
    tree = cKDTree(mid)
    r1 = tree.query_ball_point(mid, 2.0)
    r2 = tree.query_ball_point(mid, 8.0)
    len_u = length / u
    n_r1 = np.array([len(x) - 1 for x in r1], float)
    n_r2 = np.array([len(x) - 1 for x in r2], float)
    par = np.zeros(n)
    cfrac = np.zeros(n)
    mlen = np.zeros(n)
    lfrac = np.zeros(n)
    for i in range(n):
        nb = np.asarray([j for j in r1[i] if j != i], int)
        if len(nb):
            da = np.abs(((ang[nb] - ang[i]) + math.pi / 2) % math.pi - math.pi / 2)
            par[i] = float(((da < math.radians(5)) & (len_u[nb] > 0.5 * len_u[i]) & ~is_curve[nb]).sum())
        nb2 = np.asarray(r2[i], int)
        cfrac[i] = float(is_curve[nb2].mean())
        mlen[i] = float(len_u[nb2].mean())
        lfrac[i] = float((len_u[nb2] > 4).mean())
    return np.column_stack(
        [
            is_curve.astype(float),
            len_u,
            np.log1p(len_u),
            np.cos(2 * ang),
            np.sin(2 * ang),
            axis,
            widths / w0,
            info[:, 2] / u,
            info[:, 3] / 90.0,
            deg0,
            deg1,
            n_r1,
            n_r2,
            par,
            cfrac,
            mlen,
            lfrac,
        ]
    )


def load_classifier(path: str | Path):
    import joblib

    model = joblib.load(path)
    if list(getattr(model, "turn_features", FEATURES)) != FEATURES:
        raise ValueError(f"{path}: trained on other features; retrain with this version")
    return model


def stroke_groups(strokes: list[dict], model, min_prob: float = 0.8) -> dict[int, str]:
    """Stroke index -> predicted group, for strokes whose segments the model is sure about (length-weighted
    mean probability of the winning group >= min_prob). Strokes not in the result are unknown."""
    segs, info, owner = segments_from_strokes(strokes)
    if len(segs) == 0:
        return {}
    proba = model.predict_proba(features(segs, info))
    classes = list(model.classes_)
    w = np.hypot(*(segs[:, 1] - segs[:, 0]).T) + 1e-9
    out: dict[int, str] = {}
    for k in np.unique(owner):
        m = owner == k
        p = (proba[m] * w[m, None]).sum(0) / w[m].sum()
        best = int(np.argmax(p))
        if p[best] >= min_prob:
            out[int(k)] = GROUPS[int(classes[best])]
    return out
