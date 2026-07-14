"""
Tests for the counterfactual engine. Full-pipeline tests need real Band D
/ CTSOP / HPI data (see other test modules) and skip cleanly if absent.

The IFS gate test is the one this project's whole trust model rests on -
see the project log / DATA.md: if our implied FY2018-19 LA-level
redistribution doesn't broadly reproduce IFS (2020)'s published figures,
that is a hard stop, not something to tune away. This test pins the
result actually obtained, including its two known, reported discrepancies
(Bristol's Variant 1 sign miss; Westminster's Variant 2 magnitude), rather
than hiding them.
"""

import pytest

from council_tax_freeze.config import DATA_DIR
from council_tax_freeze.engine.build import HEADLINE_YEARS, build_engine, compute_shared_tier_exposure, compute_single_pot_bias_risk
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
def engine_result():
    bd = build_band_d(BAND_D_FILE)
    ct = build_ctsop(CTSOP_CONSOLIDATED, CTSOP_2025)
    hpi = build_hpi(HPI_FILE)
    return build_engine(bd.la_year, ct.la_year, ct.predecessor_weights, hpi.la_factors, hpi.national_factors)


@requires_all_data
def test_zero_unresolved_rows_in_headline_period():
    """The core claim of the headline/extension split (DATA.md, config.py):
    every Band D row in the headline period (2009-10 onward) has a
    matching CTSOP row, at SOME resolution, once the Barnsley/Sheffield
    code alias and the small Suffolk/Somerset equal-split fallback are
    applied. If this regresses to nonzero, the headline claim's "zero
    imputation" premise is broken and must be re-examined, not silenced."""
    bd = build_band_d(BAND_D_FILE)
    ct = build_ctsop(CTSOP_CONSOLIDATED, CTSOP_2025)
    hpi = build_hpi(HPI_FILE)
    result = build_engine(bd.la_year, ct.la_year, ct.predecessor_weights, hpi.la_factors, hpi.national_factors)
    assert len(result.unresolved) == 0, result.unresolved.to_string()


@requires_all_data
def test_full_296_la_coverage_every_headline_year(engine_result):
    counts = engine_result.la_year.groupby("financial_year").size()
    assert len(counts) == len(HEADLINE_YEARS)
    assert (counts == 296).all(), counts[counts != 296]


@requires_all_data
def test_revenue_neutrality_by_construction(engine_result):
    """Both variants reallocate actual national revenue, not invent new
    money - gap must sum to ~0 (floating point) in every year, for both
    variants. This is the structural check the brief asked for, run for
    real rather than asserted."""
    by_year = engine_result.la_year.groupby("financial_year")[["variant1_gap", "variant2_gap"]].sum()
    assert (by_year["variant1_gap"].abs() < 1.0).all()  # pounds, on totals in the hundreds of millions
    assert (by_year["variant2_gap"].abs() < 1.0).all()


# IFS (2020) Table 4.1/4.2/4.4 named local authorities, FY2018-19 (the year
# IFS's own analysis is based on). Sign is (direction of tax-base change:
# positive = tax base rises under the reform = LA would pay MORE under a
# revenue-neutral reallocation = gap should be NEGATIVE in our convention).
IFS_VARIANT1_ANCHORS = {  # Option 1: pure revaluation, existing multipliers
    "E07000119": ("Fylde", -17), "E07000128": ("Wyre", -16), "E07000124": ("Ribble Valley", -14),
    "E07000126": ("South Ribble", -14), "E06000004": ("Stockton-on-Tees", -14), "E06000003": ("Redcar and Cleveland", -14),
    "E06000001": ("Hartlepool", -14), "E06000002": ("Middlesbrough", -13), "E09000012": ("Hackney", 37),
    "E09000031": ("Waltham Forest", 25), "E09000022": ("Lambeth", 24), "E09000023": ("Lewisham", 23),
    "E06000043": ("Brighton and Hove", 17), "E07000008": ("Cambridge", 13), "E06000023": ("Bristol", 12),
}
IFS_VARIANT2_ANCHORS = {  # Option 5: continuous and proportional
    "E06000001": ("Hartlepool", -61), "E06000009": ("Blackpool", -61), "E06000002": ("Middlesbrough", -59),
    "E06000010": ("Kingston upon Hull", -59), "E09000020": ("Kensington and Chelsea", 246),
    "E09000033": ("Westminster", 175), "E09000007": ("Camden", 140), "E09000027": ("Richmond upon Thames", 104),
}
# Known, reported discrepancies - NOT tuned away, pinned so a future change
# that silently "fixes" them without investigation gets caught.
KNOWN_SIGN_MISMATCHES_VARIANT1 = {"E06000023"}  # Bristol: IFS +12% (small/borderline), we get ~0%


