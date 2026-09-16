# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Commands

Every developer entry point is a `make` target. **Prefer a bare `make <target>`**
over calling `.venv/bin/…` or `npm` directly — the targets pin the interpreter,
the working directory and the flags, and they are all safe to re-run.

| Target | What it does |
| --- | --- |
| `make help` | list every target (the default goal) |
| `make setup` | `setup-backend` + `setup-frontend` — the first-run command |
| `make setup-backend` | create `.venv` (uv, Python 3.11) and `uv pip install -e ".[dev]"` |
| `make setup-frontend` | `npm install` in `frontend/` |
| `make setup-hooks` | install the pre-commit hooks |
| `make setup-yolo` | add the optional neural detector (`.[yolo]`, ~2 GB) |
| `make setup-research` | add the notebook/EDA toolchain (`.[research]`) |
| `make demo` | backend + UI together (`./run_demo.sh`) |
| `make dev-backend` | uvicorn with autoreload on :8000 |
| `make dev-frontend` | Vite dev server only |
| `make test` | backend (pytest) + frontend (Vitest) |
| `make test-backend` | pytest only |
| `make test-frontend` | Vitest only |
| `make test-cov` | both suites with coverage reports |
| `make test-frontend-watch` | Vitest in watch mode |
| `make lint` | `ruff check` + `ruff format --check` on `backend tests scripts`, then ESLint |
| `make format` | auto-fix Python (ruff) and TypeScript formatting |
| `make fmt-frontend` | frontend formatting only |
| `make typecheck` | TypeScript type-check (`typecheck-frontend` is an alias) |
| `make depcheck` | unused/missing frontend dependencies |
| `make check` | `lint typecheck test-backend test-frontend` — **run before opening a PR** |
| `make build` | production frontend build, served by the backend at :8000 |
| `make verify` | drive the pipeline headlessly through the full mission sequence |
| `make notebook` | marimo notebook browser on `notebooks/` (`make marimo` is an alias) |
| `make eda` | fetch MMAUD metadata, archive index and all 40k labels (~18 MB) |
| `make eda-sample` | fetch a small random sample of real frames |
| `make eda-check` | `marimo check` + run the notebook headlessly as a script |
| `make clean` | remove caches and build output |

There is no `typecheck` for Python in this repo — `make typecheck` is the
frontend only. Python quality is `ruff` plus the pytest suite.

Two generated/derived artefacts have their own scripts, and neither is
hand-edited:

- `.venv/bin/python scripts/gen_types.py` — regenerates `frontend/src/types.ts`
  from `backend/schemas.py`. Run it after any schema change.
- `.venv/bin/python scripts/make_demo_video.py` — regenerates the bundled
  synthetic demo clip (`--platform fixed_wing|multirotor`).

`.venv/bin/python scripts/verify_pipeline.py --authorize` is the fastest way to
tell whether a demo will actually work; it prints the state timeline and exits
non-zero if the full sequence is not reached.

## Architecture

Python backend + React/Vite frontend. There is no `src/` directory — the
importable package is `backend/` (`[tool.setuptools.packages.find] include =
["backend*"]`), and `frontend/` is a separate npm workspace.

```
backend/
  config/      settings.py — every tunable, SKUNK_-prefixed env overrides
  schemas.py   the canonical API contract (frontend types are generated from it)
  video/       VideoSource + file/camera implementations, local video library
  vision/      Detector (motion | YOLO) and ByteTracker
  targets/     designations and primary-target selection
  mission/     rules, state_machine, trajectory, classification, speed
  pipeline/    runtime (frame loop), perception, engagement, inputs, hub
  api/         deps, models, routers/{system,mission,source,stream}, websocket
  actuation/   ActuatorInterface -> SimulatedActuator, interceptor (simulated)
  main.py      app assembly + entry point (`skunklabs` console script)
frontend/src/  App, api/, screens/, components/, hooks/, styles/, types.ts
scripts/       make_demo_video.py, verify_pipeline.py, gen_types.py
tests/         pytest suite (see below)
```

Data flows one way: video source → detector → tracker → target manager → rule
engine → state machine → FastAPI/WebSocket → UI, with the actuator at the end.
`backend/pipeline/` runs that loop on a worker thread so blocking OpenCV and
inference calls never stall the API event loop.

Two invariants worth knowing before changing anything:

- **The backend is the sole source of mission state.** The UI renders what it
  receives over `/ws/telemetry` and never derives mission state locally.
- **Actuation requires an explicit operator authorization**, enforced in the
  state machine — not in the UI and not in the route.
  `request_authorization()` is rejected unless the mission is in
  `AWAITING_AUTHORIZATION`.

Scope matters here: actuation is a simulated, benign event, and the
confirmation rules are demo logic, not a threat-identification capability. Do
not extend the codebase toward guidance, weapon targeting or autonomous
engagement — see "What V0 is not" in `README.md`.

## This repo is not template-managed

**Every file here is locally owned.** There is no `.rhiza/template.yml`, no
template lock, and nothing is synced from an upstream repository — so any file
in the tree can be edited in place, and no change needs to be made "upstream"
first.

