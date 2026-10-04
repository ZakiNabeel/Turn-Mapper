"""Intermediate representation passed between pipeline stages.

Pixel-space objects use image coordinates (u right, v down). Metric objects are produced only in
``scale``/``export`` and never leave the module as pixels.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from shapely.geometry import LineString, MultiPolygon, Point, Polygon


@dataclass
class FloorSpec:
    """One floor to process, as declared in a venue config (or derived for a single image)."""

    id: str
    building: str
    level: int
    name: str
    source_file: str
    page: int | None = None  # 1-based PDF page
    image_index: int | None = None
    scale_evidence: list[dict] = field(default_factory=list)
    crop: tuple[int, int, int, int] | None = None  # x0, y0, x1, y1 in px


@dataclass
class FloorImage:
    spec: FloorSpec
    rgb: np.ndarray  # HxWx3 uint8 (RGB)
    source_meta: dict


@dataclass
class TextBox:
    text: str
    conf: float  # 0..1
    box: tuple[int, int, int, int]  # x0, y0, x1, y1 px

    @property
    def center(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.box
        return ((x0 + x1) / 2, (y0 + y1) / 2)


@dataclass
class Preprocessed:
    gray: np.ndarray  # cleaned grayscale (text erased)
    gray_raw: np.ndarray
    text: list[TextBox]


@dataclass
class Segmentation:
    """Per-pixel classes. ``floor`` = interior floor of any space, ``wall`` = walls."""

    wall: np.ndarray  # bool
    floor: np.ndarray  # bool
    background: np.ndarray  # bool
    levels: dict  # estimated grey levels {'floor': .., 'wall': .., 'background': ..}
    method: str = "classical"


@dataclass
class Region:
    id: str
    polygon: Polygon  # px
    area_px: float
    kind: str  # "circulation" | "room" | "transition"
    label: str | None = None
    name: str | None = None
    ocr_conf: float | None = None


@dataclass
class Door:
    id: str
    segment: LineString  # px, across the opening
    center: Point
    regions: tuple[str, ...]  # region ids it connects
    width_px: float


@dataclass
class GeometryPx:
    regions: list[Region]
    doors: list[Door]
    walkable: MultiPolygon  # px
    wall_segments: list[tuple[tuple[float, float], tuple[float, float], float]]  # a, b, thickness px
    wall_mask_closed: np.ndarray
    debug: dict = field(default_factory=dict)


@dataclass
class GraphNode:
    id: str
    x: float
    y: float
    kind: str
    door_id: str | None = None


@dataclass
class GraphEdge:
    id: str
    a: str
    b: str
    length: float
    type: str = "corridor"


@dataclass
class NavGraph:
    nodes: dict[str, GraphNode]
    edges: list[GraphEdge]


@dataclass
class Poi:
    id: str
    name: str
    label: str | None
    node_id: str
    room_id: str
    needs_review: bool
    ocr_conf: float | None


@dataclass
class Issue:
    code: str
    message: str
    ref: str | None = None

    def to_dict(self) -> dict:
        return {"code": self.code, "ref": self.ref, "message": self.message}


@dataclass
class FloorResult:
    """Everything known about one processed floor, in pixels plus the px->m scale."""

    image: FloorImage
    pre: Preprocessed
    seg: Segmentation
    geom: GeometryPx
    graph: NavGraph
    pois: list[Poi]
    scale_m_per_px: float
    scale_source: str
    scale_evidence: list[dict]
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    timings: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.errors
