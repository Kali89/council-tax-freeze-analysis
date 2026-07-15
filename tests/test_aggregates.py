"""
Tests for LA-total / region-total cumulative gap figures (aggregates.py).
Pins the naive-vs-correct method difference explicitly, per instruction,
so the correct (year-by-year) method cannot later be "simplified" back to
the wrong one (multiplying the panel-average per-dwelling figure by a
current dwelling count).
"""

import pytest

from council_tax_freeze.aggregates import (
    SINGLE_POT_FLAGGED_LAS,
    compute_la_cumulative_gap,
    compute_london_robustness_check,
    compute_naive_aggregate,
    compute_region_cumulative_gap,
)
from council_tax_freeze.config import DATA_DIR
from council_tax_freeze.engine.build import build_engine
from council_tax_freeze.hpi.build import build_hpi
from council_tax_freeze.parsers.band_d.parse import build_band_d
from council_tax_freeze.parsers.ctsop.parse import build_ctsop

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


@pytest.fixture(scope="module")
def engine_and_ctsop():
    bd = build_band_d(BAND_D_FILE)
    ct = build_ctsop(CTSOP_CONSOLIDATED, CTSOP_2025)
    hpi = build_hpi(HPI_FILE)
    eng = build_engine(bd.la_year, ct.la_year, ct.predecessor_weights, hpi.la_factors, hpi.national_factors)
    return eng, ct


@requires_all_data
def test_la_totals_sum_to_region_totals(engine_and_ctsop):
    eng, ct = engine_and_ctsop
    la_cum = compute_la_cumulative_gap(eng.la_year, ct.la_year, "variant1")
    region_cum = compute_region_cumulative_gap(la_cum)
    # both sides are ~0 (national revenue neutrality, see the next test) so
    # compare with an absolute, not relative, tolerance
    assert region_cum["cumulative_gap_gbp"].sum() == pytest.approx(la_cum["cumulative_gap_gbp"].sum(), abs=1e-3)


@requires_all_data
def test_la_totals_sum_to_approximately_zero_nationally(engine_and_ctsop):
    """Revenue neutrality holds per year (test_engine.py); summed across
    all headline years it should still net close to zero nationally -
    this is the aggregate-level version of the same structural check."""
    eng, ct = engine_and_ctsop
    la_cum = compute_la_cumulative_gap(eng.la_year, ct.la_year, "variant1")
    assert abs(la_cum["cumulative_gap_gbp"].sum()) < 1.0


@requires_all_data
def test_north_east_region_total_matches_phase5_per_dwelling_figure(engine_and_ctsop):
    """Cross-check against the number Phase 5's sensitivity module
    computed independently (£227.63/dwelling/year, North East) - two
    different code paths landing on the same figure."""
    eng, ct = engine_and_ctsop
    la_cum = compute_la_cumulative_gap(eng.la_year, ct.la_year, "variant1")
    region_cum = compute_region_cumulative_gap(la_cum).set_index("region")
    assert region_cum.loc["North East", "per_dwelling_per_year_gbp"] == pytest.approx(227.63, abs=0.5)
    assert region_cum.loc["North East", "cumulative_gap_gbp_bn"] == pytest.approx(4.74, abs=0.05)


@requires_all_data
def test_naive_current_stock_method_materially_overstates_the_correct_total(engine_and_ctsop):
    """The instruction this test exists to enforce: multiplying the
    panel-average per-dwelling figure by a CURRENT dwelling count must
    not silently become "the" method. Pins that the naive method
    disagrees with the correct (year-by-year) one by a material amount
    for a real LA, so a future edit that collapses the two back together
    fails a test, not just a code review."""
    eng, ct = engine_and_ctsop
    la_cum = compute_la_cumulative_gap(eng.la_year, ct.la_year, "variant1").set_index("ons_code")
    correct = la_cum.loc["E06000001", "cumulative_gap_gbp"]  # Hartlepool
    naive = compute_naive_aggregate(eng.la_year, ct.la_year, "E06000001")
    assert naive != pytest.approx(correct, rel=0.001)
    assert abs(naive / correct - 1) > 0.03  # a real, non-trivial divergence, not rounding noise


@requires_all_data
def test_barnsley_sheffield_get_real_dwelling_counts_not_inf(engine_and_ctsop):
    """Regression test for a real bug found while building this: CTSOP
    never switches Barnsley/Sheffield to their 2025 codes (E08000038/
    E08000039), even in the 2025-26 file, while engine.build's output
    always uses the resolved 2025 code - an unaliased merge produced
    zero matched dwelling-years and an infinite per-dwelling figure for
    both LAs. Pins that both now get real, finite numbers."""
    eng, ct = engine_and_ctsop
    la_cum = compute_la_cumulative_gap(eng.la_year, ct.la_year, "variant1").set_index("ons_code")
    for code in ("E08000038", "E08000039"):  # Barnsley, Sheffield
        row = la_cum.loc[code]
        assert row["dwelling_years"] > 0
        assert abs(row["per_dwelling_per_year_gbp"]) < 10_000  # sane, not inf/nan
        assert isinstance(row["authority"], str)


