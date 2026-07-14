"""
Phase 5 sensitivity gate. Thresholds are copied VERBATIM from
SENSITIVITY_PREREGISTRATION.md, committed before this sweep was run (see
that file's own commit for the timestamp evidence) - do not adjust a
threshold here to make a result pass. If a result demands a different
question, that's a new, separately dated document and a new test, not an
edit to this one.

Every test hits real Band D / CTSOP / HPI data and skips cleanly if
absent, same pattern as test_engine.py.
"""

import pytest

from council_tax_freeze.config import DATA_DIR
from council_tax_freeze.engine.build import build_engine
from council_tax_freeze.hpi.build import build_hpi
from council_tax_freeze.parsers.band_d.parse import build_band_d
from council_tax_freeze.parsers.ctsop.parse import build_ctsop
from council_tax_freeze.sensitivity.sweep import (
    apply_revaluation_frequency,
    region_broadcast_hpi_la_factors,
    region_metric,
    run_collection_factor_grid,
    run_midpoint_grid,
)

BAND_D_FILE = DATA_DIR / "band_d" / "Band_D_1993_onwards.ods"
CTSOP_CONSOLIDATED = DATA_DIR / "ctsop" / "CTSOP1_0_1993_2024" / "CTSOP1_0_1993_2024_03_31.csv"
CTSOP_2025 = DATA_DIR / "ctsop" / "2025_summary.xlsx"


def _hpi_file():
    matches = sorted((DATA_DIR / "hpi").glob("UK-HPI-full-file-*.csv")) if (DATA_DIR / "hpi").exists() else []
    return matches[-1] if matches else None


HPI_FILE = _hpi_file()
requires_all_data = pytest.mark.skipif(
    not (BAND_D_FILE.exists() and CTSOP_CONSOLIDATED.exists() and CTSOP_2025.exists() and HPI_FILE),
    reason="Band D / CTSOP / HPI files not present - run `make data` first",
)

BASE_NORTH_EAST = 227.633811
BASE_LONDON = -394.921704


@pytest.fixture(scope="module")
def loaded_data():
    bd = build_band_d(BAND_D_FILE)
    ct = build_ctsop(CTSOP_CONSOLIDATED, CTSOP_2025)
    hpi = build_hpi(HPI_FILE)
    return bd, ct, hpi


@pytest.fixture(scope="module")
def midpoint_grid(loaded_data):
    bd, ct, hpi = loaded_data
    return run_midpoint_grid(bd.la_year, ct.la_year, ct.predecessor_weights, hpi.la_factors, hpi.national_factors)


# ---------------------------------------------------------------------------
# Axis 1: midpoint grid (BAND_A_RATIO x BAND_H_RATIO, 12 cells)
# ---------------------------------------------------------------------------


@requires_all_data
def test_midpoint_grid_sign_never_flips(midpoint_grid):
    """Threshold 1b (hard failure if crossed). North East must stay
    positive and London must stay negative across all 12 cells."""
    assert (midpoint_grid["north_east"] > 0).all(), midpoint_grid[midpoint_grid["north_east"] <= 0]
    assert (midpoint_grid["london"] < 0).all(), midpoint_grid[midpoint_grid["london"] >= 0]


@requires_all_data
def test_midpoint_grid_worst_cell_stays_economically_non_trivial(midpoint_grid):
    """Threshold 1c. The smallest North East value anywhere in the grid
    must exceed £50/dwelling/year - checked against the actual minimum
    cell, not the cell the pre-registered mechanical reasoning predicted
    would be smallest (that prediction turned out to have the wrong
    direction - see SENSITIVITY_PREREGISTRATION.md addendum / DATA.md).
    Pre-registering the THRESHOLD, not which cell would hit it, is what
    makes this still a fair test of the pre-registered document."""
    assert midpoint_grid["north_east"].min() > 50


@requires_all_data
def test_midpoint_grid_best_cell_does_not_exceed_ceiling(midpoint_grid):
    """Threshold 1d. The largest North East value anywhere in the grid
    must not exceed 2.5x the base case (~£570)."""
    assert midpoint_grid["north_east"].max() < 2.5 * BASE_NORTH_EAST


@requires_all_data
def test_midpoint_grid_is_monotonic_in_each_ratio(midpoint_grid):
    """Threshold 1a (hard, structural). North East must move
    monotonically as BAND_A_RATIO varies (holding BAND_H_RATIO fixed) and
    as BAND_H_RATIO varies (holding BAND_A_RATIO fixed) - a reversal
    anywhere would mean either a genuinely interesting nonlinearity or a
    bug, and either way must not be silently smoothed over. Direction is
    NOT asserted here - the pre-registered prediction of which direction
    got the sign backwards (see DATA.md), but monotonicity itself, which
    is the actual structural claim, holds exactly as pre-registered."""
    for h, sub in midpoint_grid.groupby("band_h_ratio"):
        vals = sub.sort_values("band_a_ratio")["north_east"].tolist()
        assert vals == sorted(vals) or vals == sorted(vals, reverse=True), f"non-monotonic in band_a_ratio at band_h_ratio={h}: {vals}"
    for a, sub in midpoint_grid.groupby("band_a_ratio"):
        vals = sub.sort_values("band_h_ratio")["north_east"].tolist()
        assert vals == sorted(vals) or vals == sorted(vals, reverse=True), f"non-monotonic in band_h_ratio at band_a_ratio={a}: {vals}"


