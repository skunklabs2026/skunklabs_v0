# Sensor lab - video / computer-vision pipeline

> **Status.** This was the original MVP's README. The product is now the
> operator interface described in the [main README](../README.md); this
> pipeline is kept as an optional, future track source. It is off by default -
> start the backend with `SKUNK_VIDEO_PIPELINE_ENABLED=true` and open
> **`/sensor-lab`**. Where this document says the app "opens on Canister
> Setup", read `/sensor-lab`.

Local detection, tracking and operator engagement demo.

One screen shows a sensor feed and walks a canister through the operational
sequence:

```
SEARCH → DETECT → TRACK → CONFIRM → FOLLOW → AUTHORIZE → ACTUATE
```

Everything runs locally and offline. There is no cloud dependency, no LLM, and
no database.

> **Scope and safety.** Actuation in V0 is a simulated, benign event: a log
> entry, an API event and a UI launch cue. Nothing physical is triggered. The
> confirmation rules are **demo logic**, not a threat-identification
> capability. Engagement authorization is always manual - the system will
> never actuate on its own. See [What V0 is not](#what-v0-is-not).

---

## How it runs

The app opens on **Canister Setup**, not on a live feed:

1. **Sensor feed** - drag a video in, pick one from the local library, or
   attach the live camera. Perception settings (detector, confidence
   threshold) sit behind **Advanced**, because which detector is running is
   how the canister sees, not what it does.
2. **Confirm canister ready** - the canister's own subsystem report, a
   preview, and the detector's counters. This is how you tell whether the
   system works on *your* clip before starting.

**Begin mission** opens the operator console. **Setup** in the top bar returns
at any time.

The console is built around one entity - CANISTER 01 - and one permanent
sequence:

```
SEARCH ✓   DETECT ✓   TRACK ✓   CONFIRM ✓   FOLLOW ●   AUTHORIZE ○   LAUNCH ○
```

Two views: **SENSOR** (the camera and its overlays) and **TACTICAL** (the
canister, its detection sector, and the tracks it holds - in relative
sensor-frame coordinates, labelled as such).

---

## Quick start

```bash
make setup && make demo
```

`make setup` creates the virtualenv and installs both halves; `make demo`
starts the backend and the operator UI, waits for both to be healthy,
generates the demo clip on first run, and opens the screen.

`make help` lists every entry point. The ones you will actually use:

| Command | What it does |
| --- | --- |
| `make demo` | backend + UI together (same as `./run_demo.sh`) |
| `make test` | the pytest suite |
| `make check` | lint + typecheck + tests - **run before opening a PR** |
| `make format` | auto-fix Python and TypeScript formatting |
| `make verify` | drive the pipeline headlessly through the full sequence |
| `make build` | production frontend build, served by the backend at :8000 |

If you would rather not use `make`, every target is one or two plain commands -
open the `Makefile` and copy the line.

---

## Working on this with a team

- **One formatter per language, no debates.** `ruff` for Python, `eslint` +
  `prettier` for TypeScript, all configured in-repo. `make format` fixes;
  `make check` is what CI should run.
- **Types cross the boundary.** `frontend/src/types.ts` is generated from
  `backend/schemas.py` - after changing a schema, run
  `.venv/bin/python scripts/gen_types.py`. Never hand-edit it.
- **The UI never calls `fetch` directly.** Everything goes through
  `frontend/src/api/`, so a renamed route breaks one file rather than
  failing silently at demo time.
- **Each module has one job.** The pipeline and the API are both split by
  role (see [Architecture](#architecture)); a change should touch one file.

---

## Running the pieces separately

**Backend** (http://127.0.0.1:8000):

```bash
.venv/bin/python -m backend.main
```

**Frontend** (http://localhost:5173):

```bash
cd frontend && npm run dev
```

The Vite dev server proxies `/api` and `/ws` to the backend, so the browser
only ever talks to one origin. If port 5173 is taken, Vite picks the next free
port and prints it - use the URL it prints.

---

## Run the demo

1. Start with `./run_demo.sh` and wait for the operator screen.
2. The banner reads **SEARCHING**. No target is selected.
3. The drone enters the frame. A box appears and the banner reads
   **TARGET DETECTED**.
4. A persistent ID (`UAV-001`) is assigned; the banner reads **TRACKING** and
   the progress bar fills as the demo criteria are evaluated.
5. After `CONFIRMATION_TIME`, the banner reads **THREAT CONFIRMED**.
6. It moves to **TARGET LOCKED / FOLLOWING**, with a trajectory tail showing
   the system following the same target.
7. After `FOLLOW_TIME`, the banner reads **AUTHORIZATION REQUIRED** and the
   **AUTHORIZE** button arms.
8. Press **AUTHORIZE** (or the space bar). The banner reads
   **ENGAGEMENT AUTHORIZED**.
9. The simulated actuator fires, a launch cue plays, and the banner reads
   **INTERCEPTOR LAUNCH SIMULATED**.
10. The mission auto-resets after `ACTUATED_HOLD` seconds. **Reset Mission**
    resets it immediately.

The clip loops, so the sequence repeats indefinitely without touching
anything.

---

## Load your own video

**From the operator screen (no restart needed).** Open the **Input** panel in
the right-hand column. You can:

- **Upload video** - pick any clip from your machine. It is copied to
  `assets/videos/uploads/`, validated as decodable, and loaded immediately.
  A progress bar shows large uploads.
- **Pick from the library** - every clip in `assets/videos/` is listed with
  its resolution, duration and size. Click one to load it.
- **Switch detector** - `motion` / `yolo`, on the same footage, so you can
  compare them directly.
- **Use camera** - switch to the webcam.

Changing any of these resets the perception state and restarts the mission
cleanly. The backend keeps running throughout.

**From the command line:**

```bash
curl -X POST http://127.0.0.1:8000/api/source/video \
  -H 'Content-Type: application/json' \
  -d '{"path":"/Users/you/Movies/drone.mp4"}'
```

Any absolute path on the machine is accepted - footage does not need to be
copied into the repo. The path is checked to exist, be a regular file, have a
video extension, and actually decode before it is made active.

**At startup:**

```bash
SKUNK_VIDEO_PATH=/path/to/your/drone.mp4 ./run_demo.sh
SKUNK_VIDEO_SOURCE=camera SKUNK_CAMERA_INDEX=0 ./run_demo.sh
```

**Regenerate the bundled synthetic clip:**

```bash
.venv/bin/python scripts/make_demo_video.py
```

Video ingestion sits behind `VideoSource` (`backend/video/source.py`), with
`FileVideoSource` and `CameraVideoSource` implementations. Adding an external
sensor means adding one class.

### A note on arbitrary footage

The `motion` detector assumes a *roughly static camera* - it models the
background and reports what moves against it. On handheld or panning footage
it will flag large parts of the frame. **Use `yolo` for real-world video**;
use `motion` for tripod/fixed-camera footage and the bundled clip.

Targets are designated from their detected class, so on general footage you
will see `PERSON-001`, `CAR-002` and so on - not everything labelled as a
UAV. Only tracks classified `uav` can satisfy the confirmation rules, so a
person is tracked and displayed but never confirmed as a demo threat.

---

## Configure the detector

Two detectors ship, both behind the `Detector` interface
(`backend/vision/detector.py`). The mission logic never sees which is running.

### `motion` (default)

OpenCV MOG2 background subtraction. No model weights, no download, no torch.
An airborne object against sky is close to its ideal case, which is why it is
the default - V0 prioritises repeatability over sophistication.

```bash
SKUNK_DETECTOR=motion ./run_demo.sh
```

### `yolo`

Ultralytics YOLO26n, per the reference document. Requires a one-time ~2 GB
install; inference itself is fully local and offline.

```bash
.venv/bin/pip install -r requirements-yolo.txt
SKUNK_DETECTOR=yolo ./run_demo.sh
```

Notes:

- On Apple Silicon the device resolves to `mps` automatically; set
  `SKUNK_DEVICE=cpu` for the portable fallback.
- COCO-pretrained models **have no `drone` class**. Detections labelled
  `airplane`, `bird`, `kite` or `frisbee` are relabelled `uav` (configurable
  via `uav_class_names`). Fine-tuning on real demo footage is the correct
  long-term fix and is deliberately out of V0 scope.
- If the model fails to load, the backend logs a warning and **falls back to
  the motion detector** rather than starting with a dead pipeline.

To export to CoreML later, keep the same `Detector` interface and add a
`CoreMLDetector`; nothing else changes.

---

## Airframe classification - FPV multirotor vs fixed-wing

The two platforms behave nothing alike, and treating them the same makes both
the predicted path and the assessed speed wrong:

| | **FPV / multirotor** | **Fixed-wing** (Shahed-type) |
|---|---|---|
| Can hover / stop | yes | no |
| Speed | low, highly variable | high, near-constant |
| Path | sharp turns, reversals | smooth, low curvature |
| Prediction horizon | **0.6×** (1.2 s) | **1.6×** (3.2 s) |
| Assumed size | 0.35 m | 2.5 m |

`backend/mission/classification.py` decides between them from four
deterministic kinematic features over a rolling ~3.6 s window - path
straightness, speed steadiness, turn rate, and hover fraction. Each votes; a
decision needs both a clear margin and eight consecutive agreeing frames, so
the answer cannot flicker mid-engagement.

Two things depend on the result:

**Prediction horizon.** A fixed-wing holds its course, so a straight
extrapolation is trustworthy further out. A quad can turn on the spot, so the
horizon shortens and confidence drops - extrapolating a quad as far as a
cruise missile would draw a confident line to nowhere.

**Assessed speed.** See below.

Two demo clips exercise both paths:

```bash
.venv/bin/python scripts/make_demo_video.py --platform fixed_wing --output assets/videos/demo_fixed_wing.mp4
.venv/bin/python scripts/make_demo_video.py --platform multirotor --output assets/videos/demo_multirotor.mp4
```

Measured over the full clips: the fixed-wing clip classifies FIXED_WING 95% of
frames, the multirotor clip MULTIROTOR 90%. Both are asserted in the tests.

> Classification is from *observed motion only*. It does not identify a model
> of aircraft, and it is not a threat-identification capability.

---

## Assessed speed

A single uncalibrated camera cannot measure speed - it measures angular rate.
Angular rate becomes a speed only once you know the range, and range follows
from apparent size *if you assume the real size*. That assumption is what the
classification supplies:

```
an FPV quad  (~0.35 m) subtending 20 px is close  and slow
a fixed-wing (~2.5 m)  subtending 20 px is far    and fast
```

Same pixels, ~7× the range, ~7× the speed. Get the airframe wrong and the
speed is wrong by that factor.

Absolute speed is reported **only** when the sensor field of view is set:

```bash
SKUNK_CAMERA_HFOV_DEG=65 ./run_demo.sh
```

Without it the panel shows `NOT CALIBRATED` rather than an invented number.
The image-plane rate (frame widths/second) is always shown, because that *is*
a direct measurement. Estimates falling outside the class's typical envelope
are flagged rather than silently reported.

> Cross-range only - motion toward or away from the camera is invisible to a
> single camera, so the figure is a lower bound.

---

## Performance

Measured on this machine (Apple Silicon, MPS), 960 px frames:

| Detector | Per inference | Effective fps at stride 1 / 2 |
|---|---|---|
| `motion` | 3.1 ms | 319 / 632 |
| `yolo` (YOLO26n) | 15.4 ms | 65 / 151 |

Detection is not the bottleneck at a 25 fps demo rate - 15 ms of a 40 ms
budget. Three controls exist for when it is:

- `SKUNK_DETECTION_STRIDE` - detect every Nth frame; the tracker coasts on its
  velocity estimate in between, so the target still moves smoothly on screen.
- `SKUNK_INFERENCE_WIDTH` - downscale for inference only; display keeps full
  resolution.
- `SKUNK_TARGET_FPS` - raise the playback/processing rate.

**Tracking a fast target** was the real problem, and it was not throughput.
A small target crossing quickly moves further than its own width between
frames, so consecutive boxes have IoU of exactly zero, association fails, and
the track ID breaks every few frames - on precisely the target that matters
most. `ByteTracker` therefore has a third association stage: a proximity gate
on centre distance, scaled by target size and the track's own speed
(`SKUNK_TRACK_GATE_SCALE`), with a size-ratio check so an unrelated object
cannot capture the track. Both the failure and the fix are covered by tests.

---

## Trajectory prediction and intercept estimate

Once a target is tracked, the backend continuously:

1. **Fits its recent image-plane motion** and extrapolates ~2 s forward
   (`backend/mission/trajectory.py`). Quadratic least-squares over a rolling
   window; the fit residual becomes a confidence score, so a jittery track
   reports low confidence instead of drawing a confident wrong line. Shown as
   a dashed path ahead of the target.
2. **Estimates an intercept point** - the earliest point on that path a
   notional interceptor could reach in time from the canister position. Shown
   as an amber ring, with time-to-intercept in the side panel.
3. **On authorization, flies a simulated interceptor** from the launch point
   to the point committed *at the moment of launch*
   (`backend/actuation/interceptor.py`). You see it climb, arrive, and go
   `SPENT`, with a countdown.

The aim point is deliberately **frozen at launch** and never updated
mid-flight. Re-aiming would be a (crude) guidance behaviour, and V0 must not
imply one - what is shown is a committed, ballistic shot. If the target
manoeuvres afterwards, the interceptor visibly misses. That is honest, and
it is the point: it shows what the prediction was worth.

> **Scope.** All of this is a kinematic extrapolation of *pixel* motion in
> normalised image coordinates. There is no range, altitude, camera
> calibration or 3D. It is not a flight model, not a guidance law and not a
> firing solution. Nothing acts on it - the mission state machine does not
> consume the intercept result, and the "interceptor" is a marker moving
> along a line. Both are for operator display.

Tunable via `SKUNK_TRAJECTORY_HORIZON`, `SKUNK_INTERCEPTOR_SPEED`,
`SKUNK_LAUNCH_POINT_X/Y` and `SKUNK_INTERCEPT_MIN_CONFIDENCE`.

---

## Mission recording

Every run is a test. Each one writes a JSON report:

```
runs/mission_2026_09_09_001.json
```

It captures the mission id, source and detector, the full state-transition
sequence, the structured event log, which target was primary, how many tracks
were created and lost, perception timings, the readiness state *at the moment
the operator authorized*, the launch command, and the launcher's
acknowledgement with its latency. Timings appear both absolute (to correlate
with a launcher log) and relative to the run's start (to compare between runs).

A run opens on start, and on every reset or source change - two clips never
share one report. Set `SKUNK_RECORD_RUNS=false` to disable, or
`SKUNK_RUNS_DIR` to write elsewhere. No database: a run is a few hundred
events and the consumer is a person or a short script.

```bash
jq '.summary' runs/mission_2026_09_09_001.json
```

---

## Configuration

Every tunable lives in `backend/config/settings.py`. Override with
`SKUNK_`-prefixed environment variables or a `.env` file (see `.env.example`).

| Variable | Default | Meaning |
|---|---|---|
| `SKUNK_VIDEO_SOURCE` | `file` | `file` or `camera` |
| `SKUNK_VIDEO_PATH` | `assets/videos/demo_drone.mp4` | Clip to replay |
| `SKUNK_CAMERA_INDEX` | `0` | Camera device index |
| `SKUNK_TARGET_FPS` | `25` | Pipeline frame rate |
| `SKUNK_FRAME_WIDTH` | `960` | Frames resized to this width before detection |
| `SKUNK_LOOP_VIDEO` | `true` | Replay the clip when it ends |
| `SKUNK_DETECTOR` | `motion` | `motion` or `yolo` |
| `SKUNK_DETECTION_THRESHOLD` | `0.55` | Minimum detection confidence |
| `SKUNK_MODEL_PATH` | `yolo26n.pt` | YOLO weights |
| `SKUNK_DEVICE` | `auto` | `auto`, `mps` or `cpu` |
| `SKUNK_CONFIRMATION_TIME` | `2.0` s | Dwell required before THREAT_CONFIRMED |
| `SKUNK_CONFIRMATION_CONFIDENCE` | `0.60` | Mean confidence required |
| `SKUNK_FOLLOW_TIME` | `1.5` s | FOLLOWING duration before AUTHORIZE arms |
| `SKUNK_TARGET_LOST_GRACE` | `1.0` s | Dropout tolerated before TARGET_LOST |
| `SKUNK_TARGET_LOST_HOLD` | `2.5` s | TARGET_LOST shown before SEARCHING |
| `SKUNK_ACTUATED_HOLD` | `6.0` s | ACTUATED held before auto-reset (`0` = manual) |
| `SKUNK_TRAJECTORY_HORIZON` | `2.0` s | How far ahead the path is predicted |
| `SKUNK_TRAJECTORY_WINDOW` | `24` | Observations used for the motion fit |
| `SKUNK_INTERCEPTOR_SPEED` | `0.85` | Notional interceptor speed, frame widths/s |
| `SKUNK_LAUNCH_POINT_X/Y` | `0.5` / `1.0` | Canister position (bottom centre) |
| `SKUNK_INTERCEPT_MIN_CONFIDENCE` | `0.25` | Min prediction confidence for an estimate |
| `SKUNK_MAX_UPLOAD_MB` | `2048` | Upload size limit |
| `SKUNK_PORT` | `8000` | Backend port |
| `SKUNK_LOG_LEVEL` | `INFO` | Logging level |

Track association (`SKUNK_TRACK_IOU_THRESHOLD`, `SKUNK_TRACK_MAX_AGE`,
`SKUNK_TRACK_MIN_HITS`) and motion-detector tuning
(`SKUNK_MOTION_MIN_AREA_FRAC`, …) are documented inline in `settings.py`.

---

## Architecture

```
VIDEO SOURCE          backend/video/source.py             FileVideoSource | CameraVideoSource
      ↓
PERCEPTION            backend/vision/detector.py          MotionDetector | YoloDetector
      ↓
TRACK MANAGER         backend/vision/tracker.py           ByteTracker (persistent IDs)
      ↓
TARGET MANAGER        backend/targets/                    designations, primary selection
      ↓
THREAT / RULE ENGINE  backend/mission/rules.py            deterministic demo criteria
      ↓
MISSION STATE MACHINE backend/mission/state_machine.py    authoritative mission state
      ↓
ENGAGEMENT READINESS  backend/mission/readiness.py        six named preconditions
      ↓
OPERATOR AUTHORIZATION                                    manual, always
      ↓
LAUNCH COMMAND        backend/actuation/base.py           LaunchCommand (the hardware seam)
      ↓
SAFE ACTUATOR         backend/actuation/simulated.py      ActuatorInterface → SimulatedActuator
                                                          → LaunchAcknowledgement

                              ↓ telemetry

CANISTER STATUS       backend/canister/status.py          per-subsystem health
TACTICAL PICTURE      backend/mission/tactical.py         relative, sensor-frame only
MISSION RECORDING     backend/mission/recording.py        runs/mission_YYYY_MM_DD_NNN.json
      ↓
OPERATOR INTERFACE    frontend/src/                       SENSOR / TACTICAL
```

### The launcher boundary

The seam a future validated launcher controller attaches to:

```
MissionController  →  LaunchCommand  →  ActuatorInterface  →  LaunchAcknowledgement
 (pipeline/            (command_id,       (SimulatedActuator     (command_id,
  engagement.py)        target, mission     in V0)                 accepted,
                        state, readiness,                          latency_ms,
                        authorized_at)                             launcher_state)
```

Every command carries a unique `command_id` and every command is acknowledged,
because correlating a command with its reply - and measuring how long the reply
took - is what makes hardware-in-the-loop testing tractable. A real launcher
controller implements the same interface; nothing upstream of it changes.

### Engagement readiness

Six deterministic, individually named preconditions, evaluated every frame:

`target_valid` · `track_confirmed` · `track_stable` · `canister_operational` ·
`launcher_interface_ready` · `authorization_valid`

They derive one state:

`NOT_READY → READY_FOR_AUTHORIZATION → AUTHORIZED → LAUNCH_COMMAND_ISSUED`

The gate is checked *before* the state machine advances, so the operator is
never offered a control the canister could not honour, and "NOT READY" always
names the condition that failed. Adding a real hardware precondition - launcher
continuity, interlock closed, round present - is a field on `ReadinessInputs`
and a condition in `readiness.py`. Nothing else changes.

`backend/pipeline/` owns the frame loop and wires these together on a worker
thread, so blocking OpenCV and inference calls never stall the API event loop.
It is split by role, so a change to one concern touches one file:

| File | Responsibility |
| --- | --- |
| `pipeline/runtime.py` | the frame loop and the wiring; `MissionPipeline` |
| `pipeline/perception.py` | pixels → tracks (detector, tracker, stride, health) |
| `pipeline/engagement.py` | the mission controller: designation, projection, readiness, launch command |
| `pipeline/inputs.py` | which video source and detector are live |
| `pipeline/hub.py` | shared state between the worker thread and the API |

Alongside the pipeline:

| File | Responsibility |
| --- | --- |
| `canister/status.py` | the canister's model of itself, one reporter per subsystem |
| `mission/readiness.py` | the engagement preconditions and the state they derive |
| `mission/timeline.py` | `MissionState` → the seven-phase operator timeline |
| `mission/projection.py` | trajectory → sensor-frame TRACK PROJECTION |
| `mission/tactical.py` | tracks → the relative tactical picture |
| `mission/recording.py` | one JSON mission report per run |
| `actuation/base.py` | `LaunchCommand`, `LaunchAcknowledgement`, `ActuatorInterface` |

The API layer is split the same way - `api/routers/{system,mission,source,stream}.py`,
one module per role, aggregated by `api/routers/__init__.py`.

Four principles worth knowing before changing anything:

- **The backend is the sole source of mission state.** The UI renders what it
  receives and never derives state locally. A UI that can disagree with the
  state machine is worse than one that occasionally shows a stale frame.
- **Actuation requires an explicit operator authorization**, enforced in the
  state machine (not in the UI or the route). `request_authorization()` is
  rejected unless the mission is in `AWAITING_AUTHORIZATION`.
- **Nothing is displayed as a measurement unless it was measured.** A single
  uncalibrated camera cannot produce range, absolute speed, time-to-impact or a
  firing solution. Where the geometry is unconstrained the console says
  `NOT CALIBRATED`, `N/A` or `NOT CONNECTED` rather than showing a plausible
  number. This is a product rule, not a nicety: one invented figure makes every
  real figure on the panel untrustworthy.
- **Readiness never authorizes.** No combination of healthy subsystems can move
  the mission to `AUTHORIZED`; readiness can only withhold the operator's
  control, never substitute for it.

### States

`SEARCHING · DETECTED · TRACKING · THREAT_CONFIRMED · FOLLOWING ·
AWAITING_AUTHORIZATION · AUTHORIZED · ACTUATED · TARGET_LOST · ERROR`

Off-nominal: any tracking state → `TARGET_LOST` → `SEARCHING`.

The operator timeline is a coarser projection of these states, computed in
`mission/timeline.py` and shipped inside `MissionStatus`:

`SEARCH · DETECT · TRACK · CONFIRM · FOLLOW · AUTHORIZE · LAUNCH`

It lives in the telemetry contract rather than in the UI so there is exactly
one state machine in the system. `TARGET_LOST` rewinds the timeline to
`SEARCH` - a lost target is a setback, not a step.

Once authorization is accepted, losing the target does **not** cancel the
engagement - the operator's decision stands and the sequence completes.

---

## API contract

`backend/schemas.py` is the single source of truth. The TypeScript mirror is
generated, not hand-written:

```bash
.venv/bin/python scripts/gen_types.py   # writes frontend/src/types.ts
```

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Liveness plus detector/video diagnostics |
| `GET /api/telemetry` | Current telemetry snapshot |
| `GET /api/events` | Retained operator event log |
| `GET /api/video` | MJPEG preview stream |
| `POST /api/authorize` | Operator authorization (rejected unless armed) |
| `POST /api/reset` | Reset the mission for another run |
| `GET /api/source` | Current input config + local video library |
| `POST /api/source/video` | Load a local video by absolute path |
| `POST /api/source/upload` | Upload a clip and load it |
| `POST /api/source/camera` | Switch to a camera |
| `POST /api/source/detector` | Swap detector at runtime |
| `DELETE /api/source/upload/{name}` | Remove an uploaded clip |
| `WS /ws/telemetry` | One `TelemetryFrame` per processed frame |

Target payloads use normalised (0..1) bounding boxes so the UI can overlay
them at any window size without knowing the source resolution.

---

## Tests

### Toolchain versions

Both linters and the test runner are version-sensitive, and both had drifted:

| Tool | Pinned in | Why it matters |
| --- | --- | --- |
| `ruff` | `pyproject.toml` `[dev]`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml` | The lint config uses `RUF059`/`RUF046`/`UP042`, which only exist in ruff >= 0.11. An older ruff refuses to parse `pyproject.toml` at all. **Bump all three together.** |
| `node` | `frontend/package.json` `engines`, `NODE_VERSION` in CI | `jsdom` pulls `undici`, which hard-requires a minimum Node. Above the floor it works; below it, `vitest` dies with `webidl.util.markAsUncloneable is not a function` before running a single test. |
| `jsdom` | `frontend/package.json` (exact) | Pinned exactly rather than with `^`: a major bump silently raises the Node floor. |

### Testing Frameworks

| Framework | Layer | Purpose | Manual Run Command |
|---|---|---|---|
| **pytest** | Backend (Python) | Unit and integration testing for Python code. Tests state machine transitions, API endpoints, vision pipeline, tracking logic, and end-to-end flows. | `make test-backend` or `.venv/bin/python -m pytest` |
| **pytest-cov** | Backend (Python) | Code coverage reporting for pytest. Enforces 90% minimum coverage. | `make test-cov` (includes both backend and frontend) |
| **Vitest** | Frontend (TypeScript) | Fast unit test runner for Vite projects. Native ESM support with Jest-compatible API. Runs component and utility tests. | `make test-frontend` or `cd frontend && npm run test` |
| **React Testing Library** | Frontend (TypeScript) | Testing utilities for React components. Encourages testing components as users interact with them rather than implementation details. | Used via Vitest: `cd frontend && npm run test` |
| **@vitest/coverage-v8** | Frontend (TypeScript) | Coverage reporting for Vitest using V8's built-in coverage. Enforces 90% minimum coverage. | `cd frontend && npm run test:cov` |
| **rhiza** | Backend (Python) | Template-driven testing infrastructure from [Jebel-Quant/rhiza](https://github.com/Jebel-Quant/rhiza). Provides standardized pytest configuration, pre-commit hooks, and CI/CD workflows. | Configured via `.rhiza/template.yml` |

### Running Tests

```bash
make test              # Run both backend and frontend tests
make test-backend      # Backend only (pytest)
make test-frontend     # Frontend only (Vitest)
make test-cov          # Both with coverage reports
make test-frontend-watch  # Frontend in watch mode (for development)
```

**Coverage requirement:** Both backend and frontend enforce a minimum 90% code
coverage. The coverage check will fail if coverage drops below this threshold.

### Pre-commit Hooks

To run checks automatically on every `git commit`, install pre-commit hooks:

```bash
make setup-hooks
```

This installs hooks that run linting, type checking, and tests before each
commit. Commits will be blocked if any check fails.

### Continuous Integration

GitHub Actions runs all checks automatically on push to `main` and on pull
requests. The workflow (`.github/workflows/ci.yml`) includes:

| Job | Description |
|---|---|
| `lint` | Ruff (Python) + ESLint/Prettier (TypeScript) |
| `typecheck` | TypeScript type checking |
| `test-backend` | pytest with coverage (90% threshold) |
| `test-frontend` | Vitest with coverage (90% threshold) |
| `depcheck` | Unused dependency detection |

### Backend Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

146 tests covering state transitions, detection→tracking, track loss and
recovery, the confirmation rules, the authorization interlock (including that
actuation is impossible without it), reset and repeatability, tracker ID
persistence, schema serialisation, trajectory fitting and
confidence, airframe classification (including against the real demo clips),
speed inference, fast-target track continuity, intercept feasibility, interceptor flight phases, upload path
traversal safety, and a full end-to-end run over the real clip through the
HTTP API and WebSocket - including uploading a clip and switching to it.

### Frontend Tests

```bash
cd frontend && npm run test
```

Component tests using Vitest + React Testing Library covering UI primitives
and component behavior.

Vision *accuracy* is deliberately not unit-tested; for that, run the headless
pipeline check against real footage:

```bash
.venv/bin/python scripts/verify_pipeline.py --authorize
```

It prints the state timeline and exits non-zero if the full sequence is not
reached. This is the fastest way to tell whether a demo will work - run it
first whenever something misbehaves.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Frontend on an unexpected port | Port 5173 was busy; Vite prints the port it chose |
| `Sensor Offline` banner | Video path wrong, or camera in use. Check `GET /api/health` |
| No detections | Background model still warming (12 frames), or the object is outside the motion area bounds - see `SKUNK_MOTION_MIN_AREA_FRAC` |
| Never reaches THREAT_CONFIRMED | Confidence below `SKUNK_CONFIRMATION_CONFIDENCE`, or track not held for `SKUNK_CONFIRMATION_TIME`. The banner names the blocking rule |
| AUTHORIZE stays greyed out | By design - it arms only in `AWAITING_AUTHORIZATION` |
| YOLO won't load | Run `pip install -r requirements-yolo.txt`. The backend falls back to `motion` and logs why |
| Whole frame lights up with boxes | `motion` detector on handheld/panning footage. Switch to `yolo` in the Input panel |
| Uploaded clip rejected | Not decodable by OpenCV. Re-encode as H.264 MP4 |
| `NO SOLUTION` for intercept | Track too noisy (low confidence), or the target is unreachable within the horizon at `SKUNK_INTERCEPTOR_SPEED` |

---

## What V0 is not

Explicitly out of scope, and not present in this codebase:

interceptor aerodynamics · guidance · navigation · PX4 · Gazebo · trajectory
optimisation · intercept calculation · autonomous engagement · weapon
targeting · projectile firing · destructive actuation · sensor fusion · radar
· RF detection · production threat classification · swarm coordination · cloud
infrastructure · multi-canister networking.

`ActuatorInterface` exists so a **safe** test device (LED, servo-driven lid,
GPIO test pin) can be attached later without touching mission logic. It must
not be used for projectile firing or weapon release.

The tactical view is a **relative** picture in the sensor frame. There is no
GPS, no compass and no rangefinder in V0, so `TacticalTrack.bearing_available`
and `range_available` are both false and the view labels itself
`LOCAL TRACK · RELATIVE COORDINATES · SENSOR FRAME`. The structure carries
those flags so a calibrated sensor, an external track feed or a second canister
can supply real geometry later - but nothing may fabricate it in the meantime.

`TrackProjection` replaced the earlier "time to impact" and inferred-range
readouts. Those were the output of an image-plane extrapolation with no camera
calibration behind them; shown in seconds and metres they read as measurements
and were not. What remains is direction, stability, horizon and projection
confidence, all stated as sensor-frame quantities.

---

## Repository layout

```
backend/
  config/settings.py        all tunables
  schemas.py                canonical API contract
  video/source.py           VideoSource + file/camera implementations
  vision/detector.py        Detector + motion/YOLO implementations
  vision/tracker.py         ByteTracker, persistent track IDs
  targets/target_manager.py designations, primary selection
  mission/rules.py          deterministic demo criteria
  mission/state_machine.py  authoritative mission state
  mission/timeline.py       mission state -> the seven-phase timeline
  mission/readiness.py      EngagementReadiness - the gate before the launcher
  mission/projection.py     TRACK PROJECTION (sensor frame, not a solution)
  mission/tactical.py       relative tactical picture
  mission/recording.py      MissionRun + JSON reports in runs/
  canister/status.py        per-subsystem canister health model
  mission/trajectory.py     path prediction + intercept estimate (display)
  mission/classification.py FPV multirotor vs fixed-wing, from kinematics
  mission/speed.py          absolute speed inference from assumed airframe size
  video/library.py          local video library, upload validation
  actuation/base.py         LaunchCommand + ActuatorInterface (the hardware seam)
  actuation/simulated.py    SimulatedActuator - accepts and acknowledges commands
  actuation/interceptor.py  simulated interceptor flight (animation)
  api/deps.py               shared FastAPI dependencies
  api/models.py             inbound request bodies
  api/routers/system.py     health, telemetry snapshot, event log
  api/routers/mission.py    operator authorize / reset
  api/routers/source.py     library, uploads, camera, detector selection
  api/routers/stream.py     MJPEG preview
  api/websocket.py          live telemetry channel
  pipeline/runtime.py       the frame loop; MissionPipeline
  pipeline/perception.py    pixels -> tracks
  pipeline/engagement.py    tracks -> mission decisions
  pipeline/inputs.py        runtime source + detector selection
  pipeline/hub.py           thread-safe telemetry/event state
  main.py                   app assembly + entry point
frontend/src/
  App.tsx                   routes between the two screens
  api/                      the only place that talks to the backend
    config.ts               where the backend is (VITE_API_BASE)
    endpoints.ts            every path, in one place
    client.ts               transport + ApiError
    mission.ts, source.ts   typed calls by role
  screens/                  SetupScreen, OperatorScreen (layout only)
  components/setup/         dropzone, library, advanced perception settings
  components/operator/      timeline, sensor + tactical views, target,
                            readiness, canister, details, event log
  components/common/        readout primitives, ErrorBoundary
  hooks/useTelemetry.ts     WebSocket subscription
  hooks/useSource.ts        input selection state
  hooks/useMissionCues.ts   launch cue + authorize hotkey
  hooks/useMediaQuery.ts    breakpoints for structural layout changes
  hooks/useViewMode.ts      SENSOR / TACTICAL selection
  styles/                   tokens, base, setup, operator, responsive
  format.ts                 shared display formatting
  types.ts                  generated from backend/schemas.py
scripts/
  make_demo_video.py        generate the repeatable demo clip
  verify_pipeline.py        headless end-to-end check
  gen_types.py              regenerate frontend types from schemas.py
tests/                      pytest suite
Makefile                    every developer entry point (`make help`)
pyproject.toml              packaging, pytest and ruff config
run_demo.sh                 one-command launcher
```
