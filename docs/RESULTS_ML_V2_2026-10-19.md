# Learned segmenter v2 and hybrid: dev tuning and the 12-case test (2026-10-19)

Plan: `docs/ML_IMPROVEMENT_PLAN.md`, phases C (learned v2) and D (hybrid). Network: S2 (`turn_seg_s2.pt`, sha256 `146f1fcc…2407`, `docs/RESULTS_ML_S2_2026-10-17.md`), unchanged; only how the pipeline uses its output changed.

Where it ran (Kaggle, CPU, private notebooks owned by Zaki, S2 output attached as input):

| run | notebook | commit | time |
|---|---|---|---|
| learned v2 grid + test | `notebookf6cd6bb856` (from `notebooks/tune_learned_v2_kaggle.ipynb`), `kaggle_tune_v2.sh 16 learned` | `45fb71a` | 5,774 s |
| hybrid grid | `notebook1ebba9e941` (from `notebooks/tune_hybrid_kaggle.ipynb`), `kaggle_tune_v2.sh 16 hybrid` | `2cc57e6` | 2,808 s |

Dev set: 16 procedural institutional floors, seed 2026 (never used for training), 2 per style across all 8 styles, scale given (0.04 m/px), scored against the generator's exact mask (`eval/evaluate_dev.py`). The selection rule was fixed before any result: dev score = mean(room R, room P, door R, door P, routes) − 0.05 × mean wall crossings per floor; ties go to the simpler config.

Caveat: these runs use Kaggle's Tesseract build. As in the S2 report, classical scores lower there than in the recorded local run (see the environment note in `RESULTS_ML_S2_2026-10-17.md`), so the classical rows below are the Kaggle-run classical.

## Dev set (16 floors)

| config | segmenter | dev score | rooms R | rooms P | doors R | doors P | routes | wall crossings / floor |
|---|---|---|---|---|---|---|---|---|
| classical | classical | 0.697 | 0.560 | 0.701 | 0.520 | 0.718 | 1.000 | 0.062 |
| v1 (S2 as of 2026-10-17) | learned | 0.809 | 0.767 | 0.700 | 0.738 | 0.857 | 1.000 | 0.062 |
| doors | learned | 0.895 | 0.931 | 0.710 | 0.941 | 0.891 | 1.000 | 0 |
| **doors+scales** (0.7, 1.0, 1.4) | learned | **0.911** | 0.940 | 0.750 | 0.950 | 0.916 | 1.000 | 0 |
| doors+frag (t² ≥ 6) | learned | 0.900 | 0.931 | 0.715 | 0.939 | 0.915 | 1.000 | 0 |
| doors+thr0.35 | learned | 0.881 | 0.920 | 0.707 | 0.941 | 0.843 | 0.996 | 0 |
| doors+scales+thr0.35+frag | learned | 0.896 | 0.925 | 0.745 | 0.945 | 0.873 | 0.990 | 0 |
| hybrid0.75 | hybrid | 0.917 | 0.919 | 0.863 | 0.889 | 0.916 | 1.000 | 0 |
| **hybrid0.6** | hybrid | **0.922** | 0.922 | 0.864 | 0.885 | 0.937 | 1.000 | 0 |
| hybrid0.9 | hybrid | 0.918 | 0.919 | 0.876 | 0.906 | 0.922 | 1.000 | 0.125 |
| hybrid0.75+frag | hybrid | 0.918 | 0.919 | 0.863 | 0.889 | 0.917 | 1.000 | 0 |
| hybrid0.75 without network doors | hybrid | 0.843 | 0.756 | 0.884 | 0.701 | 0.891 | 1.000 | 0.062 |

Picks by the declared rule: **doors+scales** (learned) and **hybrid0.6** (hybrid).

Reading:

- **Network doors are the big lever.** Using the door class as known openings lifts room recall from 0.77 to 0.93 and door recall from 0.74 to 0.94, and removes wall crossings. Without them the hybrid falls back to 0.76 / 0.70.
- Scale search adds a little: rooms P 0.71 → 0.75, mostly from double-line and thin-line floors.
- A lower wall threshold (0.35) and fragment removal do not help.
- **The hybrid fixes room precision** (0.75 → 0.86): classical walls stop the network splitting large spaces, while network doors keep recall at about 0.92. Thin-line room precision goes from 0.44 (learned) to 0.80.
- Per style, classical finds nothing on hatched floors (0.0) and 22% of rooms on double-line. Learned and hybrid stay at 0.89–1.0 room recall on every style.

## 12-case synthetic test

