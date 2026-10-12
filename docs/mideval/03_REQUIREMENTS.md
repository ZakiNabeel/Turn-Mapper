# Requirements: TURN-Mapper (floor plan → navigation map)

Owner: Zaki Nabeel. Scope: Pipeline 1 of TURN, the module that turns a floor plan into a navigable map.

Every requirement below has an acceptance test that can be run, and it maps to code that exists today. Status values:

- ✅ met: the test passes.
- 🟡 partial: implemented, but the target is not yet proven on real data.
- ⏳ planned.

How to run the acceptance tests:

- `python3 -m pytest -v` (log: [`evidence/pytest_log_2026-10-12.txt`](evidence/pytest_log_2026-10-12.txt)).
- `python eval/evaluate_synthetic.py` (metrics: [`evidence/eval_synthetic_METRICS.md`](evidence/eval_synthetic_METRICS.md)).
- `python scripts/style_stress.py`.

## Functional requirements

| ID | Requirement | Acceptance test (pass condition) | Code | Status |
|---|---|---|---|---|
| FR-01 | The system shall read floor plans from PDF (embedded raster images or rendered pages) and raster images (PNG/JPG). | `test_cli_inspect_and_validate`; `turn-mapper inspect <pdf>` lists pages and images; `turn-mapper run plan.png` produces output | `ingest.py` | ✅ |
| FR-02 | The system shall process a multi-building, multi-floor venue described by one YAML config: page and image index per floor, building, level, and dev/test split. | `turn-mapper run fast_blocks.pdf --venue configs/venues/fast_isb.yaml --split all` processes 14 floors | `config.py`, `api.convert` | ✅ |
| FR-03 | The system shall detect text in 0°, 90° and 270° orientations and remove it before segmentation. | `test_rotated_ocr_box_mapping_round_trip`, `test_ocr_labels_rooms` | `preprocess.py` | ✅ |
| FR-04 | The system shall separate walls, floor and outside for different drawing conventions: filled, solid black, thin line, double line, coloured and scanned. | `test_segmentation_masks`, `test_style_basic[*]` (5 styles); style stress ≥ 10/12 cases fully correct | `segment.py` | ✅ (11/12) |
| FR-05 | The system shall detect door openings, including doors drawn as slabs over a wall and thin partitions that must not seal a door. | `test_gap_closing_closes_doors_but_not_narrow_rooms`, `test_door_slab_over_unbroken_wall_is_carved`, `test_thin_partition_kept_door_arc_like_short_stroke_dropped`; door recall = 1.0 on synthetic | `vectorize.py` | ✅ |
| FR-06 | The system shall split free space into rooms and circulation (corridors). | `test_vectorize_finds_rooms_and_doors`; room recall = 1.0 on synthetic | `vectorize.py` | ✅ |
| FR-07 | The system shall convert pixels to metres from (a) two measured points, (b) a reference floor of the same footprint, or (c) a door-width prior that is flagged as an estimate. | `test_scale_from_two_points_and_residuals`, `test_footprint_scale_transfer`, `test_door_prior_scale_close_to_truth` | `scale.py`, `api.process_floor` | ✅ (c) and (b) in use. (a) is waiting for site measurements |
| FR-08 | The system shall detect stairs and lifts and expose them as transition nodes and POIs. | `test_stairs_texture_detected_and_flat_floor_ignored` | `transitions.py` | 🟡 stairs work on filled plans; lifts depend on OCR |
| FR-09 | The system shall build a navigation graph with metric edge lengths, door nodes and no edge through a wall. | `test_chain_produces_valid_routable_package`, `test_graph_edges_keep_their_geometry_regardless_of_direction`, `test_metric_lengths_and_bounds`; wall crossings = 0 in the synthetic eval | `graph.py` | ✅ |
| FR-10 | The system shall attach OCR room labels and create one destination (POI) per room door, flagging low-confidence labels for review. | `test_ocr_labels_rooms`; label accuracy reported in the synthetic eval | `pois.py` | 🟡 70% label accuracy on synthetic; thin-line styles are weak |
| FR-11 | The system shall validate every floor (schema, geometry and graph rules) and must not package a floor with errors unless `--force` is given, in which case it is marked as forced. | `test_validator_catches_wall_crossing_and_dangling`, `test_invalid_fixtures[*]`, `test_blank_page_is_rejected_not_crashed` | `validate.py`, `api.convert` | ✅ |
| FR-12 | The system shall output `venue.json` (floors embedded, images alongside) by default, and optionally a zipped `.turnmap`, both conforming to the versioned JSON Schema. | `test_valid_json_fixtures`, `test_valid_fixtures`, `test_schema_copy_in_sync`; `turn-mapper validate venue.json` | `export.py`, `contract/` | ✅ |
| FR-13 | The system shall write a QA report (overlay and sample routes per floor) and a run manifest. | `test_qa_report_and_run_manifest` | `report.py`, `api.convert` | ✅ |
| FR-14 | The system shall let the segmentation method be chosen at run time (`--segmenter classical\|learned`) without changing later stages. | `test_train_and_run_learned` (pipeline runs with `--segmenter learned`) | `segment.SEGMENTERS`, `learned/segmenter.py` | ✅ (plumbing). Accuracy is pending GPU training |
| FR-15 | The system shall provide tooling to convert CubiCasa5K into training masks, train or fine-tune a U-Net, and evaluate per-class IoU. | `test_svg_masks_match_drawing`, `test_train_and_run_learned`; `turn-mapper ml --help` | `learned/` | ✅ (offline). Real training is ⏳ |
| FR-16 | The system shall export its own result as starting annotation masks for human correction. | `test_bootstrap_masks` | `learned/annotate.py` | ✅ |
| FR-17 | The system shall reject unusable input (blank page, noise, unsupported file, missing model weights) with a clear message, not a crash. | `test_blank_page_is_rejected_not_crashed`, `test_random_noise_is_rejected`, `test_unsupported_file_gives_clear_cli_error`, `test_missing_learned_weights_gives_clear_cli_error` | `cli.py`, `validate.py` | ✅ |
| FR-18 | The system shall link floors through matching stairs and lifts (multi-floor routing). | (planned) two FAST C floors linked; route GF→F3 exists | `transitions` in the schema are reserved | ⏳ M9 |
| FR-19 | The operator shall be able to correct a floor (rooms, doors, labels) and re-export with `provenance = corrected`. | (planned) edit, then `validate` passes and provenance is updated | schema field exists | ⏳ |

