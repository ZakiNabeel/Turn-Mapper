# TURN FYP — Authoritative Project Context

> **Purpose:** This file is the authoritative context for fresh ChatGPT/Codex sessions working on TURN. Read it before proposing architecture changes, editing the repository, writing reports, preparing demonstrations, or making claims about implementation status.
>
> **Repository:** `shehryarf67/TURN-Field-Test`
>
> **Project:** TURN — infrastructure-minimised indoor navigation
>
> **Institution / FYP context:** FAST-NUCES Islamabad, Computer Science Final Year Project
>
> **Current prototype focus:** one real university floor, end-to-end, on Android
>
> **Context status:** updated to reflect the current repo direction and the one-floor revamp, including the repository's September 23, 2026 verification state. Physical university-floor positioning accuracy is still not established by source review or automated tests.

---

# 1. Read this first

TURN is **not merely a floor-plan viewer** and it is **not simply a generic indoor map app**.

The project investigates two connected deployment problems:

1. **How can a normal building floor plan be converted into a usable indoor navigation map with less manual work?**
2. **How can a phone be positioned indoors with less dependence on dense dedicated hardware?**

The long-term FYP therefore contains two major technical pipelines:

```text
PIPELINE 1
Floor plan
→ structured geometry
→ walkable space
→ navigation graph
→ route planning

PIPELINE 2
Initial position
→ PDR
→ particle filter
→ map constraints
→ radio/sensor corrections
→ fused live position
```

The current practical prototype deliberately narrows the scope to **one real university floor** so the team can demonstrate the entire workflow end to end:

```text
Create/Open project
→ Import floor plan
→ Calibrate scale
→ Define walkable geometry
→ Create paths/destinations
→ Add survey/reference points
→ Collect real Wi-Fi fingerprints
→ Reopen app and prove persistence
→ Initialize position
→ Start PDR + particle-filter tracking
→ Select destination
→ Generate A* route
→ Show fused blue dot moving on the 2D map
→ Evaluate at independent checkpoints
```

This one-floor prototype is both:

- the first complete vertical slice of the FYP; and
- the prototype intended to be recorded on a real university floor and shown to **Centaurus Mall** as evidence of TURN's deployment capability.

It must remain **building-independent**. Do not hard-code Centaurus-specific content into the product.

---

# 2. Core project vision

## 2.1 Problem

GPS works well outdoors but is unreliable or unavailable inside large buildings.

Indoor navigation systems can instead depend on:

- manually prepared indoor maps;
- venue-specific calibration;
- Wi-Fi fingerprint surveys;
- BLE beacon deployments;
- special positioning infrastructure;
- proprietary venue onboarding.

This creates a deployment trade-off among:

```text
Positioning accuracy
↕
Dedicated hardware
↕
Calibration / site-work effort
```

TURN's research interest is not to pretend these trade-offs disappear. It is to **measure how far deployment effort and dedicated hardware can be reduced while retaining useful indoor navigation**.

## 2.2 Target environments

TURN is intended for large indoor venues such as:

- shopping malls;
- universities;
- hospitals;
- airports;
- office complexes;
- large public/commercial buildings.

## 2.3 Product framing

The likely commercial model is B2B.

A venue would have venue-specific data such as:

- floor plans;
- physical geometry;
- navigation graph;
- shop/room destinations;
- radio fingerprints;
- transition points.

The software platform itself should remain shared and reusable across venues.

A different building requires different **data and calibration**, not a separate software product.

Potential future commercial elements may include:

- onboarding/setup fees;
- recurring subscription;
- white-label deployment;
- tenant/POI management;
- analytics;
- maintenance/recalibration services.

These are product possibilities, not current prototype deliverables.

---

# 3. Research contribution and novelty

TURN must be described conservatively.

## 3.1 What is NOT novel

Do not claim novelty merely because TURN:

- displays indoor maps;
- imports floor plans;
- calculates indoor routes;
- uses Wi-Fi fingerprints;
- uses BLE;
- uses PDR;
- uses a particle filter;
- performs A* routing.

These ideas and commercial systems already exist.

Commercial/reference systems such as Pointr, Mappedin and Apple indoor-map ecosystems demonstrate that indoor mapping/navigation is an established field.

## 3.2 Defensible contribution

The stronger FYP contribution is the investigation of:

### A. Reduced map-preparation effort

Long-term:

```text
floor plan
→ AI-assisted interpretation
→ geometry cleanup
→ human verification
→ navigable map
```

The goal is not necessarily zero manual work.

The correct phrase is:

> **AI-assisted, human-verified indoor-map preparation.**

### B. Infrastructure-minimised indoor positioning

The intended baseline combines:

- existing Wi-Fi infrastructure;
- phone motion sensors;
- PDR;
- map constraints;
- particle filtering;
- optional sparse BLE corrections.

The research question is not "Can we build indoor positioning?" but approximately:

> **How little dedicated infrastructure and calibration are required to achieve usable indoor positioning and navigation?**

### C. Experimental measurement

The FYP should compare trade-offs rather than only present an app.

Useful comparisons include:

```text
PDR only
PDR + map constraints
Wi-Fi only
PDR + map + Wi-Fi
PDR + map + Wi-Fi + sparse BLE (later)
```

Possible BLE experiment:

```text
0 beacons
1–2 strategic beacons
4–6 strategic beacons
dense baseline
```

Measure improvement against:

- hardware count;
- setup effort;
- accuracy;
- failure rate;
- recovery.

---

# 4. System architecture

TURN should be thought of as four connected layers.

## Layer 1 — Map intelligence and navigation representation

Responsible for transforming a floor plan into:

- metric geometry;
- walkable space;
- walls;
- destinations/POIs;
- navigation nodes/edges;
- routeable graph.

## Layer 2 — Positioning

Responsible for estimating:

- x;
- y;
- floor;
- heading;
- uncertainty/confidence.

Uses:

- initialization anchor;
- PDR;
- particles;
- map constraints;
- Wi-Fi correction;
- optional BLE and other sensors.

## Layer 3 — Application/platform

Responsible for:

- project/venue management;
- map editing;
- surveys;
- navigation UI;
- persistence;
- diagnostics;
- export;
- settings.

## Layer 4 — Evaluation/research

Responsible for:

- independent checkpoints;
- method comparison;
- accuracy metrics;
- ablations;
- hardware/calibration trade-offs;
- reproducibility.

---

# 5. Pipeline 1 — Floor plan to navigable map

## 5.1 Long-term Pipeline 1 concept

```text
Floor plan
  ↓
Vector/CAD branch OR raster/image branch
  ↓
Semantic/object extraction
  ↓
OCR labels
  ↓
Geometry cleanup
  ↓
Metric calibration
  ↓
Floor alignment
  ↓
Walkable-space extraction
  ↓
Corridor centreline / path extraction
  ↓
Doors + POIs + vertical transitions
  ↓
Navigation graph
  ↓
Human QA
  ↓
A*
  ↓
Navigable TURN map
```