# ---------------------------------------------------------------------------
# Axis 2: collection factor - algebraic identity / bug detector, not a
# substantive robustness question (see SENSITIVITY_PREREGISTRATION.md).
# ---------------------------------------------------------------------------


@requires_all_data
def test_collection_factor_scales_gap_exactly_linearly(loaded_data):
    """Threshold 2. gap(C) / gap(0.83) must equal C / 0.83 to 3 decimal
    places for both regions. Any deviation means COLLECTION_FACTOR is not
    applied uniformly somewhere in the pipeline - a bug, not a finding."""
    bd, ct, hpi = loaded_data
    grid = run_collection_factor_grid(bd.la_year, ct.la_year, ct.predecessor_weights, hpi.la_factors, hpi.national_factors)
    base = grid[grid["collection_factor"] == 0.83].iloc[0]
    for _, row in grid.iterrows():
        expected_ratio = row["collection_factor"] / 0.83
        assert row["north_east"] / base["north_east"] == pytest.approx(expected_ratio, abs=1e-3)
        assert row["london"] / base["london"] == pytest.approx(expected_ratio, abs=1e-3)


# ---------------------------------------------------------------------------
# Axis 3: HPI geography (LA-level vs region-level)
# ---------------------------------------------------------------------------


@requires_all_data
def test_hpi_geography_sign_never_flips(loaded_data):
    """Threshold 3a (hard failure). Neither region's sign may flip when
    switching from LA-level to region-level HPI."""
    bd, ct, hpi = loaded_data
    region_hpi = region_broadcast_hpi_la_factors(hpi.region_factors)
    eng = build_engine(bd.la_year, ct.la_year, ct.predecessor_weights, region_hpi, hpi.national_factors)
    metrics = region_metric(eng, ct.la_year)
    assert metrics["North East"] > 0
    assert metrics["London"] < 0


@requires_all_data
def test_hpi_geography_north_east_does_not_fall_more_than_half(loaded_data):
    """Threshold 3b. North East must stay above ~£114/dwelling/year
    (50% of base) under region-level HPI."""
    bd, ct, hpi = loaded_data
    region_hpi = region_broadcast_hpi_la_factors(hpi.region_factors)
    eng = build_engine(bd.la_year, ct.la_year, ct.predecessor_weights, region_hpi, hpi.national_factors)
    metrics = region_metric(eng, ct.la_year)
    assert metrics["North East"] > 0.5 * BASE_NORTH_EAST


# ---------------------------------------------------------------------------
# Axis 4: revaluation frequency (continuous / 5-year / 10-year)
# ---------------------------------------------------------------------------


@requires_all_data
def test_revaluation_frequency_sign_never_flips(loaded_data):
    """Threshold 4a (hard failure). Sign must not flip at either 5-year
    or 10-year frequency."""
    bd, ct, hpi = loaded_data
    for freq in (5, 10):
        la_f = apply_revaluation_frequency(hpi.la_factors, freq, "hpi_factor_la", ["ons_code"])
        nat_f = apply_revaluation_frequency(hpi.national_factors, freq, "hpi_factor_national", [])
        eng = build_engine(bd.la_year, ct.la_year, ct.predecessor_weights, la_f, nat_f)
        metrics = region_metric(eng, ct.la_year)
        assert metrics["North East"] > 0, freq
        assert metrics["London"] < 0, freq


@requires_all_data
def test_revaluation_frequency_ten_year_does_not_fall_more_than_40_percent(loaded_data):
    """Threshold 4b. North East at 10-year frequency must stay above
    ~£137/dwelling/year (60% of base)."""
    bd, ct, hpi = loaded_data
    la_f = apply_revaluation_frequency(hpi.la_factors, 10, "hpi_factor_la", ["ons_code"])
    nat_f = apply_revaluation_frequency(hpi.national_factors, 10, "hpi_factor_national", [])
    eng = build_engine(bd.la_year, ct.la_year, ct.predecessor_weights, la_f, nat_f)
    metrics = region_metric(eng, ct.la_year)
    assert metrics["North East"] > 0.6 * BASE_NORTH_EAST


@requires_all_data
def test_revaluation_frequency_dampens_monotonically(loaded_data):
    """Not a pre-registered hard threshold, but the predicted shape
    (periodic revaluation lags continuous tracking, so magnitude should
    shrink monotonically as revaluation gets less frequent) - this is the
    one axis where the a priori prediction matched the result exactly,
    worth pinning precisely because the midpoint grid's did not."""
    bd, ct, hpi = loaded_data
    values = []
    for freq in ("continuous", 5, 10):
        la_f = apply_revaluation_frequency(hpi.la_factors, freq, "hpi_factor_la", ["ons_code"])
        nat_f = apply_revaluation_frequency(hpi.national_factors, freq, "hpi_factor_national", [])
        eng = build_engine(bd.la_year, ct.la_year, ct.predecessor_weights, la_f, nat_f)
        values.append(region_metric(eng, ct.la_year)["North East"])
    assert values[0] > values[1] > values[2]
