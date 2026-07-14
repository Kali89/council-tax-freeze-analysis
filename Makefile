.PHONY: all data harmonise parse counterfactual sensitivity settlement notebooks test clean

# Full pipeline: raw downloads -> parsed data -> counterfactuals -> maps.
# Each target's script fails loudly (not silently) on validation errors,
# per DATA.md and the per-vintage parser design.
all: data harmonise parse counterfactual sensitivity settlement notebooks

data:
	uv run python -m council_tax_freeze.download

harmonise:
	uv run python -m council_tax_freeze.boundaries.build_crosswalk

parse:
	uv run python -m council_tax_freeze.parsers.band_d.build
	uv run python -m council_tax_freeze.parsers.ctsop.build
	uv run python -m council_tax_freeze.hpi.build

counterfactual:
	uv run python -m council_tax_freeze.engine.build

sensitivity:
	uv run python -m council_tax_freeze.sensitivity.run

settlement:
	uv run python -m council_tax_freeze.parsers.settlement.build
	uv run python -m council_tax_freeze.regression.variant3

notebooks:
	uv run jupyter nbconvert --to notebook --execute --inplace notebooks/*.ipynb

test:
	uv run pytest

clean:
	rm -rf outputs/*
	find . -name __pycache__ -type d -exec rm -rf {} +
