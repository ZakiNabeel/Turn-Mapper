# Live demo script: mapping module (about 9 minutes)

Run everything live on the laptop. Use no screenshots or video, except as a backup if the laptop fails.

## Before the meeting (the day before)

```bash
git pull && pip install -e ".[dev]"            # tesseract must be installed (tesseract --version)
python scripts/demo_prepare.py --out demo_inputs
turn-mapper run samples/private/fast_blocks.pdf --venue configs/venues/fast_isb.yaml --floors C-F3 --out runs/warmup
python3 -m pytest -q                           # should print "47 passed" (or more)
```

Open these tabs in advance: the GitHub repo, `docs/mideval/00_INDEX.md`, and the evidence files linked from it. Keep a terminal in the repo folder with a large font.

## Steps

| # | Say | Do (type live) | What they should see |
|---|---|---|---|
| 1 | "One command turns a building's floor plan into a navigation map. This is C block, our test building." | `turn-mapper run samples/private/fast_blocks.pdf --venue configs/venues/fast_isb.yaml --floors C-F3,C-F4,C-F1 --out runs/demo_c` | `PASS` per floor with rooms, doors, nodes, POIs, scale source and seconds (about 5 s per floor) |
| 2 | "Every run produces a QA report for the human check." | open `runs/demo_c/qa/index.html` | overlay of rooms, doors, graph and POIs; sample routes; warnings |
| 3 | "The output is JSON the Android app imports: metres, a graph, POIs, and provenance on everything." | open `runs/demo_c/venue.json` in an editor and collapse to `floors[0].floor` | `transform.scale_source`, `graph.nodes/edges`, `pois`, `provenance` |
| 4 | "It isn't tuned to FAST's drawing style. Here's the same building layout drawn five other ways." | `turn-mapper run demo_inputs/lshape_thinlines.png --out runs/demo_thin` then `… lshape_doubleline.png …` and `… basic_scanned.png …` | all valid with the right room and door counts. Open one QA page |
| 5 | "We measure accuracy against exact ground truth." | `python eval/evaluate_synthetic.py --out runs/demo_eval` (≈ 40 s; or open `evidence/eval_synthetic_METRICS.md` while it runs) | table: room and door recall 1.0, 0 wall crossings, label accuracy 0.70 |
| 6 | **Failure case 1:** "When the plan hides doors, the map breaks, and the system says so." | `turn-mapper run samples/private/fast_blocks.pdf --venue configs/venues/fast_isb.yaml --floors C-F2 --out runs/demo_c2` and open its QA page | `comps=4`, warnings `GRAPH_DISCONNECTED`, POIs not reachable. Explain the cubicle suites and the planned learned-model fix |
| 7 | **Failure case 2:** "Bad input is rejected, not turned into a bad map." | `turn-mapper run demo_inputs/edge_blank.png --out runs/demo_blank` · `turn-mapper run demo_inputs/edge_not_a_plan.txt --out runs/demo_txt` | `FAIL … WALKABLE_EMPTY`, exit code 1 · one-line `no adapter can read …` |
| 8 | **Failure case 3:** "If someone hand-edits a map and breaks it, the validator catches it before it reaches a phone." | `turn-mapper validate demo_inputs/broken_map/venue.json` | `EDGE_OUTSIDE_WALKABLE e_bad`, `EDGE_DANGLING e_dangling`, `FAILED` |
| 9 | "The deep-learning segmenter plugs into the same pipeline. Training on CubiCasa5K is the next step." | `turn-mapper ml --help` · `turn-mapper run demo_inputs/basic_greyfill.png --segmenter learned --out runs/demo_l` | the ML commands; a clear error saying where the weights go (or, once trained, a learned run) |
| 10 | "Tests run on every commit." | `python3 -m pytest -q` | 47 passed |
| 11 | "No building-specific code: everything about FAST is in one config file." | `grep -rn "FAST\|C-F" src/ --include=*.py ; cat configs/venues/fast_isb.yaml` | `grep` finds nothing in the code; the YAML only says where the floors are in the PDF |

## New business logic beyond the proposal POC (say it explicitly)

- **Drawing-style detection:** filled or paper floor, thick or thin or double-line walls. It is estimated per image, with no hardcoded colours.
- **Door detection by orientation-aware wall-gap closing:** door slabs drawn over walls are handled, and partitions are not allowed to seal doors.
- **Three scale sources with audit trail:** measured, footprint transfer between floors, or a flagged door-width prior.
- **Validators that gate output:** 13 error and warning codes in the validator, plus `--force` with a recorded flag.
- **Stairs and lift transition nodes.**
- **JSON contract 0.1.1:** versioned, with fixtures for the app team.
- **Pluggable learned segmenter, CubiCasa tooling and bootstrap annotation.**

## If something goes wrong live

- **Tesseract missing:** add `params: {ocr: false}` to the venue YAML, or install it. Rooms still come out, but without labels.
- **Laptop failure:** the evidence files in `docs/mideval/evidence/` were produced by the same commands. Say that, then continue on a teammate's laptop.
