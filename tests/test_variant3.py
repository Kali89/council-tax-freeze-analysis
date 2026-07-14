"""
Tests for the Variant 3 (rate-setting) regression. This is the module
whose finding is the strongest result in the project - the IFS objection
is tested and does not hold outside London (see regression/variant3.py
module docstring for the full account). Tests pin the actual numbers, not
just structural properties, and the one hard rule this module enforces:
the pooled/London-only coefficient must never be applied to a non-London
LA.
"""

import pytest

from council_tax_freeze.config import DATA_DIR
from council_tax_freeze.engine.build import build_engine
from council_tax_freeze.hpi.build import build_hpi
from council_tax_freeze.parsers.band_d.parse import build_band_d
from council_tax_freeze.parsers.ctsop.parse import build_ctsop
from council_tax_freeze.parsers.settlement.parse import build_settlement
from council_tax_freeze.regression.variant3 import build_variant3_panel, interpret_offset, run_variant3_regression, within_la_correlation

BAND_D_FILE = DATA_DIR / "band_d" / "Band_D_1993_onwards.ods"
CTSOP_CONSOLIDATED = DATA_DIR / "ctsop" / "CTSOP1_0_1993_2024" / "CTSOP1_0_1993_2024_03_31.csv"
CTSOP_2025 = DATA_DIR / "ctsop" / "2025_summary.xlsx"
SETTLEMENT_FILE = DATA_DIR / "settlement" / "CSP_information_table_LGFS_2025-26.xlsx"


def _hpi_file():
    matches = sorted((DATA_DIR / "hpi").glob("UK-HPI-full-file-*.csv")) if (DATA_DIR / "hpi").exists() else []
    return matches[-1] if matches else None


HPI_FILE = _hpi_file()
requires_all_data = pytest.mark.skipif(
    not (BAND_D_FILE.exists() and CTSOP_CONSOLIDATED.exists() and CTSOP_2025.exists() and SETTLEMENT_FILE.exists() and HPI_FILE),
    reason="Band D / CTSOP / HPI / settlement files not present - run `make data` first",
)


@pytest.fixture(scope="module")
def loaded():
    bd = build_band_d(BAND_D_FILE)
    ct = build_ctsop(CTSOP_CONSOLIDATED, CTSOP_2025)
    hpi = build_hpi(HPI_FILE)
    settlement = build_settlement(SETTLEMENT_FILE, ct.la_year)
    eng = build_engine(bd.la_year, ct.la_year, ct.predecessor_weights, hpi.la_factors, hpi.national_factors)
    panel = build_variant3_panel(bd.la_year, ct.la_year, hpi.la_factors, hpi.national_factors, settlement.la_year)
    return panel, eng


@requires_all_data
def test_pooled_coefficient_is_negative_and_tightly_significant(loaded):
    panel, _ = loaded
    result = run_variant3_regression(panel, "pooled")
    assert result.coefficient < -0.02
    assert result.conf_int[1] < 0  # whole CI below zero
    assert result.pvalue < 0.001


@requires_all_data
def test_non_london_is_a_tight_null_not_a_noisy_one(loaded):
    """The primary result (see module docstring): across 263 non-London
    LAs, the CI is narrow enough to rule out an economically meaningful
    offset - a tight null. Pins both halves of that claim: the point
    estimate is small, AND the CI itself is narrow (not just
    insignificant because of huge uncertainty)."""
    panel, _ = loaded
    result = run_variant3_regression(panel, "non_london")
    assert abs(result.coefficient) < 0.01
    assert result.conf_int[1] - result.conf_int[0] < 0.02  # narrow CI
    assert result.pvalue > 0.05


@requires_all_data
def test_within_la_correlation_is_the_decisive_diagnostic(loaded):
    """The number that actually establishes the London/non-London split
    (not the regression p-values, which are affected by cluster count) -
    -0.57 in London, +0.08 (effectively zero, wrong sign for the
    objection) elsewhere."""
    panel, _ = loaded
    london_corr = within_la_correlation(panel, "london")
    non_london_corr = within_la_correlation(panel, "non_london")
    assert london_corr < -0.4
    assert -0.1 < non_london_corr < 0.2


@requires_all_data
def test_pooled_result_cannot_be_applied_to_a_non_london_la(loaded):
    """The one hard rule: extrapolating London's within-LA relationship
    onto a non-London LA must raise, not silently compute a number -
    Hartlepool is the named example (see project log)."""
    panel, eng = loaded
    pooled = run_variant3_regression(panel, "pooled")
    with pytest.raises(ValueError, match="not in London"):
        interpret_offset(pooled, eng.la_year, "E06000001", bound="ceiling")  # Hartlepool


@requires_all_data
def test_non_london_result_cannot_be_applied_to_a_london_la(loaded):
    panel, eng = loaded
    non_london = run_variant3_regression(panel, "non_london")
    with pytest.raises(ValueError, match="is in London"):
        interpret_offset(non_london, eng.la_year, "E09000033", bound="ceiling")  # Westminster


@requires_all_data
def test_non_london_ceiling_offset_for_northern_headline_las_is_small(loaded):
    """The number that DOES belong in the write-up: even at the ceiling
    of what the non-London data supports, the implied offset for the
    Northern headline LAs is a small fraction of their measured gap."""
    panel, eng = loaded
    non_london = run_variant3_regression(panel, "non_london")
    for code in ("E06000001", "E06000047", "E06000009"):  # Hartlepool, County Durham, Blackpool
        interp = interpret_offset(non_london, eng.la_year, code, bound="ceiling")
        assert 0 <= interp["implied_offset_share_of_measured_gap"] < 0.05


@requires_all_data
def test_pooled_ceiling_offset_for_westminster_is_sizeable_but_flagged_as_confound(loaded):
    """The pooled/London figure IS large if taken at face value - reported
    prominently, not because it's trusted as genuine compensation, but
    because a reader who runs the pooled regression should find this
    number already here, with the diagnosis attached (see module
    docstring: confounding via the Phase 4 business-rate/reserves
    mechanism, not genuine rate-setting response to appreciation)."""
    panel, eng = loaded
    pooled = run_variant3_regression(panel, "pooled")
    interp = interpret_offset(pooled, eng.la_year, "E09000033", bound="ceiling")  # Westminster
    assert abs(interp["implied_offset_share_of_measured_gap"]) > 0.1
