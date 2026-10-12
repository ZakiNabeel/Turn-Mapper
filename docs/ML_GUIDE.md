# ML guide: the learned segmenter (CubiCasa5K pre-training → fine-tuning on our plans)

> **Status (2026-10-12):** pre-trained on Kaggle, CubiCasa test mIoU **0.65**. See [RESULTS_ML_2026-10-12.md](RESULTS_ML_2026-10-12.md). Recommended runner: `notebooks/train_segmenter_kaggle.ipynb` with the Kaggle dataset `qmarva/cubicasa5k` attached, or `bash scripts/kaggle_train.sh` from the notebook console.

## 1. What the model does, and what it does not

The pipeline has one step that has to *understand the drawing*: segmentation, i.e. deciding for every pixel whether it is wall, room, corridor, door, stairs, lift or outside. Everything after that is geometry and stays the same: closing wall gaps, doors, rooms, the graph, POIs, validators and the JSON export.

- **Classical segmenter** (today): hand-written rules (ink map, line kernels, colour levels). Fast, needs no data, and covers 11/12 synthetic drawing styles plus the FAST plans. Every new convention can break a rule, though: hatching, furniture, doors without gaps, phone photos.
- **Learned segmenter**: a U-Net (encoder ResNet-34, ~24 M parameters) that learns those decisions from labelled examples. It plugs in behind the same interface:

  ```
  turn-mapper run plan.pdf --segmenter learned
  ```

So the network does not output the graph. It outputs a per-pixel class map, and the existing pipeline turns that into the graph. This keeps the model small, the training data easy to make, and the output still checked by the same validators.

### Classes

They are chosen for navigation, not architecture (`src/turn_mapper/learned/classes.py`):

| id | class | meaning |
|---|---|---|
| 0 | background | outside the building |
| 1 | wall | blocks movement (walls, windows, railings) |
| 2 | room | a destination space |
| 3 | walkable | corridors, halls, lobbies |
| 4 | door | the opening between two spaces |
| 5 | stairs | |
| 6 | lift | |
| 7 | escalator | |
| 8 | other | balconies, voids, open-to-below |

255 in a mask means "not labelled", which is ignored by the loss. Use it for regions you don't want to annotate.

## 2. Why pre-train and then fine-tune

Training a segmentation network from zero needs thousands of labelled plans; we have 14 floors. So we train in two stages:

1. **Pre-training on CubiCasa5K.** This public dataset has 5,000 floor plans with polygon labels for walls, doors, windows and room types (Kalervo et al., 2019; CC BY-NC 4.0, so non-commercial use only, which an FYP is). The network learns what walls, doors and rooms look like in general. CubiCasa plans are Finnish apartments, not universities, so this model alone is not our final model.
2. **Fine-tuning on our own plans.** Start from the pre-trained weights and continue training with a small learning rate on a few annotated floors (FAST B/C, plus any other venue). The network keeps its general knowledge and adapts to our drawing style and building type: long corridors, lecture halls, stairs cores. Typically 5–15 annotated floors move the result a lot. That is the point of fine-tuning.

The encoder starts from ImageNet weights before stage 1 (a third, free stage of transfer learning).

### Tricks that matter

- **Grey input.** Colour conventions differ between sources and carry little information about walls.
- **Restyling** (`data.restyle`). With probability 0.3, a training image is replaced by a re-drawing of its own mask in a random flat style: grey fill, black walls, outline walls, stair treads. The network then learns shape rather than CubiCasa's colours, which is the main bridge to FAST-style exports.
- **Scale normalisation.** Training records the typical wall thickness in pixels. At inference the plan is resized so its walls match that thickness, so resolution stops mattering.
- **Loss = cross-entropy + Dice.** Dice stops thin classes (walls, doors) from being ignored next to large rooms.
- **Sliding-window inference.** Overlapping 512 px tiles are blended, so any plan size works.

## 3. How to start, step by step

All commands exist in the repo (`turn-mapper ml ...`). The Colab notebook `notebooks/train_segmenter_colab.ipynb` runs steps 1–5 on a free T4 GPU.

**Step 0: install the ML extra (laptop or Colab)**

```bash
pip install -e ".[ml]"          # torch + segmentation-models-pytorch
```

**Step 1: get CubiCasa5K.** This is the ~5.5 GB zip from Zenodo record 2613548. On Colab the notebook downloads it to Google Drive once.

**Step 2: convert labels to masks (once)**

```bash
turn-mapper ml prepare-cubicasa /content/cubicasa5k --out data/cc_masks --limit 20   # quick look first
turn-mapper ml prepare-cubicasa /content/cubicasa5k --out data/cc_masks              # full set
```

