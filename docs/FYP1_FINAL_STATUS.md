# FYP-1 final evaluation: status against the checklist (2026-11-27)

Checklist: `TURN_FYP1_Final_Eval_Checklist.pdf` (26 Nov 2026, compiled from the mid report). This file records,
for every item, what is done, the evidence, and what is left and who has to do it. Status words:
**Done**, **Partial**, **Team action** (needs a person, a site visit or the phone), **Not triggered**.
TURN-Mapper items were checked in this repo. App and positioning items were read from the owners' repos and
docs and are marked as such; the owners should confirm them.

## 1. Map intelligence — TURN-Mapper (Zaki Nabeel)

| Deliverable | Status | Evidence | What is left |
|---|---|---|---|
| Measured metric scale (FR-07a) | **Partial** | 4 floors have a measured scale from site room sizes (B-GF, B-F1, C-F3, C-F4); the rest are scaled from them (RESULTS_SCALE_2026-10-24; run `runs/mf6`). Check-only evidence is already supported (`check_only: true`) | The check: **2 distances per C floor not used for calibration, error ≤ 5 %**. One site visit, sheet in §A below |
| Annotated institutional floors (M4) | **Team action** | Tools ready: `scripts/make_annotation_drafts.py`, Studio (DATA_AND_ANNOTATION §5) | **Correct the first 8 drafts in Studio** (B/C floors + public institutional plans, never A), about 30 min each, split among 3. Steps in §B |
| Institutional synthetic data + thin/double-line restyling | **Done** | `learned/institutional.py` (corridors, lecture halls, stair cores, lifts, washroom blocks, voids); 8 drawing styles in `learned/styles.py`; used in S2–S4 training | — |
| Fine-tuned segmenter + three-way comparison (M5/M8) | **Partial** | S4 trained on real CAD drawings: stairs 0.001 → 0.852, lifts 0 → 0.929, walls 0.626 → 0.862 on 4,891 unseen real tiles. Three-way table (classical / CubiCasa-only / fine-tuned) on synthetic + pixel test sets: RESULTS_ML_S4_2026-11-27 | **A-block comparison (O4)** needs the A floors corrected in Studio first, then `scripts/eval_real_block.py`. FAST 14-floor comparison without an answer key: `scripts/compare_fast_segmenters.py` on the laptop with the S4 weights (§C) |
| Multi-floor linking (FR-18 / M9) | **Done**, extended | Routes between C floors via matched stairs/lifts, plus walkways between A, B and C: 182/182 floor pairs, 200/200 sampled routes (RESULTS_MULTIFLOOR_2026-11-10, RESULTS_CONNECTIVITY_2026-11-15); contract 0.1.3 | Check the 5 walkway ends and the C-GF lift on site / in Studio |
| Correction step (FR-19) | **Done** | TURN Studio: edit rooms, doors, labels, walls, scale, links → re-validate → export with `provenance: corrected` (`tests/test_studio.py`, STUDIO_GUIDE) | — |
| Release v0.4.0 | **Prepared** | `docs/RELEASE_NOTES_v0.4.0.md`; version 0.4.0; results docs; `turn-mapper ml eval` numbers in RESULTS_ML_S4 | Run `bash scripts/create_release_tags.sh` on the laptop (pushes v0.1.0–v0.4.0), then draft the GitHub release from the notes. Weights stay on Kaggle (sha256 in the notes); the "private annotated mask set" exists only after §B |
| Default switch (if model wins) | **Not triggered** | Promotion rule not met (synthetic thin-line cases fail; A block not measurable) → classical stays default (RESULTS_ML_S4 §3) | Re-check after S5 and the A-block answer key |

## 2. Platform / Android app — TURN-Field-Test (Shehryar Faisal)

Read from `shehryarf67/TURN-Field-Test` at `8c257c8` (25 Nov). These are not verified here, because Android
builds can't run in this workspace.

| Deliverable | Status (per the app repo) | What is left |
|---|---|---|
| M3 importer | **Done for single-floor VenuePackage v1** (`docs/MAPPER_IMPORT.md`): version/error checks, metric adapter, one Room transaction with rollback, 155 JVM + 35 emulator tests reported there. It imports the TURN-Mapper positioning export, not `venue.json` 0.1.x directly | Owner to confirm this meets "0.1.1 fixtures pass/fail with named error"; multi-floor package import |
| End-to-end C-block setup | Partial: C-F4 imported and reopened in the app | Calibrated import of the C floors; fresh radio survey that persists after restart (phone, on site) |
| Navigation integration | Multi-floor phases 3–4 landed 22 Nov (directions between floors, floor-change log) | Field test on site |
| Repeatable one-floor APK acceptance script | Field protocol docs exist (`FIELD_TEST_PROTOCOL.md`) | Owner |
| Submission evidence | — | APK screenshots, run video, Gradle test output, author-filtered git history (owner) |

## 3. Live positioning (Muhammad Sameer)

Not checked from here: the positioning repo is not in this workspace. All five items (freeze PDR + labelled
trials, first walks on C-F3, survey repeatability, PF baseline, ablations) need phone recordings on site.
The owner fills this table. Note: the checklist flags that the PF baseline and ablations are under Iteration 2
in §9.3 but FYP-2 in Table 9.1. Agree which applies with the supervisor.

## 4. Team-wide commitments

