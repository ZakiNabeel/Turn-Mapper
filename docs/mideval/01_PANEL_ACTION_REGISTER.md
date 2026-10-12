# Panel Action Register: proposal defence → mid evaluation (mapping module rows)

> **Fill-in note for the team:** rows PA-01 and PA-02 come from what the team recorded about the defence feedback ("too broad / scope creep", and the novelty question). Before the meeting, check them word for word against the **official feedback sheet**, and add every other required change as a new row. Each row needs a live evidence link (a commit, a file in this repo, or a run you can open during the meeting). Rows for the positioning and app modules are owned by MS and SF.

| ID | Required change (panel wording) | Owner | Status | What we did | Live evidence |
|---|---|---|---|---|---|
| PA-01 | Scope too broad: narrow it | All (mapping rows: ZN) | ✅ Done | Mapping is evaluated on **one pilot building** (C block = main test, B = development, A = held out for testing). Out of scope for the pilot: vector/DXF input, iOS, full automation (the AI proposes, a human verifies). | `docs/DECISIONS.md` ADR-009; `configs/venues/fast_isb.yaml` (splits); `docs/TURN_FYP_CONTEXT.md` §28 |
| PA-02 | Show what is new compared with existing systems | ZN | ✅ Done (mapping part) | The pipeline goes from an ordinary raster floor plan (no CAD) to a validated metric navigation graph, works across drawing conventions (11/12), uses a pluggable learned segmenter, gates every map with validators, and flags its scale estimates. | `docs/RESULTS_GENERALITY_2026-10-11.md`; `docs/mideval/04_DESIGN.md` §8; live demo |
| PA-03 | *[copy the next item from the feedback sheet]* | | | | |
| PA-04 | *[…]* | | | | |
| PA-05 | *[…]* | | | | |

## How to show it in the meeting (2 minutes)

1. Open this file on GitHub.
2. For each row, click the evidence link and show the item: for PA-01, the split in `fast_isb.yaml`; for PA-02, the generality table, then the live run.
3. State the status in one sentence. If an item isn't done, point to its row in `02_MILESTONE_LOG.md` with the new date.
