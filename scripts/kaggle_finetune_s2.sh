#!/usr/bin/env bash
# Stage S2 of docs/MASTER_PLAN.md: fine-tune the CubiCasa (S1) checkpoint on ResPlan drawings in 8 styles +
# procedural institutional floors (+ a CubiCasa replay subset so S1 skills are not forgotten).
# Kaggle inputs (Add Input):
#   - output of notebook "turn-segmenter-cubicasa-pretrain"  (contains turn_seg_cubicasa.pt)   [required]
#   - dataset qmarva/cubicasa5k                                                                 [optional replay]
#   - ResPlan: dataset resplan/resplan, or Internet On (cloned from GitHub)
# Run from the repo root:  bash scripts/kaggle_finetune_s2.sh [epochs] [resplan_variants] [institutional_n]
set -euo pipefail
EPOCHS="${1:-20}"; VARIANTS="${2:-1}"; NINST="${3:-3000}"
OUT=/kaggle/working/out_s2; W=/tmp/turn; mkdir -p "$OUT" "$W"
date
# the S1 notebook output also keeps run 1 (label-misaligned, mIoU 0.32): never start from it
INIT=$(find /kaggle/input -name 'turn_seg_cubicasa.pt' 2>/dev/null | grep -v -i misaligned | head -1 || true)
[ -n "$INIT" ] || { echo "S1 checkpoint turn_seg_cubicasa.pt not found under /kaggle/input (attach the pre-train notebook output)"; exit 1; }
echo "init: $INIT"; sha256sum "$INIT" | tee "$OUT/init_sha256.txt"

PKL=$(find /kaggle/input -name 'ResPlan.pkl' 2>/dev/null | head -1 || true)
SPLIT=$(find /kaggle/input -name 'split.json' -path '*esplan*' 2>/dev/null | head -1 || true)
if [ -z "$PKL" ]; then
  git clone -q --depth 1 https://github.com/m-agour/ResPlan.git "$W/ResPlan"
  (cd "$W/ResPlan" && unzip -q -o ResPlan.zip)
  PKL="$W/ResPlan/ResPlan.pkl"; SPLIT="$W/ResPlan/split.json"
fi
SPLIT_ARG=""; [ -n "$SPLIT" ] && SPLIT_ARG="--split-json $SPLIT"
echo "ResPlan: $PKL"
[ -s "$W/rp/train.txt" ] || turn-mapper ml prepare-resplan "$PKL" --out "$W/rp" $SPLIT_ARG --variants "$VARIANTS" | tee "$OUT/resplan_dataset.json"
[ -s "$W/inst/train.txt" ] || turn-mapper ml make-institutional --out "$W/inst" -n "$NINST" | tee "$OUT/institutional_dataset.json"
DATA=(--data "$W/rp" --data "$W/inst")

CC=$(python - <<'PY'
import glob, os
c = sorted({os.path.dirname(p) for p in glob.glob("/kaggle/input/**/train.txt", recursive=True)})
c = [x for x in c if os.path.isdir(os.path.join(x, "high_quality"))]
print(c[0] if c else "")
PY
)
if [ -n "$CC" ]; then
  [ -s "$W/cc/train.txt" ] || turn-mapper ml prepare-cubicasa "$CC" --out "$W/cc" --limit 1500 | tail -3
  DATA+=(--data "$W/cc")
fi
date
turn-mapper ml train "${DATA[@]}" --init "$INIT" --out "$OUT/turn_seg_s2.pt" \
  --epochs "$EPOCHS" --batch 8 --crop 512 --lr 2e-4 --workers 4 2>&1 | tee "$OUT/train_stdout.txt"
date
sha256sum "$OUT/turn_seg_s2.pt" | tee "$OUT/s2_sha256.txt"
for d in rp inst cc; do
  [ -d "$W/$d" ] || continue
  split=test; [ -s "$W/$d/test.txt" ] || split=val
  turn-mapper ml eval --data "$W/$d" --weights "$OUT/turn_seg_s2.pt" --split $split | tee "$OUT/eval_s2_${d}_${split}.json"
  turn-mapper ml eval --data "$W/$d" --weights "$INIT" --split $split | tee "$OUT/eval_s1_${d}_${split}.json"
done
python scripts/demo_prepare.py --out "$W/demo" > /dev/null
TURN_SEG_WEIGHTS="$OUT/turn_seg_s2.pt" python eval/evaluate_synthetic.py --segmenter learned --out "$OUT/eval_synth_s2" | tail -16
echo "ALL DONE"; date
