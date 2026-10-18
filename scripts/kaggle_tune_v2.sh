#!/usr/bin/env bash
# Kaggle (CPU) runner for phase C of docs/ML_IMPROVEMENT_PLAN.md. Needs the turn-segmenter-s2-finetune output
# attached. Args: n set [test-only names]. One notebook cell:
#   !git clone -q https://github.com/ZakiNabeel/Turn-Mapper.git /kaggle/working/Turn-Mapper && bash /kaggle/working/Turn-Mapper/scripts/kaggle_tune_v2.sh
set -uo pipefail
cd /kaggle/working/Turn-Mapper
apt-get -qq install -y tesseract-ocr > /dev/null 2>&1 || true
pip -q install -e ".[ml]" 2>&1 | tail -2
git log --oneline -1
export TURN_SEG_WEIGHTS=$(find /kaggle/input -name 'turn_seg_s2.pt' | head -1)
echo "weights: $TURN_SEG_WEIGHTS"
python scripts/tune_learned.py --n "${1:-16}" --set "${2:-learned}" ${3:+--test-only "$3"} --out /kaggle/working/tune 2>&1 | grep -v -i warning | tee /kaggle/working/tune_log.txt | grep -E "^(classical|v1|doors|hybrid|BEST|DONE|test:)"
python - <<'PY'
import json
R = json.load(open('/kaggle/working/tune/tune_results.json'))
print('| config | dev score | rooms R | rooms P | doors R | doors P | routes | wall x |')
for n, r in R['dev'].items():
    d = r['dev']
    print(f"| {n} | {r['dev_score']} | {d.get('room_recall')} | {d.get('room_precision')} | {d.get('door_recall')} | {d.get('door_precision')} | {d.get('routes')} | {d.get('wall_crossings')} |")
print('best:', R['best'])
names = list(R['test'])
print('| test case | ' + ' | '.join(names) + ' |  (rooms R/P, doors R/P, routes, wall x)')
for i, row in enumerate(R['test'][names[0]]):
    cells = [f"{R['test'][n][i]['room_recall']}/{R['test'][n][i]['room_precision']}, {R['test'][n][i]['door_recall']}/{R['test'][n][i]['door_precision']}, {R['test'][n][i]['route_found']}, {R['test'][n][i]['wall_crossing_edges']}" for n in names]
    print(f"| {row['layout']} {row['style']} | " + ' | '.join(cells) + ' |')
PY
