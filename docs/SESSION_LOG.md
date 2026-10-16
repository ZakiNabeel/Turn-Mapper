# Session Log — TURN-Mapper

Newest entry at the top. Every Claude Code session (and every human session that changes the module) adds one. `/handoff` writes it.

## Template

```markdown
## YYYY-MM-DD — <who> — <milestone/step>
**Goal:**
**Changed:** (files / modules)
**Verified:** (exact commands and real results; QA report paths)
**Not verified / unknown:**
**Broken or risky:**
**Decisions / ADRs proposed:**
**Next step:**
```

---

## 2026-10-16 (later) — Zaki (+Claude) — multi-floor links, DWG, stairs filter, tests
**Goal:** execute the cloud-doable remainder of docs/MASTER_PLAN.md.
**Changed:** src/turn_mapper/link.py (new), export.py (`venue_dict(transitions=)`), api.py (links + `link_warnings` in manifest), transitions.py (min-area filter), ingest.py (`dwg_to_dxf`), studio/{project,server}.py + static (links tab, DWG upload), tests/test_link.py, tests/test_cli_links_studio.py, tests/test_adapters_cad.py, docs (MASTER_PLAN, STUDIO_GUIDE, MAP_PACKAGE_SCHEMA, contract/CHANGELOG note).
**Verified:** `pytest -q` 83 passed; ruff clean. FAST re-run (`runs` in /tmp): 10 floors valid, 12 auto stair links, same per-floor transition counts as before the stairs filter. Style stress 11/12 as recorded.
**Not verified / unknown:** links against real geometry (no ground truth; confidence is a distance heuristic); real DWG (only a stand-in converter); the learned-model door-arc false positive (not reproduced here); S2 training (needs Kaggle); Studio on Windows.
**Broken or risky:** D-10 not auto-fixed (2-4 graph parts on B-F1, C-GF, C-F2, C-F5); C-B1 vs C-GF footprints differ 39% so not linked; D-11 vector-PDF DPI sensitivity open.
**Decisions:** a fat-blob stair filter was tried and reverted (removed a real staircase on C-F2); only a 1 m2 minimum stays.
**Next step:** Zaki runs the Kaggle S2 notebook; correct B/C floors in Studio; team site measurements.

---

