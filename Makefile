# Orrin developer task interface (CODEBASE_CLEANUP_PLAN Phase 0/1).
#
# One documented entry point for the standard local verification set. CI runs
# the same targets, so "make verify" locally == the gate.
#
#   make verify      backend lint + tests, then frontend typecheck + build
#   make test        pytest (hermetic; see tests/conftest.py)
#   make lint        ruff check (narrow high-signal config in pyproject.toml)
#   make lint-fix    ruff check --fix (safe autofixes only)
#   make format      ruff format (NOT run in verify — reformats in place)
#   make fe-typecheck / fe-build / fe-lint   frontend equivalents
#
# Uses the project venv if present, else python3 on PATH.

PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
RUFF   := $(PYTHON) -m ruff
MYPY   := $(PYTHON) -m mypy

.DEFAULT_GOAL := help
.PHONY: help verify test lint lint-fix format py-typecheck audit-exceptions size-report coverage coverage-update audit-deps telemetry-types fe-typecheck fe-build fe-lint frontend

help:
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) 2>/dev/null | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' || \
		echo "see the header of this Makefile for targets"

verify: lint py-typecheck test fe-typecheck fe-build ## Full local verification set (== CI gate)

test: ## Run the Python test suite (hermetic)
	$(PYTHON) -m pytest -q

lint: ## Ruff lint (high-signal rules; must be green)
	$(RUFF) check .

py-typecheck: ## mypy strict check of the typed-module allowlist (pyproject [tool.mypy].files)
	$(MYPY)

lint-fix: ## Ruff lint with safe autofixes applied
	$(RUFF) check --fix .

format: ## Ruff format in place (run deliberately; not part of verify)
	$(RUFF) format .

audit-exceptions: ## Report broad exception handlers that silently discard failures
	$(PYTHON) brain/scripts/audit_exception_handlers.py

size-report: ## Report source modules by size; flag >600-line soft-limit (ratchet: tests/test_module_size.py)
	$(PYTHON) -m brain.scripts.size_report --warn-only

coverage: ## Run the suite under coverage and gate against the recorded floor (.coverage-floor)
	$(PYTHON) -m coverage run -m pytest -q
	$(PYTHON) -m coverage json -o coverage.json >/dev/null
	$(PYTHON) -m coverage report
	$(PYTHON) -m brain.scripts.coverage_ratchet

coverage-update: ## Raise the coverage floor to current after coverage gains (run `make coverage` first)
	$(PYTHON) -m brain.scripts.coverage_ratchet --update

audit-deps: ## Report dependency vulnerabilities + outdated packages (pip-audit; informational)
	$(PYTHON) -m pip_audit --desc || true

telemetry-types: ## Regenerate the FE telemetry wire types (zod + TS) from schema.py
	$(PYTHON) -m backend.server.generate_telemetry_ts

fe-typecheck: ## Frontend TypeScript type-check
	cd frontend && npm run typecheck

fe-build: ## Frontend production build
	cd frontend && npm run build

fe-lint: ## Frontend ESLint
	cd frontend && npm run lint

frontend: fe-typecheck fe-lint fe-build ## All frontend checks
