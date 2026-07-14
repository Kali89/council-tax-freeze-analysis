"""
Tests for the CTSOP parser, including the double-counting fix - see
parse.py's module docstring and DATA.md "CTSOP: a double-counting bug in
VOA's own consolidated file" for the full finding. Full-pipeline tests need
the real VOA files (fetched by `make data` / fetch_voa_ctsop) and skip
cleanly if absent.
"""

import pandas as pd
import pytest

from council_tax_freeze.config import DATA_DIR
from council_tax_freeze.parsers.ctsop.parse import (
    INDEPENDENT_NATIONAL_DWELLING_ANCHORS,
    CTSOPValidationError,
    build_ctsop,
    financial_year_from_snapshot,
)

CONSOLIDATED = DATA_DIR / "ctsop" / "CTSOP1_0_1993_2024" / "CTSOP1_0_1993_2024_03_31.csv"
STANDALONE_2025 = DATA_DIR / "ctsop" / "2025_summary.xlsx"
requires_ctsop_files = pytest.mark.skipif(
    not (CONSOLIDATED.exists() and STANDALONE_2025.exists()),
    reason=f"{CONSOLIDATED} / {STANDALONE_2025} not present - run `make data` first",
)


def test_financial_year_from_snapshot():
    assert financial_year_from_snapshot("2000") == "2000-01"
    assert financial_year_from_snapshot("2024") == "2024-25"


@requires_ctsop_files
def test_national_validation_passes_against_independent_anchors():
    result = build_ctsop(CONSOLIDATED, STANDALONE_2025)
    anchored = result.validation[result.validation["independent_anchor"].notna()]
    assert len(anchored) == len(INDEPENDENT_NATIONAL_DWELLING_ANCHORS)
    assert anchored["within_tolerance"].all()


@requires_ctsop_files
def test_validation_raises_on_a_genuine_mismatch():
    import council_tax_freeze.parsers.ctsop.parse as parse_module

    original = dict(parse_module.INDEPENDENT_NATIONAL_DWELLING_ANCHORS)
    try:
        parse_module.INDEPENDENT_NATIONAL_DWELLING_ANCHORS["2020-21"] = 1  # absurd, must fail
        with pytest.raises(CTSOPValidationError):
            parse_module.build_ctsop(CONSOLIDATED, STANDALONE_2025)
    finally:
        parse_module.INDEPENDENT_NATIONAL_DWELLING_ANCHORS.clear()
        parse_module.INDEPENDENT_NATIONAL_DWELLING_ANCHORS.update(original)


@requires_ctsop_files
def test_raw_file_shows_the_documented_duplication():
    """Pins the finding itself: the RAW (pre-fix) file really does
    double-count the 2019-2023 reorg waves by roughly 1.4-1.8 million
    dwellings a year, growing over time as those areas' stock grows. If
    this stops being true (VOA fixes their file), this test should fail
    and PREDECESSOR_CODES_TO_DROP should be revisited, not silently kept."""
    result = build_ctsop(CONSOLIDATED, STANDALONE_2025)
    dup = result.duplication_check
    pre_2025 = dup[dup["financial_year"] != "2025-26"]
    assert (pre_2025["excess"] > 1_000_000).all()
    assert (pre_2025["excess"] < 2_000_000).all()
    # the standalone 2025 file is NOT built the same (buggy) way - no
    # comparable excess there
    row_2025 = dup[dup["financial_year"] == "2025-26"]
    assert abs(row_2025["excess"].values[0]) < 10_000


@requires_ctsop_files
def test_fix_eliminates_the_duplication():
    """The whole point of PREDECESSOR_CODES_TO_DROP: post-fix, summing
    la_year should closely match the national row - not exactly (VOA's own
    NATL row vs LA-row sum has a small, immaterial residual, a few hundred
    dwellings out of tens of millions - see DATA.md) but within a tight
    fraction of a percent, not the ~7% the raw file shows."""
    result = build_ctsop(CONSOLIDATED, STANDALONE_2025)
    la_sum = result.la_year.groupby("financial_year")["all_properties"].sum()
    natl = result.national.set_index("financial_year")["published_national_total"]
    compared = pd.DataFrame({"la_sum": la_sum, "natl": natl}).dropna()
    compared = compared[(compared.index >= "2000-01") & (compared.index <= "2025-26")]
    relative_diff = (compared["la_sum"] - compared["natl"]).abs() / compared["natl"]
    assert (relative_diff < 0.001).all(), relative_diff[relative_diff >= 0.001]


@requires_ctsop_files
def test_predecessor_weights_preserved_not_discarded():
    """The dropped 2019-2023-wave predecessor rows must still exist
    somewhere - Phase 4 needs them as dwelling-count weights for combining
    Band D's predecessor-level rates. Confirms East Dorset specifically
    (the row that first revealed the duplication) ends up here, not lost."""
    result = build_ctsop(CONSOLIDATED, STANDALONE_2025)
    assert "E07000049" in set(result.predecessor_weights["ons_code"])  # East Dorset


@requires_ctsop_files
def test_no_ambiguous_resolutions():
    result = build_ctsop(CONSOLIDATED, STANDALONE_2025)
    assert (result.coverage["n_ambiguous"] == 0).all()


@requires_ctsop_files
def test_no_unmapped_resolutions_including_2025_26_boundary_snapshot():
    """Regression test for a real bug this parser's coverage report caught:
    the 2025-26 CTSOP snapshot is dated 31 March 2025, one day BEFORE the
    Barnsley/Sheffield boundary change took effect (1 April 2025), so it
    genuinely still uses the old codes. Resolving against the financial
    year's 1 April label (rather than the snapshot's own 31 March date)
    incorrectly flagged both as unmapped. Fixed in _coverage_report by
    using the snapshot date itself as `as_of`."""
    result = build_ctsop(CONSOLIDATED, STANDALONE_2025)
    cov = result.coverage
    cov = cov[(cov["financial_year"] >= "2000-01") & (cov["financial_year"] <= "2025-26")]
    assert (cov["n_unmapped"] == 0).all(), cov[cov["n_unmapped"] != 0]


@requires_ctsop_files
def test_coverage_is_flat_296_across_the_whole_period():
    """Unlike Band D (which shows a declining count as predecessor rows
    genuinely disappear), CTSOP's coverage should be a flat 296 for every
    year - VOA's retroactive aggregation (once de-duplicated) means there's
    no time variation in identity count the way Band D has."""
    result = build_ctsop(CONSOLIDATED, STANDALONE_2025)
    cov = result.coverage
    cov = cov[(cov["financial_year"] >= "2000-01") & (cov["financial_year"] <= "2025-26")]
    assert (cov["n_la_rows"] == 296).all(), cov[cov["n_la_rows"] != 296]
