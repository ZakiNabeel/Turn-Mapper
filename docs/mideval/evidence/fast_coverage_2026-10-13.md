# FAST plans, coverage check (2026-10-13)

Run `runs/fast_2026-10-13` (commit `11ebe04`, classical segmenter). Counts per floor and room / door / POI numbers are identical to the v0.3.0 reference run in [fast_regression_summary.md](fast_regression_summary.md).

These are **coverage** numbers, not accuracy: there is no FAST ground truth yet. "Rooms" includes sub-spaces such as cubicles, shafts and stair wells, so not every room should have a door.

| floor | split | rooms | rooms with a door | rooms with a code or name (OCR) | POIs | POIs in main graph piece | graph pieces |
|---|---|---|---|---|---|---|---|
| A-GF | test | 20 | 19 | 19 | 21 | 19 | 3 |
| A-F1 | test | 33 | 21 | 27 | 20 | 20 | 1 |
| A-F2 | test | 27 | 20 | 25 | 20 | 19 | 3 |
| A-F3 | test | 20 | 19 | 19 | 22 | 21 | 2 |
| B-GF | dev | 40 | 24 | 32 | 23 | 23 | 1 |
| B-F1 | dev | 37 | 24 | 36 | 25 | 24 | 2 |
| B-F2 | dev | 42 | 29 | 30 | 26 | 26 | 1 |
| C-B1 | dev | 8 | 2 | 8 | 5 | 5 | 1 |
| C-GF | dev | 20 | 8 | 17 | 5 | 4 | 2 |
| C-F1 | dev | 10 | 5 | 9 | 7 | 7 | 1 |
| C-F3 | dev | 13 | 13 | 13 | 15 | 15 | 1 |
| C-F4 | dev | 12 | 12 | 12 | 14 | 14 | 1 |
| C-F2 | dev | 26 | 14 | 21 | 9 | 7 | 4 |
| C-F5 | dev | 30 | 18 | 21 | 11 | 10 | 3 |
| **all 14** | | 338 | 228 (67%) | 289 (86%) | 223 | 214 (96%) | |

Visible problems in the overlays (manual review):

- **A-F1:** the *Open to Ground Floor* void is marked walkable and gets a graph branch. Cubicle suites (A-111x, A-114x, A-115x) have no inner doors.
- **B-GF:** the top-left cluster (B-01…B-13) is not connected, and one false door is drawn across B-01.
- **C-F2:** faculty-office suites are split off (known failure F4).

Script: an inline networkx count over `venue.json` (rooms with a door id, POI node in the largest component).