## 5.2 Preferred floor-plan formats

Best to worst:

1. CAD/DWG/DXF;
2. vector PDF;
3. high-resolution raster PDF;
4. PNG/JPEG;
5. scan/image fallback.

Key design principle:

> Preserve vector geometry when it already exists instead of rasterising everything and asking AI to rediscover it.

## 5.3 Necessary map information

Essential:

- building/floor boundary;
- walls;
- corridors/walkable region;
- entrances/doors;
- stairs/lifts/escalators where applicable;
- floor identifier;
- scale or at least one known physical distance.

Useful:

- room/shop labels;
- unit numbers;
- washrooms;
- exits;
- accessibility metadata;
- restricted areas.

When information is missing, operator input is acceptable.

Example:

```text
Select two known map points
→ enter measured distance = 12.4 m
→ calculate image-to-metre scale
```

## 5.4 Vector/CAD branch

Potential structured data:

- LINE;
- POLYLINE;
- POLYGON;
- TEXT;
- block/INSERT symbols;
- layers.

Possible tools:

- `ezdxf`;
- PDF vector parsing;
- Shapely/geometry processing.

AI should be used only where structured geometry is ambiguous.

## 5.5 Raster/image branch

This is mainly a **computer-vision semantic segmentation** problem.

Possible architectures:

- U-Net;
- DeepLab;
- SegFormer;
- CubiCasa-style parsers.

Example navigation-relevant classes:

- background;
- wall;
- room/shop;
- corridor/walkable;
- door;
- stairs;
- elevator;
- escalator.

The model produces a **pixel-wise semantic mask**.

Example conceptual output:

```text
0 = background
1 = wall
2 = room
3 = corridor
4 = door
...
```

Important distinction:

> The segmentation model provides pixel-level understanding. Classical geometry code converts this into usable polygons/lines.

Pipeline:

```text
semantic mask
→ contours / polygons
→ morphology / gap closing
→ simplification
→ clean metric geometry
```

## 5.6 Training direction

Do not assume a model must be trained from scratch.

A sensible long-term strategy:

```text
pretrained floor-plan parser
→ fine-tune on existing floor-plan dataset
→ fine-tune on TURN commercial/institutional examples
```

A useful starting dataset is CubiCasa5K, with the important caveat that it is heavily residential and therefore has a domain gap relative to malls/universities/hospitals.

Possible provisional training setup:

- image size: ~512–1024 px;
- AdamW;
- learning rate around `1e-4`;
- batch size around 4–8;
- ~30–50 epochs;
- CrossEntropy + Dice loss.

These are starting hyperparameters only, not fixed project claims.

## 5.7 OCR

Possible tools:

- PaddleOCR;
- EasyOCR;
- Tesseract.

Use OCR for labels such as:

- room codes;
- shop names;
- "Food Court";
- "Prayer Room";
- unit numbers.

Associate extracted text with the nearest polygon/space.

## 5.8 Metric calibration

Everything should ultimately use one metric coordinate system.

Example:

```text
Floor 1
origin = (0, 0)
units = metres
```

Objects then have coordinates such as:

```text
Door C-405 = (14.2, 8.5)
Lift A     = (31.0, 9.2)
```

Metric coordinates are required for:

- route length;
- positioning;
- particle motion;
- evaluation;
- radio-reference coordinates.

## 5.9 Walkable-space detection

Conceptually:

```text
building interior
− walls
− shops/rooms
− obstacles/restricted regions
=
walkable area
```

For CAD/vector inputs, derive this from geometry.

For raster inputs, AI may classify walkable pixels, but geometry processing should create the final usable polygon.

## 5.10 Physical geometry versus navigation graph

Important:

> **Geometry describes the environment. The graph describes how a person can move through it.**

Geometry can contain:

- walls;
- corridor polygons;
- rooms;
- doors;
- stairs/lifts;
- POIs.

Graph contains:

- nodes;
- edges;
- weights;
- connectivity.

Example edge:

```json
{
  "from": 31,
  "to": 32,
  "distance": 7.4,
  "floor": 1,
  "accessible": true,
  "type": "corridor"
}
```

For vertical movement:

```json
{
  "from": "lift_F1",
  "to": "lift_F2",
  "type": "elevator"
}
```

Rooms/shops should normally connect through their entrance/door rather than their geometric centre.

## 5.11 A*

TURN uses a navigation graph suitable for A*.

Concept:

```text
f(n) = g(n) + h(n)
```

where:

- `g(n)` = known route cost so far;
- `h(n)` = heuristic estimated remaining cost.

## 5.12 Accessibility wording

Do not claim "accessible route" merely because stairs are removed.

Use:

> **Step-free route according to verified accessibility attributes.**

If accessibility metadata is not verified, do not guarantee accessibility.

---

# 6. Current prototype approach to Pipeline 1

For the current one-floor university prototype, full AI map extraction is intentionally **out of scope**.

The current practical workflow is:

```text
Import PNG/JPEG
→ calibrate metric scale
→ define walkable polygon
→ define walls
→ manually/semi-manually define path nodes and connections
→ assign destinations/POIs
→ save graph
→ A* routing
```

This is acceptable for the current vertical slice.

The purpose of the one-floor prototype is to prove:

- the deployment workflow;
- positioning;
- route generation;
- live navigation;
- persistence;
- evaluation.

It is not necessary to finish the full AI floor-plan pipeline before showing the prototype externally.

---

# 7. Pipeline 2 — Live indoor positioning

## 7.1 Required output

Pipeline 2 estimates:

- `x`;
- `y`;
- floor;
- heading;
- uncertainty/confidence.

## 7.2 Inputs

### Map inputs

- walkable polygon(s);
- walls;
- navigation graph;
- reference points;
- destinations;
- transition topology later.

### Phone/environment inputs

- user-declared known start and/or QR anchor;
- accelerometer;
- step detector/counter;
- gyroscope / rotation vector;
- Wi-Fi RSSI;
- BLE RSSI later;
- magnetometer optionally;
- barometer optionally;
- Wi-Fi RTT optionally where supported.

Core mental model:

> **PDR moves the estimate, the map constrains it, radio evidence corrects it, and the particle filter decides what hypotheses remain plausible.**

---

# 8. Initial absolute position

PDR is relative, so it needs an initial absolute anchor.

Possible anchors:

- known start selected by user;
- known reference point;
- QR anchor;
- confident Wi-Fi fingerprint fix.

Long-term QR payload could encode:

```text
venue
floor
x
y
anchor ID
```

QR is an **anchor/recovery mechanism**, not continuous tracking.

The current one-floor revamp supports known-start / fresh Wi-Fi initialization. Full physical QR-camera initialization remains outside the present slice.

---

# 9. PDR — Pedestrian Dead Reckoning