## 2026-10-16 — Zaki (+Claude) — master plan, TURN Studio, CAD inputs, S2 training data
**Goal:** a GUI to convert/correct/export maps on the laptop; CAD/vector inputs; plan and data for fine-tuning.
**Changed:** docs/MASTER_PLAN.md (new), src/turn_mapper/studio/* (new), ingest.py (DxfAdapter, SvgAdapter,
vector-aware PdfRasterPageAdapter), scale.py (cad_units), api.py (seg_override), ir.py (FloorSpec.options),
learned/styles.py, learned/resplan.py, learned/institutional.py, cli.py (studio, ml prepare-resplan,
ml make-institutional), scripts/kaggle_finetune_s2.sh, notebooks/finetune_s2_kaggle.ipynb, tests (+25).
**Verified:**
- `pytest -q` → all pass (73); ruff clean.
- Studio driven in headless Chromium on FAST C-F3: run → valid (13 rooms, 23 doors, 15 POIs, 1 graph part,
  30/30 routes, 4.5 s); node/edge/door/POI edits, void polygon, undo, scale (two points), mask paint + re-run,
  venue.json export (validates).
- DXF (synthetic plan written in mm and m): scale_source cad_units, exactly 0.02 m/px; 7 rooms/6 doors (basic),
  9/8 (L-shape); corridor length 29.7 m vs 30 m drawn. Vector PDF at 1:100 → 7 rooms/6 doors.
- ResPlan pickle opened with a restricted unpickler (only shapely from_wkb + numpy found); 300-plan and
  100-institutional-floor smoke datasets train through `ml train` on CPU.
**Not verified / unknown:** S2 training itself (needs the Kaggle GPU run); Studio on Windows (built with
cross-platform stack, not yet run there); DXF files from real AutoCAD drawings (only synthetic DXFs tested).
**Broken or risky:** vector PDFs without a drawing scale are sensitive to render DPI (at 130 dpi the test plan
merged rooms; default now chosen from the drawing scale) → log as D-11. Re-running from masks drops the
classical partition/stairs detectors (rooms 8 vs 7 on one synthetic case).
**Next step:** Zaki runs notebooks/finetune_s2_kaggle.ipynb on Kaggle (attach the S1 notebook output);
correct 8–10 B/C floors in Studio and export training annotations (S3); try Studio on the laptop.

---

## 2026-10-12 (evening) — Zaki (+Claude) — CubiCasa pre-training on Kaggle
**Goal:** train the learned segmenter.
**Changed:** scripts/kaggle_train.sh, Kaggle notebook (attached dataset qmarva/cubicasa5k), fix learned/cubicasa.py label alignment (+ regression test), docs/RESULTS_ML_2026-10-12.md, evidence files.
**Verified (Kaggle console output):** run 1 test mIoU 0.323 (labels misaligned); run 2 test mIoU 0.650 (wall 0.745, door 0.635); learned in-pipeline synthetic: room R 0.833, door R 0.819, 1.42 wall-crossing edges/case (classical: 1.0/1.0/0). Outputs saved in the Kaggle notebook version.
**Not verified / unknown:** learned model on FAST floors (no ground truth); weights not in git.
**Next step:** annotate B/C floors, fine-tune, add thin/double-line restyling.

---

## 2026-10-12 — Zaki (+Claude in claude.ai) — mid-evaluation package
**Goal:** verifiable evidence for every mid-eval rubric item (mapping module).
**Changed:** docs/mideval/* (index, action register, milestone log, requirements FR/NFR with acceptance tests, design + 7 diagrams from code, testing with failure cases, demo script, report sections, Q&A prep, task log), eval/evaluate_synthetic.py (Level B/C metrics vs exact truth), tests/test_edge_cases.py + tests/test_requirements.py, CLI clean errors, scripts/demo_prepare.py, notebooks/train_segmenter_kaggle.ipynb, contract 0.1.1 (embedded-floor JSON) + tool 0.3.0, CODEOWNERS, tags v0.1.0/v0.2.0/v0.3.0; removed unused style_hints from the venue config.
**Verified:** pytest 47 passed, 87 % coverage (docs/mideval/evidence/); synthetic eval: room/door recall 1.0, free-space IoU 0.983, 0 wall crossings, label acc 0.70, mean |scale err| 8.7 %; FAST 14/14 valid.
**Not verified / unknown:** FAST geometric accuracy (no ground truth), learned model accuracy (no GPU training yet), panel feedback rows PA-03+ (need the official sheet).
**Next step:** Kaggle pre-training; fill the action register; request site measurements; rehearse the demo.

---

## 2026-10-11 — Zaki (+Claude in claude.ai) — generality, JSON output, learned segmenter scaffold
**Goal:** verify the pipeline is generic, JSON output, start the CubiCasa-trained DL model.
**Changed:** api/export/cli/schema (venue.json default output, `--format`, embedded floors), segment.py/vectorize.py/preprocess.py (style-generic segmentation, ADR-017), synthetic.render_style + scripts/style_stress.py + tests/test_generality.py, src/turn_mapper/learned/* + `turn-mapper ml ...` + tests/test_learned.py + notebooks/train_segmenter_colab.ipynb, docs/ML_GUIDE.md, docs/RESULTS_GENERALITY_2026-10-11.md, ADR-017/018.
**Verified:**
- style stress: 11/12 synthetic style cases fully correct (was 2/12), runs/stress_v12.
- FAST 14/14 valid (runs/fast_regress_7); C-F1/F3/F4/B1, B-GF/F2 equal to reference.
- ML path offline: fake CubiCasa SVGs -> masks (transforms handled) -> CPU training -> `--segmenter learned` runs.
- pytest + ruff green.
**Not verified / unknown:** any accuracy of the learned model (no GPU training done; CubiCasa download blocked from this sandbox, must run on Colab).
**Broken or risky:** C-F2 now 4 graph pieces (was 1), B-F1 slightly fewer rooms/doors; one extra door on the "scanned" style; A block (test) has been run repeatedly as regression check.
**Next step:** Colab: prepare CubiCasa + pre-train; annotate 5–10 B/C floors with `ml bootstrap-masks`; fine-tune; compare classical vs learned on A.

---

## 2026-10-04 — Zaki (+Claude in claude.ai) — C-block pass
**Goal:** make all 7 C floors (main testing building) produce good graphs before site measurements.
**Changed:** segment (stairs, partitions), transitions.py (new), preprocess (3-orientation OCR, colour mask), vectorize (door-slab carving, partition/door-band logic, circulation by distinct neighbours), graph (validator-consistent region, greedy simplification, split lines, routed bridging), api (scale_like footprint transfer), schema (+transition, +footprint_transfer), config (door_max_width 1.2, splits dev=B+C/test=A), tests (+5).
**Verified:** `pytest -q` → 28 passed; ruff clean. `turn-mapper run … --split all --out runs/cblock_v1_all` (commit 801d5e4): 14/14 valid (A held-out 4/4). Visual check of all 7 C overlays (contact sheet) + A-F1.
**Not verified / unknown:** metric accuracy (no site measurements); geometry vs ground truth; app import; C-F2/C-F5 true scale (aspect differs ~7 % from C-F3).
**Broken or risky:** rooms without drawn doors unreachable (by design, reported); C-F1 C109/C104 classified walkable; voids walkable (A-F1); A-block OCR weak.
**Decisions / ADRs:** ADR-009 accepted (dev=B+C, test=A); ADR-014 stairs/lifts as transitions; ADR-015 scale_like; ADR-016 circulation rule.
**Next step:** site measurements on C-F3 (+C-F2/C-F5 if possible) → `scale_evidence`; then Android importer (A1/A2).

---

## 2026-10-04 — Zaki (+Claude in claude.ai) — M1 + first M2 built
**Goal:** working module end to end on the FAST PDF.
**Changed:** src/turn_mapper/* (all stages), contract/turnmap.schema.json + fixtures, tests/, scripts/make_fixtures.py, .github/workflows/ci.yml, configs/venues/fast_isb.yaml (splits), docs/RESULTS_2026-10-04.md.
**Verified:**
- `pytest -q` → 23 passed; `ruff check .` + `ruff format --check .` → clean.
- `turn-mapper run … --split all --out runs/all_v2_bugfix` (commit 2b99f5f): dev 3/3 valid, test 4/11 valid; `turn-mapper validate runs/all_v2_bugfix/venue.turnmap` → PASSED (7 floors packaged).
- Synthetic plans: exact room/door/POI counts; door-prior scale within 2% of truth.
**Not verified / unknown:** metric accuracy (no site measurements; all scales are door-width estimates); geometry accuracy vs ground truth (none exists yet); app import (no importer yet); coordinate frame vs app (ADR-007 open).
**Broken or risky:** stairwells/voids walkable; edited images C-F2/C-F5 fail; small-font OCR on A block; A/C now partly seen (see ADR-009 note).
**Decisions / ADRs proposed:** ADR-012 (door-width prior), ADR-013 (validators on metric JSON); dev=B/test=A+C written into config (still Proposed).
**Next step:** site measurements → `scale_evidence`; then stairs/void detection on B.

---

## 2026-10-04 — Zaki (+Claude in claude.ai) — FAST PDF first look
**Goal:** inspect Floor_Plans_2.pdf before planning.
**Changed:** docs/PLAN_INVENTORY.md, docs/img/proto_*.png, configs/venues/fast_isb.yaml (draft), ADR-009 proposal, ADR-011.
**Verified:** PyMuPDF inventory: 8 pages, 0 vector drawings, 16 embedded images (14 floors + site plan + logo). Grey levels floor≈238 / wall≈191,153 / bg 255 on all floors. Throwaway classical test on A-GF and B-F1: walls/floor separate trivially; many rooms merge with the corridor through open door gaps; text holes and wide areas break the skeleton.
**Not verified / unknown:** whether the drawings are to scale; image_index order on multi-image pages; permission to use the PDF.
**Next step:** team picks the ADR-009 split; measure distances on site; Prompt 1 (verify inventory) in Claude Code.

---

## 2026-10-04 — Zaki — Repo setup
**Goal:** create TURN-Mapper module repo with docs, contract plan, project skills/agents.
**Changed:** CLAUDE.md, docs/*, .claude/skills/*, .claude/agents/*, samples/README.md.
**Verified:** nothing run yet; docs only.
**Not verified / unknown:** whether the FAST A/B/C PDF is vector or raster; app coordinate frame; how the app stores walkable/graph/POIs.
**Next step:** Prompt 1 (inspect FAST PDF) in TURN-Mapper; Prompt A1 (app audit) in TURN-Field-Test.