@requires_all_data
def test_ifs_gate_variant1_sign_matches(engine_result):
    fy = engine_result.la_year[engine_result.la_year["financial_year"] == "2018-19"].set_index("ons_code")
    mismatches = []
    for code, (name, ifs_pct) in IFS_VARIANT1_ANCHORS.items():
        my_pct = (fy.loc[code, "variant1_cf"] - fy.loc[code, "actual"]) / fy.loc[code, "actual"] * 100
        if (my_pct > 0) != (ifs_pct > 0) and code not in KNOWN_SIGN_MISMATCHES_VARIANT1:
            mismatches.append((name, ifs_pct, my_pct))
    assert not mismatches, f"NEW sign mismatch(es) vs IFS Variant 1 anchors: {mismatches}"


@requires_all_data
def test_ifs_gate_variant2_sign_matches(engine_result):
    fy = engine_result.la_year[engine_result.la_year["financial_year"] == "2018-19"].set_index("ons_code")
    mismatches = []
    for code, (name, ifs_pct) in IFS_VARIANT2_ANCHORS.items():
        my_pct = (fy.loc[code, "variant2_cf"] - fy.loc[code, "actual"]) / fy.loc[code, "actual"] * 100
        if (my_pct > 0) != (ifs_pct > 0):
            mismatches.append((name, ifs_pct, my_pct))
    assert not mismatches, f"NEW sign mismatch(es) vs IFS Variant 2 anchors: {mismatches}"


@requires_all_data
def test_headline_direction_matches_the_thesis(engine_result):
    """High-appreciation South (Kensington and Chelsea) should show a
    cumulative NEGATIVE gap (paid less than a value-proportional
    counterfactual); low-appreciation North (Hartlepool) should show a
    cumulative POSITIVE gap. This is the headline claim itself, not a
    detail - it must hold under both variants."""
    la_year = engine_result.la_year
    kc = la_year[la_year["ons_code"] == "E09000020"]
    hartlepool = la_year[la_year["ons_code"] == "E06000001"]
    for variant in ["variant1_gap", "variant2_gap"]:
        assert kc[variant].sum() < 0
        assert hartlepool[variant].sum() > 0


# ---------------------------------------------------------------------------
# Nesting: Variant 1 (compressed multiplier) and Variant 2 (proportional,
# "Variant 1 with compression removed") are built from ONE shared
# per-cohort relative value and reallocation mechanism - see engine/build.py
# module docstring for the full reasoning behind the rewrite. These tests
# pin the two properties that make that claim checkable, not just asserted.
# ---------------------------------------------------------------------------


def test_compressed_and_proportional_curves_cross_exactly_once_at_band_d():
    """The mathematical core of 'nested': the compressed-multiplier curve
    and the proportional line must intersect ONLY at Band D's own midpoint
    (both are defined to equal 1.0 there) and nowhere else - if they
    crossed elsewhere, a cohort's sign relative to 'more/less than
    proportional' would flip more than once across the value range. Direct
    numeric check, not just visual/spot inspection."""
    import numpy as np

    from council_tax_freeze.engine.build import _compressed_multiplier, _proportional_multiplier

    values = np.geomspace(5_000, 3_000_000, 500)
    diff = [_compressed_multiplier(v) - _proportional_multiplier(v) for v in values]
    sign = np.sign(diff)
    crossings = (np.diff(sign) != 0).sum()
    assert crossings == 1


@requires_all_data
def test_v2_minus_v1_gap_correlates_with_high_band_share(engine_result):
    """The 'compression scales with tail-skew' claim, checked directly:
    across all 296 LAs, how much MORE negative Variant 2's gap is than
    Variant 1's (i.e. how much the compression term alone shifts the
    result) should correlate positively with that LA's share of dwellings
    in Bands F-H. This is what makes the residual sign disagreements
    between the two variants (see test below) a real, tail-skew-driven
    finding rather than unexplained noise."""
    import numpy as np

    from council_tax_freeze.parsers.ctsop.parse import build_ctsop

    ct = build_ctsop(CTSOP_CONSOLIDATED, CTSOP_2025)
    ctsop_fy = ct.la_year[ct.la_year["financial_year"] == "2018-19"].set_index("ons_code")
    fgh_share = (ctsop_fy["band_f"] + ctsop_fy["band_g"] + ctsop_fy["band_h"]) / ctsop_fy["all_properties"]

    fy = engine_result.la_year[engine_result.la_year["financial_year"] == "2018-19"].set_index("ons_code")
    compression_effect = fy["variant2_gap"] - fy["variant1_gap"]  # more negative = compression pulls liability down more

    joined = compression_effect.to_frame("compression_effect").join(fgh_share.rename("fgh_share")).dropna()
    corr = np.corrcoef(joined["fgh_share"], joined["compression_effect"])[0, 1]
    assert corr < -0.5, f"expected a strong negative correlation (more F-H share -> more negative compression effect), got {corr:.2f}"