PDR estimates relative movement from steps and heading.

Concept:

```text
distance d = number_of_steps × stride_length

x' = x + d cos(theta)
y' = y + d sin(theta)
```

Relevant phone signals:

- step detector / step counter;
- accelerometer;
- relative orientation / game rotation vector;
- gyroscope;
- magnetometer only as supplementary evidence.

PDR errors include:

- missed steps;
- double-counted steps;
- stride variability;
- heading drift;
- grip/phone-placement differences.

PDR therefore accumulates drift and must not be the only absolute positioning method.

---

# 10. Particle filter — correct mental model

This is important because it has caused confusion in discussions.

## 10.1 What a particle represents

A particle represents **one possible user state/location**.

Example:

```text
x = 18.2 m
y = 7.6 m
floor = 1
heading bias = ...
stride scale = ...
weight = 0.012
```

A particle does **not** represent Wi-Fi, BLE, PDR, or another technology.

There are not "Wi-Fi particles" and "BLE particles."

## 10.2 How particles are initialized

Particles are typically sampled around a plausible starting location/distribution.

They are not normally scattered randomly across the whole building every update.

If the system becomes lost, a global relocalization operation may distribute hypotheses much more broadly.

## 10.3 How sensors interact with particles

All evidence scores the **same particles**.

For a particle:

```text
How consistent is it with PDR?
Is it in walkable space?
Did it cross a wall?
How consistent is it with Wi-Fi?
How consistent is it with BLE?
Is its floor plausible?
```

Conceptually:

```text
weight_i
∝
P(map evidence | particle_i)
× P(Wi-Fi evidence | particle_i)
× P(BLE evidence | particle_i)
× other available likelihoods
```

PDR is primarily used to **propagate/move** the particle cloud.

Wi-Fi/BLE primarily **reweight/correct** hypotheses.

## 10.4 Resampling

High-weight particles generate more descendants.

Low-weight particles disappear.

This concentrates the distribution around more plausible positions.

## 10.5 Final user position

TURN should not normally choose the single highest-weight particle as "the user."

The displayed blue dot should be derived from the strongest/high-probability particle distribution/cluster.

Possible estimators:

- weighted mean when distribution is unimodal;
- densest/highest-probability cluster where multiple modes exist.

Do not average two widely separated clusters if the mean would fall in a wall/shop.

Particle spread provides uncertainty.

```text
tight cloud     → high confidence
wide cloud      → lower confidence
multiple modes  → ambiguous state
```

---

# 11. Wi-Fi fingerprinting

## 11.1 Survey process

At a known reference point:

```text
known x/y
→ collect multiple genuinely fresh Wi-Fi snapshots
→ store BSSID + RSSI observations
→ aggregate statistics
→ save fingerprint associated with that coordinate
```

Example scan vector:

```text
AP_A  -52 dBm
AP_B  -71 dBm
AP_C  -83 dBm
...
```

Use **BSSID**, not SSID, as the radio identifier.

## 11.2 Matching

Current baseline: weighted k-nearest-neighbour.

Live vector:

```text
visible BSSID/RSSI set
```

is compared against saved fingerprints.

Nearest radio fingerprints provide:

- Wi-Fi position estimate;
- floor vote;
- match distance/confidence;
- likelihood used by the particle filter.

## 11.3 Wi-Fi is correction, not continuous motion

Android application-requested Wi-Fi scanning is throttled.

Therefore:

> Wi-Fi should not be treated as a high-rate continuous tracker.

Correct architecture:

```text
PDR propagates frequently
Wi-Fi periodically corrects
```

## 11.4 Fresh versus cached evidence

This is critical to TURN's research integrity.

TURN should:

- check `startScan()`;
- listen for scan-result broadcasts;
- inspect whether results were updated;
- retain timestamps;
- detect cached/stale results.

A cached result must **not** count as a new independent survey snapshot or correction.

## 11.5 RSSI instability

Wi-Fi RSSI changes because of:

- people/crowds;
- walls/glass;
- multipath;
- interference;
- access-point load;
- orientation;
- hand grip;
- phone model;
- environmental changes.

Mitigations:

- use multiple APs;
- aggregate repeated snapshots;
- median filtering;
- estimate variance;
- downweight unstable APs;
- handle missing signals;
- avoid hard snapping;
- increase measurement uncertainty when evidence is unstable;
- use PDR/map between fresh scans;
- allow relocalization/re-anchor.

Correct defence line:

> **TURN treats Wi-Fi probabilistically as a correction source rather than as standalone continuous tracking.**

---

# 12. BLE and Wi-Fi together

BLE is not required for the current university prototype.

Later, fixed BLE beacons can be registered at known coordinates.

BLE and Wi-Fi should not produce separate particle sets.

Correct fusion concept:

```text
same particle set
    ↓
Wi-Fi scores each particle
BLE scores each particle
map scores each particle
    ↓
combined weight
    ↓
resampling
```

Example:

```text
Particle A
Wi-Fi: strong match
BLE: strong match
Map: valid
→ high weight

Particle B
Wi-Fi: strong
BLE: weak
Map: valid
→ medium

Particle C
Wi-Fi: weak
BLE: weak
Map: invalid
→ near zero
```

BLE's intended role:

- reduce drift;
- disambiguate similar Wi-Fi regions;
- strengthen junction/floor evidence;
- aid recovery.

Potential sparse-hardware research experiment:

```text
0 BLE
1–2 BLE
4–6 BLE
dense baseline
```

Place beacons strategically around:

- entrances;
- ambiguous junctions;
- large open spaces;
- lifts/stairs;
- floor transitions.

---

# 13. Triangulation / trilateration

A supervisor may casually use the word "triangulation."

Technical distinction:

- **Triangulation** uses measured angles.
- **Trilateration** uses measured distances from known points.

TURN's core Wi-Fi RSSI fingerprinting is **not classical triangulation/trilateration**.

It matches a live signal vector to surveyed radio fingerprints.

Possible trilateration scenario:

```text
known AP A → distance
known AP B → distance
known AP C → distance
→ solve location from distance geometry
```

Wi-Fi RTT is more relevant to this because it estimates distance using signal propagation time rather than RSSI magnitude.

Correct presentation wording:

> TURN's core radio method is fingerprint matching rather than geometric triangulation. If compatible Wi-Fi RTT infrastructure exists, RTT ranging and trilateration can be added as another absolute correction source.

---

# 14. Wi-Fi RTT

Wi-Fi RTT / FTM estimates propagation time.

Simplified:

```text
distance ≈ time × c / 2
```

Advantages over RSSI ranging:

- less dependent on received signal amplitude;
- can provide actual range-like observations.

Limitations:

- compatible phone required;
- RTT/FTM-capable access points required;
- AP coordinates generally required;
- multipath and non-line-of-sight still introduce error.

