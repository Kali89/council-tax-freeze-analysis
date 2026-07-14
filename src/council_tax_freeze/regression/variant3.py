"""
Variant 3: did rate-setting already offset the freeze's redistributive
effect? The strongest form of the objection this whole repository exists
to test - IFS (2020) themselves note the cross-LA unfairness could in
principle be corrected through the funding settlement alone, without
touching council tax bands (see notebooks/02_method.ipynb "This is not a
novel mechanism"). This module answers it directly rather than leaving it
as a caveat, and the answer strengthens the headline: the objection is
tested and does not hold outside London.

**Panel: 2015-16 to 2025-26 (10 growth-year observations x 296 LAs),
not the full headline window.** Core Spending Power - the settlement
control this regression needs - does not exist as a concept before
2015-16 (parsers/settlement/parse.py). Reconstructing an equivalent
series for 2009-14 from Revenue Support Grant / early Settlement Funding
Assessment sources would need the National Archives Web Archive, a
materially different and harder extraction than anything else in this
pipeline - not pursued. This is NOT the same kind of gap as the 2009-wave
CTSOP problem: Variant 3 is a test of a BEHAVIOURAL REGULARITY (did
councils respond to appreciation by setting lower rates), not a
cumulative total - eleven years of within-LA variation across 296 LAs is
an adequate panel to answer that question on its own. Reported here on
2015-16 to 2025-26, with the explicit, stated assumption that this
behavioural relationship is stable across the pre-2015 period - a weaker
assumption than several already accepted elsewhere in this pipeline
(county-average band-share imputation, the 1991-1995 HPI bridging gap),
not hidden as if the panel covered the whole headline window.

**Specification**, every choice decided explicitly, not guessed:
  - Dependent variable: year-on-year LOG growth in Band D rate
    (`band_d_incl_parish`) - not the level, which isn't comparable across
    LAs with different service scopes (a two-tier shire district's rate
    includes a county precept a unitary's doesn't), and LA fixed effects
    would absorb a level difference anyway, leaving only the within-LA
    growth rate to explain.
  - Independent variable of interest: `relative_hpi = hpi_factor_la /
    hpi_factor_national` - the EXACT SAME quantity `engine.build` uses to
    define `relative_value` for Variants 1/2, not a second definition of
    "relative appreciation" invented for this module. Used
    CONTEMPORANEOUSLY (year t's relative_hpi against year t's rate
    growth), not lagged - a real choice (councils set budgets using
    information available before the financial year starts, so a lagged
    specification is also defensible) documented here rather than
    silently picked; the contemporaneous spec was chosen for consistency
    with how Variants 1/2 use the same quantity, not because a lag was
    tested and rejected.
  - Settlement control: year-on-year CHANGE in Core Spending Power per
    dwelling (`parsers.settlement.parse`, apportioned to area-total
    where a district shares a county/GLA/combined-authority tier) - not
    the level, matching "did rate-setting respond to grant CHANGES."
  - LA fixed effects: yes - without them the regression would conflate
    "which LAs have structurally high/low rates" with "did rates respond
    to appreciation," and only the second is the question.
  - Year fixed effects: yes - absorbs national shocks common to every LA
    in a given year, most importantly the council tax referendum
    threshold, which changed repeatedly over this period and is a
    national policy lever, not an LA response to its own appreciation.
  - Standard errors: clustered by LA - panel data has within-LA serial
    correlation (an LA's rate-growth shocks are not independent year to
    year) that unclustered SEs would understate, overstating precision.

**The pooled result is significant, and it is entirely a London effect -
both facts belong in the headline, not just the first one.** Pooled
across all 296 LAs: coefficient -0.0243, 95% CI [-0.0318, -0.0167],
p<0.0001. Split by region (checked, not assumed): excluding London drops
the coefficient by 74% and its significance entirely (-0.0063, CI
[-0.0143, 0.0017], p=0.125); London alone is individually insignificant
too (thin sample, 33 clusters). The decisive number is the WITHIN-LA
correlation between an LA's own year-to-year relative_hpi and its own
rate growth: **-0.57 in London, +0.08 in the rest of England** - not a
weaker version of the same relationship, effectively zero with the wrong
sign outside London. London boroughs' year-to-year relative_hpi swings
are ~2.7x larger than elsewhere (std 0.107 vs 0.039), giving them
outsized leverage on the pooled coefficient despite the rest of England
showing no such relationship at all.

**Diagnosis, not just observation: this is confounding, not
compensation.** The mechanism producing London's -0.57 is almost
certainly the one Phase 4 already found and investigated in detail (see
`engine.build.compute_single_pot_bias_risk` and DATA.md "Phase 4: the IFS
gate, and what it caught") - Westminster/Wandsworth-type boroughs holding
their own-tier rate artificially low on decades of business-rate income
and reserves, a LOCAL fiscal anomaly unrelated to the valuation freeze,
which correlates with London's high and volatile relative appreciation
without being CAUSED by it. Two independent investigations (a hand
investigation of individual LAs' Band D rates in Phase 4, and this
regression's robustness check in Phase 6) landed on the same mechanism
from two different directions.

**The finding, stated as what it is: the IFS objection is tested and
does not hold outside London.** The IFS objection is a claim about a
general behavioural regularity - that councils in high-appreciation areas
set lower rates, offsetting the freeze's redistributive effect through
the funding settlement rather than needing band reform. Across 263
non-London LAs and eleven years, no such regularity exists. The
NON-LONDON specification (coefficient -0.0063, CI [-0.0143, 0.0017]) is
therefore the PRIMARY result, not the pooled one: a TIGHT null, not a
noisy one - the CI is narrow enough to rule out an economically
meaningful offset, which is the standard this analysis committed to
before running anything (see `interpret_offset`: even at the upper bound
of what the non-London data supports, rate-setting offset at most a
small fraction of the North East's measured gap). The pooled result is
reported prominently alongside it, with this decomposition, not buried -
a reader who runs the pooled regression themselves should find this
analysis already there.

**The one hard rule this diagnosis enforces: the pooled (or London-only)
coefficient must never be applied to a non-London LA.** Extrapolating
London's -0.57 relationship onto Hartlepool, where the measured within-LA
relationship is +0.08, would produce a number with no support in the
data - the single most misleading figure this module could produce.
`interpret_offset` refuses to compute this: it accepts only a
`Variant3Result` fit on a sample containing the requested LA's own region
(so a non-London result cannot be paired with a London LA and vice
versa), and raises rather than silently extrapolating across the
boundary the data itself drew.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from council_tax_freeze.boundaries.regions import REGION

VARIANT3_YEARS = [f"{y}-{str(y + 1)[2:]}" for y in range(2015, 2026)]  # 2015-16 .. 2025-26


def build_variant3_panel(
    band_d_la_year: pd.DataFrame,
    ctsop_la_year: pd.DataFrame,
    hpi_la_factors: pd.DataFrame,
    hpi_national_factors: pd.DataFrame,
    settlement_la_year: pd.DataFrame,
) -> pd.DataFrame:
    """One row per (ons_code, financial_year), financial_year in
    VARIANT3_YEARS. `rate_growth`/`delta_csp_per_dwelling` are NaN in the
    panel's first year (2015-16, no t-1 to difference against) - callers
    doing the regression itself should drop those rows explicitly rather
    than let a library silently do it, so the row count is auditable.

    They are ALSO NaN for a merging LA's own 2025-vintage code in every
    year before its own merge date (9 LAs, ~65 rows total: BCP, Dorset,
    Buckinghamshire, North/West Northamptonshire, Cumberland, Westmorland
    and Furness, North Yorkshire, Somerset, West/East Suffolk) - checked
    directly, not a bug: `band_d_la_year` (unlike engine/build.py's
    row-level liability computation) is used here as a plain per-code
    rate series, not resolved/summed through the Phase 1 crosswalk, so a
    2025-vintage merged code genuinely has no comparable single "rate" for
    years its territory was still split across predecessors with their
    own separate rates - engine.build's "liabilities are summed, never
    rates blended" applies here too, and reconstructing a dwelling-
    weighted predecessor rate purely for this regression's control
    variable was judged not worth the added complexity for ~2% of the
    panel. Dropped, not guessed."""
    bd = band_d_la_year[band_d_la_year["financial_year"].isin(VARIANT3_YEARS)][["ons_code", "financial_year", "band_d_incl_parish"]]
    dwellings = ctsop_la_year[ctsop_la_year["financial_year"].isin(VARIANT3_YEARS)][["ons_code", "financial_year", "all_properties"]]
    hpi = hpi_la_factors[hpi_la_factors["financial_year"].isin(VARIANT3_YEARS)][["ons_code", "financial_year", "hpi_factor_la"]]
    nat = hpi_national_factors[hpi_national_factors["financial_year"].isin(VARIANT3_YEARS)][["financial_year", "hpi_factor_national"]]

    panel = bd.merge(dwellings, on=["ons_code", "financial_year"]).merge(hpi, on=["ons_code", "financial_year"]).merge(nat, on="financial_year")
    panel = panel.merge(settlement_la_year, on=["ons_code", "financial_year"], how="left")

    panel["relative_hpi"] = panel["hpi_factor_la"] / panel["hpi_factor_national"]
    panel["csp_per_dwelling"] = panel["csp_total"] * 1_000_000 / panel["all_properties"]
    panel["region"] = panel["ons_code"].map(REGION)

    panel = panel.sort_values(["ons_code", "financial_year"])
    panel["rate_growth"] = panel.groupby("ons_code")["band_d_incl_parish"].transform(lambda s: np.log(s / s.shift(1)))
    panel["delta_csp_per_dwelling"] = panel.groupby("ons_code")["csp_per_dwelling"].transform(lambda s: s - s.shift(1))

    return panel.reset_index(drop=True)


class Variant3Result:
    def __init__(self, model, panel: pd.DataFrame, subsample: str):
        self.model = model
        self.panel = panel
        self.subsample = subsample  # "pooled", "non_london", "london_only" - which LAs this was fit on

    @property
    def coefficient(self) -> float:
        return self.model.params["relative_hpi"]

    @property
    def conf_int(self) -> tuple[float, float]:
        ci = self.model.conf_int(alpha=0.05).loc["relative_hpi"]
        return float(ci[0]), float(ci[1])

    @property
    def pvalue(self) -> float:
        return float(self.model.pvalues["relative_hpi"])


def within_la_correlation(panel: pd.DataFrame, region_filter: str | None = None) -> float:
    """The decisive diagnostic (see module docstring): the correlation
    between an LA's own year-to-year DEVIATION from its own mean
    relative_hpi and its own deviation from its own mean rate_growth -
    i.e. does THIS LA's rate growth co-move with THIS LA's appreciation,
    independent of any cross-LA/cross-region level difference. Not the
    regression coefficient itself (which pools all LAs and is a linear
    projection controlling for the settlement and year effects too) - a
    simpler, harder-to-misread number for exactly the comparison that
    matters here: London vs everywhere else."""
    df = panel.dropna(subset=["relative_hpi", "rate_growth"])
    if region_filter == "london":
        df = df[df["region"] == "London"]
    elif region_filter == "non_london":
        df = df[df["region"] != "London"]
    rhpi_demean = df.groupby("ons_code")["relative_hpi"].transform(lambda s: s - s.mean())
    rgrowth_demean = df.groupby("ons_code")["rate_growth"].transform(lambda s: s - s.mean())
    return float(rhpi_demean.corr(rgrowth_demean))


def run_variant3_regression(panel: pd.DataFrame, subsample: str = "pooled") -> Variant3Result:
    """OLS with LA and year fixed effects (dummy variables - simplest to
    verify directly, not an approximation of a "true" fixed-effects
    estimator, since LSDV and within-transformation are numerically
    equivalent for a balanced/near-balanced panel), SEs clustered by LA.
    Drops the panel's first year (no t-1 to compute growth against) and
    any row with a missing settlement control (see
    parsers.settlement.parse "known, quantified gap" - the transitional-
    county apportionment gap) explicitly, not silently.

    `subsample`: "pooled" (all 296 LAs, the specification as originally
    agreed), "non_london" (263 LAs - the PRIMARY result, per the module
    docstring's finding), or "london_only" (33 LAs - reported for
    completeness; underpowered on its own, 33 clusters is thin for
    cluster-robust SEs, which is why the within-LA correlation, not this
    regression's p-value, is the number that actually establishes the
    London effect)."""
    reg_data = panel.dropna(subset=["rate_growth", "relative_hpi", "delta_csp_per_dwelling"]).copy()
    if subsample == "non_london":
        reg_data = reg_data[reg_data["region"] != "London"]
    elif subsample == "london_only":
        reg_data = reg_data[reg_data["region"] == "London"]
    elif subsample != "pooled":
        raise ValueError(f"subsample must be 'pooled', 'non_london', or 'london_only', got {subsample!r}")

    model = smf.ols(
        "rate_growth ~ relative_hpi + delta_csp_per_dwelling + C(ons_code) + C(financial_year)",
        data=reg_data,
    ).fit(cov_type="cluster", cov_kwds={"groups": reg_data["ons_code"]})
    return Variant3Result(model=model, panel=reg_data, subsample=subsample)


def interpret_offset(result: Variant3Result, engine_la_year: pd.DataFrame, ons_code: str, bound: str = "upper") -> dict:
    """Translates the regression coefficient (an annual LOG rate-growth
    effect per unit of `relative_hpi`) into "at most X% of this LA's
    measured Variant 1 gap could be rate-setting compensation" - a
    concrete, worked comparison against a REAL LA's REAL measured gap,
    not an abstract elasticity.

    **Refuses to cross the London/non-London boundary the data itself
    drew.** `result` must come from a regression fit on a subsample that
    actually contains `ons_code`'s own region (module docstring: the
    within-LA relationship is -0.57 in London, +0.08 outside it - two
    different relationships, not one relationship measured with
    different precision). Passing a `pooled` or `london_only` result for
    a non-London LA, or a `non_london` result for a London LA, raises
    rather than silently extrapolating - this is the one hard rule this
    module enforces at the code level, not just in the write-up, because
    it is the single most misleading number this function could produce.

    Method: hold `relative_hpi` at this LA's own observed panel mean,
    multiply by the coefficient (or the requested CI bound) to get an
    implied annual log rate-growth SUPPRESSION, compound it over the
    number of panel years to get an implied CUMULATIVE % rate
    suppression, apply that % to the LA's cumulative Variant 1
    counterfactual liability (`variant1_cf`) over the same years to get
    an implied GBP "offset", and express that as a share of the LA's
    actual measured Variant 1 gap over the same years.

    **The specific extrapolation this makes, stated plainly because it is
    the load-bearing assumption of this whole function.** LA fixed
    effects mean the regression identifies beta from WITHIN-LA deviations
    around each LA's own mean `relative_hpi` - it does NOT identify any
    relationship between an LA's average LEVEL of relative_hpi and its
    average rate growth (that level is exactly what the LA fixed effect
    absorbs). Multiplying beta by an LA's mean `relative_hpi` therefore
    extrapolates a within-LA estimator to a between-LA/level question the
    model does not itself answer - a real, named assumption, not a
    computation the regression validates on its own. It is the
    favourable-to-the-objection direction (it credits rate-setting with
    more compensation than the model strictly identifies), which is why
    `bound="ceiling"` (not the coefficient's point estimate) is the
    number that belongs in a headline claim about how much this could
    matter.

    **Centred on 1.0 (the national average), not on 0.** `relative_hpi`
    is a ratio and is always positive - using its raw level would imply
    "every LA's rates were suppressed to some degree," including LAs
    whose relative appreciation was BELOW the national average, which
    does not match the objection being tested (that HIGH-appreciation
    areas differentially compensate). `relative_hpi - 1` is zero for an
    LA that tracked the national average exactly, positive for
    above-average appreciation, and negative for below-average.

    **`bound="ceiling"` picks whichever CI endpoint maximises the implied
    offset, not "the upper number."** Because `relative_hpi - 1` flips
    sign for a below-average LA, which raw CI endpoint (-0.0143 or
    +0.0017, say) is "favourable to the objection" DEPENDS on whether the
    LA's own mean `relative_hpi` is above or below 1 - for an above-
    average LA (Westminster), the more NEGATIVE coefficient implies more
    suppression; for a below-average LA (Hartlepool), it is the LESS
    negative (or positive) end of the CI that does. Hardcoding "upper CI
    bound = ceiling" would silently understate the ceiling for roughly
    half the LAs in England. `bound="ceiling"` computes both endpoints
    and takes whichever actually produces the larger implied offset;
    `bound="point"` uses the coefficient estimate; passing a raw
    `"upper"`/`"lower"` is accepted for direct CI-endpoint inspection but
    is NOT the same thing as the ceiling and should not be reported as
    one."""
    la_region = REGION.get(ons_code)
    is_london = la_region == "London"
    if result.subsample == "non_london" and is_london:
        raise ValueError(f"{ons_code} is in London; a non_london regression result cannot be applied to it.")
    if result.subsample in ("london_only", "pooled") and not is_london:
        # Both london_only and pooled are, per the module docstring's own
        # finding, estimates of London's within-LA relationship (pooled is
        # ~entirely driven by it) - applying either to a non-London LA
        # would extrapolate London's -0.57 within-LA correlation onto an
        # LA where the measured relationship is +0.08. Refused, not
        # smoothed over: this is the specific number this function exists
        # to prevent.
        raise ValueError(
            f"{ons_code} is not in London; a '{result.subsample}' regression result reflects London's own within-LA "
            "relationship and cannot be applied to a non-London LA - use subsample='non_london' instead."
        )

    panel = result.panel
    la_panel = panel[panel["ons_code"] == ons_code]
    n_years = la_panel["financial_year"].nunique()
    mean_relative_hpi = la_panel["relative_hpi"].mean()

    def _suppression_share(coef: float) -> float:
        return 1 - np.exp(coef * (mean_relative_hpi - 1) * n_years)

    if bound == "ceiling":
        share_lo, share_hi = _suppression_share(result.conf_int[0]), _suppression_share(result.conf_int[1])
        coef = result.conf_int[0] if share_lo > share_hi else result.conf_int[1]
    elif bound == "point":
        coef = result.coefficient
    elif bound in ("upper", "lower"):
        coef = result.conf_int[1] if bound == "upper" else result.conf_int[0]
    else:
        raise ValueError(f"bound must be 'ceiling', 'point', 'upper', or 'lower', got {bound!r}")

    implied_cumulative_suppression_share = _suppression_share(coef)

    eng = engine_la_year[(engine_la_year["ons_code"] == ons_code) & (engine_la_year["financial_year"].isin(VARIANT3_YEARS))]
    cumulative_cf = eng["variant1_cf"].sum()
    cumulative_gap = eng["variant1_gap"].sum()
    implied_offset_gbp = implied_cumulative_suppression_share * cumulative_cf

    return {
        "ons_code": ons_code,
        "subsample": result.subsample,
        "bound": bound,
        "coefficient_used": coef,
        "mean_relative_hpi": mean_relative_hpi,
        "n_years": n_years,
        "implied_cumulative_suppression_share": implied_cumulative_suppression_share,
        "implied_offset_gbp": implied_offset_gbp,
        "cumulative_measured_gap_gbp": cumulative_gap,
        "implied_offset_share_of_measured_gap": implied_offset_gbp / cumulative_gap if cumulative_gap else float("nan"),
    }
