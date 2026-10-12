# Learned segmenter: CubiCasa5K pre-training runs (2026-10-12)

Where it ran:

- Kaggle notebook `turn-segmenter-cubicasa-pretrain` (private, owner Zaki), interactive session on 2× Tesla T4 (one used).
- Data: Kaggle dataset `qmarva/cubicasa5k` (a copy of CubiCasa5K, CC BY-NC).
- Script: `scripts/kaggle_train.sh 25`.
- Model: U-Net ResNet-34 (ImageNet init), crop 512, batch 8, AdamW, lr 3e-4 one-cycle, CE + Dice, restyle p = 0.3, 25 epochs (13,125 iterations, about 0.56 s/iteration).

## Run 1: labels misaligned (failure, kept as evidence)

| split | mIoU | background | wall | room | walkable | door | other |
|---|---|---|---|---|---|---|---|
| val (50 plans, best = last epoch) | 0.316 | 0.561 | 0.119 | 0.582 | 0.253 | 0.045 | 0.334 |
| test (CubiCasa test split) | 0.323 | 0.525 | 0.134 | 0.594 | 0.297 | 0.041 | 0.346 |

In our pipeline, on the 12 synthetic layout × style cases (`eval/evaluate_synthetic.py --segmenter learned`), mean values:

| metric | value |
|---|---|
| free-space IoU | 0.877 |
| corridor IoU | 0.402 |
| room precision / recall | 0.274 / 0.251 |
| door recall | 0.264 |
| route edges through walls | 10.75 per case |

This is far worse than the classical segmenter (room/door recall 1.0, 0 wall crossings).

**Diagnosis.** Walls should be the easiest class, yet wall IoU was 0.12. A check run in the Kaggle console:

- With the run-1 labels, image pixels labelled *wall* averaged **grey 220**, almost white, against 248 for background. The labels were not on the walls.
- `model.svg` width/height is the drawing's bounding box. For example, sample 10004 has an SVG size of 1216×876 while `F1_scaled.png` is 1432×1050. Our loader rescaled the polygons to the image size, which stretched them off the walls.
- The official CubiCasa loader paints the raw polygon coordinates on `F1_scaled.png`. Doing the same gives wall pixels averaging **grey 146** on 25 samples, so the labels now sit on dark strokes.

**Fix.** Commit `4a084d8`:

- `learned/cubicasa.py` now uses the raw coordinates on `F1_scaled.png`.
- New regression test: `test_svg_size_attribute_does_not_rescale_labels`.

Run-1 outputs are kept in the Kaggle session as `out_run1_misaligned/`.

## Run 2: corrected labels (current model)

Started 17:28 UTC, same settings. Training ended about 19:40 UTC and everything finished at 20:24 UTC.

- Checkpoint `turn_seg_cubicasa.pt` (98 MB), sha256 `2a1c4277d65aba1b…`.
- Kept in the saved Kaggle notebook version's output, under `out/`. Run 1 is under `out_run1_misaligned/`.
- Weights stay out of git (ADR-018).

| split | mIoU | background | wall | room | walkable | door | other |
|---|---|---|---|---|---|---|---|
| val (best, epoch 24 of 25) | 0.627 | 0.742 | 0.701 | 0.733 | 0.475 | 0.613 | 0.495 |
| **test (CubiCasa test split)** | **0.650** | 0.717 | 0.745 | 0.732 | 0.520 | 0.635 | 0.554 |
| *run 1 test, for comparison* | *0.323* | *0.525* | *0.134* | *0.594* | *0.297* | *0.041* | *0.346* |

Stairs, lift and escalator are `null` because CubiCasa has almost no such labels. Those classes need our own annotated floors.

### In our pipeline (synthetic ground truth, 12 layout × style cases)

Per-case table: [`mideval/evidence/ml_run2_learned_synthetic_METRICS.md`](mideval/evidence/ml_run2_learned_synthetic_METRICS.md).

| metric (mean of 12) | classical | learned run 1 | **learned run 2** |
|---|---|---|---|
| free-space IoU | 0.983 | 0.877 | 0.922 |
| corridor IoU | 0.976 | 0.402 | 0.726 |
| room precision / recall | 1.000 / 1.000 | 0.274 / 0.251 | 0.714 / 0.833 |
| door precision / recall | 0.988 / 1.000 | n/a / 0.264 | 0.738 / 0.819 |
| destination pairs routable | 1.000 | n/a | 0.667 |
| route edges through a true wall | 0 | 10.75 | 1.42 |

### What this means

- Pre-training now works. CubiCasa test **mIoU 0.65**, with walls at 0.75 and doors at 0.64, is a usable starting point for fine-tuning.
- On the synthetic styles, the learned model alone **matches classical on 6 cases**: basic greyfill, blackwalls, colored and scanned all come out with every room and door correct, all routes found and 0 wall crossings.
- It **fails on thin-line and double-line drawings**: rooms are merged, doors are missed, and the thin-line plans get wall-crossing edges. CubiCasa has no plans drawn that way. This is the domain gap that fine-tuning on our own annotated floors and adding thin-line restyling are meant to close (next steps).
- **The classical segmenter remains the default.** The learned one is selectable with `--segmenter learned`. The comparison above becomes the M5/M8 evaluation once FAST floors are annotated.

### Next

1. Annotate 5–8 B/C floors (`turn-mapper ml bootstrap-masks`, then correct them).
2. Fine-tune from this checkpoint (`--init`).
3. Add thin-line and double-line drawing styles to `data.restyle`.
4. Compare classical vs CubiCasa-only vs fine-tuned on the A block (held out) and on the synthetic styles.