RTT should be treated as an optional enhancement/experiment, not a universal requirement.

---

# 15. Magnetometer and barometer

## Magnetometer

Produces field values such as:

```text
Mx, My, Mz
```

Magnitude:

```text
M = sqrt(Mx² + My² + Mz²)
```

Indoor magnetic disturbances may form location fingerprints.

Limitations:

- device variation;
- orientation sensitivity;
- nearby metal;
- changing environment.

Use only as supplementary/experimental evidence if real data demonstrates value.

Do not assume magnetic north is reliable indoors.

## Barometer

Pressure changes may provide altitude/floor-transition evidence.

Useful for:

- up/down movement;
- validating a floor transition.

It does not give x/y.

Combine with map transition topology and radio evidence.

Current prototype does not claim full barometer-assisted multi-floor tracking.

---

# 16. Device-specific adaptive calibration

Do not say "calibrate the particles."

Calibration adjusts the **motion/sensor error model** that governs particles.

Parameters may include:

- stride scale;
- stride bias;
- heading bias;
- motion noise;
- Wi-Fi RSSI offset/noise;
- sensor confidence.

Example:

```text
Known start A
→ PDR predicts 21.6 m at known point B
→ actual A-B = 20.0 m
→ stride scale ≈ 20 / 21.6 = 0.926
```

Future motion can then apply the corrected scale.

If device behavior is inconsistent, increase particle motion uncertainty.

No heavy ML model is required for this.

---

# 17. Does Pipeline 2 require ML?

No.

The core can remain classical/probabilistic:

- PDR;
- particle filter;
- map matching;
- weighted kNN Wi-Fi;
- BLE likelihood;
- barometer logic;
- magnetic matching;
- QR/known-start anchors;
- adaptive calibration.

ML is optional later for:

- stride estimation;
- learned fingerprinting;
- device normalization;
- learned sensor fusion.

Correct defence wording:

> **Pipeline 1 can use ML for floor-plan understanding. Pipeline 2 primarily uses classical sensor fusion and probabilistic localisation.**

---

# 18. Android platform and APIs

The runtime platform is Android/Kotlin.

Important distinction:

> Android APIs collect measurements. TURN algorithms interpret and fuse them.

Likely/current APIs:

### Motion

- `SensorManager`
- `TYPE_ACCELEROMETER`
- `TYPE_GYROSCOPE`
- `TYPE_ROTATION_VECTOR` / game rotation vector
- `TYPE_STEP_DETECTOR`
- `TYPE_STEP_COUNTER`
- `TYPE_MAGNETIC_FIELD`
- `TYPE_PRESSURE`

### Wi-Fi

- `WifiManager`
- `ScanResult`

Outputs include:

- BSSID;
- RSSI;
- frequency;
- metadata.

### Wi-Fi RTT

- `WifiRttManager`
- ranging requests.

### BLE

- `BluetoothLeScanner`
- scan callback.

### QR

- CameraX;
- ML Kit or ZXing-style barcode decoding.

### Persistence

- Room database;
- DataStore for preferences/settings.

---

# 19. Repository architecture

Repository:

```text
shehryarf67/TURN-Field-Test
```

High-level source layout:

```text
app/src/main/java/com/turn/fieldtest/
  core/       positioning, geometry, PDR, particle filtering, BLE logic
  data/       Room entities, DAOs, database, repositories
  platform/   Android Wi-Fi, sensors, BLE, QR, storage/file adapters
  ui/         Jetpack Compose screens, app state, visualizations
```

The app is offline-first.

Real Device mode must never silently substitute simulated data.

Demo mode must remain clearly labelled.

---

# 20. Current application state — important update

Older project discussions described the app as a research dashboard without a finished navigation-map workflow.

That description is now outdated.

The current one-floor revamp has moved the main physical workflow to:

```text
Projects
→ Map setup
→ Survey
→ Navigate
```

The current repository documentation states that the following are connected for the one-floor prototype:

- persistent project selection;
- PNG/JPEG floor-plan import;
- metric calibration;
- walkable geometry;
- walls;
- persistent navigation graph;
- persistent POIs/destinations;
- manual path editing;
- wall-safe A* routing;
- survey workflow;
- survey target/completion state;
- known-start initialization;
- fresh Wi-Fi initialization;
- PDR;
- particle-filter tracking;
- fused blue dot;
- uncertainty;
- route;
- remaining distance;
- independent evaluation;
- Room persistence;
- JSON/CSV export.

Do **not** revert the context to "navigation graph and 2D live map are still entirely missing."

---

# 21. Current app workflow

## 21.1 Projects

Real Device mode supports creating/opening saved project context.

A project includes venue/floor state.

Project selection persists.

New projects should not overwrite legacy project IDs or data.

## 21.2 Map setup

The current one-floor prototype supports:

### Scale

- import PNG/JPEG;
- imported image copied into private app storage in the current revamp;
- set dimensions or two-point calibration;
- metric coordinate system.

### Layout

- one simple walkable polygon;
- walls;
- openings at doors;
- coordinate protections.

### Paths

Manual graph construction:

- **Node**: place nodes at corridor ends, turns, intersections, destinations;
- **Connect**: connect successive nodes.

Connections:

- bidirectional;
- weighted by metric length;
- rejected if they cross a wall;
- rejected if they leave walkable space.

Important:

> Crossing graph lines are not automatically connected. Place a shared node at the intersection.

### Destinations

Select/inspect a graph node and attach destination name.

Examples:

- Lab 1;
- Lab 2;
- Main Entrance;
- Office;
- Stairs;
- Elevator.

### Points

Place known Wi-Fi survey/reference points.

Map geometry, graph, destinations and points should save together.

## 21.3 Scale lock

Calibrate before:

- adding final path nodes;
- collecting physical measurements.

Once measurements/fingerprints depend on the coordinate system, silently rescaling the floor would invalidate them.

The app therefore protects measured coordinates.

---

# 22. Survey workflow — current intended behavior

At each reference point:

1. stand physically at the marker;
2. select that saved reference point;
3. choose target fresh-snapshot count;
4. press **Begin collection**;
5. keep TURN in foreground;
6. collect genuinely fresh Wi-Fi batches;
7. store raw observations;
8. aggregate;
9. reach target;
10. save/close the completed fingerprint.

The current revamp supports durable survey-completion state.

Important behavior:

- cached Wi-Fi batches do not count as fresh samples;
- readings from before survey start do not count;
- repeated AP timestamps cannot manufacture additional evidence;
- Android throttle/wait state should be visible;
- full raw lineage is preserved.

If **Finish and save** occurs early:

- a partial collection can be preserved;
- incomplete new data should not be treated as a completed live-matching fingerprint;
- previously completed data at that point can remain usable.

After app restart:

- map reloads;
- graph reloads;
- surveys reload;
- completion badges/state reload.

---

# 23. Persistence

This is a critical implementation requirement.