| Commitment | Status | Notes |
|---|---|---|
| Outside person follows a route on C-F3; every problem logged | **Prepared** | Printed directions in §D; defect log template there |
| Recovery dates confirmed with supervisor | Team action | Bring this file to the meeting |
| One-week buffer before FYP-1 final | Team action | — |
| Contract fixtures in CI on both repos; FAST maps import into the app | **Mapper side done** (CI runs every contract test incl. the new multi-floor fixture) | App side: owner |
| Supervisor meeting log (Appendix F.1) | Team action | — |
| Form 10 feedback copied verbatim into the action register | Team action | — |
| Release tags v0.1.0–v0.3.0 pushed | **Prepared** | Same script as v0.4.0 (pushes from this workspace are refused) |
| Every member can explain Chapter 2 | Team action | — |
| FAST floor-plan permission confirmed | Team action | Until confirmed, keep the FAST figures private (they are gitignored) |

## 5. Measurable objectives (O1–O7)

| ID | Target | Now | Evidence |
|---|---|---|---|
| O1 | Valid map for ≥ 90 % of pilot floors | **14/14** valid | `runs/mf6` (2026-11-15) |
| O2 | ≥ 10/12 synthetic style cases fully correct | **11/12** | `runs/style_mf6` |
| O3 | 0 wall-crossing edges; room/door recall ≥ 0.95 | Synthetic: 0 crossings, room R 1.0, door R 1.0 | `runs/eval_mf6`; real floors after §B corrections |
| O4 | Fine-tuned IoU > classical IoU on held-out floors | **Not measurable yet** (A block not annotated); S4 beats S3a on real CAD tiles, not classical in the pipeline | RESULTS_ML_S4 |
| O5 | Median checkpoint error ≤ 3 m | FYP-2 (Sameer) | — |
| O6 | App: import fixtures, persist after restart, C-block route | Importer + persistence per app repo; C-block route on site pending | app repo |
| O7 | ≥ 60 % set-up effort reduction | FYP-2 | — |

---

## A. Site sheet: scale check distances (FR-07a)

Measure with a tape, wall to wall, inside dimensions (feet or metres). These are **checks**, never fits: the
pipeline reports how far the map is from each one (`residual_pct`, acceptance ≤ 5 %).

| Floor | Check 1 | Check 2 |
|---|---|---|
| C-B1 | corridor width (median stretch) | one named room, both sides |
| C-GF | corridor width | one named room |
| C-F1 | corridor width | one named room |
| C-F2 | corridor width | one named room |
| C-F3 | corridor width | C-311, both sides (C-F3's fit used the *typical* room size, not C-311) |
| C-F4 | corridor width | C-406, both sides |
| C-F5 | corridor width | one named room |

Photograph the door sign of every room you measure. Enter each floor's checks in `configs/venues/fast_isb.yaml`
under `scale_evidence`. Example for C-F4 (the numbers are placeholders, not measurements):

```yaml
  C-F4:
    - {method: corridor_width, width_ft: 8.5, check_only: true}
    - {method: room_size, label: C-406, size_ft: [30.1, 24.9], check_only: true}
```

Then run `turn-mapper run samples/private/fast_blocks.pdf --venue configs/venues/fast_isb.yaml --out runs/scale_check`.
Each floor's `transform.scale_evidence` and the run report list the checks with `residual_pct`. Copy them into
`docs/RESULTS_SCALE_<date>.md`. (Studio's Scale tab also takes check pairs: every pair after the first. But the
first pair replaces the floor's scale, so use the config for floors already measured.)

## B. Annotation: first 8 corrected floors

1. `python scripts/make_annotation_drafts.py <plans dir> <sources.tsv> --studio studio_projects --set dev`
   For FAST B/C use `--files fast_blocks.pdf:<page>,...`. **Never A** for training: A is the test set.
2. Open `turn-mapper studio`. In each `annotate-<id>` project fix, in order: walls, doors (dashed ones first),
   walkable / not walkable, room names. Then save.
3. Note who corrected it and the minutes taken (effort study, O7).
4. For the O4 test, correct 3–4 **A** floors the same way. Then run
   `python scripts/eval_real_block.py --studio studio_projects/<A project> --methods classical learned hybrid`
   once per model.

## C. FAST comparison with the S4 weights (laptop)

1. On Kaggle open `turn-segmenter-s4-finetune` → Output → `out_s4/turn_seg_s4.pt` → Download.
2. Check its sha256, which must be `3f38249e…a2bad8`. In PowerShell:
   `Get-FileHash turn_seg_s4.pt -Algorithm SHA256`.
3. `$env:TURN_SEG_WEIGHTS="C:\...\turn_seg_s4.pt"`
4. `python scripts/compare_fast_segmenters.py samples/private/fast_blocks.pdf --venue configs/venues/fast_isb.yaml --out runs/compare_s4`
5. Paste `runs/compare_s4/COMPARISON.md` into RESULTS_ML_S4 §2c.

## D. External route test on C-F3 (Section 7.5)

Give the tester the plan and one route at a time; do not help. Log every problem as a defect: where, what the
map said, what was there, minutes lost. The routes below are from `runs/mf6/venue.json`. Distances use the
measured C-F3 scale.

**Route 1: Stairs 1 → C-311 ClassRoom (51 m)**
1. Start at Stairs 1. 2. Walk 3 m. 3. Turn right and walk 6 m. 4. Turn right and walk 39 m.
5. Turn left and walk 3 m. 6. Arrive at C-311.

**Route 2: Lift 1 → C-301 ClassRoom (57 m)**
1. Start at Lift 1. 2. Walk 5 m. 3. Turn right and walk 10 m. 4. Turn right and walk 39 m.
5. Turn right and walk 3 m. 6. Arrive at C-301.

**Route 3: C-305 ClassRoom → Men's Washroom (49 m)**
1. Start at C-305. 2. Walk 3 m. 3. Turn right and walk 42 m. 4. Turn left and walk 3 m.
5. Arrive at the Men's Washroom.

Defect log columns: `#, route, step, location, map says, reality, severity (blocks / slows / cosmetic), fixed in`.
