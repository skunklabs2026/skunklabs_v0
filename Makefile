# SkunkLabs MVP V0 — developer entry points.
#
# Start here:  make setup && make demo
#
# Every target is safe to re-run.

SHELL      := /bin/bash
VENV       := .venv
FRONTEND   := frontend
NOTEBOOKS  := backend/notebooks
VIDEO_DIR  := assets/videos
# The suite skips ~18 tests when these are absent, which silently drops
# backend coverage by 22 points — so they are a prerequisite of the test
# targets, not something to remember to run.
DEMO_VIDEO := $(VIDEO_DIR)/demo_drone.mp4
DEMO_CLIPS := $(DEMO_VIDEO) $(VIDEO_DIR)/demo_multirotor.mp4 $(VIDEO_DIR)/demo_fixed_wing.mp4

.DEFAULT_GOAL := help
.PHONY: help setup setup-backend setup-frontend setup-hooks setup-yolo lock demo dev-backend \
        dev-frontend demo-video marimo marimo-run test test-backend test-frontend test-cov \
        test-backend-cov test-frontend-cov test-frontend-watch lint format fmt-frontend \
        lint-backend lint-frontend typecheck typecheck-backend typecheck-frontend \
        depcheck security verify check build clean

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[38;5;173m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- setup

setup: setup-backend setup-frontend ## Install everything (first-run command)
	@echo "Ready. Run: make demo"

# uv reads .python-version, so the interpreter is declared in exactly one
# place. `uv sync` installs the locked versions rather than re-resolving, so a
# fresh checkout gets the environment CI got.
setup-backend: ## Install backend + dev dependencies from uv.lock
	uv sync --extra dev

setup-frontend: ## Install frontend dependencies
	cd $(FRONTEND) && npm install

setup-hooks: ## Install pre-commit hooks (runs checks on every commit)
	uvx pre-commit install

setup-yolo: ## Add the optional neural detector (~2 GB download)
	uv sync --extra dev --extra yolo

lock: ## Re-resolve and rewrite uv.lock after a dependency change
	uv lock
	@echo "Lockfile updated. Run 'make setup-backend' to install it."

# ---------------------------------------------------------------- running

demo: ## Start backend + UI together and open the console
	./run_demo.sh

dev-backend: ## Backend only, with autoreload
	$(VENV)/bin/uvicorn backend.main:app --reload --port 8000

dev-frontend: ## Frontend dev server only
	cd $(FRONTEND) && npm run dev

# The clip is synthesised, not committed (assets/videos/*.mp4 is gitignored),
# so anything that replays it has to be able to produce it first.
demo-video: $(DEMO_CLIPS) ## Generate the synthetic demo clips the tests replay
$(DEMO_VIDEO):
	$(VENV)/bin/python scripts/make_demo_video.py --output $@
$(VIDEO_DIR)/demo_multirotor.mp4:
	$(VENV)/bin/python scripts/make_demo_video.py --output $@ --platform multirotor
$(VIDEO_DIR)/demo_fixed_wing.mp4:
	$(VENV)/bin/python scripts/make_demo_video.py --output $@ --platform fixed_wing

# ---------------------------------------------------------------- notebooks

# Notebooks live in backend/notebooks/ so they can `import backend.*` directly
# — the package is installed editable by `make setup-backend`, so a notebook
# exercises the same code the pipeline runs, not a copy of it.
marimo: ## Open the marimo notebook editor on backend/notebooks/
	$(VENV)/bin/marimo edit $(NOTEBOOKS)

marimo-run: ## Serve a notebook read-only as an app (make marimo-run NB=foo.py)
	@test -n "$(NB)" || { echo "Usage: make marimo-run NB=<file.py>"; exit 2; }
	$(VENV)/bin/marimo run $(NOTEBOOKS)/$(NB)

# ---------------------------------------------------------------- quality

test: demo-video ## Run both backend and frontend test suites
	$(VENV)/bin/pytest
	cd $(FRONTEND) && npm run test

test-backend: demo-video ## Run the backend test suite only
	$(VENV)/bin/pytest

test-frontend: ## Run the frontend test suite only
	cd $(FRONTEND) && npm run test

test-cov: test-backend-cov test-frontend-cov ## Run all tests with coverage reports

test-backend-cov: demo-video ## Backend tests with coverage (term + xml for Codecov)
	$(VENV)/bin/pytest --cov=backend --cov-report=term-missing --cov-report=xml

test-frontend-cov: ## Frontend tests with coverage
	cd $(FRONTEND) && npm run test:cov

test-frontend-watch: ## Run frontend tests in watch mode
	cd $(FRONTEND) && npm run test:watch

lint: lint-backend lint-frontend ## Check Python and TypeScript

# $(VENV)/bin/ruff, not `uvx ruff`: uvx resolves the newest release every
# time, so the lint gate floated free of the pinned version and CI could go
# red on a ruff release with no change here.
lint-backend: ## Ruff check + format check
	$(VENV)/bin/ruff check backend tests scripts
	$(VENV)/bin/ruff format --check backend tests scripts

lint-frontend: ## ESLint + Prettier check
	cd $(FRONTEND) && npm run lint

format: ## Auto-fix formatting and safe lint errors
	$(VENV)/bin/ruff check --fix backend tests scripts
	$(VENV)/bin/ruff format backend tests scripts
	cd $(FRONTEND) && npm run format

fmt-frontend: ## Auto-fix frontend formatting only
	cd $(FRONTEND) && npm run format

typecheck: typecheck-backend typecheck-frontend ## Type-check both halves

typecheck-backend: ## Type-check the backend (mypy; config in pyproject.toml)
	$(VENV)/bin/mypy

typecheck-frontend: ## Type-check the frontend
	cd $(FRONTEND) && npm run typecheck

depcheck: ## Check for unused/missing dependencies (frontend)
	cd $(FRONTEND) && npm run depcheck

security: ## Scan Python and Node dependencies and code for known problems
	$(VENV)/bin/bandit -c pyproject.toml -r backend scripts -q
	$(VENV)/bin/pip-audit
	cd $(FRONTEND) && npm audit --audit-level=high

# Keep this list identical to the jobs in .github/workflows/ci.yml. Each CI
# job invokes one of these targets, so the only way they can disagree is if a
# job is added there without being added here.
check: lint typecheck test-backend test-frontend depcheck verify security ## Everything CI runs — do this before a PR

# ---------------------------------------------------------------- build

build: ## Production frontend build, served by the backend at :8000
	cd $(FRONTEND) && npm run build
	@echo "Built. Run 'make dev-backend' and open http://127.0.0.1:8000"

verify: demo-video ## Drive the pipeline headlessly through the full mission sequence
	$(VENV)/bin/python scripts/verify_pipeline.py --authorize

clean: ## Remove caches and build output
	find . -path ./$(VENV) -prune -o -name __pycache__ -type d -print0 | xargs -0 rm -rf
	rm -rf .pytest_cache .ruff_cache .mypy_cache coverage.xml \
	       $(FRONTEND)/dist $(FRONTEND)/coverage