Normal app restart must not delete:

- venue/floor;
- floor-plan configuration;
- metric calibration;
- walkable geometry;
- walls;
- graph nodes;
- graph edges;
- destinations;
- survey/reference points;
- survey sessions;
- raw Wi-Fi observations;
- aggregate fingerprints;
- positioning sessions;
- evaluation records.

The app uses Room for operational data.

DataStore persists settings/project/mode preferences where appropriate.

Current graph/survey revamp uses an explicit additive **Room schema 1 → 2 migration**.

There is no destructive migration fallback for this workflow.

Normal restart preserves data.

These operations can remove local data:

- uninstalling the app;
- clearing app storage;
- explicit delete/reset workflows.

Backup/export caveat:

- JSON/CSV export exists;
- cross-device restore/backup UI is not fully part of the prototype;
- image bytes/URI portability must not be overstated.

---

# 24. Navigate workflow — current intended behavior

## 24.1 Destination

User selects a saved POI/destination.

## 24.2 Start location

Possible prototype initialization:

- choose known start from map;
- choose a known reference point while physically standing there;
- wait for a confident fresh Wi-Fi fix.

Do not claim automatic localization if a known point was manually declared.

## 24.3 Heading alignment

The user enters the direction the phone is facing in the map coordinate system.

Prototype convention:

```text
0°   = right
90°  = up
180° = left
270° = down
```

This aligns relative phone heading with the drawing.

It does **not** infer global compass orientation from the image.

## 24.4 Tracking

Once started:

```text
step / relative heading
→ PDR
→ particle propagation
→ map rejection
→ fresh Wi-Fi correction
→ fused estimate
→ blue dot
```

The blue dot is a particle-filter estimate, not ground truth.

An uncertainty circle should communicate spread/confidence.

## 24.5 Routing

A* attaches the current estimate to the mapped path/graph and routes to destination.

The current prototype documentation uses a wall-safe nearby-path attachment threshold around 3 m.

Route should recalculate from new estimates.

It shows remaining metric distance.

Do **not** move/snap the physical position artificially onto the route for visual smoothness.

If:

- graph disconnected;
- position off usable path;
- tracking lost;

show an explicit unavailable/lost state.

## 24.6 Arrival

Current prototype logic uses conservative arrival gating such as:

- within approximately 1.5 m along route;
- confidence ≥ approximately 0.35;
- uncertainty ≤ approximately 3 m.

These are prototype UI thresholds, **not accuracy guarantees**.

Estimates older than approximately 20 seconds should be treated as last-known/stale and should not generate confident arrival guidance.

---

# 25. Normal navigation UI versus research/debug UI

The product should not expose every research detail to normal users.

## Normal Navigate UI

Prioritize:

- large 2D map;
- route;
- blue dot;
- uncertainty;
- destination;
- remaining distance;
- current floor;
- tracking state.

## Optional debug/research overlays

May include:

- particles;
- raw PDR trail;
- Wi-Fi fixes;
- kNN neighbours;
- rejected particle count;
- sensor values;
- correction events.

Research diagnostics should be accessible, but not overwhelm the main navigation experience.

---

# 26. Visual/UX direction

The original app evolved from a research/field-test instrument and contained dense diagnostic screens.

The revamp should retain technical functionality while presenting a clearer deployment workflow.

Visual goals:

- modern Android / Material;
- professional dark/navy base;
- restrained cyan/blue accents;
- large map surfaces;
- fewer long explanatory paragraphs in primary workflows;
- strong information hierarchy;
- one obvious primary action per screen;
- clear progress states;
- consistent cards/buttons;
- debug details behind optional panels/overlays;
- credible enough for a major mall demonstration.

Desired character:

> **polished engineering prototype**

Not:

> flashy concept mockup with fake capabilities.

Current/legacy theme colors used in TURN have included:

```text
TurnNavy       #071522
TurnNavyRaised #102536
TurnCyan       #4FD8EB
TurnBlue       #4B87FF
TurnMint       #72E0B1
TurnAmber      #FFC568
TurnRed        #FF7C7C
TurnPaper      #F5F8FA
TurnInk        #142432
```

Exact visuals can evolve, but retain visual consistency.

---

# 27. Centaurus objective

Centaurus management previously showed willingness to explore the concept after seeing:

- a working prototype;
- a formal proposal.

This must **not** be described as:

- a signed partnership;
- a client deployment;
- a contract;
- confirmed venue access.

The strongest demonstration is building-independent:

> record TURN making one real university floor navigable and then show that recording to Centaurus.

Ideal external demonstration:

```text
Open TURN
→ create/open university project
→ import floor plan
→ calibrate
→ define walkable geometry
→ build path graph
→ define destination
→ add reference points
→ collect Wi-Fi fingerprints
→ close and reopen app
→ prove data persisted
→ initialize at known start or Wi-Fi
→ choose destination
→ generate A* route
→ physically walk
→ show real blue-dot motion
→ show Wi-Fi corrections
→ arrive / stop
```

This is intentionally a **one-floor prototype**, not the entire final product.

---

# 28. Current scope boundary

For the external one-floor prototype, focus on:

- one venue;
- one floor;
- real imported floor plan;
- metric calibration;
- walkable area;
- walls;
- graph;
- destinations;
- reference points;
- real Wi-Fi fingerprint survey;
- Room persistence;
- PDR;
- particle filter;
- map constraints;
- fresh Wi-Fi correction;
- live blue dot;
- uncertainty;
- A* route;
- independent evaluation;
- clean UI.

Do not block the prototype on:

- full multi-floor navigation;
- complete automatic floor-plan AI;
- iOS;
- cloud backend;
- production auth;
- analytics;
- payment/subscription;
- complete tenant CMS;
- dense BLE infrastructure;
- emergency-routing certification;
- accessibility certification;
- universal Wi-Fi RTT deployment;
- full QR camera workflow.

---

# 29. Current implementation classification

## Implemented and reusable in the current one-floor direction

Treat these as existing foundations unless source inspection proves otherwise:

- Android/Kotlin/Jetpack Compose application;
- Real Device versus Demo distinction;
- saved projects;
- one active physical floor;
- PNG/JPEG floor-plan import;
- metric dimensions;
- two-point calibration;
- walkable polygon editing;
- wall editing;
- saved reference points;
- Room persistence;
- persistent navigation graph;
- persistent destinations/POIs;
- path/node editing;
- wall-safe A*;
- Wi-Fi scanner;
- freshness/staleness handling;
- survey sessions;
- raw BSSID/RSSI observations;
- aggregate fingerprint statistics;
- survey completion metadata;
- weighted kNN;
- PDR;
- relative heading;
- particle filter;
- map constraints;
- Wi-Fi corrections;
- fused blue dot;
- uncertainty;
- known-start/fresh-Wi-Fi initialization;
- route distance/progress;
- independent evaluation records;
- JSON/CSV export;
- algorithm settings;
- deterministic Demo mode;
- core JVM/instrumentation tests.