@requires_all_data
def test_london_aggregate_depends_materially_on_the_five_flagged_las(engine_and_ctsop):
    """Pins the finding that must be visible, not footnoted: a third or
    more of London's aggregate underpayment total comes from the five
    LAs already flagged as single-pot-inflated upper bounds."""
    eng, ct = engine_and_ctsop
    la_cum = compute_la_cumulative_gap(eng.la_year, ct.la_year, "variant1")
    check = compute_london_robustness_check(la_cum)
    assert check["flagged_five_share_of_london_total"] > 0.25
    assert check["london_total_gbp_bn"] < check["london_total_excl_flagged_gbp_bn"]  # more negative with them in


@requires_all_data
def test_north_east_has_no_single_pot_flagged_las(engine_and_ctsop):
    """The asymmetry the write-up must state: the side of the ledger the
    headline leads with carries no single-pot caveat at all."""
    eng, ct = engine_and_ctsop
    la_cum = compute_la_cumulative_gap(eng.la_year, ct.la_year, "variant1")
    north_east_codes = set(la_cum[la_cum["region"] == "North East"]["ons_code"])
    assert north_east_codes.isdisjoint(SINGLE_POT_FLAGGED_LAS)


# ---------------------------------------------------------------------------
# Headline-figure pins. "Per dwelling" is ambiguous unless every number also
# says WHOSE rate and over what base - Hartlepool-at-its-own-rate and
# Hartlepool-at-the-region-average-rate are both real, both legitimate, and
# differ by 31%; an LA's own cumulative-per-dwelling and a region's
# cumulative-per-dwelling are two more, different again. Each assertion
# message below states the exact definition of the number it pins, so a
# future edit that quietly reuses one number's wording for a different
# quantity (or vice versa) fails a test, not just a copy-edit review.
# ---------------------------------------------------------------------------


@requires_all_data
def test_headline_figures_are_pinned_with_their_exact_definitions(engine_and_ctsop):
    eng, ct = engine_and_ctsop
    la_cum = compute_la_cumulative_gap(eng.la_year, ct.la_year, "variant1")
    region_cum = compute_region_cumulative_gap(la_cum)

    hartlepool = la_cum.set_index("ons_code").loc["E06000001"]
    north_east = region_cum.set_index("region").loc["North East"]

    hartlepool_2025_dwellings = ct.la_year[
        (ct.la_year.ons_code == "E06000001") & (ct.la_year.financial_year == "2025-26")
    ]["all_properties"].iloc[0]
    hartlepool_cumulative_per_current_dwelling = hartlepool["cumulative_gap_gbp"] / hartlepool_2025_dwellings

    ne_2025_dwellings = (
        ct.la_year[ct.la_year.financial_year == "2025-26"]
        .merge(la_cum[["ons_code", "region"]], on="ons_code")
        .query("region == 'North East'")["all_properties"]
        .sum()
    )
    ne_cumulative_per_current_dwelling = north_east["cumulative_gap_gbp"] / ne_2025_dwellings

    assert hartlepool["per_dwelling_per_year_gbp"] == pytest.approx(365.52, abs=0.5), (
        "Hartlepool's OWN dwelling-year-weighted rate (its own annual gaps / its own dwelling-years) "
        "should be ~£365.52/dwelling/year - NOT the North East region average (£227.63) and NOT any "
        "cumulative figure. If this fails, check whether the wrong column or the wrong scope (LA vs "
        "region) is being read."
    )
    assert north_east["per_dwelling_per_year_gbp"] == pytest.approx(227.63, abs=0.5), (
        "The North East REGION AVERAGE rate (all 12 North East LAs' annual gaps / their combined "
        "dwelling-years) should be ~£227.63/dwelling/year - NOT Hartlepool's own rate (£365.52), which "
        "is higher because Hartlepool is the region's highest-rate LA despite being only 3.6% of its "
        "dwelling stock."
    )
    assert hartlepool_cumulative_per_current_dwelling == pytest.approx(5863, abs=50), (
        "Hartlepool's cumulative total GBP gap (2009-10 to 2025-26) divided by HARTLEPOOL'S OWN "
        "2025-26 dwelling count should be ~£5,863 - this is a CUMULATIVE-PER-CURRENT-DWELLING figure, "
        "not a rate, and not the region's equivalent figure (£3,677). Must never be computed as "
        "rate x number-of-years (that method is deliberately not used anywhere in this pipeline - see "
        "aggregates.py module docstring)."
    )
    assert ne_cumulative_per_current_dwelling == pytest.approx(3677, abs=50), (
        "The North East region's cumulative total GBP gap (2009-10 to 2025-26) divided by the REGION'S "
        "OWN combined 2025-26 dwelling count should be ~£3,677 - this is the region-level "
        "cumulative-per-current-dwelling figure, not Hartlepool's equivalent (£5,863), and not "
        "region-average-rate x 17 (~£3,870, a different, deliberately-unused method - see above)."
    )
    assert north_east["cumulative_gap_gbp_bn"] == pytest.approx(4.7, abs=0.05), (
        "The North East region's cumulative TOTAL gap (2009-10 to 2025-26, summed across all 12 LAs "
        "and 17 years) should be ~£4.7bn - a plain total, not divided by any dwelling count at all, "
        "and not the same number as either per-dwelling figure above."
    )
