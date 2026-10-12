# FAST regression run (classical) — summary

run_id: 2026-10-11T09-08-29Z_fast-isb · generator {'name': 'turn-mapper', 'version': '0.1.0', 'git_commit': '9b6030d'} · command: `turn-mapper run samples/private/fast_blocks.pdf --venue configs/venues/fast_isb.yaml --split all --out runs/fast_regress_7`

Counts only (the plan images stay private until the PDF's use is approved).

| floor | split | valid | rooms | doors | nodes | edges | POIs | graph pieces | scale m/px (source) | seconds |
|---|---|---|---|---|---|---|---|---|---|---|
| A-GF | test | yes | 20 | 25 | 86 | 83 | 21 | 3 | 0.0273 (door_width_prior) | 9.5 |
| A-F1 | test | yes | 33 | 28 | 95 | 94 | 20 | 1 | 0.0273 (door_width_prior) | 9.0 |
| A-F2 | test | yes | 27 | 25 | 84 | 81 | 20 | 3 | 0.0273 (door_width_prior) | 11.0 |
| A-F3 | test | yes | 20 | 26 | 90 | 88 | 22 | 2 | 0.0281 (door_width_prior) | 7.9 |
| B-GF | dev | yes | 40 | 31 | 108 | 107 | 23 | 1 | 0.0391 (door_width_prior) | 10.4 |
| B-F1 | dev | yes | 37 | 32 | 114 | 113 | 25 | 2 | 0.0450 (door_width_prior) | 8.7 |
| B-F2 | dev | yes | 42 | 36 | 107 | 106 | 26 | 1 | 0.0486 (door_width_prior) | 9.8 |
| C-B1 | dev | yes | 8 | 2 | 32 | 31 | 5 | 1 | 0.0281 (door_width_prior) | 4.0 |
| C-GF | dev | yes | 20 | 8 | 20 | 18 | 5 | 2 | 0.0228 (door_width_prior) | 5.6 |
| C-F1 | dev | yes | 10 | 8 | 42 | 42 | 7 | 1 | 0.0243 (door_width_prior) | 4.5 |
| C-F3 | dev | yes | 13 | 23 | 65 | 64 | 15 | 1 | 0.0265 (door_width_prior) | 4.7 |
| C-F4 | dev | yes | 12 | 22 | 71 | 70 | 14 | 1 | 0.0265 (door_width_prior) | 4.8 |
| C-F2 | dev | yes | 26 | 24 | 55 | 51 | 9 | 4 | 0.0190 (footprint_transfer) | 14.2 |
| C-F5 | dev | yes | 30 | 36 | 46 | 43 | 11 | 3 | 0.0160 (footprint_transfer) | 15.5 |