## Implemented but still needs real-world validation/tuning

- actual phone Wi-Fi cadence;
- RSSI stability;
- step detection;
- relative heading;
- stride model;
- particle motion/noise parameters;
- Wi-Fi matcher parameters;
- live tracking stability;
- real route attachment behavior;
- arrival thresholds;
- uncertainty calibration;
- accuracy.

## Partial / intentionally deferred

- richer multi-floor management;
- full transition topology runtime;
- QR camera initialization/recovery UI;
- backup restore/import;
- multi-phone exchange;
- stabilized display estimate;
- advanced survey curation/AP exclusion;
- complete live raw-scan lineage;
- BLE hardware registration/fusion;
- barometer transitions;
- adaptive device calibration UI.

## Long-term FYP / research work

- AI-assisted map extraction;
- CAD/vector pipeline;
- raster semantic segmentation;
- OCR;
- automatic corridor/centreline extraction;
- commercial-domain training/fine-tuning;
- automatic floor alignment;
- sparse-BLE hardware experiment;
- possible RTT experiment.

---

# 30. Verification status

Source/build verification is not the same as physical accuracy.

The current one-floor prototype documentation records a September 23, 2026 verification with:

- 88 passing JVM tests;
- successful debug build;
- successful Android-test build;
- lint with no errors and existing warnings;
- 7 passing emulator instrumentation tests covering migration/persistence and important one-floor workflows.

These checks support:

- storage behavior;
- routing logic;
- freshness logic;
- state transitions;
- UI/instrumentation flows.

They do **not** establish:

- real Wi-Fi quality;
- physical PDR accuracy;
- real heading alignment;
- physical positioning error;
- mall-scale performance.

Correct language:

> **Build/tests verify code behavior. Physical-phone field trials establish positioning performance.**

---

# 31. Field-test protocol

## 31.1 Start small

Before expanding:

- one corridor/wing;
- approximately 15–25 reference points;
- at least 10 independent checkpoints.

Do not expand until end-to-end pipeline works.

## 31.2 Freeze pilot conditions

Record:

- floor;
- area;
- phone model(s);
- Android version(s);
- app build;
- Wi-Fi scan-throttling state;
- date/time;
- crowd condition;
- reference-point spacing.

## 31.3 Map measurement

- choose stable origin;
- measure important corridor lengths;
- record measuring tool;
- calibrate image;
- validate scale against more than one physical measurement if possible;
- correct obvious map errors before radio collection.

## 31.4 Reference points versus checkpoints

Reference points:

> training/fingerprint locations.

Checkpoints:

> independent ground truth used only for evaluation.

Never use evaluation checkpoint truth to update the fingerprint database.

Do not place checkpoint at same coordinate as a reference point.

## 31.5 Hardware check

Before data collection:

- verify fresh Wi-Fi timestamps;
- verify visible BSSID count;
- verify step source;
- verify relative heading;
- walk known 10–20 m segment;
- rotate approximately 90°;
- record missing sensors/fallbacks.

Do not continue if all radio results are cached.

## 31.6 PDR calibration

A controlled stride-calibration approach may use a known straight path.

Do not tune stride or heading using evaluation checkpoint truth.

Retain raw/un-calibrated baseline where comparing methods.

## 31.7 Wi-Fi surveys

At each reference point:

- select exact point ID;
- stand on marker;
- record phone orientation;
- collect bounded fresh-scan window;
- keep cached scans in lineage but not as independent samples;
- record crowd/obstruction notes;
- save session.

Where feasible:

- repeat different orientations;
- repeat later time;
- use at least two Android devices for generality.

Do not merge device evidence invisibly.

## 31.8 Freeze radio map before evaluation

Inspect:

- BSSID detection rate;
- RSSI standard deviation;
- unstable/mobile APs;
- low-detection APs;
- exclusions and reasons.

Export/checksum training set before final evaluation.

## 31.9 Live runs

For each run:

1. start new positioning session;
2. initialize with predefined method;
3. align heading;
4. walk naturally;
5. do not manually help estimator except predefined recovery rules;
6. capture independent checkpoint samples;
7. store Wi-Fi-only, PDR-only and fused estimates together;
8. retain failures/reanchors.

---

# 32. Evaluation metrics

Report more than mean error.

Core metrics:

- attempted samples;
- successful estimates;
- mean horizontal error;
- median horizontal error;
- P90 error;
- maximum error;
- percentage within 3 m;
- percentage within 5 m;
- floor correctness;
- failure/no-estimate rate;
- confidence coverage;
- error versus time since fresh Wi-Fi;
- drift versus time/distance;
- wall violations;
- relocalization count;
- recovery time;
- per-device results;
- per-floor results later.

Training and evaluation must be separated.

Suggested ablations:

```text
Wi-Fi only
PDR only
PDR + map
PDR + map + Wi-Fi particle filter
```

Later:

```text
+ sparse BLE
+ device normalization
+ optional RTT
```

---

# 33. Provisional success targets

Earlier project planning discussed provisional targets such as:

- median positioning error ≤ 5 m;
- P90 ≤ 10 m;
- correct floor ≥ 95%;
- route success ≥ 90%;
- mapping-effort reduction ≥ 60%;
- BLE count minimized while meeting accuracy target.

These are **provisional planning targets only**.

Do not state them as achieved.

Final thresholds should be justified by experiment requirements and FYP rubric.

---

# 34. Lost-state and recovery behavior

TURN must not manufacture confidence.

The estimator should admit uncertainty when:

- no fresh radio evidence;
- particle spread is excessive;
- Wi-Fi neighbours strongly disagree;
- live radio vector appears out-of-distribution;
- map constraints kill the particle cloud;
- required sensor unavailable;
- floor transition cannot be explained.

Possible recovery:

- explicit relocalization;
- known reference point;
- QR anchor later;
- fresh strong Wi-Fi evidence;
- manual confirmation when appropriate.

Correct principle:

> **Graceful abstention is better than a confidently wrong blue dot.**

---

# 35. Multi-floor direction

Long-term multi-floor support should combine:

- persistent floors;
- shared vertical transition nodes;
- stairs;
- lifts;
- escalators;
- floor-aware graph;
- radio floor likelihood;
- topology;
- optional barometer;
- QR/known anchors.

Current prototype is one active floor.

Do not claim complete physical multi-floor tracking today.

---

# 36. Security/privacy/research integrity

TURN is offline-first for the prototype.

Important principles:

- no participant identity required;
- anonymous session IDs;
- raw research lineage retained;
- floor plans/radio identifiers can be sensitive;
- explicit export;
- Real Device mode never silently uses simulated data;
- test checkpoints never become training fingerprints;
- failures should be stored/reported rather than removed.

---

# 37. Team context

Known FYP division discussed:

- **Zaki Nabeel:** map intelligence / computer vision;
- **M Sameer:** positioning / fusion;
- **Shehryar Faisal:** platform / evaluation.

Lead assignments may evolve.

The technical architecture should remain understandable across the team rather than becoming isolated into three incompatible mini-projects.

---

# 38. Presentation / defence framing

Strong project line:

> **TURN investigates how little manual setup and dedicated hardware are needed for deployable indoor navigation.**

Another useful line:

> **Pipeline 1 builds the navigable world. Pipeline 2 tracks the person inside it.**

Pipeline summary:

> **AI understands the floor plan; geometry structures it; graph algorithms make it navigable.**

Positioning summary:

> **PDR moves the estimate, the map constrains it, radio evidence corrects it, and the particle filter decides what to believe.**

Particle explanation:

> **Particles are possible user locations. Sensors are judges that score those locations.**

Wi-Fi/BLE explanation:

> **Wi-Fi and BLE score the same position hypotheses; they do not create separate sensor-specific particles.**

Triangulation explanation:

> **TURN's core radio method is fingerprinting, not classical triangulation. RTT-based distance ranging could support trilateration where compatible infrastructure exists.**

Novelty explanation:

> **We are not inventing indoor navigation. We are investigating the deployment trade-off between accuracy, calibration effort and dedicated hardware.**

Defence attitude:

> **Ambitious architecture, conservative claims.**

---

# 39. Claims to avoid

Do not say:

- "TURN is the first indoor navigation system."
- "TURN requires zero hardware."
- "TURN needs no site survey."
- "TURN is fully automatic."
- "TURN has proven sub-metre accuracy."
- "TURN has proven 5 m accuracy." unless experiment actually shows it.
- "Centaurus is our client."
- "Centaurus has partnered with us."
- "The app works on iOS." unless implemented.
- "Multi-floor tracking is complete." unless physically validated.
- "BLE is already validated." if no beacon experiment has been run.
- "Wi-Fi RTT works in any mall." because AP/phone compatibility is required.
- "Step-free route is guaranteed accessible." without verified accessibility data.
- "The blue dot is ground truth."
- "Automated tests prove physical positioning accuracy."
- "Generated UI mockups are actual app screenshots."

Prefer:

- "prototype";
- "implemented";
- "source-verified";
- "physically validated" only when actually tested;
- "planned";
- "optional";
- "AI-assisted";
- "infrastructure-minimised";
- "step-free according to verified attributes."

---

# 40. Current prototype priorities

Priority order:

```text
1. Stabilize one-floor project/map workflow
2. Collect real Wi-Fi fingerprints
3. Verify persistence after restart
4. Validate weighted-kNN baseline
5. Validate PDR on a measured walk
6. Validate particle-filter fusion
7. Validate live blue-dot behavior
8. Validate A* route and route progress
9. Capture independent checkpoints
10. Tune parameters using training/calibration data only
11. Record polished university-floor demonstration
12. Prepare Centaurus-facing video/proposal
13. Expand research experiments
14. Add BLE only after baseline is stable
15. Continue long-term AI map pipeline
```

Do not let secondary features delay the first genuine end-to-end physical run.

---

# 41. One-month working philosophy

The project should prioritize one complete chain:

```text
real floor
→ real map
→ real reference points
→ real fingerprints
→ real tracking
→ real route
→ real checkpoint evaluation
```

This is more valuable than ten partially implemented advanced features.

The one-floor prototype is not separate from the FYP.

It is:

> **the first polished, experimentally usable vertical slice of the FYP.**

---

# 42. Coding guidance for Codex / future agents

## 42.1 Inspect before editing

Before code changes:

1. inspect repository;
2. inspect latest README/current prototype guide;
3. inspect Room schema/migrations;
4. inspect project/map repositories;
5. inspect survey runtime;
6. inspect Wi-Fi freshness logic;
7. inspect PDR/particle filter;
8. inspect navigation graph;
9. inspect Navigate UI;
10. inspect tests.

Do not assume old chat context is current.

## 42.2 Preserve working systems

Do not replace working backend functionality merely because UI needs improvement.

Preserve:

- Room data;
- additive migrations;
- project identity;
- Wi-Fi freshness semantics;
- raw lineage;
- Real/Demo separation;
- PDR;
- particle filter;
- graph;
- A*;
- evaluation;
- exports;
- offline behavior.

## 42.3 Incremental changes

Keep project compiling after each meaningful phase.

Avoid a full rewrite unless an inspected technical blocker proves necessary.

## 42.4 No fake success

In Real Device mode:

- no simulated APs;
- no fake steps;
- no fake position;
- no fake route progress;
- no fabricated "successful" survey.

If hardware/data unavailable, show:

- unavailable;
- stale;
- waiting;
- uncertain;
- lost.

## 42.5 Persistence safety

Any schema change requires:

- explicit Room migration;
- migration tests;
- no destructive fallback;
- compatibility with existing stored pilot data where feasible.

## 42.6 Coordinate integrity

Do not silently change the coordinate system after:

- fingerprints;
- checkpoints;
- graph;
- positioning sessions

depend on it.

## 42.7 Research/debug separation

Keep normal user flow clean.

Move diagnostics behind:

- Tools;
- Settings;
- Research details;
- Debug overlays.

---

# 43. Suggested screen architecture

Current physical prototype should conceptually revolve around:

## Projects

- create/open venue/floor;
- saved status;
- project selection.

## Map setup

Tabs/subsections:

- Scale;
- Layout;
- Paths;
- Points.

Map is the primary visual surface.

## Survey

- select point;
- survey completion badges;
- target fresh snapshots;
- Begin Collection;
- live progress;
- AP count;
- saved/partial/completed status;
- access to detailed radio diagnostics.

## Navigate

- large 2D map;
- start initialization;
- destination picker;
- route;
- blue dot;
- uncertainty;
- remaining distance;
- tracking state;
- optional debug overlays.

## Tools & settings

- Radio diagnostics;
- Evaluate;
- Export;
- Algorithm settings;
- debug/research views.

---

# 44. Demonstration script at product level

The external product story should be understandable without explaining all algorithms first.

Example:

1. "TURN takes a normal floor plan."
2. "We calibrate it into real-world metres."
3. "We define where people can walk."
4. "We turn that into a routeable graph."
5. "We mark survey points and collect the existing Wi-Fi environment."
6. "TURN stores those fingerprints locally."
7. "During navigation, phone sensors move the estimate between radio updates."
8. "The map prevents impossible motion."
9. "Wi-Fi periodically corrects accumulated drift."
10. "The particle filter fuses this into a blue-dot estimate."
11. "A* calculates the route to the selected destination."
12. "We measure the actual error at independent checkpoints."

This communicates both product value and technical credibility.

---

# 45. Long-term Pipeline 1 research roadmap

After the one-floor prototype is stable:

