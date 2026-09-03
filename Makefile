PYTHON ?= python
PYTHON_FILES = src tests tools examples

.PHONY: install format lint typecheck test coverage verify

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

format:
	$(PYTHON) -m black $(PYTHON_FILES)
	$(PYTHON) -m isort $(PYTHON_FILES)

lint:
	$(PYTHON) -m black --check $(PYTHON_FILES)
	$(PYTHON) -m isort --check-only $(PYTHON_FILES)
	$(PYTHON) -m ruff check $(PYTHON_FILES)

typecheck:
	$(PYTHON) -m mypy --strict $(PYTHON_FILES)

test:
	$(PYTHON) -m pytest

coverage:
	$(PYTHON) tools/check_coverage.py --input coverage.xml --minimum-line-rate 90 --minimum-branch-rate 80

verify: lint typecheck test coverage
