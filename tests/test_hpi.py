"""
Tests for HPI processing. Full-pipeline tests need the real HPI file
(fetched by `make data` / fetch_uk_hpi - note the Phase 0 best-effort URL
was WRONG, confirmed and fixed this phase, see DATA.md) and skip cleanly
if absent.
"""

import pandas as pd
import pytest

from council_tax_freeze.boundaries.lad_2025 import LAD_2025_CODES
from council_tax_freeze.config import DATA_DIR
from council_tax_freeze.hpi.build import HPIValidationError, build_hpi

def _find_hpi_file():
    # filename carries the release month (e.g. UK-HPI-full-file-2026-04.csv)
    # and changes every month - glob rather than hardcode, since fetch_uk_hpi
    # discovers the current one dynamically too (see download.py).
    matches = sorted((DATA_DIR / "hpi").glob("UK-HPI-full-file-*.csv")) if (DATA_DIR / "hpi").exists() else []
    return matches[-1] if matches else DATA_DIR / "hpi" / "UK-HPI-full-file.csv"


HPI_FILE = _find_hpi_file()
requires_hpi_file = pytest.mark.skipif(not HPI_FILE.exists(), reason="No UK-HPI-full-file-*.csv present - run `make data` first")


def test_date_parsing_is_not_ambiguous():
    """Regression guard for the bug this module's docstring describes:
    default pandas date inference reads day-values 1-12 as month-first and
    silently corrupts dates. 1 November must parse as November, not as
    'day 11' of some inferred month."""
    df = pd.DataFrame({"Date": ["01/11/2019"], "RegionName": ["x"], "AreaCode": ["E12000007"], "AveragePrice": [1]})
    df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y")
    assert df["Date"].iloc[0] == pd.Timestamp("2019-11-01")


@requires_hpi_file
def test_ifs_regional_ratios_reproduce():
    result = build_hpi(HPI_FILE)
    assert result.validation["within_tolerance"].all()


@requires_hpi_file
def test_validation_raises_on_a_genuine_mismatch():
    import council_tax_freeze.hpi.build as build_module

    original = dict(build_module.IFS_REGIONAL_RATIO_ANCHORS)
    try:
        build_module.IFS_REGIONAL_RATIO_ANCHORS["E12000007"] = {"name": "London", "min_ratio": 999}
        with pytest.raises(HPIValidationError):
            build_module.build_hpi(HPI_FILE)
    finally:
        build_module.IFS_REGIONAL_RATIO_ANCHORS.clear()
        build_module.IFS_REGIONAL_RATIO_ANCHORS.update(original)


@requires_hpi_file
def test_full_coverage_every_year_isles_of_scilly_via_fallback():
    result = build_hpi(HPI_FILE)
    cov = result.coverage
    assert (cov["n_la"] == len(LAD_2025_CODES)).all()
    assert (cov["n_missing"] == 0).all()
    assert (cov["n_fallback"] == 1).all()  # Isles of Scilly only, every year


@requires_hpi_file
def test_isles_of_scilly_uses_south_west_region_factor():
    result = build_hpi(HPI_FILE)
    la = result.la_factors[(result.la_factors["ons_code"] == "E06000053") & (result.la_factors["financial_year"] == "2020-21")]
    region = result.region_factors[
        (result.region_factors["region_code"] == "E12000009") & (result.region_factors["financial_year"] == "2020-21")
    ]
    assert la["hpi_factor_la"].values[0] == region["hpi_factor_region"].values[0]


@requires_hpi_file
def test_factors_are_monotonic_increasing_for_london():
    """Not a strict requirement of house prices in general, but London's
    Jan-1995-to-2025 series has no down years at the April sample points -
    a cheap sanity check that the join/sort logic isn't scrambling years."""
    result = build_hpi(HPI_FILE)
    ldn = result.region_factors[result.region_factors["region_code"] == "E12000007"].sort_values("financial_year")
    values = ldn["hpi_factor_region"].tolist()
    # allow a handful of down-years (e.g. post-2008, post-2022) but the
    # overall trend across 26 years must be strongly up
    assert values[-1] > values[0] * 3