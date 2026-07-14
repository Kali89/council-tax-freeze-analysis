"""
Tests for the Core Spending Power (settlement) parser - see
parsers/settlement/parse.py module docstring for the tiering/apportionment
design this pins.
"""

import pytest

from council_tax_freeze.config import DATA_DIR
from council_tax_freeze.parsers.ctsop.parse import build_ctsop
from council_tax_freeze.parsers.settlement.parse import SHEET_NAMES, build_settlement

CTSOP_CONSOLIDATED = DATA_DIR / "ctsop" / "CTSOP1_0_1993_2024" / "CTSOP1_0_1993_2024_03_31.csv"
CTSOP_2025 = DATA_DIR / "ctsop" / "2025_summary.xlsx"
SETTLEMENT_FILE = DATA_DIR / "settlement" / "CSP_information_table_LGFS_2025-26.xlsx"

requires_all_data = pytest.mark.skipif(
    not (CTSOP_CONSOLIDATED.exists() and CTSOP_2025.exists() and SETTLEMENT_FILE.exists()),
    reason="CTSOP / settlement files not present - run `make data` first",
)


@pytest.fixture(scope="module")
def settlement_result():
    ct = build_ctsop(CTSOP_CONSOLIDATED, CTSOP_2025)
    return build_settlement(SETTLEMENT_FILE, ct.la_year), ct


@requires_all_data
def test_full_296_la_coverage_every_year(settlement_result):
    result, _ = settlement_result
    for fy in SHEET_NAMES:
        n = result.la_year[result.la_year["financial_year"] == fy]["ons_code"].nunique()
        assert n == 296, f"{fy}: expected 296 LAs, got {n}"


@requires_all_data
def test_zero_unresolved_rows(settlement_result):
    result, _ = settlement_result
    assert len(result.unresolved) == 0, result.unresolved.to_string()


@requires_all_data
def test_upper_tier_apportionment_is_material_not_a_rounding_error(settlement_result):
    """Pins the finding that motivated apportioning county/GLA CSP at all -
    checked directly against the real 2025-26 figures in the module
    docstring: Cambridgeshire's own county row is 7.1x its five districts'
    own CSP combined, and the GLA's own row is 31.7% of the 33 London
    boroughs' own CSP combined. Checked in aggregate (not per-borough -
    apportionment is dwelling-weighted, so a low-dwelling/high-value
    borough like Westminster can show a smaller apportioned share than
    its own row without that being a bug)."""
    result, _ = settlement_result
    fy = result.la_year[result.la_year["financial_year"] == "2025-26"].set_index("ons_code")
    cambridge = fy.loc["E07000008"]  # Cambridge district
    assert cambridge["csp_upper_tier_apportioned"] > 5 * cambridge["csp_own"]

    from council_tax_freeze.boundaries.regions import REGION

    london_codes = [c for c in fy.index if REGION.get(c) == "London"]
    london = fy.loc[london_codes]
    assert london["csp_upper_tier_apportioned"].sum() > 0.25 * london["csp_own"].sum()


@requires_all_data
def test_standalone_unitary_has_no_upper_tier_apportionment(settlement_result):
    """Hartlepool is a standalone unitary (boundaries.precepting_groups) -
    its own CSP row already IS the area total, so nothing should be
    apportioned to it from a county/GLA/combined-authority row."""
    result, _ = settlement_result
    fy = result.la_year[result.la_year["financial_year"] == "2025-26"].set_index("ons_code")
    assert fy.loc["E06000001", "csp_upper_tier_apportioned"] == 0


@requires_all_data
def test_transitional_county_gap_shrinks_to_zero_on_the_known_reorg_schedule(settlement_result):
    """Pins the exact, checked internal-consistency finding from
    development (see project log): the count of (predecessor, year) cells
    with a known-unapportioned county gap drops by exactly the number of
    predecessor codes in each transitional reorg, on the exact known reorg
    dates (Dorset/BCP 2019, Northamptonshire 2021, Cumbria/North
    Yorkshire/Somerset 2023) - not a coincidence, a direct check that the
    gap-detection logic is counting the right thing."""
    result, _ = settlement_result
    cov = result.coverage.set_index("financial_year")["n_unapportioned_upper_tier_gap"]
    assert cov["2015-16"] == 31
    assert cov["2018-19"] == 31
    assert cov["2019-20"] == 24  # Dorset/BCP 2019: -7
    assert cov["2020-21"] == 24
    assert cov["2021-22"] == 17  # Northamptonshire 2021: -7
    assert cov["2022-23"] == 17
    assert cov["2023-24"] == 0  # Cumbria/North Yorkshire/Somerset 2023: -17
    assert cov["2025-26"] == 0
