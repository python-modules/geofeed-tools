PYTHON ?= .venv/bin/python
PYTEST ?= $(PYTHON) -m pytest
RUFF ?= $(PYTHON) -m ruff
REPORT ?= reports/pytest-report.html

.PHONY: help lint test test-html test-integration clean-reports

help:
	@echo "Available targets:"
	@echo "  make lint             Run Ruff lint checks"
	@echo "  make test             Run non-integration tests"
	@echo "  make test-html        Run non-integration tests and generate HTML report"
	@echo "  make test-integration Run integration tests (real HTTP requests)"
	@echo "  make clean-reports    Remove generated test reports"

lint:
	$(RUFF) check src tests

test:
	$(PYTEST) -q -m "not integration" -o addopts=""

test-html:
	$(PYTEST) -q -m "not integration" -o addopts="" \
		--html=$(REPORT) --self-contained-html

test-integration:
	$(PYTEST) -v -m integration -o addopts=""

clean-reports:
	rm -rf reports
