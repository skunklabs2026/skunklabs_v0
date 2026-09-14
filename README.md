# SkunkLabs MVP V0

[![Release](https://img.shields.io/github/v/release/skunklabs2026/skunklabs_v0?sort=semver)](https://github.com/skunklabs2026/skunklabs_v0/releases)

[![Python versions](https://img.shields.io/badge/Python-3.11-blue?logo=python)](https://www.python.org/)
[![CI](https://github.com/skunklabs2026/skunklabs_v0/actions/workflows/ci.yml/badge.svg?event=push)](https://github.com/skunklabs2026/skunklabs_v0/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/skunklabs2026/skunklabs_v0/branch/main/graph/badge.svg)](https://codecov.io/gh/skunklabs2026/skunklabs_v0)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg?logo=ruff)](https://github.com/astral-sh/ruff)
[![CodeFactor](https://www.codefactor.io/repository/github/skunklabs2026/skunklabs_v0/badge)](https://www.codefactor.io/repository/github/skunklabs2026/skunklabs_v0)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/skunklabs2026/skunklabs_v0/badge)](https://scorecard.dev/viewer/?uri=github.com/skunklabs2026/skunklabs_v0)

Local detection, tracking and operator engagement demo.

One screen shows a sensor feed and walks a canister through the operational
sequence:

```text
SEARCH → DETECT → TRACK → CONFIRM → FOLLOW → AUTHORIZE → ACTUATE
```

Everything runs locally and offline. There is no cloud dependency, no LLM, and
no database.

> **Scope and safety.** Actuation in V0 is a simulated, benign event: a log
> entry, an API event and a UI launch cue. Nothing physical is triggered. The
> confirmation rules are **demo logic**, not a threat-identification
> capability. Engagement authorization is always manual — the system will
> never actuate on its own. See [What V0 is not](#what-v0-is-not).

---

## How it runs

The app opens on **Mission Setup**, not on a live feed:

1. **Load footage** — drag a video in, or pick one from the local library.
2. **Choose a detector** — `motion` or `yolo`, with a live confidence slider.
3. **Confirm it is tracking** — a preview plus the detector's own counters
   (frames, detections, active tracks, inference time, classes seen). This is
   how you tell whether the model works on *your* clip before starting.

**Begin mission** then opens the operator console. **Change source** in the
top bar returns to setup at any time.

---

## Quick start

```bash
make setup && make demo
```

`make setup` creates the virtualenv from `uv.lock` (Python version from
`.python-version`) and installs both halves; `make demo`
starts the backend and the operator UI, waits for both to be healthy,
generates the demo clip on first run, and opens the screen.

`make help` lists every entry point. The ones you will actually use:

| Command | What it does |
| --- | --- |
| `make demo` | backend + UI together (same as `./run_demo.sh`) |
| `make test` | the pytest suite |
| `make check` | every gate CI runs — **run before opening a PR** |
| `make format` | auto-fix Python and TypeScript formatting |
| `make security` | bandit, pip-audit and npm audit |
| `make verify` | drive the pipeline headlessly through the full sequence |
| `make lock` | re-resolve `uv.lock` after a dependency change |
| `make build` | production frontend build, served by the backend at :8000 |

If you would rather not use `make`, every target is one or two plain commands —
open the `Makefile` and copy the line.

---

## Working on this with a team

- **One formatter per language, no debates.** `ruff` for Python, `eslint` +
  `prettier` for TypeScript, all configured in-repo. `make format` fixes;
  `make check` is exactly what CI runs — each CI job invokes one of its
  targets, so the two cannot drift.
- **Types cross the boundary.** `frontend/src/types.ts` is generated from
  `backend/schemas.py` — after changing a schema, run
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
port and prints it — use the URL it prints.

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

- **Upload video** — pick any clip from your machine. It is copied to
  `assets/videos/uploads/`, validated as decodable, and loaded immediately.
  A progress bar shows large uploads.
- **Pick from the library** — every clip in `assets/videos/` is listed with
  its resolution, duration and size. Click one to load it.
- **Switch detector** — `motion` / `yolo`, on the same footage, so you can
  compare them directly.
- **Use camera** — switch to the webcam.

Changing any of these resets the perception state and restarts the mission
cleanly. The backend keeps running throughout.

**From the command line:**

```bash
curl -X POST http://127.0.0.1:8000/api/source/video \
  -H 'Content-Type: application/json' \
  -d '{"path":"/Users/you/Movies/drone.mp4"}'
```

Any absolute path on the machine is accepted — footage does not need to be
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

The `motion` detector assumes a *roughly static camera* — it models the
background and reports what moves against it. On handheld or panning footage
it will flag large parts of the frame. **Use `yolo` for real-world video**;
use `motion` for tripod/fixed-camera footage and the bundled clip.

Targets are designated from their detected class, so on general footage you
will see `PERSON-001`, `CAR-002` and so on — not everything labelled as a
UAV. Only tracks classified `uav` can satisfy the confirmation rules, so a
person is tracked and displayed but never confirmed as a demo threat.

---

## Configure the detector

Two detectors ship, both behind the `Detector` interface
(`backend/vision/detector.py`). The mission logic never sees which is running.

### `motion` (default)

OpenCV MOG2 background subtraction. No model weights, no download, no torch.
An airborne object against sky is close to its ideal case, which is why it is
the default — V0 prioritises repeatability over sophistication.

```bash
SKUNK_DETECTOR=motion ./run_demo.sh
```

### `yolo`

Ultralytics YOLO26n, per the reference document. Requires a one-time ~2 GB
install; inference itself is fully local and offline.

```bash
make setup-yolo
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

## Airframe classification — FPV multirotor vs fixed-wing

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
deterministic kinematic features over a rolling ~3.6 s window — path
straightness, speed steadiness, turn rate, and hover fraction. Each votes; a
decision needs both a clear margin and eight consecutive agreeing frames, so
the answer cannot flicker mid-engagement.

Two things depend on the result:

**Prediction horizon.** A fixed-wing holds its course, so a straight
extrapolation is trustworthy further out. A quad can turn on the spot, so the
horizon shortens and confidence drops — extrapolating a quad as far as a
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

A single uncalibrated camera cannot measure speed — it measures angular rate.
Angular rate becomes a speed only once you know the range, and range follows
from apparent size *if you assume the real size*. That assumption is what the
classification supplies:

```text
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

> Cross-range only — motion toward or away from the camera is invisible to a
> single camera, so the figure is a lower bound.

---

## Performance

Measured on this machine (Apple Silicon, MPS), 960 px frames:

| Detector | Per inference | Effective fps at stride 1 / 2 |
|---|---|---|
| `motion` | 3.1 ms | 319 / 632 |
| `yolo` (YOLO26n) | 15.4 ms | 65 / 151 |

Detection is not the bottleneck at a 25 fps demo rate — 15 ms of a 40 ms
budget. Three controls exist for when it is:

- `SKUNK_DETECTION_STRIDE` — detect every Nth frame; the tracker coasts on its
  velocity estimate in between, so the target still moves smoothly on screen.
- `SKUNK_INFERENCE_WIDTH` — downscale for inference only; display keeps full
  resolution.
- `SKUNK_TARGET_FPS` — raise the playback/processing rate.

**Tracking a fast target** was the real problem, and it was not throughput.
A small target crossing quickly moves further than its own width between
frames, so consecutive boxes have IoU of exactly zero, association fails, and
the track ID breaks every few frames — on precisely the target that matters
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
2. **Estimates an intercept point** — the earliest point on that path a
   notional interceptor could reach in time from the canister position. Shown
   as an amber ring, with time-to-intercept in the side panel.
3. **On authorization, flies a simulated interceptor** from the launch point
   to the point committed *at the moment of launch*
   (`backend/actuation/interceptor.py`). You see it climb, arrive, and go
   `SPENT`, with a countdown.

The aim point is deliberately **frozen at launch** and never updated
mid-flight. Re-aiming would be a (crude) guidance behaviour, and V0 must not
imply one — what is shown is a committed, ballistic shot. If the target
manoeuvres afterwards, the interceptor visibly misses. That is honest, and
it is the point: it shows what the prediction was worth.

> **Scope.** All of this is a kinematic extrapolation of *pixel* motion in
> normalised image coordinates. There is no range, altitude, camera
> calibration or 3D. It is not a flight model, not a guidance law and not a
> firing solution. Nothing acts on it — the mission state machine does not
> consume the intercept result, and the "interceptor" is a marker moving
> along a line. Both are for operator display.

Tunable via `SKUNK_TRAJECTORY_HORIZON`, `SKUNK_INTERCEPTOR_SPEED`,
`SKUNK_LAUNCH_POINT_X/Y` and `SKUNK_INTERCEPT_MIN_CONFIDENCE`.

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
| `SKUNK_HOST` | `127.0.0.1` | Bind address — **see the caveat below** |
| `SKUNK_PORT` | `8000` | Backend port |
| `SKUNK_LOG_LEVEL` | `INFO` | Logging level |

> **`SKUNK_HOST` caveat.** The default binds loopback, and the rest of the
> demo's threat model assumes it. `POST /api/source/video` accepts any
> absolute path on the host by design (so footage need not be copied into the
> repo) and answers whether that path exists, is a regular file and decodes as
> video. From `127.0.0.1` that is a convenience; on `0.0.0.0` it is a
> filesystem probe offered to the whole network. Uploads are separately
> guarded — `safe_upload_path()` blocks traversal and `SKUNK_MAX_UPLOAD_MB`
> caps size — but the path-selection endpoint is not, and is not meant to be.
> Do not expose this demo beyond localhost.

Track association (`SKUNK_TRACK_IOU_THRESHOLD`, `SKUNK_TRACK_MAX_AGE`,
`SKUNK_TRACK_MIN_HITS`) and motion-detector tuning
(`SKUNK_MOTION_MIN_AREA_FRAC`, …) are documented inline in `settings.py`.

---

## Architecture

```text
VIDEO SOURCE      backend/video/source.py       FileVideoSource | CameraVideoSource
      ↓
DETECTOR          backend/vision/detector.py    MotionDetector | YoloDetector
      ↓
TRACKER           backend/vision/tracker.py     ByteTracker (persistent IDs)
      ↓
TARGET MANAGER    backend/targets/              designations, primary selection
      ↓
RULE ENGINE       backend/mission/rules.py      deterministic demo criteria
      ↓
STATE MACHINE     backend/mission/state_machine.py   authoritative mission state
      ↓
FASTAPI + WS      backend/api/                  REST commands + telemetry push
      ↓
OPERATOR UI       frontend/src/                 React + Vite, one screen
      ↓
ACTUATOR          backend/actuation/            ActuatorInterface → SimulatedActuator
```

`backend/pipeline/` owns the frame loop and wires these together on a worker
thread, so blocking OpenCV and inference calls never stall the API event loop.
It is split by role, so a change to one concern touches one file:

| File | Responsibility |
| --- | --- |
| `pipeline/runtime.py` | the frame loop and the wiring; `MissionPipeline` |
| `pipeline/perception.py` | pixels → tracks (detector, tracker, stride, health) |
| `pipeline/engagement.py` | tracks → mission decisions (designation, prediction, actuation) |
| `pipeline/inputs.py` | which video source and detector are live |
| `pipeline/hub.py` | shared state between the worker thread and the API |

The API layer is split the same way — `api/routers/{system,mission,source,stream}.py`,
one module per role, aggregated by `api/routers/__init__.py`.

Two principles worth knowing before changing anything:

- **The backend is the sole source of mission state.** The UI renders what it
  receives and never derives state locally. A UI that can disagree with the
  state machine is worse than one that occasionally shows a stale frame.
- **Actuation requires an explicit operator authorization**, enforced in the
  state machine (not in the UI or the route). `request_authorization()` is
  rejected unless the mission is in `AWAITING_AUTHORIZATION`.

### States

`SEARCHING · DETECTED · TRACKING · THREAT_CONFIRMED · FOLLOWING ·
AWAITING_AUTHORIZATION · AUTHORIZED · ACTUATED · TARGET_LOST · ERROR`

Off-nominal: any tracking state → `TARGET_LOST` → `SEARCHING`.

Once authorization is accepted, losing the target does **not** cancel the
engagement — the operator's decision stands and the sequence completes.

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

### Testing Frameworks

| Framework | Layer | Purpose | Manual Run Command |
|---|---|---|---|
| **pytest** | Backend (Python) | Unit and integration testing for Python code. Tests state machine transitions, API endpoints, vision pipeline, tracking logic, and end-to-end flows. | `make test-backend` or `.venv/bin/python -m pytest` |
| **pytest-cov** | Backend (Python) | Branch-coverage reporting for pytest. Fails under 87%. | `make test-cov` (includes both backend and frontend) |
| **mypy** | Backend (Python) | Static type checking over `backend/`. | `make typecheck-backend` |
| **Vitest** | Frontend (TypeScript) | Fast unit test runner for Vite projects. Covers the `api/` layer, display formatting, and one UI primitive. | `make test-frontend` or `cd frontend && npm run test` |
| **React Testing Library** | Frontend (TypeScript) | Component-rendering utilities. Currently used by a single test file (`Readout.test.tsx`). | Used via Vitest: `cd frontend && npm run test` |
| **@vitest/coverage-v8** | Frontend (TypeScript) | Coverage reporting for Vitest using V8's built-in coverage. Holds `src/api/**` at 90%; the rest at a measured floor. | `cd frontend && npm run test:cov` |
| **bandit / pip-audit / npm audit** | Both | Code and dependency vulnerability scanning. | `make security` |

### Running Tests

```bash
make test              # Run both backend and frontend tests
make test-backend      # Backend only (pytest)
make test-frontend     # Frontend only (Vitest)
make test-cov          # Both with coverage reports
make test-frontend-watch  # Frontend in watch mode (for development)
```

**Coverage requirements.** The two sides are held to different bars, and the
numbers below are the ones actually enforced — not aspirations:

| Scope | Enforced | Actual | Where |
|---|---|---|---|
| `backend/` | 87% branch | ~88% | `[tool.coverage.report] fail_under` |
| `frontend/src/api/**` | 90% | ~99% | `frontend/vite.config.ts` |
| rest of `frontend/src` | 20% stmts / 12% branch | ~22% / ~13% | `frontend/vite.config.ts` |

The frontend floor is low because it is honest. The React component and hook
layers are largely untested; the `api/` layer — the contract with the backend
— is not. Both gates fail the build on a drop, so the floor is a ratchet to
raise as tests land, not a target to design to.

The backend figure is **branch** coverage, which is the informative number in
a codebase this full of state-machine conditionals. The YOLO detector is
excluded (`# pragma: no cover`): it needs the optional ~2 GB extra that CI
does not install, so counting it would report a permanently unfixable gap.

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

Every job invokes a `make` target rather than repeating its commands, so
`make check` and CI cannot drift apart:

| Job | Runs | Description |
|---|---|---|
| `lint` | `make lint` | Ruff (Python) + ESLint/Prettier (TypeScript) |
| `typecheck` | `make typecheck` | mypy (Python) + `tsc` (TypeScript) |
| `test-backend` | `make test-backend-cov` | pytest with branch coverage (87% threshold) |
| `test-frontend` | `make test-frontend-cov` | Vitest with coverage |
| `depcheck` | `make depcheck` | Unused dependency detection |
| `verify` | `make verify` | Headless end-to-end run over the demo clip |
| `security` | `make security` | bandit, pip-audit and npm audit |

Third-party actions are pinned to commit SHAs rather than moving major tags;
Dependabot (`.github/dependabot.yml`) keeps them, and the `uv`/`npm`
dependency sets, current.

### Backend Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

~150 tests (plus doctests in `backend/mission/`) covering state transitions, detection→tracking, track loss and
recovery, the confirmation rules, the authorization interlock (including that
actuation is impossible without it), reset and repeatability, tracker ID
persistence, schema serialisation, trajectory fitting and
confidence, airframe classification (including against the real demo clips),
speed inference, fast-target track continuity, intercept feasibility, interceptor flight phases, upload path
traversal safety, and a full end-to-end run over the real clip through the
HTTP API and WebSocket — including uploading a clip and switching to it.

### Frontend Tests

```bash
cd frontend && npm run test
```

Vitest covers the `api/` layer end to end — every endpoint path, the HTTP
client's error handling, and the XHR upload path — plus the display formatting
helpers and one UI primitive (`Readout`). The screens, hooks and remaining
components have no tests yet; the coverage floor above reflects that rather
than hiding it.

Vision *accuracy* is deliberately not unit-tested; for that, run the headless
pipeline check against real footage:

```bash
.venv/bin/python scripts/verify_pipeline.py --authorize
```

It prints the state timeline and exits non-zero if the full sequence is not
reached. This is the fastest way to tell whether a demo will work — run it
first whenever something misbehaves.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Frontend on an unexpected port | Port 5173 was busy; Vite prints the port it chose |
| `Sensor Offline` banner | Video path wrong, or camera in use. Check `GET /api/health` |
| No detections | Background model still warming (12 frames), or the object is outside the motion area bounds — see `SKUNK_MOTION_MIN_AREA_FRAC` |
| Never reaches THREAT_CONFIRMED | Confidence below `SKUNK_CONFIRMATION_CONFIDENCE`, or track not held for `SKUNK_CONFIRMATION_TIME`. The banner names the blocking rule |
| AUTHORIZE stays greyed out | By design — it arms only in `AWAITING_AUTHORIZATION` |
| YOLO won't load | Run `make setup-yolo`. The backend falls back to `motion` and logs why |
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

---

## Repository layout

```text
backend/
  config/settings.py        all tunables
  schemas.py                canonical API contract
  video/source.py           VideoSource + file/camera implementations
  vision/detector.py        Detector + motion/YOLO implementations
  vision/tracker.py         ByteTracker, persistent track IDs
  targets/target_manager.py designations, primary selection
  mission/rules.py          deterministic demo criteria
  mission/state_machine.py  authoritative mission state
  mission/trajectory.py     path prediction + intercept estimate (display)
  mission/classification.py FPV multirotor vs fixed-wing, from kinematics
  mission/speed.py          absolute speed inference from assumed airframe size
  video/library.py          local video library, upload validation
  actuation/                ActuatorInterface + SimulatedActuator
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
  components/setup/         dropzone, library, detector choice, verification
  components/operator/      video stage, overlays, banner, side panel, log
  components/common/        readout primitives, ErrorBoundary
  hooks/useTelemetry.ts     WebSocket subscription
  hooks/useSource.ts        input selection state
  hooks/useMissionCues.ts   launch cue + authorize hotkey
  hooks/useMediaQuery.ts    breakpoints for structural layout changes
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
