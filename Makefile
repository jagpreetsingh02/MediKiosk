# MediKiosk. Plain venv + pip, no uv, no poetry.

VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip
export PYTHONPATH := .

.PHONY: help setup demo api web test lint fmt eval eval-strict eval-hosted ocr-bench fixtures check clean

help:
	@echo "make setup        create the venv and install everything"
	@echo "make demo         run the API and the frontend together (one command)"
	@echo "make test         run the whole test suite"
	@echo "make lint         ruff + mypy + tsc"
	@echo "make eval         the 50 gold scripts plus the held-out set"
	@echo "make eval-strict  the same on the offline extractor, non-zero on a hard-target failure"
	@echo "make eval-hosted  the same against the hosted model — reports, never gates"
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

supabase-check:
	@$(PY) scripts/check_supabase.py

e2e:
	@echo "Both browser suites. The stack must already be running (make demo)."
	cd frontend && node e2e/smoke.mjs && node e2e/interaction.mjs

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

# Pinned to the offline extractor deliberately, and this is the gate `make check` runs.
#
# The strict gate exists to fail the build when OUR code regresses hallucination rate or
# red-flag sensitivity. Run against the hosted model it fails for a different reason: on the
# development set `gpt-oss-120b` scores 0.9333 red-flag sensitivity against a >=0.98 target,
# which is a published, expected property of that backend (docs/EVALUATION.md) and not a
# regression in this repo. Worse, it is not reproducible — the vendor can change the model
# under us. A gate that is permanently red on any machine holding a Groq key is a gate people
# learn to ignore.
#
# The offline extractor is also what the shipped kiosk runs. `make eval-hosted` publishes the
# comparison; nothing here hides it.
eval-strict:
	LLM_BACKEND=offline $(PY) -m eval.runner --both --strict

# The hosted comparison. Reports, never gates — see above.
eval-hosted:
	LLM_BACKEND=groq $(PY) -m eval.runner --both

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
