# SkunkLabs MVP V0 — developer entry points.
#
# Start here:  make setup && make demo
#
# Every target is safe to re-run.

SHELL    := /bin/bash
VENV     := .venv
FRONTEND := frontend

.DEFAULT_GOAL := help
.PHONY: help setup setup-backend setup-frontend setup-hooks setup-yolo setup-research \
        demo dev-backend dev-frontend notebook marimo eda eda-sample eda-check \
        test test-backend test-frontend test-cov test-frontend-watch \
        lint format fmt-frontend typecheck typecheck-frontend depcheck check build verify clean

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[38;5;173m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- setup

setup: setup-backend setup-frontend ## Install everything (first-run command)
	@echo "Ready. Run: make demo"

setup-backend: ## Install backend + dev dependencies
	@test -d $(VENV) || uv venv $(VENV) --python 3.11
	uv pip install -e ".[dev]"

setup-frontend: ## Install frontend dependencies
	cd $(FRONTEND) && npm install

setup-hooks: ## Install pre-commit hooks (runs checks on every commit)
	uvx pre-commit install

setup-yolo: ## Add the optional neural detector (~2 GB download)
	uv pip install -e ".[yolo]"

setup-research: ## Add the notebook/EDA toolchain (marimo, pandas, matplotlib)
	uv pip install -e ".[research]"

# ---------------------------------------------------------------- running

demo: ## Start backend + UI together and open the console
	./run_demo.sh

dev-backend: ## Backend only, with autoreload
	$(VENV)/bin/uvicorn backend.main:app --reload --port 8000

dev-frontend: ## Frontend dev server only
	cd $(FRONTEND) && npm run dev

# ---------------------------------------------------------------- research
#
# Offline dataset analysis. Nothing here is part of the demo, and nothing in
# backend/ imports it. Needs `make setup-research` first.

notebook: ## Open the marimo notebook browser on notebooks/
	$(VENV)/bin/marimo edit notebooks/

marimo: notebook ## Open the marimo notebook browser (alias)

eda: ## Fetch everything the notebook needs cheaply (~18 MB, no bulk download)
	$(VENV)/bin/python scripts/fetch_mmaud.py --download meta
	$(VENV)/bin/python scripts/fetch_mmaud.py --index val
	$(VENV)/bin/python scripts/fetch_mmaud.py --labels train

eda-sample: ## Pull a small random sample of real frames for the plotting cells
	$(VENV)/bin/python scripts/fetch_mmaud.py --sample val

eda-check: ## Run the EDA notebook headlessly as a script, plus marimo's own checks
	$(VENV)/bin/marimo check notebooks/01_mmaud_eda.py
	$(VENV)/bin/python notebooks/01_mmaud_eda.py
	@echo "EDA notebook executed cleanly"

# ---------------------------------------------------------------- quality

test: ## Run both backend and frontend test suites
	$(VENV)/bin/pytest
	cd $(FRONTEND) && npm run test

test-backend: ## Run the backend test suite only
	$(VENV)/bin/pytest

test-frontend: ## Run the frontend test suite only
	cd $(FRONTEND) && npm run test

test-cov: ## Run all tests with coverage reports
	$(VENV)/bin/pytest --cov=backend --cov-report=term-missing
	cd $(FRONTEND) && npm run test:cov

test-frontend-watch: ## Run frontend tests in watch mode
	cd $(FRONTEND) && npm run test:watch

lint: ## Check Python and TypeScript
	uvx ruff check backend tests scripts
	uvx ruff format --check backend tests scripts
	cd $(FRONTEND) && npm run lint

format: ## Auto-fix formatting and safe lint errors
	uvx ruff check --fix backend tests scripts
	uvx ruff format backend tests scripts
	cd $(FRONTEND) && npm run format

fmt-frontend: ## Auto-fix frontend formatting only
	cd $(FRONTEND) && npm run format

typecheck: ## Type-check the frontend
	cd $(FRONTEND) && npm run typecheck

typecheck-frontend: ## Type-check the frontend (alias)
	cd $(FRONTEND) && npm run typecheck

depcheck: ## Check for unused/missing dependencies (frontend)
	cd $(FRONTEND) && npm run depcheck

check: lint typecheck test-backend test-frontend ## Everything CI runs — do this before a PR

# ---------------------------------------------------------------- build

build: ## Production frontend build, served by the backend at :8000
	cd $(FRONTEND) && npm run build
	@echo "Built. Run 'make dev-backend' and open http://127.0.0.1:8000"

verify: ## Drive the pipeline headlessly through the full mission sequence
	$(VENV)/bin/python scripts/verify_pipeline.py

clean: ## Remove caches and build output
	find . -path ./$(VENV) -prune -o -name __pycache__ -type d -print0 | xargs -0 rm -rf
	rm -rf .pytest_cache .ruff_cache coverage.xml htmlcov $(FRONTEND)/dist $(FRONTEND)/coverage