## Non-functional requirements

| ID | Requirement | Measure / acceptance test | Current evidence | Status |
|---|---|---|---|---|
| NFR-01 | Performance: one floor in < 2 min on a laptop CPU (classical). | `test_floor_runtime_under_budget` (< 30 s synthetic); timings in `run_manifest.json` | FAST floors: 3.6–13.2 s each (`runs/fast_v030`) | ✅ |
| NFR-02 | Generality: works on drawing conventions it was not tuned for. | ≥ 10/12 synthetic layout×style cases fully correct (`scripts/style_stress.py`) | 11/12 ([results](../RESULTS_GENERALITY_2026-10-11.md)) | ✅ |
| NFR-03 | Geometric accuracy on ground truth. | synthetic eval: room recall ≥ 0.95, door recall ≥ 0.95, free-space IoU ≥ 0.9, mean \|scale error\| ≤ 15% without evidence | 1.00 / 1.00 / 0.983 / 8.7% | ✅ synthetic; FAST ground truth ⏳ |
| NFR-04 | Safety of routes: an exported route never crosses a wall. | validator `EDGE_CROSSES_WALL` is an error; `test_validator_catches_wall_crossing_and_dangling`; eval wall crossings = 0 | 0 in all 12 synthetic cases | ✅ |
| NFR-05 | Reproducibility: the same input and config give the same map, and every run records code version, input hashes and parameters. | `test_deterministic_output`, `test_qa_report_and_run_manifest` | passes | ✅ |
| NFR-06 | Modularity: the classical pipeline runs without the ML stack, and the learned model is an optional extra behind one interface. | ML tests skip cleanly without torch; `segment._LazyLearned` | CI installs `.[dev]` only | ✅ |
| NFR-07 | Maintainability: lint-clean, ≥ 80% line coverage, CI on every push. | `ruff check .`, `pytest --cov` | 87% coverage | ✅ |
| NFR-08 | Privacy and licensing: no floor plans, datasets or weights in git; dataset licences respected. | `test_no_private_data_in_git` | passes | ✅ |
| NFR-09 | Interoperability: the output contract is versioned (semver), and fixtures validate in Python and in the app importer. | contract tests; `contract/CHANGELOG.md` | 0.1.1; app importer pending (M3) | 🟡 |
| NFR-10 | Human in the loop: every automatic element carries provenance and confidence, and uncertain items are flagged. | `test_every_element_has_provenance`; POI `needs_review` | passes | ✅ |

## Traceability: requirements ↔ modules ↔ tests

| Module | Requirements |
|---|---|
| `ingest.py` | FR-01, FR-17 |
| `config.py` | FR-02 |
| `preprocess.py` | FR-03 |
| `segment.py`, `learned/segmenter.py` | FR-04, FR-14, NFR-02, NFR-06 |
| `vectorize.py` | FR-05, FR-06 |
| `scale.py` | FR-07 |
| `transitions.py` | FR-08 |
| `graph.py` | FR-09, NFR-04 |
| `pois.py` | FR-10, NFR-10 |
| `validate.py` | FR-11, FR-17, NFR-04 |
| `export.py`, `contract/` | FR-12, NFR-09 |
| `report.py`, `api.py` | FR-13, NFR-05 |
| `learned/*` | FR-14–FR-16 |
