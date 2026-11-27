# Results: stage S4, fine-tuning on real CAD drawings (FloorPlanCAD), and the three-way comparison (2026-11-27)

Every number below was produced by a recorded run. The S4 run is Kaggle notebook `turn-segmenter-s4-finetune`,
**Version 3** (session 371939722, commit `8da3bc8`, GPU T4, started 2026-11-20 20:16 UTC, "Successfully ran
in 34807.2 s"). Earlier rows are copied from the reports named in each table. Weights stay on Kaggle and are
not in git (ADR-009 / licences).

| | |
|---|---|
| Initial weights | S3a `turn_seg_s3a.pt`, sha256 `d7db04ad…afd23b` |
| **S4 weights** | `out_s4/turn_seg_s4.pt`, 97,926,275 bytes, sha256 `3f38249efe0da58f48ae6591a9063c33899624879dd3aa48fae15a95c3a2bad8` |
| Training data | FloorPlanCAD (10,530 train tiles, **partial masks**: wall / stairs / lift / escalator / "open space of unknown use"), ResPlan 4,847, generated institutional floors 2,700, CubiCasa5K replay |
| Labels | FloorPlanCAD ids as found in the files (wall 1, stairs 30, lift 31, escalator 32), not the published list; see ML_GUIDE §3c |
| Best validation mIoU | 0.6603 (checkpoint saved at that epoch) |

## 1. Pixel IoU on held-out splits (same run: S3a = before, S4 = after)

| test set | S3a mIoU | **S4 mIoU** | wall | stairs | lift | escalator | door | room |
|---|---|---|---|---|---|---|---|---|
| **FloorPlanCAD test** (4,891 real CAD tiles) | 0.157 | **0.661** | 0.626 → **0.862** | 0.001 → **0.852** | 0.000 → **0.929** | 0.000 → 0.000 | — | — |
| ResPlan test | 0.907 | 0.897 | 0.979 → 0.972 | 0.925 → 0.892 | — | — | 0.911 → 0.900 | 0.990 → 0.989 |
| Institutional val † | 0.782 | 0.782 | 0.960 → 0.955 | 0.842 → 0.839 | 0.091 → 0.090 | — | 0.824 → 0.827 | 0.901 → 0.882 |
| CubiCasa5K test | 0.647 | **0.653** | 0.740 → 0.729 | — | — | — | 0.618 → 0.617 | 0.755 → 0.766 |

† Also used to pick the best epoch: not a clean held-out number. "—" = class absent from that split's labels.

- **The real-drawing gain is large and real.** On 4,891 unseen real CAD tiles, stairs go from never detected
  (0.001) to 0.852 and lifts from 0 to 0.929; walls from 0.626 to 0.862. These are the symbols FAST plans use.
- **Nothing that was already learned was lost.** ResPlan drops by 0.010, institutional is flat, CubiCasa rises
  by 0.007.
- **Escalators stay at 0.** Only 143 tiles have one; S4 did not learn them.
- **The generated institutional floors' lift class stays near 0.09.** Their lift drawing differs from
  real CAD lifts; FAST uses real drawings, so the real-CAD score is the one that matters.

## 2. Three-way comparison: classical vs CubiCasa-only vs fine-tuned

### 2a. Pixel IoU on CubiCasa5K test (the only split all models were scored on)

| | CubiCasa-only (S1) | S2 | S3a | **S4** |
|---|---|---|---|---|
| mIoU | 0.650 | 0.634 | 0.647 | **0.653** |
| source | RESULTS_ML_2026-10-12 | RESULTS_ML_S2 | this run (init) | this run |

The classical segmenter does not produce these classes, so it has no pixel IoU here.

### 2b. In the pipeline: 12 synthetic layout × style cases (mean of 12)

Columns: room recall / door recall / routes found / wall-crossing edges (lower is better).

| | classical | CubiCasa-only (S1) | S2 | S3a | **S4** |
|---|---|---|---|---|---|
| mean | **1.000 / 1.000 / 1.000 / 0** | 0.833 / 0.819 / 0.667 / 1.42 | 0.979 / 0.986 / 0.818 / 0 | 0.854 / 0.819 / 0.697 / 1.92 | 0.854 / 0.819 / 0.697 / 1.33 |
| source | `runs/eval_mf6` (local, 2026-11-15) | RESULTS_ML_S2 | RESULTS_ML_S2 | this run | this run |

- **Classical is still best inside the pipeline on the synthetic cases.**
- **S4 equals S3a and keeps S3a's thin-line failure.** On both thin-line cases rooms drop to 0.14 / 0.11 and
  doors to 0, with 6 and 10 wall crossings (S3a: 16 and 7). This is the scale feedback loop described in
  RESULTS_ML_V2 §S3a: no scale given → door-width prior → missed thin-line doors → wrong scale.
- **S2 was better inside the pipeline than S3a/S4** (0 crossings), though worse on pixels. Its numbers come from
  an earlier run and session, so the comparison is indicative only.
- **The learned runs here used Kaggle's environment.** Classical run on Kaggle scored lower than locally
  (RESULTS_ML_S2: room R 0.897, door R 0.892, routes 0.728), so the gap is partly environmental. The classical
  column is the stricter local baseline, as in every earlier report.

### 2c. On real FAST floors

- **A block (held-out, the checklist's O4 test): not measurable yet.** It needs the A-block floors corrected by
  a person in Studio (answer key). `scripts/eval_real_block.py` then scores classical, learned and hybrid
  against the corrections (pixel IoU, rooms, doors), once per model (ADR-009).
- **All 14 floors without an answer key: script ready, not yet run.** The S4 weights could not be brought into
  this session: the in-app browser's download was cut off twice, and the cloud session cannot reach Kaggle.
  Run on the laptop:
  `set TURN_SEG_WEIGHTS=...\turn_seg_s4.pt` then
  `python scripts/compare_fast_segmenters.py samples/private/fast_blocks.pdf --venue configs/venues/fast_isb.yaml --out runs/compare_s4`.
  It writes `runs/compare_s4/COMPARISON.md`, with validity, rooms, doors, destinations, graph pieces, map grade
  and cross-floor routes per method. Check the sha256 above first.

## 3. Promotion rule and the default switch

Rule (ML_IMPROVEMENT_PLAN): learned or hybrid becomes the default only if it is at least as good as classical
on ≥ 10/12 synthetic cases **and** on the held-out A block.

- **Synthetic: not met.** S4 fails both thin-line cases, and every non-trivial case has lower room or door recall
  than classical.
- **A block: not measurable** (no answer key).
- **Decision: classical stays the default.** The checklist item "Default switch (if model wins)" is not
  triggered. The fallback design (learned → classical when validators fail) stays as planned for FYP-2.

## 4. What S4 is good for now

- **Stairs and lifts on real drawings.** Since 2026-11-15 the pipeline uses the learned lift and stairs classes
  (`Segmentation.lifts`), so `--segmenter hybrid` can add lift/stair transitions that the classical texture/OCR
  rules miss (FAST: lifts were found on only 6 of 7 C floors and on no A/B floor). Measure this with the
  laptop comparison above before relying on it.
- **Next model (S5):** fix the thin-line scale loop, either by giving the network the classical scale estimate
  or by training thin-line drawings at the door-width-prior scale. Then fine-tune on the corrected B/C floors.
