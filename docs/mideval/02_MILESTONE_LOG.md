# Milestone log: mapping module (TURN-Mapper)

Baseline plan: `docs/ROADMAP_AND_WORKFLOW.md` (2026-10-04, weeks counted from repo creation on 2026-10-04). Status as of **2026-10-12**.

Owners:

- **ZN**: Zaki Nabeel (map intelligence / CV, module owner)
- **SF**: Shehryar Faisal (platform / Android app)
- **MS**: M Sameer (positioning)

Status values: ✅ done, 🟡 in progress, ⏳ not started, 🔁 re-planned.

| M | Milestone | Owner | Planned | Actual / status | Evidence |
|---|---|---|---|---|---|
| M0 | Repo, docs, plan inventory of the FAST PDF, decisions log | ZN | wk 1 | ✅ 2026-10-04 | commit `9cf8406`, `docs/PLAN_INVENTORY.md`, `docs/DECISIONS.md` |
| M1 | Package skeleton, CLI, contract v0.1 schema + fixtures, CI | ZN | wk 1–2 | ✅ 2026-10-04 (ahead) | commit `a606f67`, tag `v0.1.0`, `.github/workflows/ci.yml` |
| M2 | Classical chain: plan → valid routable map | ZN | wk 2–4 | ✅ 2026-10-04 first version; C block 2026-10-04; style-generic 2026-10-11 (ahead) | tags `v0.1.0`, `v0.2.0`, `v0.3.0`; `RESULTS_*.md` |
| M6 | OCR labels + POIs (3 orientations) | ZN | wk 8–10 | ✅ 2026-10-04 (ahead of plan) | commit `801d5e4`, FR-03/FR-10 |
| — | JSON output + contract 0.1.1 | ZN | not in plan (request from integration) | ✅ 2026-10-11 | commit `9b6030d`, `contract/CHANGELOG.md` |
| — | Generality check + ground-truth evaluation script | ZN | part of M8 | ✅ 2026-10-11 / 2026-10-12 (early) | `scripts/style_stress.py`, `eval/evaluate_synthetic.py` |
| M4 | Data: CubiCasa mapped, institutional plans annotated, splits frozen | ZN (+team) | wk 2–6 | 🟡 CubiCasa → mask converter done and tested; FAST split frozen (ADR-009); annotation not started | `learned/cubicasa.py`, `test_svg_masks_match_drawing` |
| M5 | Learned segmentation behind the interface | ZN | wk 6–9 | 🟡 code complete and tested offline; GPU training not run | `learned/`, `notebooks/train_segmenter_colab.ipynb`, `docs/ML_GUIDE.md` |
| M3 | App import of the map package | SF (+ZN) | wk 4–5 | ⏳ (owner to update) | contract + fixtures ready for the importer |
| M7 | Vector PDF / DXF adapters | ZN | wk 10–12 | 🔁 deferred: the FAST PDF is raster, so no vector input is needed for the pilot | `PLAN_INVENTORY.md` (0 vector drawings) |
| M8 | Evaluation: FAST ground truth, routes, effort study | All | wk 12–14 | 🟡 synthetic Level B/C done; FAST ground truth blocked on site measurements | `05_TESTING.md` |
| M9 | Multi-floor linking | ZN + MS | later | 🟡 transition nodes per floor done; linking not started | ADR-014 |
| — | Operator correction step (FR-19) | ZN (+SF) | implied by "human-verified" | ⏳ | schema `provenance: corrected` |

## Delays: justification and recovery plan

The new dates below are proposed. The team confirms them at the next supervisor meeting.

| Item | Delay | Reason | Recovery action | New date |
|---|---|---|---|---|
| Metric scale from site measurements (FR-07a) | ~1 week | Measurements need management permission (request pending) | Footprint transfer + flagged door prior keep the maps usable; measure 2 distances per C floor in one visit | request sent by 2026-10-14, measured by **2026-10-23** |
| CubiCasa pre-training (M5) | ~1 week | Dataset download is blocked from the dev sandbox; needs a GPU notebook | Notebook ready; run on Colab or Kaggle (≈ 4 GPU-hours) | **2026-10-19** |
| Annotation of 5–8 B/C floors (M4) | ~1 week | Waiting for the pipeline to stabilise so that bootstrap masks are good | `ml bootstrap-masks` gives starting masks; ~30 min correction per floor | **2026-10-26** |
| Fine-tune + learned vs classical evaluation (M5/M8) | — | depends on the two rows above | run notebook stage 2; `ml eval` + A-block comparison | **2026-11-02** |
| App import (M3) | owner SF | app team priority was the positioning demo | contract 0.1.1 and fixtures handed over; importer reads `venue.json` | SF to confirm (target **2026-11-09**) |
| Multi-floor linking (M9) | on plan (stretch) | — | pair transition nodes by type + position across C floors | **2026-11-16** |
| Correction step (FR-19) | new item | needed to justify "human-verified" | minimal: edit rooms/doors/labels in JSON via a small web page or the app editor | **2026-11-23** |
