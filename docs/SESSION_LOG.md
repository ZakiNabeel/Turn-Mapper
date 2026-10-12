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
