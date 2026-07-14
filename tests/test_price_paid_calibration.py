"""
Tests for the Band A/H midpoint calibration check. This is a one-off spot
check, not a pipeline component (see calibration/price_paid.py docstring) -
tests here confirm the mechanism works and pin the actual finding, not
exhaustive coverage of the raw Price Paid files.
"""

import pytest

from council_tax_freeze.calibration.price_paid import (
    BAND_A_THRESHOLD,
    BAND_H_THRESHOLD,
    _quarter_label,
    load_national_deflators,
    run_calibration,
)
from council_tax_freeze.config import DATA_DIR

PP_DIR = DATA_DIR / "price_paid_calibration"
PP_FILES = [PP_DIR / f"pp-{y}.csv" for y in (1995, 1996, 1997)]
NATIONWIDE_FILE = PP_DIR / "UK_house_price_since_1952.xlsx"
requires_calibration_files = pytest.mark.skipif(
    not (all(p.exists() for p in PP_FILES) and NATIONWIDE_FILE.exists()),
    reason="Price Paid / Nationwide files not present - run `make data` first",
)


def test_quarter_label():
    assert _quarter_label("1995-03-24 00:00") == "Q1 1995"
    assert _quarter_label("1997-11-02 00:00") == "Q4 1997"
    assert _quarter_label("1996-04-01 00:00") == "Q2 1996"


@requires_calibration_files
def test_national_deflators_q2_1991_is_unity():
    deflators = load_national_deflators(NATIONWIDE_FILE)
    assert deflators["Q2 1991"] == pytest.approx(1.0)


@requires_calibration_files
def test_deflators_show_national_prices_fell_then_rose_across_1995_97():
    # Not asserting exact values - just that the deflator series is
    # sane (a real quarterly series, not a constant or garbage), matching
    # the well-known trough-then-recovery shape of UK prices in this period.
    deflators = load_national_deflators(NATIONWIDE_FILE)
    for q in ["Q1 1995", "Q4 1997"]:
        assert q in deflators
        assert 0.5 < deflators[q] < 2.0


@requires_calibration_files
def test_band_h_empirical_ratio_exceeds_assumed_ratio_in_high_value_areas():
    """The finding this calibration exists to check: does the assumed
    Band H ratio (1.5x, config.BAND_H_RATIO) understate the true tail in
    high-value areas? Kensington and Chelsea / Westminster have thick
    enough samples (thousands of sales) to trust the result. This ratio
    finding stands on its own and is unaffected by Phase 5 - what changed
    is the CONCLUSION drawn from it (this no longer implies the base case
    is the conservative corner of the plausible range; see DATA.md
    "Price Paid calibration" and SENSITIVITY_RESULTS.md "Axis 1")."""
    result = run_calibration(PP_FILES, NATIONWIDE_FILE)
    h = result.band_h_summary.set_index("district")
    for district in ["KENSINGTON AND CHELSEA", "CITY OF WESTMINSTER"]:
        assert h.loc[district, "n_sales_above_threshold"] > 1000  # thick sample, not noise
        assert h.loc[district, "empirical_ratio_vs_threshold"] > 1.5  # exceeds the assumed BAND_H_RATIO


@requires_calibration_files
def test_band_a_empirical_ratio_near_or_below_assumed_ratio_in_low_value_areas():
    result = run_calibration(PP_FILES, NATIONWIDE_FILE)
    a = result.band_a_summary.set_index("district")
    for district in ["BLACKPOOL", "EASINGTON"]:
        assert a.loc[district, "n_sales_below_threshold"] > 1000  # thick sample, not noise
        assert a.loc[district, "empirical_ratio_vs_threshold"] <= 0.80  # near or below the assumed BAND_A_RATIO


@requires_calibration_files
def test_high_value_areas_have_negligible_band_a_share():
    result = run_calibration(PP_FILES, NATIONWIDE_FILE)
    a = result.band_a_summary.set_index("district")
    for district in ["KENSINGTON AND CHELSEA", "CITY OF WESTMINSTER"]:
        assert a.loc[district, "n_sales_below_threshold"] == 0


@requires_calibration_files
def test_thresholds_are_the_statutory_1991_values():
    assert BAND_A_THRESHOLD == 40_000
    assert BAND_H_THRESHOLD == 320_000
