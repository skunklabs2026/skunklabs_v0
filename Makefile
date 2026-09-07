# SkunkLabs MVP V0 — developer entry points.
#
# Start here:  make setup && make demo
#
# Every target is safe to re-run.

SHELL   := /bin/bash
VENV    := .venv
PYTHON  := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
FRONTEND := frontend

.DEFAULT_GOAL := help
.PHONY: help setup setup-backend setup-frontend setup-yolo demo dev-backend dev-frontend \
        test test-cov lint format typecheck check build clean

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[38;5;173m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- setup

setup: setup-backend setup-frontend ## Install everything (first-run command)
	@echo "Ready. Run: make demo"

setup-backend: ## Create the venv and install backend + dev dependencies
	@test -d $(VENV) || python3 -m venv $(VENV)
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -e ".[dev]"

setup-frontend: ## Install frontend dependencies
	cd $(FRONTEND) && npm install

setup-yolo: ## Add the optional neural detector (~2 GB download)
	$(PIP) install -e ".[yolo]"

# ---------------------------------------------------------------- running

demo: ## Start backend + UI together and open the console
	./run_demo.sh

dev-backend: ## Backend only, with autoreload
	$(VENV)/bin/uvicorn backend.main:app --reload --port 8000

dev-frontend: ## Frontend dev server only
	cd $(FRONTEND) && npm run dev

# ---------------------------------------------------------------- quality

test: ## Run the backend test suite
	$(PYTHON) -m pytest

test-cov: ## Run tests with a coverage report
	$(PYTHON) -m pytest --cov=backend --cov-report=term-missing

lint: ## Check Python and TypeScript
	$(VENV)/bin/ruff check backend tests scripts
	$(VENV)/bin/ruff format --check backend tests scripts
	cd $(FRONTEND) && npm run lint

format: ## Auto-fix formatting and safe lint errors
	$(VENV)/bin/ruff check --fix backend tests scripts
	$(VENV)/bin/ruff format backend tests scripts
	cd $(FRONTEND) && npm run format

typecheck: ## Type-check the frontend
	cd $(FRONTEND) && npm run typecheck

check: lint typecheck test ## Everything CI runs — do this before a PR

# ---------------------------------------------------------------- build

build: ## Production frontend build, served by the backend at :8000
	cd $(FRONTEND) && npm run build
	@echo "Built. Run 'make dev-backend' and open http://127.0.0.1:8000"

verify: ## Drive the pipeline headlessly through the full mission sequence
	$(PYTHON) scripts/verify_pipeline.py

clean: ## Remove caches and build output
	find . -path ./$(VENV) -prune -o -name __pycache__ -type d -print0 | xargs -0 rm -rf
	rm -rf .pytest_cache .ruff_cache $(FRONTEND)/dist