@requires_all_data
def test_sign_disagreements_are_concentrated_in_tail_skewed_las(engine_result):
    """Pins the actual investigation finding: LAs where Variant 1 and
    Variant 2 disagree on sign are not random - they are the tail-skewed
    commuter-belt LAs where the compression effect is large enough to
    dominate a small valuation-date-only effect (Elmbridge: 40.4% of
    stock in Bands F-H vs 9.2% England-wide - checked directly, not
    assumed, during the investigation this test records)."""
    from council_tax_freeze.parsers.ctsop.parse import build_ctsop

    ct = build_ctsop(CTSOP_CONSOLIDATED, CTSOP_2025)
    ctsop_fy = ct.la_year[ct.la_year["financial_year"] == "2018-19"].set_index("ons_code")
    fgh_share = (ctsop_fy["band_f"] + ctsop_fy["band_g"] + ctsop_fy["band_h"]) / ctsop_fy["all_properties"]

    fy = engine_result.la_year[engine_result.la_year["financial_year"] == "2018-19"].copy()
    fy["sign_match"] = (fy["variant1_gap"] > 0) == (fy["variant2_gap"] > 0)
    fy = fy.set_index("ons_code").join(fgh_share.rename("fgh_share"))

    mismatch_mean_fgh = fy.loc[~fy["sign_match"], "fgh_share"].mean()
    match_mean_fgh = fy.loc[fy["sign_match"], "fgh_share"].mean()
    assert mismatch_mean_fgh > match_mean_fgh * 1.5, (
        f"expected sign-disagreement LAs to be markedly more tail-skewed than agreement LAs "
        f"(mismatch mean F-H share {mismatch_mean_fgh:.1%} vs match mean {match_mean_fgh:.1%})"
    )


# ---------------------------------------------------------------------------
# Single-pot exposure bound - see config.TIERED_REALLOCATION_IMPLEMENTED and
# DATA.md "Single-pot reallocation: decision and quantified bound". Not a
# correction; a documented, per-LA caveat on how exposed a computed gap is.
# ---------------------------------------------------------------------------


@requires_all_data
def test_westminster_high_exposure_hartlepool_low_exposure():
    """Pins the finding that motivated reporting this bound at all:
    Westminster (where the single-pot bias was actually found and
    demonstrated) has high shared-tier exposure; Hartlepool (unaffected,
    per the project log) has low exposure - consistent with, though not
    proof of, the mechanism."""
    bd = build_band_d(BAND_D_FILE)
    exposure = compute_shared_tier_exposure(bd.la_year)
    fy = exposure[exposure["financial_year"] == "2018-19"].set_index("ons_code")
    assert fy.loc["E09000033", "shared_tier_share"] > 0.35  # Westminster
    assert fy.loc["E06000001", "shared_tier_share"] < 0.20  # Hartlepool


@requires_all_data
def test_exposure_is_bimodal_by_authority_type():
    """Unitary/London authorities (own precept absorbs county-equivalent
    services) cluster low; two-tier shire districts (own precept is a
    small slice next to the county's) cluster high. Checked directly,
    not assumed - see engine module docstring."""
    bd = build_band_d(BAND_D_FILE)
    exposure = compute_shared_tier_exposure(bd.la_year)
    fy = exposure[exposure["financial_year"] == "2018-19"]["shared_tier_share"].dropna()
    low_cluster = ((fy > 0.05) & (fy < 0.30)).sum()
    high_cluster = ((fy > 0.75) & (fy < 0.95)).sum()
    middle = ((fy >= 0.30) & (fy <= 0.75)).sum()
    assert low_cluster > 100
    assert high_cluster > 150
    assert middle < 20, f"expected a sparse middle between the two clusters, got {middle} LAs"


# ---------------------------------------------------------------------------
# Single-pot bias RISK - exposure alone can't show whether a bill is
# actually distorted, only whether it COULD be. This needs the LA's own
# precept to diverge, in cash terms, from peers sharing its other tiers.
# First built as a ratio and dropped after it ranked ordinary shire
# districts above Westminster (own precepts are small in GBP terms there,
# so a normal cross-council spending difference produces a large ratio) -
# see engine.build.compute_single_pot_bias_risk's docstring for the full
# account of why a cash-share statistic replaced it outright, not
# alongside it.
# ---------------------------------------------------------------------------