This parses each `model.svg` (handling SVG transforms), picks the image the SVG coordinates belong to, paints the polygons in priority order (spaces < railings < walls < doors) and writes `images/`, `masks/` and `train/val/test.txt`. Check a few previews before training: a wrong class mapping here wastes hours.

**Step 3: pre-train**

```bash
turn-mapper ml train --data data/cc_masks --out weights/turn_seg_cubicasa.pt --epochs 30 --lr 3e-4
```

- About 3–5 h on a T4 for 30 epochs.
- The best checkpoint (by validation mIoU) is saved together with a `.json` manifest (sha256, data, settings, metrics) and a `.log.json` of every epoch.
- Resume after a disconnect with `--init`.

**Step 4: evaluate**

```bash
turn-mapper ml eval --data data/cc_masks --weights weights/turn_seg_cubicasa.pt --split test
```

This reports per-class IoU. Record the numbers in a results doc; never quote a number you did not get from this command.

**Step 5: make our own training masks (annotation)**

```bash
turn-mapper ml bootstrap-masks samples/private/fast_blocks.pdf --venue configs/venues/fast_isb.yaml \
    --floors C-F3,C-F4,C-F1,B-GF,B-F2 --out data/fast_masks
```

This writes the classical pipeline's result as a starting mask, plus a colour preview. You **correct** it instead of drawing from scratch, which takes about 20–40 minutes per floor:

- Open `masks/<floor>.png` in an editor that keeps exact pixel values: GIMP (indexed/greyscale, pencil tool, no anti-aliasing) or Krita. Alternatively, import image + mask into CVAT or Label Studio.
- Paint the true class ids. Fix doors (class 4) especially: they are what the classical method misses (e.g. C-F2's office suites).
- Write `train.txt` and `val.txt` (one floor id per line). Hold out at least one floor for validation.
- **Never put A block in training.** It is the held-out test building (ADR-009).
- Plans stay private: `data/` is gitignored, and FAST plans need permission before they leave the team.

**Step 6: fine-tune**

```bash
turn-mapper ml train --data data/fast_masks --init weights/turn_seg_cubicasa.pt \
    --out weights/turn_seg_fast.pt --epochs 15 --lr 5e-5
```

Tiny datasets are automatically repeated so that each epoch sees at least 64 random crops.

**Step 7: use it and compare with classical**

```bash
export TURN_SEG_WEIGHTS=weights/turn_seg_fast.pt
turn-mapper run samples/private/fast_blocks.pdf --venue configs/venues/fast_isb.yaml --split test \
    --segmenter learned --out runs/learned_test
turn-mapper run samples/private/fast_blocks.pdf --venue configs/venues/fast_isb.yaml --split test \
    --segmenter classical --out runs/classical_test
python scripts/style_stress.py --segmenter learned --out runs/stress_learned
```

Compare validity, rooms, doors, graph pieces and the QA overlays, and report both honestly.

## 4. What "done" looks like for the FYP

| milestone | evidence |
|---|---|
| CubiCasa pre-trained model | `ml eval` per-class IoU on the CubiCasa test split |
| 5–10 annotated floors (not A block) | `data/fast_masks` + annotation log |
| Fine-tuned model | IoU on held-out annotated floors: classical vs pre-trained vs fine-tuned |
| End-to-end | A block (test) with `--segmenter learned` vs `classical`: valid packages, room/door counts, routes |

The ablation "classical vs CubiCasa-only vs fine-tuned" is a strong evaluation chapter: it shows *why* each stage exists.

## 5. Code map

| file | role |
|---|---|
| `learned/classes.py` | class ids, CubiCasa room-name → class mapping, palette |
| `learned/cubicasa.py` | SVG parser (transforms), rasteriser, `prepare` |
| `learned/data.py` | mask dataset, crops, augmentation, restyling |
| `learned/model.py` | U-Net build, checkpoint + manifest, sliding-window inference |
| `learned/train.py` | training loop, mIoU evaluation |
| `learned/segmenter.py` | `LearnedSegmenter` (registered as `--segmenter learned`) |
| `learned/annotate.py` | classical result → starting masks |
| `learned/fake_cubicasa.py` | tiny CubiCasa-format dataset from synthetic plans (offline tests) |

Tested offline (`tests/test_learned.py`): SVG parsing and transforms, mask preparation, two training iterations on CPU, and a pipeline run with `--segmenter learned`. Those tests check that the plumbing works. They say nothing about accuracy, which only comes from real training on a GPU.
