"""Public API of the TURN-Mapper module (see docs/INTEGRATION_CONTRACT.md §5).

Only ``convert``, ``process_floor``, ``validate_package`` and ``load_package`` are public;
everything else in the package is internal and may change.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import cv2
import networkx as nx

from . import __version__
from .config import VenueConfig, load_venue_config, single_image_config
from .export import floor_to_dict, png_bytes, read_package, venue_dict, write_package
from .graph import build_graph
from .ingest import load_floor, sha256_file
from .ir import FloorResult, FloorSpec, Issue
from .pois import label_rooms, make_pois
from .preprocess import preprocess
from .report import overlay, route_overlay, write_html
from .scale import estimate_scale, scale_from_evidence
from .segment import SEGMENTERS
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


def process_floor(spec: FloorSpec, cfg: VenueConfig, method: str = "classical") -> FloorResult:
    """Run every stage on one floor and return the pixel-space result (+ scale)."""
    p = cfg.params
    t: dict[str, float] = {}
    t0 = time.perf_counter()
    img = load_floor(spec)
    t["ingest"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    pre = preprocess(img, p)
    t["preprocess"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    seg = SEGMENTERS[method].segment(pre, p)
    t["segment"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    s_known = scale_from_evidence(spec.scale_evidence)[0] if spec.scale_evidence else None
    geom = vectorize(seg, pre.gray_raw, pre.text, p, s_known)
    t["vectorize"] = time.perf_counter() - t0
    s, s_src, s_ev, issues = estimate_scale(geom, spec.scale_evidence, p.door_width_prior_m)
    t0 = time.perf_counter()
    patterns = [cfg.label_patterns[spec.building]] if spec.building in cfg.label_patterns else []
    label_rooms(geom, pre.gray_raw, p, patterns)
    t["ocr_labels"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    graph, g_issues = build_graph(geom, s, p, seg.wall)
    t["graph"] = time.perf_counter() - t0
    pois, p_issues = make_pois(geom, graph)
    warnings = issues + g_issues + p_issues
    for r in geom.regions:
        if r.kind != "circulation" and not any(r.id in d.regions for d in geom.doors):
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


def convert(
    inputs: list[str] | str,
    venue_config: str | None = None,
    out_dir: str = "runs/latest",
    floors: list[str] | None = None,
    method: str = "classical",
    force: bool = False,
) -> ConvertResult:
    """Convert floor plan(s) into a venue .turnmap package + QA report + run manifest."""
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
    for spec in specs:
        t0 = time.perf_counter()
        fr = process_floor(spec, cfg, method)
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
    pkg_path = out / "venue.turnmap"
    if venue_floors:
        vd = venue_dict(cfg.id, cfg.name, cfg.buildings, venue_floors, run_id, commit, method)
        write_package(pkg_path, vd, pkg_floors, qa_files)
    manifest = {
        "run_id": run_id,
        "generator": {"name": "turn-mapper", "version": __version__, "git_commit": commit},
        "method": method,
        "venue_config": cfg.path,
        "venue_config_sha256": sha256_file(cfg.path) if cfg.path else None,
        "inputs": {Path(i).name: sha256_file(i) for i in inputs if Path(i).exists()},
        "params": cfg.params.to_dict(),
        "floors": [{k: v for k, v in s.items() if k not in ("routes",)} for s in summaries],
        "package": str(pkg_path) if venue_floors else None,
    }
    mpath = out / "run_manifest.json"
    mpath.write_text(json.dumps(manifest, indent=1, default=str))
    return ConvertResult(package=pkg_path, report=report, manifest=mpath, floors=summaries)


def validate_package(path: str) -> dict:
    """Schema + geometry validation of a .turnmap package. Returns {'passed', 'venue', 'floors'}."""
    pkg = read_package(path)
    out = {"venue": [e.to_dict() for e in schema_errors(pkg["venue"], "venue")], "floors": {}}
    for fid, fd in pkg["floors"].items():
        errs, warns = validate_floor(fd)
        out["floors"][fid] = {"errors": [e.to_dict() for e in errs], "warnings": [w.to_dict() for w in warns]}
    out["passed"] = not out["venue"] and all(not f["errors"] for f in out["floors"].values())
    return out


def load_package(path: str) -> dict:
    """Read a .turnmap into plain dicts: {'venue', 'floors': {id: floor.json}, 'images': {id: png bytes}}."""
    return read_package(path)
