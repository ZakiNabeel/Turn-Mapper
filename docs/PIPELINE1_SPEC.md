# Pipeline 1 Specification — Floor Plan → Navigable Map

Status: **Draft v0.1 (2026-10-03).** To be refined by the Claude Code audit + master plan. Owner: Zaki Nabeel (map intelligence / CV), with Shehryar Faisal (platform integration).

---

## 1. Goal

Given a floor plan of a large non-residential building (university, mall, hospital), produce a **TURN Map Package**: metric walkable geometry, walls, doors, labelled destinations and a routeable navigation graph, which the existing Android app imports into a project and routes over with its existing A*.

Research claim we want to be able to support (conservatively):

> AI-assisted, human-verified map preparation reduces the operator effort to make a floor navigable, compared with fully manual setup in the same app, while producing a graph whose routes are valid (no wall crossings, all destinations reachable).

We are **not** claiming fully automatic mapping. The human QA step is part of the design.

## 2. Scope

### In scope (FYP)

- Raster input (PNG/JPEG, raster PDF) — primary branch.
- Vector PDF and DXF input — second branch (preserve geometry, don't rasterise it away).
- Classes: wall, door, room/shop, walkable/corridor, stairs, lift, escalator (icons), text labels.
- Metric scale from operator two-point input (and dimension-text OCR as a bonus).
- Walkable polygon, corridor centreline graph, door connections, POIs from OCR labels.
- Validators and a visual QA report.
- Export to Map Package; Android import; manual correction in the app's existing editor.
- Evaluation against hand-made ground truth, including effort measurement.

### Out of scope (for now)

- Multi-floor alignment and vertical transition linking (later milestone; schema must allow it).
- Photos of printed evacuation signs taken at an angle (perspective) — stretch goal only.
- Any on-device ML inside the Android app.
- Cloud backend / web portal.

## 3. Architecture overview

Offline Python tool, run on a laptop (training on Colab/Kaggle GPU). Output is a file, the app imports it.

```text
                    ┌──────────────── TURN-Mapper repo ───────────────┐
 plan.pdf/.dxf/.png │                                                  │
 ──────────────────►│ ingest ─┬─ vector branch (PDF paths / DXF) ─┐    │
                    │         └─ raster branch                    │    │
                    │              preprocess                     │    │
                    │              segment (classical | learned)  │    │
                    │              detect symbols                 │    │
                    │              ocr                            │    │
                    │              vectorize ◄────────────────────┘    │
                    │         scale (operator points / OCR dims)       │
                    │         walkable  ->  graph  ->  pois            │
                    │         validate  ->  qa_report.html             │
                    │         export    ->  floor.turnmap  ────────────┼──► Android app
                    └──────────────────────────────────────────────────┘    import → project
                                                                             → operator fixes in
                                                                               existing editor
                                                                             → A* routing
```

Rationale is in `DECISIONS.md` (ADR-001 to ADR-010).

### 3.1 Module shape

TURN-Mapper is a standalone module (own repo, ADR-002). Its public surface is only:

- `turn_mapper.api` — `convert()`, `validate_package()`, `load_package()` (see `INTEGRATION_CONTRACT.md` §5);
- the `turn-mapper` CLI (`inspect`, `run`, `validate`, later `eval`), a thin wrapper over the API;
- the `.turnmap` output defined by `contract/`.

Everything inside (IR, stages, models) is private and may change freely.

### 3.2 "Any floor plan" = adapters + venue config + human QA

- **Input adapters** (`ingest/`): `pdf_vector`, `pdf_raster`, `image`, `dxf`, later `photo` (perspective-corrected). A registry picks the best adapter per file/page.
- **Venue config** (`configs/venues/*.yaml`): which file/page is which building and floor, optional crop box per page, measured distances for scale, label regex (e.g. FAST rooms like `C-\d{3}`), classes to ignore. A new building needs a new config, not new code.
- **Multi-page / multi-building input**: one PDF may contain several blocks and floors (e.g. FAST A/B/C). `inspect` lists pages with thumbnails, text and vector/raster type to help write the venue config; `run` processes every configured page into one venue package.
- **Human QA**: validators + QA report + correction in the app. The pipeline is judged on how much correction it saves, not on being perfect.

## 4. Stages — inputs, outputs, methods

Each stage writes artefacts to `runs/<run>/<NN_stage>/` and can be re-run alone. Every artefact carries provenance.

### 4.0 `inspect` (operator helper, run first on any new plan)
- For every page/file: vector drawing count, embedded image count/resolution, extractable text sample, page size, presence of scale bar / dimension text, thumbnail.
- Output: `inspect.json` + an HTML contact sheet. Used to write the venue config and to decide vector vs raster branch.

### 4.1 `ingest`
- Detect type per page: DXF / PDF with vector content / raster PDF / image.
- PDF: use PyMuPDF. If page has substantial vector drawings (`get_drawings()`), route to vector branch **and** also render a raster (e.g. 300 DPI) for the raster branch / visual QA.
- Output: `source.json` (type, page, DPI, pixel size, hash), `raster.png`.

### 4.2 `preprocess` (raster)
- Grayscale, deskew, denoise, adaptive binarisation.
- Crop/mask title block, legend, north arrow, dimension lines where detectable (operator can supply a crop box in config).
- Normalise resolution for the model (tile large plans rather than downscaling them into mush).
- Output: `clean.png`, `mask_ignore.png`.

### 4.3 `segment`
Two interchangeable implementations behind one interface `segment(image) -> SemanticMask + per-class probability`:

1. **Classical baseline** (build first): thick-line / morphology wall extraction, flood-fill regions, heuristics for corridor vs room (area, elongation, connectivity). Exists so (a) the end-to-end chain works on day one and (b) the learned model has a baseline to beat in the report.
2. **Learned model**: semantic segmentation with a pretrained encoder (start with `segmentation_models_pytorch` U-Net or DeepLabV3+ with ResNet/EfficientNet encoder; SegFormer as an alternative). Pretrain on CubiCasa5K mapped to TURN classes, fine-tune on annotated non-residential plans. Sliding-window inference with overlap for large plans.

Classes: `0 background, 1 wall, 2 room, 3 corridor/walkable, 4 door, 5 stairs, 6 lift, 7 escalator` (final list fixed in `DATA_AND_ANNOTATION.md`).

### 4.4 `detect_symbols` (optional stage, later)
- Doors/stairs/lifts as objects (YOLO-family detector) if segmentation alone handles them poorly. Results fused into the mask/vector layer.

### 4.5 `ocr`
- PaddleOCR (EasyOCR/Tesseract as fallbacks). Output text boxes with confidence.
- Classify text: room code (e.g. `C-405`), name ("Lab 2"), dimension (`12.4 m`, `4500`), noise.
- Associate names/codes to the room polygon that contains (or is nearest to) the box centroid.

### 4.6 `vectorize`
- Mask → polygons (contours, hole handling), morphological gap closing, Douglas–Peucker simplification, optional Manhattan snapping (most institutional plans are axis-aligned; snap angles within a tolerance).
- Walls → line segments with thickness; doors → opening segments in walls.
- Vector branch joins here: DXF/PDF entities are classified by layer name, line weight and geometry heuristics into the same intermediate representation.
- Output: `geometry_px.json` (pixel coords, clean topology, Shapely-valid).

### 4.7 `scale`
- Primary: operator supplies two pixel points + measured distance (config or CLI). Additional measured pairs are used to report scale error.
- Bonus: parse dimension text near dimension lines to propose a scale for confirmation.
- Builds the affine `image_px → world_m` transform, including the y-axis flip if the app's world frame is y-up (to be confirmed from source in the audit).
- Output: `transform.json`, `geometry_m.json`.

### 4.8 `walkable`
- Walkable = interior − walls − rooms/shops − obstacles, plus door openings connecting rooms to corridors.
- Union small slivers, remove tiny islands, keep the largest connected component(s) plus any explicitly kept.
- Output: walkable MultiPolygon in metres.

### 4.9 `graph`
- Corridor centreline from the walkable polygon: medial axis / skeletonisation (`skimage.morphology.skeletonize` on a rasterised walkable mask at fixed cm/px, or Voronoi-based straight skeleton).
- Skeleton → graph (junctions + endpoints as nodes), prune spurs shorter than a threshold, merge near-duplicate nodes, simplify straight runs, insert nodes at regular max spacing (e.g. ≤ 8 m) so the app's ~3 m path-attachment works.
- Door nodes: one per room door, connected to the nearest visible corridor node with a wall-safe edge.
- Edge weights = metric length. Edge attributes: `type` (corridor|door|stairs|lift|escalator), `accessible` = unknown unless verified.
- Must satisfy the app's own rules: edges never cross walls and never leave walkable space; crossing edges share a node.

### 4.10 `pois`
- Each labelled room → POI attached to its door node (not its centroid).
- Unlabelled rooms → POI with placeholder name and `needs_review: true`.

### 4.11 `validate`
Hard failures block export (unless `--force` with the failure recorded in the package):
- geometry valid (Shapely `is_valid`), walkable non-empty;
- no edge intersects a wall; every edge lies inside walkable (with tolerance);
- graph connected (or every component reported);
- every POI reachable from the largest component;
- coordinates inside floor bounds; scale present.

Warnings (shown in QA report): tiny rooms, rooms without doors, very long edges, dangling spurs, unlabelled POIs, low-confidence regions.

### 4.12 `qa_report`
- HTML page with overlays on the plan: mask, walls, walkable, graph, POIs, low-confidence heatmap, validator results, sample A* routes between random POI pairs.
- This is what the operator looks at before importing.

### 4.13 `export`
- Writes `<floor>.turnmap` (see `MAP_PACKAGE_SCHEMA.md`).

## 5. Android integration (done in the app repo — see INTEGRATION_CONTRACT.md)

- **Importer** (Kotlin): reads a `.turnmap`, validates `schema_version`, creates a **new** project/floor (never overwrites an existing one in v1), writes floor plan image, calibration, walkable polygon, walls, graph nodes/edges and POIs through existing repositories. Marks imported items with provenance if the schema supports it (may need an additive migration).
- **Exporter for ground truth**: export a manually built floor to the same package format so evaluation compares like with like.
- **Correction**: operator uses existing Layout/Paths/Destinations tools. Optionally count editor operations for the effort study (see `EVALUATION_PROTOCOL.md`).
- If the app's internal model cannot represent something (e.g. multiple walkable polygons, door entities, edge types), the audit must list it and the plan must choose: extend Room additively, or degrade gracefully in the importer and record what was dropped.

## 6. Engineering requirements

- Deterministic runs (fixed seeds, recorded versions); `run_manifest.json` per run.
- Stage caching keyed by input hash + config hash.
- Unit tests on synthetic plans (generated rectangles/corridors with known answers) for vectorize, scale, walkable, graph, validate, export.
- Golden test: one small real plan with a checked-in expected package (tolerant comparison).
- Schema round-trip test: Python writes → JSON Schema validates → Kotlin reads (fixture shared between both test suites).
- Runs on CPU for inference on a single plan in reasonable time (target < 2 min for one floor); GPU only for training.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Domain gap (CubiCasa is residential) | Fine-tune on annotated institutional/commercial plans; report pretrain-only vs fine-tuned; human QA always in loop |
| Plans have title blocks, hatching, furniture, dimension clutter | Preprocess masks; ignore regions in config; class for "other" |
| Only a photo of the plan is available | Ask estate office for PDF/DWG first; perspective correction as stretch |
| App data model too limited for imported geometry | Audit first; additive migration or explicit degrade |
| Graph has unreachable POIs / wall-crossings | Hard validators; QA report; fix in app editor |
| Scale error | Multiple measured pairs; report scale residual |
| Effort study is unconvincing | Pre-registered protocol, same operator tasks, time + operation counts, multiple operators if possible |
| Time sink in model training | Classical baseline + manual fallback means the chain never depends on the model |
