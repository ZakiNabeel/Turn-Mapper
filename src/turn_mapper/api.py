"""Public API of the TURN-Mapper module (see docs/INTEGRATION_CONTRACT.md §5).

Only ``convert``, ``process_floor``, ``validate_package`` and ``load_package`` are public;
everything else in the package is internal and may change.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import cv2
import networkx as nx
import numpy as np

from . import __version__
from .config import VenueConfig, load_venue_config, single_image_config
from .export import floor_to_dict, png_bytes, read_package, venue_dict, write_json_package, write_package
from .graph import build_graph
from .ingest import load_floor, sha256_file
from .ir import FloorResult, FloorSpec, Issue, Segmentation
from .link import link_floors
from .pois import label_rooms, make_pois
from .preprocess import preprocess
from .report import overlay, route_overlay, write_html
from .scale import ROOM_METHODS, estimate_scale, point_evidence, room_evidence_scale, scale_from_evidence
from .segment import SEGMENTERS
from .transitions import find_transitions
from .validate import route_lengths, schema_errors, validate_floor
from .vectorize import vectorize


@dataclass
class ConvertResult:
    package: Path
    report: Path
    manifest: Path
    floors: list[dict]

    @property
    def all_passed(self) -> bool:
        return all(f["passed"] for f in self.floors)


def _git_commit() -> str | None:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL, cwd=Path(__file__).parent
            )
            .decode()
            .strip()
        )
    except Exception:
        return None


def footprint_px(seg) -> tuple[float, float]:
    """Width/height of the drawn building (bounding box of wall pixels)."""
    ys, xs = np.nonzero(seg.wall)
    return (float(xs.max() - xs.min()), float(ys.max() - ys.min())) if len(xs) else (0.0, 0.0)


def process_floor(
    spec: FloorSpec,
    cfg: VenueConfig,
    method: str = "classical",
    ref: FloorResult | None = None,
    seg_override: Segmentation | None = None,
) -> FloorResult:
    """Run every stage on one floor and return the pixel-space result (+ scale).

    ``ref``: an already-processed floor of the same building footprint (``scale_like`` in the venue config);
    if this floor has no measured evidence, its scale is transferred by footprint width.
    ``seg_override``: use these (e.g. hand-corrected) wall/floor masks instead of running a segmenter; every
    later stage runs as usual (the correction step, FR-19)."""
    p = cfg.params
    t: dict[str, float] = {}
    t0 = time.perf_counter()
    img = load_floor(spec)
    cad_s = img.source_meta.get("cad_m_per_px")
    if cad_s and not any(e.get("method") == "cad_units" for e in spec.scale_evidence):
        cad_ev = {"method": "cad_units", "m_per_px": cad_s, "units": img.source_meta.get("units")}
        spec = replace(spec, scale_evidence=[cad_ev, *spec.scale_evidence])
        img = replace(img, spec=spec)
    t["ingest"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    pre = preprocess(img, p)
    t["preprocess"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    seg = seg_override if seg_override is not None else SEGMENTERS[method].segment(pre, p)
    t["segment"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    pt_ev = point_evidence(spec.scale_evidence)
    room_ev = [e for e in spec.scale_evidence if e.get("method") in ROOM_METHODS]
    s_known = scale_from_evidence(pt_ev)[0] if pt_ev else None
    fw, fh = footprint_px(seg)
    transfer = None
    if s_known is None and ref is not None and fw > 0:
        rw, rh = ref.timings.get("_footprint", (0, 0))
        if rw > 0:
            s_known = ref.scale_m_per_px * rw / fw
            aspect_diff = abs((fw / fh) / (rw / rh) - 1) if fh and rh else 0.0
            transfer = {
                "method": "footprint_transfer",
                "from_floor": ref.image.spec.id,
                "from_scale_source": ref.scale_source,
                "ref_width_px": rw,
                "width_px": fw,
                "aspect_mismatch": round(aspect_diff, 3),
            }
    # only a measured scale drives metric geometry rules; a transferred one is used for the scale alone, so a
    # floor's doors and rooms do not depend on which other floor it borrowed its scale from
    s_geom = scale_from_evidence(pt_ev)[0] if pt_ev else None
    geom = vectorize(seg, pre.gray_raw, pre.text, p, s_geom, color_mask=pre.color_mask)
    t["vectorize"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    patterns = [cfg.label_patterns[spec.building]] if spec.building in cfg.label_patterns else []
    label_rooms(geom, pre.gray_raw, p, patterns, pre.text)  # before scale: room-size evidence names rooms
    t["ocr_labels"] = time.perf_counter() - t0
    room_fit, room_records, room_issues = (
        room_evidence_scale(geom, room_ev, [d.width_px for d in geom.doors]) if room_ev else (None, [], [])
    )
    if room_fit is not None and not pt_ev:
        s, s_src, s_ev = room_fit, "measured_room_size", room_records
        issues = list(room_issues)
    elif transfer:
        s, s_src, s_ev = s_known, "footprint_transfer", [transfer]
        issues = [
            Issue(
                "SCALE_TRANSFERRED",
                f"scale transferred from {transfer['from_floor']} "
                f"({transfer['from_scale_source']}) by footprint width",
            )
        ]
        if transfer["aspect_mismatch"] > 0.03:
            issues.append(
                Issue(
                    "SCALE_ANISOTROPY_SUSPECTED",
                    f"footprint aspect differs by "
                    f"{transfer['aspect_mismatch']:.1%} from {transfer['from_floor']}: image may be "
                    "stretched or cropped differently; measure this floor",
                )
            )
    else:
        s, s_src, s_ev, issues = estimate_scale(geom, pt_ev, p.door_width_prior_m)
        if s_src == "door_width_prior" and p.door_width_calibrated:
            s_src = "door_width_calibrated"
            s_ev = [{**e, "calibrated_from": "measured floors of this venue"} for e in s_ev]
    if s_src != "measured_room_size" and room_records:
        # room evidence that could not fit is still reported, as a check against the scale actually used
        for rec in room_records:
            if "m_per_px" in rec:
                rec["residual_pct"] = round(100 * (rec["m_per_px"] / s - 1), 1)
        s_ev = list(s_ev) + room_records
        issues = list(issues) + room_issues
    t["_footprint"] = (fw, fh)
    t_issues = find_transitions(geom, seg, s)
    t0 = time.perf_counter()
    graph, g_issues = build_graph(geom, s, p, seg.wall)
    t["graph"] = time.perf_counter() - t0
    pois, p_issues = make_pois(geom, graph)
    warnings = issues + t_issues + g_issues + p_issues
    if p.ocr:
        from .ocr import status as ocr_status

        st = ocr_status()
        if not st["available"]:
            warnings.append(Issue("OCR_UNAVAILABLE", st["detail"]))
    for r in geom.regions:
        if r.kind not in ("circulation", "transition") and not any(r.id in d.regions for d in geom.doors):
            warnings.append(Issue("ROOM_NO_DOOR", "no door detected for this room", r.id))
    return FloorResult(
        image=img,
        pre=pre,
        seg=seg,
        geom=geom,
        graph=graph,
        pois=pois,
        scale_m_per_px=s,
        scale_source=s_src,
        scale_evidence=s_ev,
        warnings=warnings,
        timings=t,
    )


def calibrate_door_width(done: dict[str, FloorResult], min_floors: int = 2) -> dict | None:
    """Drawn door width (m) on this venue's plans, from floors whose scale was measured: median door width in
    px times the measured scale, per floor, then the median over floors.
    None with fewer than ``min_floors``."""
    per = []
    for fid, fr in done.items():
        if fr.scale_source not in ("measured_room_size", "operator_two_point", "cad_units"):
            continue
        w = [d.width_px for d in fr.geom.doors]
        if w:
            per.append((fid, float(np.median(w)) * fr.scale_m_per_px))
    if len(per) < min_floors:
        return None
    return {
        "door_width_m": round(float(np.median([v for _, v in per])), 3),
        "floors": {f: round(v, 3) for f, v in per},
    }


def convert(
    inputs: list[str] | str,
    venue_config: str | None = None,
    out_dir: str = "runs/latest",
    floors: list[str] | None = None,
    method: str = "classical",
    force: bool = False,
    output_format: str = "json",
) -> ConvertResult:
    """Convert floor plan(s) into a venue map + QA report + run manifest.

    ``output_format``: ``"json"`` (default) writes ``<out>/venue.json`` with every floor embedded plus
    ``<out>/images/<floor>.png``; ``"turnmap"`` writes the zipped ``venue.turnmap``; ``"both"``: both."""
    if output_format not in ("json", "turnmap", "both"):
        raise ValueError("output_format must be json, turnmap or both")
    inputs = [inputs] if isinstance(inputs, str) else list(inputs)
    cfg = (
        load_venue_config(venue_config, input_file=inputs[0] if inputs else None)
        if venue_config
        else single_image_config(inputs[0])
    )
    specs = [f for f in cfg.floors if not floors or f.id in floors]
    if not specs:
        raise ValueError(f"no floors selected (available: {[f.id for f in cfg.floors]})")
    out = Path(out_dir)
    (out / "qa").mkdir(parents=True, exist_ok=True)
    run_id = f"{datetime.now(UTC):%Y-%m-%dT%H-%M-%SZ}_{cfg.id}"
    commit = _git_commit()
    test_buildings = set((cfg.splits or {}).get("test", []))

    pkg_floors: dict[str, tuple[dict, bytes]] = {}
    qa_files: dict[str, bytes] = {}
    summaries, venue_floors = [], []
    # floors that borrow scale from another floor are processed after it
    order = sorted(specs, key=lambda sp: 1 if sp.scale_like else 0)
    done: dict[str, FloorResult] = {}
    seconds: dict[str, float] = {}

    def _run(spec, c):
        t0 = time.perf_counter()
        ref = None
        if spec.scale_like:
            ref = done.get(spec.scale_like)
            if ref is None:
                ref_spec = next((f for f in cfg.floors if f.id == spec.scale_like), None)
                ref = process_floor(ref_spec, c, method) if ref_spec else None
        done[spec.id] = process_floor(spec, c, method, ref=ref)
        seconds[spec.id] = time.perf_counter() - t0

    for spec in order:
        _run(spec, cfg)
    calibration = calibrate_door_width(done)
    if calibration:
        # floors still on the generic door prior are re-scaled with the door width measured on this venue
        c2 = replace(
            cfg,
            params=replace(
                cfg.params, door_width_prior_m=calibration["door_width_m"], door_width_calibrated=True
            ),
        )
        for spec in order:
            fr0 = done[spec.id]
            ref_src = (
                done[spec.scale_like].scale_source if spec.scale_like and spec.scale_like in done else None
            )
            if fr0.scale_source == "door_width_prior" or (
                fr0.scale_source == "footprint_transfer" and ref_src == "door_width_calibrated"
            ):
                _run(spec, c2)
    for spec in order:
        t0 = time.perf_counter() - seconds[spec.id]
        fr = done[spec.id]
        fd = floor_to_dict(fr)
        errs, warns = validate_floor(fd, cfg.params.inside_tolerance_m)
        all_warn = [w.to_dict() for w in fr.warnings] + [w.to_dict() for w in warns]
        passed = not errs
        fd["validation"] = {
            "passed": passed,
            "forced": (not passed) and force,
            "errors": [e.to_dict() for e in errs],
            "warnings": all_warn,
        }
        routes = route_lengths(fd)
        ov = overlay(fr)
        ro = route_overlay(fr, routes)
        cv2.imwrite(str(out / "qa" / f"{spec.id}_overlay.png"), ov)
        cv2.imwrite(str(out / "qa" / f"{spec.id}_routes.png"), ro)
        qa_files[f"{spec.id}_overlay.png"] = cv2.imencode(".png", ov)[1].tobytes()
        g = nx.Graph([(e["from"], e["to"]) for e in fd["graph"]["edges"]])
        g.add_nodes_from(n["id"] for n in fd["graph"]["nodes"])
        summaries.append(
            {
                "id": spec.id,
                "name": spec.name,
                "passed": passed,
                "split": "test" if spec.building in test_buildings else "dev",
                "scale": fr.scale_m_per_px,
                "scale_source": fr.scale_source,
                "n_rooms": len(fd["rooms"]),
                "n_doors": len(fd["doors"]),
                "n_nodes": len(fd["graph"]["nodes"]),
                "n_edges": len(fd["graph"]["edges"]),
                "n_pois": len(fd["pois"]),
                "n_review": sum(p["needs_review"] for p in fd["pois"]),
                "n_components": nx.number_connected_components(g) if len(g) else 0,
                "errors": fd["validation"]["errors"],
                "warnings": all_warn,
                "routes": routes,
                "overlay": f"{spec.id}_overlay.png",
                "routes_img": f"{spec.id}_routes.png",
                "seconds": time.perf_counter() - t0,
                "timings": fr.timings,
            }
        )
        (out / "floors").mkdir(exist_ok=True)
        (out / "floors" / f"{spec.id}.json").write_text(json.dumps(fd, indent=1))
        if passed or force:
            pkg_floors[spec.id] = (fd, png_bytes(fr.image.rgb))
            venue_floors.append(
                {
                    "id": spec.id,
                    "building_id": spec.building,
                    "level": spec.level,
                    "name": spec.name,
                    "path": f"floors/{spec.id}/floor.json",
                    "source": fr.image.source_meta,
                    "validation_passed": passed,
                }
            )

    report = write_html(
        out,
        {"run_id": run_id, "generator": f"turn-mapper {__version__}", "method": method, "git_commit": commit},
        summaries,
    )
    qa_files["index.html"] = report.read_bytes()
    pkg_path = out / ("venue.json" if output_format == "json" else "venue.turnmap")
    link_warns: list[dict] = []
    if venue_floors:
        links, link_warns = link_floors(
            [(v, pkg_floors[v["id"]][0]) for v in venue_floors if v["id"] in pkg_floors]
        )
        vd = venue_dict(cfg.id, cfg.name, cfg.buildings, venue_floors, run_id, commit, method, links)
        if output_format in ("turnmap", "both"):
            write_package(out / "venue.turnmap", vd, pkg_floors, qa_files)
        if output_format in ("json", "both"):
            write_json_package(out / "venue.json", vd, pkg_floors)
    manifest = {
        "run_id": run_id,
        "generator": {"name": "turn-mapper", "version": __version__, "git_commit": commit},
        "method": method,
        "venue_config": cfg.path,
        "venue_config_sha256": sha256_file(cfg.path) if cfg.path else None,
        "inputs": {Path(i).name: sha256_file(i) for i in inputs if Path(i).exists()},
        "params": cfg.params.to_dict(),
        "floors": [{k: v for k, v in s.items() if k not in ("routes",)} for s in summaries],
        "link_warnings": link_warns,
        "door_width_calibration": calibration,
        "package": str(pkg_path) if venue_floors else None,
    }
    mpath = out / "run_manifest.json"
    mpath.write_text(json.dumps(manifest, indent=1, default=str))
    return ConvertResult(package=pkg_path, report=report, manifest=mpath, floors=summaries)


def validate_package(path: str) -> dict:
    """Schema + geometry validation of a ``venue.json`` or ``.turnmap``.

    Returns {'passed', 'venue', 'floors'}."""
    pkg = read_package(path)
    out = {"venue": [e.to_dict() for e in schema_errors(pkg["venue"], "venue")], "floors": {}}
    for fid, fd in pkg["floors"].items():
        errs, warns = validate_floor(fd)
        out["floors"][fid] = {"errors": [e.to_dict() for e in errs], "warnings": [w.to_dict() for w in warns]}
    out["passed"] = not out["venue"] and all(not f["errors"] for f in out["floors"].values())
    return out


def load_package(path: str) -> dict:
    """Read a ``venue.json`` or ``.turnmap`` into plain dicts.

    Returns {'venue', 'floors': {id: floor dict}, 'images': {id: png bytes}}."""
    return read_package(path)
