.PHONY: all data notebooks test lint clean

# Every parsing/counterfactual/regression/aggregate step lives in
# src/council_tax_freeze/ as an IMPORTABLE library, not a standalone CLI
# script - notebooks/03_results.ipynb is what actually calls the pipeline
# end to end and produces the charts in outputs/. An earlier version of
# this Makefile assumed each module (parsers.band_d, engine.build,
# sensitivity, regression.variant3, ...) had its own runnable __main__;
# none of them do, and pretending otherwise here would be exactly the
# kind of misleading state this project's own methodology exists to
# avoid. `make all` therefore fetches data, then executes the notebooks
# (which import and run the real pipeline), then tests.
all: data notebooks test

data:
	uv run python -m council_tax_freeze.download

notebooks:
	uv run jupyter nbconvert --to notebook --execute --inplace notebooks/02_method.ipynb notebooks/03_results.ipynb

test:
	uv run pytest -q

lint:
	uv run ruff check src/ tests/

clean:
	rm -rf outputs/*
	find . -name __pycache__ -type d -exec rm -rf {} +