Learned pick (doors+scales), run once, notebook `notebookf6cd6bb856`. Cells: rooms R/P, doors R/P, routes found, wall-crossing edges.

| case | classical (recorded, local) | classical (Kaggle run) | v1 | **doors+scales** |
|---|---|---|---|---|
| basic greyfill | 1/1, 1/1, 1.0, 0 | 0.857/0.667, 1/1, 1.0, 0 | 1/1, 1/1, 1.0, 0 | 1/1, 1/1, 1.0, 0 |
| basic blackwalls | 1/1, 1/1, 1.0, 0 | 1/1, 1/1, 1.0, 0 | 1/1, 1/1, 1.0, 0 | 1/1, 1/1, 1.0, 0 |
| basic thinlines | 1/1, 1/1, 1.0, 0 | 1/1, 1/1, 1.0, 0 | 1/0.583, 1/1, 1.0, 0 | 1/1, 1/1, 1.0, 0 |
| basic doubleline | 1/1, 1/1, 1.0, 0 | 0.571/0.308, 0.667/0.333, 0.0, 0 | 0.857/0.75, 0.833/0.5, 0.4, 0 | 0.857/0.5, 0.833/0.714, **0.0**, 0 |
| basic colored | 1/1, 1/1, 1.0, 0 | 1/1, 1/1, 1.0, 0 | 1/1, 1/1, 1.0, 0 | 1/1, 1/1, 1.0, 0 |
| basic scanned | 1/1, 1/0.86, 1.0, 0 | 1/0.389, 0.667/0.267, 0.2, 0 | 1/1, 1/1, 0.667, 0 | 1/1, 1/1, **1.0**, 0 |
| lshape greyfill | 1/1, 1/1, 1.0, 0 | 0.889/0.727, 1/1, 1.0, 0 | 1/0.818, 1/0.889, 1.0, 0 | 1/0.9, 1/1, 1.0, 0 |
| lshape blackwalls | 1/1, 1/1, 1.0, 0 | 0.778/1, 0.75/1, 0.536, 0 | 1/0.643, 1/0.889, 1.0, 0 | 1/0.9, 1/1, 1.0, 0 |
| lshape thinlines | 1/1, 1/1, 1.0, 0 | 1/1, 1/1, 1.0, 0 | 1/0.643, 1/1, 1.0, 0 | 1/0.818, 1/1, 1.0, 0 |
| lshape doubleline | 1/1, 1/1, 1.0, 0 | 0.667/0.3, 0.625/0.312, 0.0, 0 | 0.889/0.533, 1/0.667, 0.0, 0 | 0.889/0.533, 1/0.667, **0.0**, 0 |
| lshape colored | 1/1, 1/1, 1.0, 0 | 1/1, 1/1, 1.0, 0 | 1/0.818, 1/0.889, 1.0, 0 | 1/0.9, 1/1, 1.0, 0 |
| lshape scanned | 1/1, 1/1, 1.0, 0 | 1/1, 1/1, 1.0, 0 | 1/0.818, 1/0.889, 0.75, 0 | 1/0.75, 1/1, **1.0**, 0 |

**Promotion rule** ("at least as good" = room recall, door recall and routes ≥ classical, wall crossings ≤ classical):

- Against the **recorded** classical baseline, doors+scales qualifies on **10/12** cases (v1: 8/12). It now passes both scanned cases (routes 1.0). It still fails both double-line cases: 0 routes, and the basic case also has room recall 0.857.
- Against the Kaggle-run classical, it qualifies on 12/12 (not used, weaker baseline).
- **The synthetic half of the rule is met for the first time. The A-block half is still open** (it needs Zaki's annotations, phase F), so classical stays the default for now.

### Hybrid test: invalid run, rerun queued

The hybrid notebook's test column was identical to v1 in every cell. Cause: `scripts/tune_learned.py` always ran the pick with `--segmenter learned`, so the test ran "learned with `hybrid_wall_conf=0.6`", which is v1. Fixed (the pick's own segmenter is now used, and `--test-only` reruns only the test). The hybrid0.6 test had therefore never actually been run. It is queued in `notebooks/test_picks_kaggle.ipynb` together with doors+scales, rerun in the same environment for a side-by-side comparison; it is deterministic and not a new tuning step. Results go here when it finishes.

## Next

1. Hybrid0.6 test (above).
2. Double-line routes are 0 on both test cases for every learned config, although dev double-line routes are 1.0. The test's double-line style (1 px lines, gap = wall + 4 px) differs from training and dev. S3a (training with wider double-line variety) is the fix being tried. Phase A images of these two cases are the next diagnosis.
3. A-block annotation (phase F), then the full promotion decision.