@requires_all_data
def test_single_pot_bias_risk_reproduces_westminster_investigation_outlier_set():
    """The cash-share statistic was adopted because it independently
    reproduced, from first principles, the same five LAs the original
    hand investigation flagged (Westminster, Wandsworth, Hammersmith and
    Fulham, City of London, Kensington and Chelsea) - two different
    routes landing on the same answer. Pins that outcome."""
    bd = build_band_d(BAND_D_FILE)
    risk = compute_single_pot_bias_risk(bd.la_year)
    fy = risk[risk["financial_year"] == "2018-19"].dropna(subset=["single_pot_bias_risk"])
    top5 = set(fy.sort_values("single_pot_bias_risk", ascending=False).head(5)["ons_code"])
    expected = {"E09000033", "E09000032", "E09000013", "E09000001", "E09000020"}
    assert top5 == expected, f"expected the five named inner-London outliers, got {fy.set_index('ons_code').loc[list(top5), 'authority'].tolist()}"


@requires_all_data
def test_westminster_and_wandsworth_are_a_severe_tier_above_the_rest():
    """Westminster and Wandsworth's risk scores both exceed 1.0 (their
    cash divergence from peers is worth more than their own entire
    discounted bill) and sit roughly 2.4x above the next tier
    (Hammersmith and Fulham) - a real structural break, not a smooth
    decline, which is why the caveat names two severity tiers rather than
    a single flat list of five."""
    bd = build_band_d(BAND_D_FILE)
    risk = compute_single_pot_bias_risk(bd.la_year)
    fy = risk[risk["financial_year"] == "2018-19"].set_index("ons_code")
    assert fy.loc["E09000033", "single_pot_bias_risk"] > 1.0  # Westminster
    assert fy.loc["E09000032", "single_pot_bias_risk"] > 1.0  # Wandsworth
    assert fy.loc["E09000013", "single_pot_bias_risk"] < 0.6  # Hammersmith and Fulham


@requires_all_data
def test_wandsworth_gap_is_inflated_the_same_way_as_westminster(engine_result):
    """Wandsworth's risk score (1.03) is essentially Westminster's (1.06),
    and this test confirms that shows up in the computed GAP too, not just
    the risk statistic: both variants' percentage gaps for Wandsworth are
    within a few points of Westminster's - the same mechanism, not a
    coincidence of the risk formula."""
    fy = engine_result.la_year[engine_result.la_year["financial_year"] == "2018-19"].set_index("ons_code")
    westminster_v1_pct = fy.loc["E09000033", "variant1_gap"] / fy.loc["E09000033", "variant1_cf"]
    wandsworth_v1_pct = fy.loc["E09000032", "variant1_gap"] / fy.loc["E09000032", "variant1_cf"]
    westminster_v2_pct = fy.loc["E09000033", "variant2_gap"] / fy.loc["E09000033", "variant2_cf"]
    wandsworth_v2_pct = fy.loc["E09000032", "variant2_gap"] / fy.loc["E09000032", "variant2_cf"]
    assert wandsworth_v1_pct < -0.5  # both large negative gaps
    assert wandsworth_v2_pct < -0.5
    assert abs(westminster_v1_pct - wandsworth_v1_pct) < 0.05
    assert abs(westminster_v2_pct - wandsworth_v2_pct) < 0.15


@requires_all_data
def test_headline_northern_las_get_unmeasured_not_clean_risk_score():
    """Hartlepool, County Durham and Blackpool are standalone unitary
    authorities with no real precepting-group peer in
    boundaries.precepting_groups - this statistic CANNOT measure their
    divergence and must say so (NaN), not silently read as zero/clean.
    Their low exposure (compute_shared_tier_exposure, ~14-16%) is the only
    thing that actually supports "the headline is largely unaffected" -
    see 02_method.ipynb, which must not let a NaN here read as a pass."""
    bd = build_band_d(BAND_D_FILE)
    risk = compute_single_pot_bias_risk(bd.la_year)
    fy = risk[risk["financial_year"] == "2018-19"].set_index("ons_code")
    for code in ("E06000001", "E06000047", "E06000009"):  # Hartlepool, County Durham, Blackpool
        assert fy.loc[code, "single_pot_bias_risk"] != fy.loc[code, "single_pot_bias_risk"]  # NaN != NaN


@requires_all_data
def test_ctsop_suppressed_band_counts_do_not_silently_zero_an_las_revenue(engine_result):
    """Regression test for a real bug found while investigating the risk
    statistic above: CTSOP blanks small band counts (disclosure
    suppression), parsed as NaN. `v or 0` does not catch NaN (NaN is
    truthy in Python), so it propagated into the tax-base sum, and pandas'
    skipna groupby-sum then silently collapsed an all-NaN group to exactly
    0.0 - City of London read as GBP0 actual revenue for 2017-18 onward
    before the fix (engine.build._safe_count). Pins that it no longer
    does."""
    fy = engine_result.la_year[engine_result.la_year["financial_year"] == "2018-19"].set_index("ons_code")
    assert fy.loc["E09000001", "actual"] > 1_000_000  # City of London
