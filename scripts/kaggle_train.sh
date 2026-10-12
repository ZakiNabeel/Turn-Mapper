#!/usr/bin/env bash
# One-shot CubiCasa5K pre-training on a Kaggle GPU session (dataset qmarva/cubicasa5k attached as input,
# or the Zenodo zip already extracted to /tmp/turn/cubicasa5k). Run from the repo root:
#   bash scripts/kaggle_train.sh [epochs]
# Everything worth keeping goes to /kaggle/working/out (saved with the notebook version).
set -euo pipefail
EPOCHS="${1:-25}"
OUT=/kaggle/working/out
mkdir -p "$OUT" /tmp/turn
if [ ! -e /tmp/turn/cubicasa5k ]; then
  ROOT=$(python - <<'PY'
import glob, os
c = sorted({os.path.dirname(p) for p in glob.glob("/kaggle/input/**/train.txt", recursive=True)})
c = [x for x in c if os.path.isdir(os.path.join(x, "high_quality"))] or c
print(c[0] if c else "")
PY
)
  [ -n "$ROOT" ] || { echo "CubiCasa5K not found under /kaggle/input"; exit 1; }
  ln -sfn "$ROOT" /tmp/turn/cubicasa5k
fi
echo "data: $(readlink -f /tmp/turn/cubicasa5k)"
date
if [ ! -s /tmp/turn/cc_masks/train.txt ]; then
  turn-mapper ml prepare-cubicasa /tmp/turn/cubicasa5k --out /tmp/turn/cc_masks 2>&1 | tail -20 | tee "$OUT/prepare_stdout.txt"
fi
wc -l /tmp/turn/cc_masks/*.txt
date
turn-mapper ml train --data /tmp/turn/cc_masks --out "$OUT/turn_seg_cubicasa.pt" \
  --epochs "$EPOCHS" --batch 8 --crop 512 --lr 3e-4 --workers 4 2>&1 | tee "$OUT/train_stdout.txt"
date
turn-mapper ml eval --data /tmp/turn/cc_masks --weights "$OUT/turn_seg_cubicasa.pt" --split test | tee "$OUT/eval_cubicasa_test.json"
python scripts/demo_prepare.py --out /tmp/turn/demo > /dev/null
TURN_SEG_WEIGHTS="$OUT/turn_seg_cubicasa.pt" python eval/evaluate_synthetic.py --segmenter learned \
  --out "$OUT/eval_synth_learned" | tail -16
echo "ALL DONE"; date
