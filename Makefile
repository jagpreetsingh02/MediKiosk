# MediKiosk. Plain venv + pip, no uv, no poetry.

VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip
export PYTHONPATH := .

.PHONY: help setup demo api web test lint fmt eval eval-strict ocr-bench fixtures check clean

help:
	@echo "make setup        create the venv and install everything"
	@echo "make demo         run the API and the frontend together (one command)"
	@echo "make test         run the whole test suite"
	@echo "make lint         ruff + mypy + tsc"
	@echo "make eval         the 50 gold scripts plus the held-out set"
	@echo "make eval-strict  the same, exiting non-zero on any hard-target failure"
	@echo "make ocr-bench    compare the two OCR backends against ground truth"
	@echo "make check        lint + test + eval-strict  (run this before committing)"

setup:
	python3.12 -m venv $(VENV)
	$(PIP) install -q --upgrade pip setuptools wheel
	$(PIP) install -q -r requirements-dev.txt
	cd frontend && npm install --silent
	@echo "Ready. Now run: make demo"

demo:
	./scripts/demo.sh

api:
	$(PY) -m uvicorn app.main:app --reload --port 8000

web:
	cd frontend && npm run dev

test:
	$(PY) -m pytest tests/ -q

lint:
	$(VENV)/bin/ruff check app tests eval scripts
	$(VENV)/bin/mypy app
	cd frontend && npx tsc --noEmit

fmt:
	$(VENV)/bin/ruff check --fix app tests eval scripts
	$(VENV)/bin/ruff format app tests eval scripts

eval:
	$(PY) -m eval.runner --both

eval-strict:
	$(PY) -m eval.runner --both --strict

ocr-bench:
	$(PY) -m eval.ocr_bench

fixtures:
	$(PY) scripts/make_document_fixtures.py
	$(PY) scripts/make_eval_scripts.py
	$(PY) scripts/make_holdout_scripts.py

check: lint test eval-strict
	@echo ""
	@echo "All checks passed."

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache medikiosk.db
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