## Stage 1

Manual/semi-manual map setup and route graph.

## Stage 2

Raster segmentation:

- walls;
- rooms;
- walkable corridors;
- doors.

## Stage 3

Object detection:

- stairs;
- lifts;
- escalators.

## Stage 4

OCR labels.

## Stage 5

Automatic geometry cleanup and centreline extraction.

## Stage 6

Vector/CAD direct parsing.

## Stage 7

Multi-floor alignment.

## Stage 8

Human QA interface.

Evaluate:

- time saved;
- geometry correctness;
- topology correctness;
- manual corrections;
- route success.

---

# 46. Long-term Pipeline 2 research roadmap

## Stage 1

Known start + PDR + map constraint + particle filter.

## Stage 2

Real Wi-Fi fingerprint correction.

Compare:

```text
PDR
PDR + map
PDR + map + Wi-Fi
```

## Stage 3

Device normalization / calibration.

## Stage 4

Sparse BLE experiment.

## Stage 5

Optional magnetic/barometer evidence.

## Stage 6

Optional RTT where compatible infrastructure exists.

## Stage 7

Multi-floor fusion.

---

# 47. Failure modes to actively test

## Map

- incorrect scale;
- wall gaps;
- path crossing without graph node;
- disconnected graph;
- route crossing wall;
- reference point outside walkable area;
- rescaling after survey.

## Wi-Fi

- permission denial;
- location service off;
- throttle delay;
- cached scan;
- AP disappears;
- very sparse AP vector;
- device RSSI offset;
- symmetric/ambiguous fingerprints.

## PDR

- missed steps;
- double steps;
- wrong initial heading;
- phone tilt;
- turning;
- different stride;
- step sensor unavailable.

## Fusion

- particle collapse;
- particle cloud outside walkable area;
- wrong Wi-Fi correction;
- conflicting evidence;
- lost state;
- global relocalization.

## Persistence

- kill/reopen app;
- restart phone;
- project switching;
- migration;
- interrupted survey;
- interrupted navigation.

## Routing

- user off graph;
- disconnected destination;
- wall-safe connector unavailable;
- route changes after corrected position;
- stale last-known position.

---

# 48. Terminology reference

## Reference point

Known physical location used to collect training fingerprints.

## Checkpoint

Independent known location used for evaluation only.

## Fingerprint

Aggregated radio signature tied to known coordinates.

## PDR

Pedestrian Dead Reckoning; relative movement estimate from steps/heading.

## Particle

One possible user-state hypothesis.

## Particle filter

Probabilistic estimator that propagates, weights and resamples position hypotheses.

## Map constraint

Rule eliminating physically impossible motion, e.g. crossing a wall.

## Fused position

Final estimate combining motion, map and correction evidence.

## Wi-Fi fix

Absolute-ish radio position estimate from fingerprint matching.

## BLE beacon

Fixed radio transmitter at known location; optional correction source.

## Triangulation

Positioning using angles.

## Trilateration

Positioning using distances.

## Wi-Fi RTT

Time-based distance ranging to compatible access points.

## Navigation graph

Nodes and edges representing legal movement paths.

## A*

Shortest-path search using travelled cost plus heuristic.

## Uncertainty radius

Visual/statistical indication of location uncertainty; not guaranteed error bound unless specifically calibrated.

---

# 49. Current truth table for external claims

| Claim | Status |
|---|---|
| Android prototype exists | Yes |
| Offline-first architecture | Yes |
| Floor-plan import | Yes |
| Metric calibration | Yes |
| Walkable/wall editing | Yes |
| Persistent reference points | Yes |
| Persistent navigation graph | Yes in current one-floor revamp |
| Destinations/POIs | Yes in current one-floor revamp |
| A* routing | Yes in current one-floor revamp |
| Wi-Fi scanner | Yes |
| Fresh/stale scan handling | Yes |
| Wi-Fi fingerprint survey | Implemented; physical field validation still required |
| Survey persistence | Yes by current design/tests |
| Weighted kNN | Yes |
| PDR | Yes |
| Particle filter | Yes |
| Map-constrained fusion | Yes |
| Known-start initialization | Yes in current prototype |
| Fresh-Wi-Fi initialization | Yes in current prototype |
| Live blue dot | Yes in current one-floor Navigate direction |
| Uncertainty display | Yes |
| Route/remaining distance | Yes in current one-floor prototype |
| BLE architecture | Present but disabled/not physically validated |
| Wi-Fi RTT | Optional concept, not core implementation claim |
| Full QR camera workflow | Not part of current slice |
| Multi-floor physical runtime | Not complete |
| AI automatic map extraction | Long-term FYP pipeline, not current one-floor implementation |
| Physical positioning accuracy | Not yet established by repository tests |
| Centaurus deployment | No |
| Centaurus interest in prototype/proposal | Yes, exploratory interest only |

---

# 50. If a fresh agent is asked to revamp TURN

The correct instruction is:

> **Revamp the existing repository. Do not create a new app from scratch.**

Reason:

The current project already contains substantial working infrastructure.

The UI/UX may be redesigned, but backend work should be reused.

Treat this as:

> **TURN prototype UX/product revamp of the existing codebase**

not:

> a greenfield second implementation.

First response from a coding agent should be an audit:

```text
IMPLEMENTED AND REUSABLE
IMPLEMENTED BUT NEEDS REFACTORING
UI/UX NEEDS REPLACEMENT
PARTIALLY IMPLEMENTED
MISSING
PHYSICAL VALIDATION REQUIRED
```

Only then should changes begin.

---

# 51. Final north-star statement

TURN should ultimately demonstrate this:

> **A venue can provide a floor plan; TURN can convert or prepare it into a navigable map, learn enough of the existing indoor radio environment with limited calibration, use phone motion plus probabilistic fusion to maintain a live indoor position, and route the visitor through the building while exposing uncertainty and minimizing dedicated infrastructure.**

For the present prototype, prove that idea honestly on **one real university floor** first.

The strongest near-term milestone is not another feature.

It is:

```text
one real floor
+
one persisted navigable map
+
real fingerprints
+
real PDR
+
real particle-filter fusion
+
real blue dot
+
real route
+
independent measured checkpoints
+
a clean recorded demonstration
```

That is the foundation for the remaining FYP research and for the Centaurus pitch.

---

# 52. Context maintenance rule

This file should be updated whenever any of the following materially changes:

- repository architecture;
- Room schema;
- main app workflow;
- physical validation status;
- map pipeline implementation;
- positioning algorithm;
- BLE/RTT status;
- multi-floor status;
- Centaurus relationship;
- achieved evaluation results;
- agreed FYP scope;
- team responsibility split.

When repository source conflicts with this file on implementation status, inspect the latest source and current project documentation before making claims.

When a prior chat conflicts with this file, this file should take precedence unless the user explicitly provides a newer decision.
