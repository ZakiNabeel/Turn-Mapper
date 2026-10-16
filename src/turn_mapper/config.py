"""Pipeline parameters and venue configuration.

Venue configs (configs/venues/*.yaml) hold building-specific knowledge (ADR-010). Pipeline
parameters below are generic defaults; units are metres unless suffixed ``_px``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from .ir import FloorSpec


@dataclass
class PipelineParams:
    # preprocess
    ocr: bool = True
    ocr_upscale: float = 2.0
    ocr_min_conf: float = 0.45
    # segmentation (grey levels are estimated per image; these are tolerances)
    floor_tolerance: int = 8
    wall_max_gray: int = 210
    ink_threshold: float = 0.08  # min darkness relative to local paper/fill to count as a stroke
    wall_min_run_frac: float = 0.025  # straight run length (of the short side) that marks a wall stroke
    stairs_max_noise: float = 2.5  # stairs/partition detectors need a clean (non-scanned) drawing
    # vectorize
    door_max_width_m: float = 1.2  # largest opening closed as a (single) door; double doors via partitions
    door_gap_wall_ratio: float = 8.5  # before scale is known: max door gap = ratio x wall thickness
    min_region_area_m2: float = 1.0
    circulation_min_doors: int = 3
    # stairs: smooth grey gradient close to the floor colour (not flat floor, not walls/text)
    stairs_window_frac: float = 0.05  # texture window as a fraction of the image's short side
    stairs_density: float = 0.35
    stairs_min_area_frac: float = 0.5  # min blob area, in window^2
    # partitions: thin (1-2 px) straight lines with floor on both sides, at least this long
    partition_min_len_frac: float = 0.035  # of the image's short side (min 25 px)
    # scale
    door_width_prior_m: float = 0.9
    # graph
    hole_fill_m2: float = 2.0
    spur_prune_m: float = 1.5
    node_merge_m: float = 0.6
    simplify_tol_m: float = 0.25
    max_edge_m: float = 8.0
    door_link_max_m: float = 6.0
    # validate
    inside_tolerance_m: float = 0.05

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VenueConfig:
    id: str
    name: str
    buildings: list[dict]
    floors: list[FloorSpec]
    label_patterns: dict = field(default_factory=dict)
    params: PipelineParams = field(default_factory=PipelineParams)
    source_sha256: str | None = None
    path: str | None = None
    splits: dict = field(default_factory=dict)  # {'dev': [building ids], 'test': [...]}  (ADR-009)


def load_venue_config(path: str | Path, input_file: str | None = None) -> VenueConfig:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    src = raw.get("source", {}) or {}
    src_file = input_file or src.get("file")
    scale_ev = raw.get("scale_evidence") or {}
    floors = []
    for f in raw["floors"]:
        floors.append(
            FloorSpec(
                id=f["id"],
                building=f["building"],
                level=int(f["level"]),
                name=f.get("name") or f"{f['building']} Block – level {f['level']}",
                source_file=f.get("file", src_file),
                page=f.get("page"),
                image_index=f.get("image_index"),
                scale_evidence=list(scale_ev.get(f["id"], []) or []),
                crop=tuple(f["crop"]) if f.get("crop") else None,
                scale_like=f.get("scale_like"),
                options=dict(f.get("options") or {}),
            )
        )
    params = PipelineParams(**(raw.get("params") or {}))
    return VenueConfig(
        id=raw["venue"]["id"],
        name=raw["venue"]["name"],
        buildings=raw.get("buildings", []),
        floors=floors,
        label_patterns=raw.get("label_patterns", {}) or {},
        params=params,
        source_sha256=src.get("sha256"),
        path=str(path),
        splits=raw.get("splits", {}) or {},
    )


def single_image_config(image_path: str) -> VenueConfig:
    stem = Path(image_path).stem
    spec = FloorSpec(id="F1", building="B1", level=0, name=stem, source_file=image_path)
    return VenueConfig(id=stem, name=stem, buildings=[{"id": "B1", "name": "Building"}], floors=[spec])
