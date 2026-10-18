# Learned segmenter: stage S2 fine-tuning (2026-10-17)

Where it ran:

- Kaggle notebook `turn-segmenter-s2-finetune`, Version 1 (private, owner Zaki). Saved run ("Save & Run All") on 2× Tesla T4, of which one is used.
- Code: commit `70a0a7e`; script `scripts/kaggle_finetune_s2.sh 20 1 3000`.
- Timing: queued for about 2 h 50 min (09:13 to ~12:05 UTC). Total run time 38,364 s (10.7 h), including data preparation, training and evaluation.
- Initial weights: S1 `out/turn_seg_cubicasa.pt`, run 2 of `turn-segmenter-cubicasa-pretrain`, test mIoU 0.650. The misaligned run-1 checkpoint was excluded.
- Data (`resplan_dataset.json`, `institutional_dataset.json`):
  - **ResPlan**: 17,000 plans, one drawing each, in 8 styles at about 2,100 drawings per style, 2.0–4.5 cm/px. Split: train 13,736, val 1,632, test 1,632, using ResPlan's own `split.json`.
  - **Procedural institutional floors**: 3,000 floors in 8 styles. Split: train 2,700, val 300.
  - **CubiCasa replay**: 1,500 plans.
- Training settings: U-Net ResNet-34, crop 512, batch 8, lr 2e-4 one-cycle, 20 epochs (44,840 iterations), full fp32 precision.
- Best checkpoint: epoch 16 (validation mIoU 0.809). File `turn_seg_s2.pt`, sha256 `146f1fcc…2407`. The weights stay on Kaggle and are not in git.

## Pixel IoU: S1 vs S2 on each dataset's held-out split

| test set | S1 mIoU | **S2 mIoU** | wall S1 → S2 | door S1 → S2 | room S1 → S2 | stairs S1 → S2 |
|---|---|---|---|---|---|---|
| ResPlan **test** (1,632 drawings, 8 styles) | 0.431 | **0.781** | 0.814 → 0.973 | 0.539 → 0.899 | 0.770 → 0.982 | 0.000 → 0.892 |
| Institutional **val** (300 floors, 8 styles) † | 0.343 | **0.770** | 0.795 → 0.956 | 0.614 → 0.837 | 0.564 → 0.785 | 0.000 → 0.893 |
| CubiCasa5K **test** | 0.650 | **0.634** | 0.745 → 0.731 | 0.635 → 0.616 | 0.732 → 0.728 | — |

† The institutional val split was also part of the validation set used to pick the best epoch, so it is not a clean held-out number. ResPlan test and CubiCasa test are clean.

Reading:

- The new drawing styles were learned.
  - On ResPlan's unseen test plans, wall IoU goes from 0.81 to 0.97 and door IoU from 0.54 to 0.90.
  - Stairs go from never detected to 0.89.
  - The S1 model had never seen thin-line, double-line, hatched or CAD drawings.
- CubiCasa drops slightly, by 0.016 mIoU, even with the 1,500-plan replay. This is the expected cost of moving towards the new drawing styles.
- **Walkable is weak on ResPlan (0.12) but strong on the institutional floors (0.93).** ResPlan labels the circulation left over between named rooms as "walkable", and that region is small and ambiguous. The model mostly calls it room. For the pipeline, room and walkable both become free space, and the corridor is decided by the doors and the graph. So this matters less than the number suggests.
- Lift remains near zero (0.09). Lifts are rare and small in the training data.

## In the pipeline: 12 synthetic layout × style cases

Two runs:

- Version 1 crashed after 5 cases with `networkx.NodeNotFound`: a destination node had no edges. This is fixed in `9fba62b`.
- The full comparison ran in a separate Kaggle notebook, **`turn-segmenter-s2-eval`** (Version 1). It used CPU only, took 482 s, and loaded both checkpoints from the notebook inputs.

Per case: room recall / precision, door recall / precision, and the share of routes found between destinations. "Classical (recorded)" is the classical segmenter run here (`python eval/evaluate_synthetic.py`). It matches `RESULTS_GENERALITY_2026-10-11.md`.

