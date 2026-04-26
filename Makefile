# Cross-platform make targets. On Windows, run via `gmake` from msys2 / WSL.

PYTHON      ?= python3
PIP         ?= $(PYTHON) -m pip
PYTEST      ?= $(PYTHON) -m pytest
RUFF        ?= $(PYTHON) -m ruff
BLACK       ?= $(PYTHON) -m black
MYPY        ?= $(PYTHON) -m mypy

SRC         := src/photo_mcp
TESTS       := tests

.PHONY: help install lint format type test test-fast test-cov build dist clean

help:
	@echo "Targets:"
	@echo "  install      pip install -e '.[test,dev,http]'"
	@echo "  lint         ruff + mypy"
	@echo "  format       black + ruff --fix"
	@echo "  type         mypy --strict"
	@echo "  test         full pytest with coverage gate"
	@echo "  test-fast    pytest without coverage"
	@echo "  build        wheel"
	@echo "  dist         wheel + standalone binary (PyInstaller)"
	@echo "  clean        rm build artifacts"

install:
	$(PIP) install -e '.[test,dev,http]'

lint:
	$(RUFF) check $(SRC) $(TESTS)
	$(MYPY) $(SRC)

format:
	$(BLACK) $(SRC) $(TESTS)
	$(RUFF) check --fix $(SRC) $(TESTS)

type:
	$(MYPY) $(SRC)

test:
	$(PYTEST) --cov=photo_mcp --cov-report=term --cov-report=xml --cov-fail-under=90

test-fast:
	$(PYTEST) -x --no-cov

build:
	$(PYTHON) -m build --wheel

dist: build
	$(PYTHON) -m PyInstaller --onefile --name photo-mcp src/photo_mcp/__main__.py

clean:
	rm -rf build dist *.egg-info .coverage coverage.xml htmlcov .mypy_cache .pytest_cache .ruff_cache