This was a deliberate call. The repo previously carried a `.rhiza/` pointer at
`Jebel-Quant/rhiza`, but it named profiles that do not exist in that template
(`python-pytest`, `python-ruff`, `pre-commit`, `github-actions` — the real ones
are `local`, `github-project`, …), so it had never synced anything. Adopting it
properly would have meant handing rhiza ownership of repo-root files this
project has deliberately hand-written: the `Makefile` (rhiza ships a 71-line
shim that forwards to `rhiza-task`, and expects repo targets to move to
`local.mk`) and the ruff config (rhiza ships a root `ruff.toml`, which ruff
reads *in preference to* `[tool.ruff]` in `pyproject.toml` rather than merging
with it — the annotated `ignore` list here would have been silently shadowed).

The `/rhiza:quality` command is still used periodically as an **advisory**
scorecard — it assesses and proposes, it never applies. Treat its output as
suggestions to weigh, not as drift to correct: there is no template to conform
to. Do not re-add a `.rhiza/` directory in response to it.

## Research notebooks

`notebooks/` holds offline dataset analysis. Nothing in `backend/` imports it,
nothing in it runs during a demo, and it needs `make setup-research` first —
the core dependency list stays at seven packages so "runs locally and offline"
keeps meaning what it says.

**Notebooks are [marimo](https://marimo.io), not Jupyter.** A marimo notebook
is a plain `.py` file — it diffs, it has no stored outputs to strip, and
`python notebooks/01_mmaud_eda.py` runs the whole thing headlessly, which is
what `make eda-check` uses as a smoke test. `make notebook` (or `make marimo`)
opens marimo's notebook browser rooted at `notebooks/`, so you pick a notebook
from the menu rather than landing in one — add a second notebook and it shows
up there with no Makefile change. Do not hand-edit the `@app.cell` scaffolding.

Two marimo rules that shape how the cells are written:

- **A name may only be defined by one cell.** Throwaways — figures, loop
  variables, local helpers — are `_`-prefixed to make them cell-local. Only the
  names later cells actually consume (`meta`, `segs`, `vel`, `R`, …) are global.
- **The last expression is the cell's output.** Plotting cells end with `_fig`;
  cells with several things to show use `mo.vstack([...])`.

`notebooks/` stays **outside** every lint, coverage and packaging path: `make
lint` covers `backend tests scripts`, coverage is measured over `backend` only,
and `[tool.setuptools.packages.find] include = ["backend*"]`. marimo owns the
file's formatting, so running ruff over it would just fight the editor. Real
code therefore lives in `scripts/` — `mmaud_io.py` (reader + synthetic fixture)
and `fetch_mmaud.py` (download helper) are both linted, and the notebook stays
thin.

- The dataset lives at `SKUNK_MMAUD_DIR`, default `assets/datasets/mmaud`,
  gitignored like `assets/videos/`. It is **not** a `Settings` field — nothing
  in `backend/` reads it, so a tunable there would be dead weight in the README
  table and `.env.example`. Promote it if a trained model ever ships.
- **Nothing bulk-downloads.** MMAUD's `train.zip` is 139.7 GB, but Google Drive
  serves it with `Accept-Ranges: bytes`, so `scripts/mmaud_io.py` reads the
  archives as random-access storage. `RemoteZip` parses the ZIP64 central
  directory (~0.7-17 MB) for structure, sizes and every sensor timestamp;
  `read_many()` coalesces adjacent members so the 81,400 label files come down
  in **103 range requests, ~17 MB**. Sizes come from a ranged GET, never HEAD —
  Drive answers HEAD on large files with an HTML interstitial and
  `Content-Length: 0`.
- `make eda` fetches the metadata, the archive index and all 40,800 labels
  (~18 MB). `make eda-sample` pulls real frames for the plotting cells only.
  Both are idempotent and cached; re-runs are offline.

Scope: MMAUD is multi-modal (audio, image, LiDAR, radar), and
`README.md` "What V0 is not" currently excludes *sensor fusion · radar ·
production threat classification*. Analysing a dataset does not change what V0
does, so that stands. But if a learned position/velocity model ever lands in
`backend/`, amend that list and the guardrail above deliberately rather than
letting the code contradict the docs.

## Conventions

- **Tests** live in `tests/` (`[tool.pytest.ini_options] testpaths = ["tests"]`,
  `addopts = "-q --strict-markers"`), one `test_*.py` per backend concern:
  `test_api.py`, `test_state_machine.py`, `test_rules.py`, `test_tracker.py`,
  `test_trajectory.py`, `test_classification.py`, `test_video_library.py`.
  Shared fixtures go in `tests/conftest.py`. Frontend component tests live
  beside the components and run under Vitest.
- **Coverage** is measured over `backend` only, with the threshold in
  `[tool.coverage.report] fail_under`. Check the current value before claiming
  a number — the README quotes 90% in several places.
- **Vision accuracy is deliberately not unit-tested.** Use
  `scripts/verify_pipeline.py` against real footage instead of asserting on
  detector output.
- **Lint/format is ruff only**, `line-length = 96`, `target-version = "py311"`,
  excluding `.venv`, `assets` and `frontend`. The `ignore` list in
  `pyproject.toml` is annotated with the reason for each entry — add a reason
  if you add a rule.
- **Requires Python 3.11** (`requires-python = ">=3.11"`); CI and
  `make setup-backend` both pin 3.11.
- **New tunables go in `backend/config/settings.py`** with a `SKUNK_` env
  override, documented inline, and added to the table in `README.md`.
- **The UI never calls `fetch` directly** — everything goes through
  `frontend/src/api/`, so a renamed route breaks one file instead of failing
  silently at demo time.
- Docstrings: module- and class-level docstrings explaining *why*, in the style
  of the surrounding code. There is no docstring-coverage gate.