| case | classical (recorded) | S1 (CubiCasa) | **S2 (fine-tuned)** |
|---|---|---|---|
| basic greyfill | 1/1, 1/1, 1.0 | 1/1, 1/1, 1.0 | 1/1, 1/1, 1.0 |
| basic blackwalls | 1/1, 1/1, 1.0 | 1/1, 1/1, 1.0 | 1/1, 1/1, 1.0 |
| basic thinlines | 1/1, 1/1, 1.0 | 0.14/0.25, 0/0, 0.0 (10 wall crossings) | 1/0.58, 1/1, 1.0 |
| basic doubleline | 1/1, 1/1, 1.0 | 0.86/0.55, 0.83/0.56, 0.0 | 0.86/0.75, 0.83/0.50, 0.4 |
| basic colored | 1/1, 1/1, 1.0 | 1/1, 1/1, 1.0 | 1/1, 1/1, 1.0 |
| basic scanned | 1/1, 1/0.86, 1.0 | 1/1, 1/1, 1.0 | 1/1, 1/1, 0.67 |
| lshape greyfill | 1/1, 1/1, 1.0 | 1/0.69, 1/1, 1.0 | 1/0.82, 1/0.89, 1.0 |
| lshape blackwalls | 1/1, 1/1, 1.0 | 1/0.75, 1/0.89, 1.0 | 1/0.64, 1/0.89, 1.0 |
| lshape thinlines | 1/1, 1/1, 1.0 | 0.11/0.33, 0/0, 0.0 (7 wall crossings) | 1/0.64, 1/1, 1.0 |
| lshape doubleline | 1/1, 1/1, 1.0 | 0.89/0.50, 1/0.62, 0.0 | 0.89/0.53, 1/0.67, 0.0 |
| lshape colored | 1/1, 1/1, 1.0 | 1/0.75, 1/1, 1.0 | 1/0.82, 1/0.89, 1.0 |
| lshape scanned | 1/1, 1/1, 1.0 | 1/0.75, 1/0.8, 1.0 | 1/0.82, 1/0.89, 0.75 |
| **mean** | rooms R 1.000, doors R 1.000, routes 1.000, 0 crossings | 0.833 / 0.819 / 0.667, **1.42 crossings** | **0.979 / 0.986 / 0.818, 0 crossings** |

Reading:

- **S2 fixes S1's thin-line failure.**
  - On thin lines S1 found no doors and drew 7–10 graph edges through walls.
  - S2 finds every room and door on both thin-line cases, with zero wall crossings.
  - Across all 12 cases S2 never puts a route through a wall.
- **Double-line is still the weak style.** On the L-shape, S2 finds 0 of the 28 routes. On the basic layout it finds 40% (6 of 15).
- **S2 adds extra rooms.** Room precision is 0.53–0.82 on 7 of 12 cases, against 1.0 for classical. It splits large spaces.
- **Promotion rule, with "at least as good" meaning room recall, door recall and routes found ≥ classical, and wall crossings ≤ classical.** Against the recorded classical baseline, S2 qualifies on **8/12** cases. It falls short on basic/lshape double-line and on basic/lshape scanned, where routes are 0.67 and 0.75. The rule needs 10/12 plus the A block. **Not met: classical stays the default.**

### Environment note (reproducibility)

The notebook also ran the classical segmenter on Kaggle, with the same commit and Kaggle's own Tesseract and library versions. There it scored noticeably lower: mean room recall 0.897, door recall 0.892, routes found 0.728.

- The worst cases were double-line (rooms 0.57, routes 0.0) and basic scanned (room precision 0.39).
- Against that Kaggle-run classical, the notebook's own count says S2 qualifies on 11/12 and S1 on 10/12. **Those counts are not used**, because the baseline is weaker than the recorded one.
- The likely cause is OCR or text erasure: a different Tesseract build changes which text boxes are erased before segmentation.
- To do: pin the OCR engine and version in the evaluation and in `run_manifest.json`, and log it in DECISIONS as a risk.

## Next

1. Pin the OCR engine and version for evaluations (environment note above).
2. S3: corrected FAST B/C floors from Studio (*Export → Training annotations*), lr 5e-5, with S2 replay.
3. The double-line style is the weak case. More double-line wall widths and gaps in the renderer (`learned/styles.py`) would help there.
