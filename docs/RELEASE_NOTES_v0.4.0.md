# TURN-Mapper v0.4.0 — FYP-1 final release (2026-11-27)

Since v0.3.0 (mid-evaluation, `e00ee57`). Contract: **schema 0.1.3** (additive; 0.1.1 readers still work).
Every number is from a recorded run; the results files are linked.

## Map intelligence

- **Inputs:** DXF, SVG and vector-PDF adapters with measured `cad_units` scale; DWG via conversion; text-layer
  room labels; RapidOCR fallback when Tesseract is missing.
- **Scale:** site-measured room sizes (`measured_room_size`) and venue door-width calibration
  (RESULTS_SCALE_2026-10-24). Floors with an estimated scale are corrected from a measured floor of the same
  building by wall alignment.
- **TURN Studio (FR-19 correction step):** a local GUI to convert, correct (rooms, doors, labels, walls, scale,
  links), re-validate and export. Corrected elements carry `provenance: corrected`. Studio also exports to
  editable DXF and saves corrections as training annotations.
- **Generality:** 24 public plans from 21 institutions (RESULTS_PUBLIC_PLANS_2026-10-27/28).

## Multi-floor and multi-building routing (FR-18 / M9)

- **Floor alignment and linking:** floors are aligned by their walls; stairs, lifts and escalators are paired
  by optimal matching; shafts are chained; a lift stop missed on a floor in between is proposed.
- **Connections between buildings:** from the venue config, by node, label, point or drawing edge.
- **Routing:** `turn-mapper route` gives per-floor legs, turn-by-turn steps, a time estimate and a
  step-free option.
- **Venue checks and grades:** a reach matrix, sampled cross-floor routes and a per-floor grade, shown in the
  QA report, `validate` and Studio.
- **FAST:** 182/182 floor pairs connected, 200/200 sampled cross-floor routes, 86/200 step-free
  (RESULTS_MULTIFLOOR_2026-11-10, RESULTS_CONNECTIVITY_2026-11-15).

## Learned segmenter

- **Stages:** S1 CubiCasa5K → S2 (ResPlan + generated institutional floors, 8 drawing styles) → S3a →
  **S4 (real CAD drawings, FloorPlanCAD, partial labels)**.
- **S4 on 4,891 unseen real CAD tiles:** mIoU 0.157 → 0.661; stairs 0.001 → 0.852; lifts 0 → 0.929; walls
  0.626 → 0.862 (RESULTS_ML_S4_2026-11-27).
- **Hybrid segmenter** (classical walls + confident network walls + network doors); the learned lift/stairs
  classes feed transitions.
- **Promotion rule not met** (synthetic thin-line cases; A block not yet annotated): **classical stays the
  default.**
- **Weights are not in git and not in this release:**
  - S4: Kaggle `turn-segmenter-s4-finetune` v3 output `out_s4/turn_seg_s4.pt`, sha256 `3f38249e…a2bad8`;
  - S3a: sha256 `d7db04ad…afd23b`.
  The training data licences (CubiCasa5K, FloorPlanCAD: CC BY-NC 4.0) allow research use only.

## For the Android app

- **Contract:** 0.1.3 types `venue.transitions` (stairs, lift, escalator, ramp, walkway) and adds
  `floor.building_frame`; the fixture is `contract/fixtures/json_synthetic_multifloor`.
- **Positioning export:** `positioning_export.py` writes the app's VenuePackage, imported by TURN-Field-Test
  (`docs/MAPPER_IMPORT.md` there).

## Quality

- **Tests:** 146 tests (CI runs ruff and pytest; the ML and Studio tests run where their extras are
  installed).
- **Synthetic:** 12/12 valid, free-space IoU 0.983, room and door recall 1.0, 0 wall crossings; style stress
  11/12.
