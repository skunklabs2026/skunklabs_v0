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
| `make setup-backend` | `uv sync --extra dev` — installs from `uv.lock` |
| `make setup-frontend` | `npm install` in `frontend/` |
| `make setup-hooks` | install the pre-commit hooks |
| `make setup-yolo` | add the optional neural detector (`.[yolo]`, ~2 GB) |
| `make lock` | re-resolve `uv.lock` after changing a dependency |
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
| `make typecheck` | mypy over `backend/` + `tsc` over `frontend/` |
| `make typecheck-backend` | mypy only |
| `make typecheck-frontend` | `tsc` only |
| `make security` | bandit + pip-audit + `npm audit` |
| `make depcheck` | unused/missing frontend dependencies |
| `make check` | `lint typecheck test-backend test-frontend depcheck verify security` — **run before opening a PR**, and exactly what CI runs |
| `make build` | production frontend build, served by the backend at :8000 |
| `make verify` | drive the pipeline headlessly through the full mission sequence |
| `make clean` | remove caches and build output |

Python quality is `ruff` (lint/format), `mypy` (types, `[tool.mypy]` in
`pyproject.toml`, scoped to `backend/`), the pytest suite, and `bandit` +
`pip-audit`. `scripts/` is linted and scanned but not yet type-checked — three
opencv/numpy stub gaps stand in the way, noted in the mypy config.

**The dependency set is locked.** `uv.lock` is committed and is the only
pinned path — there is no `requirements.txt`. Change a version in
`pyproject.toml`, then run `make lock`. `[tool.uv] constraint-dependencies`
carries floors on *transitive* packages that a direct pin cannot reach; each
entry names the advisory that forced it, and `make security` is what tells you
when one is needed or can be dropped.

Every CI job in `.github/workflows/ci.yml` invokes a `make` target rather than
repeating its commands, and third-party actions are pinned to commit SHAs. If
you add a gate, add it to **both** the `check` target and a CI job — the
comment above `check` says so too.

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

## Conventions

- **Frontend tests live beside the code they test**, with shared telemetry
  fixtures in `frontend/src/test/factories.ts` — build test data from those
  rather than hand-rolling objects, so a `types.ts` regeneration breaks one
  file. `src/test/helpers.ts` has `expectRenderErrors()`, which silences
  jsdom's stack traces for suites that throw during render on purpose; scope
  it to those suites so an unexpected throw stays loud.
- **Tests** live in `tests/` (`[tool.pytest.ini_options] testpaths = ["tests"]`,
  `addopts = "-q --strict-markers"`), one `test_*.py` per backend concern:
  `test_api.py`, `test_state_machine.py`, `test_rules.py`, `test_tracker.py`,
  `test_trajectory.py`, `test_classification.py`, `test_video_library.py`.
  Shared fixtures go in `tests/conftest.py`. Frontend component tests live
  beside the components and run under Vitest.
- **Coverage is 90%, enforced on both sides.** Backend: **branch** coverage
  over `backend`, `[tool.coverage.report] fail_under = 90` against ~93%
  actual. Frontend: all four metrics at 90 in `frontend/vite.config.ts`,
  against ~96-99%. Two exclusions, both because counting them would report a
  permanently unfixable gap: `YoloDetector` (`# pragma: no cover`, needs the
  2 GB extra CI does not install) and `frontend/src/main.tsx` (the bootstrap).
  Raise the thresholds as coverage rises; never lower one to make a red build
  green — a change that drops coverage owes a test. Check the real value
  before quoting a number anywhere.
- **The tests need the demo clips.** `tests/` skips ~18 tests when
  `assets/videos/demo_{drone,multirotor,fixed_wing}.mp4` are absent — a silent
  22-point drop in backend coverage. `make test-backend` depends on
  `demo-video`, which generates them; never call `pytest` directly in CI.
- **Vision accuracy is deliberately not unit-tested.** Use
  `scripts/verify_pipeline.py` against real footage instead of asserting on
  detector output. It runs in CI as the `verify` job (`make verify`), which
  generates the demo clip first if it is missing.
- **Docstring examples are executed.** `addopts` carries `--doctest-modules`
  and `testpaths` includes `backend`, so a `>>>` in a docstring is a test.
  That is why the safety banners use `=== SAFETY SCOPE ===` rather than
  `>>> SAFETY SCOPE <<<`, which doctest parses as code and fails on.
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
