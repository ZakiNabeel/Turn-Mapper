# Metric scale from site measurements (2026-10-24)

**Input:** the team's measurement sheet (tape, feet, inside dimensions), photographed 2026-10-24:

- Typical room: A block 30 × 20 ft, B 30 × 24 ft, C 30 × 25 ft. The sheet also gives D as 30 × 25–26 ft, but there is no D block in this PDF.
- B227-A: 19.7 + 16.08 by 19.7 + 5.41 ft = 35.78 × 25.11 ft. The sheet's own note says "almost 34 by 24".
- A block 2nd-floor corridor: 90 × 12 ft.

These numbers are in `configs/venues/fast_isb.yaml` under `scale_evidence`. Room numbers are site facts, not plan content.

**Runs:**

- Code: `ab3a5d1` + this change. Classical segmenter on all 14 floors.
- Before: `runs/fast_2026-10-24_base`, no measurements.
- After: `runs/fast_2026-10-24_measured`.
- Both runs are local, and the plans stay private.

## Method (fixed before running on FAST)

- **`typical_room`.** Each room region's minimum-area rectangle is compared with the measured size.
  - A room is a candidate when its side ratio is within 15% of the measured ratio and it fills its rectangle (0.9–1.1).
  - Candidates that agree on a scale within 6% form a group. Groups are scored by total room area, so the common large rooms beat many small rooms of the same shape.
  - The fit is accepted only with **at least 5 agreeing rooms**, and only if the drawn doors then measure 0.6–2.5 m.
- **`room_size`.** One named room (matched by its OCR label) gives the scale directly.
- **`corridor_width`.** The median width of the largest circulation space. It is used **as a check only**.
- **Calibrated door prior** (`door_width_calibrated`). For floors without an accepted measurement, the drawn door width is measured on this venue's measured floors (median door width in px × measured scale, then the median over floors), and that width replaces the generic 0.9 m. This is still an **estimate**, and it is flagged as one.
- **Footprint transfer.** A floor marked `scale_like` borrows its scale from its reference floor, as before. A transferred scale no longer changes that floor's door and room detection; only measured scales do.

## Result

| floor | before (m/px, source) | **after (m/px, source)** | factor | floor image in metres | fit |
|---|---|---|---|---|---|
| A-GF | 0.0273 door prior | **0.0602** calibrated door prior | 2.21× | 96.3 × 41.2 | typical 30×20 ft: 1 agreeing room, rejected |
| A-F1 | 0.0273 door prior | **0.0602** calibrated door prior | 2.21× | 96.3 × 40.9 | 1 room, rejected |
| A-F2 | 0.0273 door prior | **0.0602** calibrated door prior | 2.21× | 96.3 × 41.5 | 3 rooms, rejected |
| A-F3 | 0.0281 door prior | **0.0621** calibrated door prior | 2.21× | 99.4 × 42.7 | 2 rooms, rejected |
| B-GF | 0.0391 door prior | **0.0897** measured rooms | 2.29× | 96.7 × 83.5 | 6 rooms (spread 9.6%), doors 2.06 m |
| B-F1 | 0.0450 door prior | **0.1008** measured rooms | 2.24× | 94.8 × 87.4 | 6 rooms (spread 11.9%), doors 2.02 m |
| B-F2 | 0.0486 door prior | **0.1074** calibrated door prior | 2.21× | 109.7 × 100.2 | 3 rooms, rejected |
| C-B1 | 0.0281 door prior | **0.0621** calibrated door prior | 2.21× | 60.1 × 34.6 | 0 rooms |
| C-GF | 0.0228 door prior | **0.0503** calibrated door prior | 2.21× | 48.9 × 20.9 | 1 room |
| C-F1 | 0.0243 door prior | **0.0537** calibrated door prior | 2.21× | 51.0 × 27.6 | 1 room |
| C-F3 | 0.0265 door prior | **0.0576** measured rooms | 2.17× | 57.0 × 24.9 | 7 classrooms (spread 8.5%), doors 1.96 m |
| C-F4 | 0.0265 door prior | **0.0572** measured rooms | 2.16× | 56.7 × 24.8 | 8 classrooms (spread 9.6%), doors 1.94 m |
| C-F2 | 0.0190 transfer | **0.0414** transfer from C-F3 | 2.18× | 57.1 × 23.5 | 2 rooms |
| C-F5 | 0.0160 transfer | **0.0349** transfer from C-F3 | 2.18× | 57.2 × 23.6 | 2 rooms |

Calibrated drawn door width: **1.99 m**. The four measured floors give B-GF 2.06, B-F1 2.02, C-F3 1.96 and C-F4 1.94 m. The run manifest records this as `door_width_calibration`.

## What this means

- **Every map was about 2.2 times too small.** The 0.9 m door prior assumed drawn door gaps are one door wide, but on the FAST plans they measure about 2 m. Every distance, route length and position in metres from the previous runs was therefore short by a factor of about 2.2. Positioning needs real metres, so the old maps would have made a 10 m walk look like 4.5 m.
- **Evidence the measured scale is right:**
  - C-F3 and C-F4 were fitted independently from their own classrooms and agree within 0.7% (0.0576 vs 0.0572 m/px, images 990 and 992 px wide).
  - The four C floors with the same footprint come out at 56.7–57.2 m wide (two measured, two by transfer).
  - The drawn door width implied by the fits is about 2 m on all four measured floors, in two buildings.
- **Failed or open checks:**
  - **A block typical room (30 × 20 ft):** never matched. The A classrooms in the drawing are nearly square (about 160 × 150 px), so either the drawing differs from the building or the typical size refers to other rooms. A uses the calibrated estimate.
  - **A-F2 corridor (12 ft):** the median width of A-F2's largest circulation space implies 0.0339 m/px, 44% below the A estimate. That space mixes the corridor with wider halls, so the check does not isolate the 12 ft corridor. It is reported as a failed check, not used, and the statistic was not changed after seeing the result (A is the held-out block, ADR-009).
  - **B227-A:** no room carries that OCR label (B-227 exists, at 9.2 × 8.5 m on B-F1). It is not used.
- **Counts:** room and door counts are unchanged on 12 floors, because detection does not use the scale. On C-F2 and C-F5, transferred scales no longer drive detection (see Method), so C-F2 has 30 rooms and 28 doors (before 26 / 24) and C-F5 has 32 / 42 (before 30 / 36). Graph node counts rise everywhere because node spacing is set in metres.

## Next measurements (cheapest high-value)

1. **C-F4 corridor width and C-406 door width** (tape, wall to wall). They test the C fit directly.
2. **One A classroom (for example A-201)**, length and width, to replace the A estimate.
3. **B227-A:** which room on the plan it is (a photo of the door sign and the room), so the label can be matched.
