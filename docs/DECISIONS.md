# Decision Log — TURN-Mapper

One ADR per decision. Status ∈ Proposed | Accepted | Superseded. Claude Code may add **Proposed** ADRs; humans accept them.

---

## ADR-001 — Mapping runs offline in Python, not on the phone
Status: Proposed (2026-10-03)
Decision: TURN-Mapper produces a file; the app only imports it. No on-device ML.
Why: heavy ML/OCR/geometry libraries; operator QA on a laptop; Android app stays stable. Fits the B2B story (a venue is mapped once by an operator).

## ADR-002 — TURN-Mapper is its own repository (module) — supersedes the earlier "monorepo folder" idea
Status: Proposed (2026-10-04)
Decision: separate repo `TURN-Mapper`. Integration with the app repo only through the versioned `.turnmap` contract (`docs/INTEGRATION_CONTRACT.md`). The app repo vendors tagged contract files.
Why: the team is building several modules that are integrated later; a separate repo gives an independent Python toolchain/CI, clear ownership, and a clean public API.
Cost: contract changes need two PRs (one per repo). Mitigated by shared fixtures and tags.

## ADR-003 — `.turnmap` (ZIP + JSON, venue-level, per-floor files) is the only interface
Status: Proposed (2026-10-04)
Decision: see `MAP_PACKAGE_SCHEMA.md`. One package can hold multiple buildings/floors (needed for the FAST A/B/C block PDF). App v1 may import one floor at a time.

## ADR-004 — Human-in-the-loop is part of the design
Status: Proposed
Decision: provenance + confidence on all auto output; validators gate export; corrections in the app's existing editor (and optionally a later mapper-side editor). Claim: "AI-assisted, human-verified".

## ADR-005 — Vector-first when vectors exist
Status: Proposed
Decision: DXF / vector PDF parsed directly into the IR; segmentation only for raster input or ambiguous parts.

## ADR-006 — Thin end-to-end chain before ML
Status: Proposed
Decision: build ingest → classical segmentation → vectorize → scale → walkable → graph → validate → export → app import first; learned model replaces the classical segmenter behind the same interface later; classical stays as reported baseline.

## ADR-007 — Coordinate frame
Status: OPEN — filled after the app audit (Prompt A1).

## ADR-008 — How the app handles fields it cannot store
Status: OPEN — app audit decides per field: additive Room migration vs drop-with-warning.

## ADR-009 — Test set freeze
Status: **Accepted (rev. 2026-10-04): dev = B + C, test = A.** C is the main testing/demo building (team decision), so it's developed on. Earlier proposal was dev = B, test = A + C. File: Floor_Plans_2.pdf, SHA-256 8316d9d778c7468d54d3de471216a95c5d340b5f9d95c1ddc2656a47070cd38d. Floors of one block never split across dev/test. Change Status to Accepted with the date once agreed.
**Note 2026-10-04:** A/C floors were run once untuned (v1: test 1/11 valid) and their overlays inspected; one code-correctness fix followed (no threshold changes), giving v2 test 4/11. For the final evaluation, add floors nobody has looked at (see RESULTS_2026-10-04.md).

## ADR-010 — Pluggable input adapters + venue configs
Status: Proposed (2026-10-04)
Decision: every input format is an adapter in `ingest/` behind a registry (`can_handle(path) -> score`, `load(path, page) -> IngestResult`). Building-specific knowledge (page→floor mapping, crop boxes, measured distances, label patterns like `C-\d{3}`) lives in `configs/venues/<venue>.yaml`, never in code.
Why: the goal is "digest any floor plan"; new buildings should need a config, not code changes.

## ADR-011 — FAST plans: raster-first; treat as not-to-scale diagrams
Status: Proposed (2026-10-04)
Context: `Floor_Plans_2.pdf` (see `PLAN_INVENTORY.md`) has no vector content: embedded PNG/JPEG floor-planner screenshots in a Word export, with no scale bar or dimensions; per-floor pixel scale differs.
Decision: the raster branch is the critical path for the FAST demo; the vector branch (M7) stays for other venues. Scale is per floor, from on-site measurements on both axes, and the residual drawing error is reported. Ingest takes embedded images at native resolution instead of re-rendering pages.
Consequences: on-site measurement is a hard dependency before M2 can claim metric output; positioning results must mention map-drawing error.

## ADR-012 — Scale fallback: door-width prior, always flagged
Status: Proposed (2026-10-04)
Decision: if a floor has no measured `scale_evidence`, scale = 0.9 m / median detected door width (px). The package records `scale_source: door_width_prior` and a SCALE_ESTIMATED warning. On synthetic plans the error is about 2%; on real plans it's unknown until measured.
Why: lets the chain run end to end on any plan before site work, without pretending the scale is measured.

## ADR-013 — Validators run on the metric JSON, not on internal state
Status: Proposed (2026-10-04)
Decision: `validate_floor` checks the exported floor.json, so the same validator checks our output, app-exported ground truth, and hand-edited packages. Invalid fixtures name the error code the consumer must report.

## ADR-014 — Stairs and lifts are transition nodes, not traced space
Status: Proposed (2026-10-04)
Decision: detect stairs by texture (smooth grey gradient near the floor colour) and lifts by OCR text; exclude stairs from centre-line tracing; add a `transition` node at a walkable anchor (`transition: stairs|lift`) plus a POI. Multi-floor linking (M9) pairs these nodes across floors.

## ADR-015 — Scale transfer between floors of the same building (`scale_like`)
Status: Proposed (2026-10-04)
Decision: a floor may declare `scale_like: <floor>`; if it has no measured evidence, its scale = ref scale × ref footprint width / own footprint width (`scale_source: footprint_transfer`), with a warning if the outline aspect differs > 3 %. Lets one set of site measurements serve a whole block.

## ADR-016 — Circulation classification
Status: Proposed (2026-10-04)
Decision: circulation = the largest space plus spaces that connect to ≥3 *distinct* neighbouring spaces and are reachable from it through doors. Prevents rooms with several doors into one hall, and closed cubicle clusters, from becoming corridors.

## ADR-017 — Style-generic classical segmentation; measured door size only on line drawings
Status: Proposed (2026-10-11)
Decision: walls come from an ink map (darkness relative to local paper colour) with two modes: thick (solid walls) and thin (straight strokes, double lines fused). Plans whose floor is paper-coloured get their outside geometrically from the closed wall outline. Without scale, the door gap is measured from wall-end pairs on paper-floor plans; filled plans keep `door_gap_wall_ratio × wall thickness` (measuring there inflated gaps on FAST and broke A-F2/B-F1). Evidence: docs/RESULTS_GENERALITY_2026-10-11.md.

## ADR-018 — Learned segmenter = per-pixel U-Net behind the Segmenter interface
Status: Proposed (2026-10-11)
Decision: the network predicts 9 navigation classes per pixel (bg, wall, room, walkable, door, stairs, lift, escalator, other); the rest of the pipeline is unchanged and its validators still gate output. U-Net/ResNet-34 (segmentation_models_pytorch), grey input, CE + Dice, pre-trained on CubiCasa5K (CC BY-NC, non-commercial, never in git), fine-tuned on own annotated plans (never A block). Inference rescales plans to the training wall thickness and tiles them. Rejected: end-to-end graph prediction (needs far more labels, can't reuse validators); raster-to-vector models (e.g. CubiCasa's multi-task heads) as a first step: more complex for no navigation benefit yet.
