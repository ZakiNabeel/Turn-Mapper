#!/usr/bin/env bash
# Stage S4: fine-tune on REAL CAD drawings (FloorPlanCAD: offices, schools, hospitals, malls) so the model learns
# real stair, lift and escalator symbols and institutional wall drawings. FloorPlanCAD has no room labels, so its
# masks are partial (classes.OPEN); ResPlan + procedural institutional floors (+ CubiCasa replay) are trained
# alongside so rooms, corridors and doors are not forgotten.
# Kaggle: GPU T4, Internet On. Inputs (Add Input):
#   - output of the S3a notebook (turn_seg_s3a.pt)  [preferred]  or of the S2 notebook (turn_seg_s2.pt)
#   - dataset qmarva/cubicasa5k                      [optional replay]
# FloorPlanCAD is downloaded from the authors' Google Drive (annotations CC BY-NC 4.0, research use only);
# data and weights stay in /kaggle/working and are never committed.
# Run from the repo root:  bash scripts/kaggle_finetune_s4.sh [epochs] [fpc_limit] [institutional_n] [train_min]
set -euo pipefail
EPOCHS="${1:-10}"; FPC_LIMIT="${2:-7000}"; NINST="${3:-3000}"; TRAIN_MIN="${4:-300}"
OUT=/kaggle/working/out_s4; W=/tmp/turn; mkdir -p "$OUT" "$W"
date
INIT=$(find /kaggle/input -name 'turn_seg_s3a.pt' 2>/dev/null | head -1 || true)
[ -n "$INIT" ] || INIT=$(find /kaggle/input -name 'turn_seg_s2.pt' 2>/dev/null | head -1 || true)
[ -n "$INIT" ] || { echo "no turn_seg_s3a.pt / turn_seg_s2.pt under /kaggle/input (attach the S3a notebook output)"; exit 1; }
echo "init: $INIT"; sha256sum "$INIT" | tee "$OUT/init_sha256.txt"

# ---- FloorPlanCAD (real CAD drawings) ----
if [ ! -s "$W/fpc/train.txt" ]; then
  pip -q install gdown > /dev/null
  python - <<'PY'
import glob, os, shutil, subprocess
D = "/tmp/turn/fpc_raw"; os.makedirs(D, exist_ok=True)
ids = {"train1": "1HcyKt6qWeXog-tRfvEjdO3O3TN91PXGL", "train2": "1kSS7OB_EEu7VJzb0W8DK9_nu1EvshioV",
       "test": "1jxpYgxnLUbXEzMOsjaMPQFSuvmvHimiZ"}
for name, fid in ids.items():
    out = f"{D}/{name}.archive"
    subprocess.run(["gdown", "-q", "--fuzzy", f"https://drive.google.com/file/d/{fid}/view", "-O", out])
    if not os.path.exists(out):
        print("FETCH FAIL", name); continue
    os.makedirs(f"{D}/{name}", exist_ok=True)
    for fmt in ("zip", "gztar", "xztar", "tar"):
        try:
            shutil.unpack_archive(out, f"{D}/{name}", fmt); break
        except Exception:
            continue
    os.remove(out)
    print("SVGS", name, len(glob.glob(f"{D}/{name}/**/*.svg", recursive=True)))
PY
  TRAIN_DIRS=(); for d in "$W/fpc_raw/train1" "$W/fpc_raw/train2"; do [ -d "$d" ] && TRAIN_DIRS+=("$d"); done
  [ "${#TRAIN_DIRS[@]}" -gt 0 ] || { echo "FloorPlanCAD download failed (Google Drive quota?). Re-run later."; exit 1; }
  TEST_ARG=(); [ -d "$W/fpc_raw/test" ] && TEST_ARG=(--test "$W/fpc_raw/test")
  turn-mapper ml prepare-floorplancad "${TRAIN_DIRS[@]}" "${TEST_ARG[@]}" --out "$W/fpc" --limit "$FPC_LIMIT" | tee "$OUT/floorplancad_dataset.json"
  rm -rf "$W/fpc_raw"
fi
date

# ---- replay data so rooms / corridors / doors are kept ----
PKL=$(find /kaggle/input -name 'ResPlan.pkl' 2>/dev/null | head -1 || true)
SPLIT=$(find /kaggle/input -name 'split.json' -path '*esplan*' 2>/dev/null | head -1 || true)
if [ -z "$PKL" ]; then
  git clone -q --depth 1 https://github.com/m-agour/ResPlan.git "$W/ResPlan"
  (cd "$W/ResPlan" && unzip -q -o ResPlan.zip)
  PKL="$W/ResPlan/ResPlan.pkl"; SPLIT="$W/ResPlan/split.json"
fi
SPLIT_ARG=""; [ -n "$SPLIT" ] && SPLIT_ARG="--split-json $SPLIT"
[ -s "$W/rp/train.txt" ] || turn-mapper ml prepare-resplan "$PKL" --out "$W/rp" $SPLIT_ARG --variants 1 --limit 6000 --ignore-residual | tee "$OUT/resplan_dataset.json"
[ -s "$W/inst/train.txt" ] || turn-mapper ml make-institutional --out "$W/inst" -n "$NINST" --seed 2 | tee "$OUT/institutional_dataset.json"
DATA=(--data "$W/fpc" --data "$W/rp" --data "$W/inst")
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
turn-mapper ml train "${DATA[@]}" --init "$INIT" --out "$OUT/turn_seg_s4.pt" \
  --epochs "$EPOCHS" --batch 8 --crop 512 --lr 5e-5 --workers 4 --amp --max-minutes "$TRAIN_MIN" 2>&1 | tee "$OUT/train_stdout.txt"
date
sha256sum "$OUT/turn_seg_s4.pt" | tee "$OUT/s4_sha256.txt"
# before (init) vs after (S4) on every test split; FloorPlanCAD test = real stairs / lifts / escalators / walls
for d in fpc rp inst cc; do
  [ -d "$W/$d" ] || continue
  split=test; [ -s "$W/$d/test.txt" ] || split=val
  turn-mapper ml eval --data "$W/$d" --weights "$OUT/turn_seg_s4.pt" --split $split | tee "$OUT/eval_s4_${d}_${split}.json"
  turn-mapper ml eval --data "$W/$d" --weights "$INIT" --split $split | tee "$OUT/eval_init_${d}_${split}.json"
done
python scripts/demo_prepare.py --out "$W/demo" > /dev/null
TURN_SEG_WEIGHTS="$OUT/turn_seg_s4.pt" python eval/evaluate_synthetic.py --segmenter learned --out "$OUT/eval_synth_s4" | tail -16
TURN_SEG_WEIGHTS="$INIT" python eval/evaluate_synthetic.py --segmenter learned --out "$OUT/eval_synth_init" | tail -16
echo "ALL DONE"; date
