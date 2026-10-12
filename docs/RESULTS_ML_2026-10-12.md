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

## Run 2: corrected labels

Started 17:28 UTC with the same settings. Results are added here when the run finishes. Only numbers printed by the script are reported.
