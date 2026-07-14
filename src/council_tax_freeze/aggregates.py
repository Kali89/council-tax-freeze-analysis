"""
LA-total and region-total cumulative gap figures - a second unit of
analysis alongside the per-dwelling figures Phases 4-6 already produce.
The per-dwelling figure (£227.63/dwelling/year, North East, Variant 1) is
the honest primary unit and stays primary throughout this pipeline and in
notebooks/03_results.ipynb - it is what a reader can check against their
own bill, and it carries every caveat (single-pot exposure, the Phase 5
central-estimate correction) cleanly. This module exists because the
debate this analysis lands in - "London funds the rest of the country" -
is conducted in £-billions of regional net fiscal transfer, and a
£-per-household figure cannot answer a £-billions claim on its own; the
two are different currencies, and both are needed.

**The arithmetic this module exists to get right, stated precisely
because it is easy to get wrong in a way a critic could dismantle.**
`engine.build`'s `variant1_gap`/`variant2_gap` are ALREADY total-GBP
figures per (LA, financial year), not per-dwelling - confirmed directly,
not assumed: `tests/test_engine.py::test_revenue_neutrality_by_construction`
already pins that `variant1_gap` sums to ~0 across all 296 LAs in every
year, which is only possible if it is a real GBP transfer figure (summing
296 LAs' PER-DWELLING averages would not net to zero; summing 296 LAs'
actual GBP transfers within a closed revenue-neutral reallocation does,
by construction). The cumulative LA-total is therefore a plain sum of the
already-correct annual figures - `Σ_t gap[i,t]` - built up year by year
from that year's own real Band D rates and real dwelling stock.

**What this module deliberately does NOT do, because it is the wrong
answer and a critic's first move would be to check for it**: take the
single dwelling-year-weighted per-dwelling headline figure (a weighted
AVERAGE across the whole 2009-26 panel) and multiply it by a CURRENT
(e.g. 2025-26) dwelling count. Dwelling stock grew materially over
2009-2026 - multiplying a panel-average rate by today's larger stock
implicitly assumes today's housing stock existed throughout the whole
period, overstating the true cumulative total. `compute_naive_aggregate`
exists ONLY to demonstrate this error's size in a pinned regression test
(`tests/test_aggregates.py`), specifically so the difference between the
two methods cannot later be "simplified" away.
"""

from __future__ import annotations

import pandas as pd

from council_tax_freeze.boundaries.regions import REGION
from council_tax_freeze.config import HEADLINE_FIRST_YEAR, LAST_YEAR

# The five LAs Phase 4 found and quantified as inflated by the single-pot
# reallocation method (engine.build.compute_single_pot_bias_risk) - their
# gaps are upper bounds, not point estimates. Used here to compute a
# London aggregate WITH and WITHOUT these five, so a reader can see how
# much of the London total depends on the cells already flagged as
# inflated.
SINGLE_POT_FLAGGED_LAS = {
    "E09000033": "Westminster",
    "E09000032": "Wandsworth",
    "E09000013": "Hammersmith and Fulham",
    "E09000001": "City of London",
    "E09000020": "Kensington and Chelsea",
}


def _headline_years() -> list[str]:
    y0, y1 = int(HEADLINE_FIRST_YEAR[:4]), int(LAST_YEAR[:4])
    return [f"{y}-{str(y + 1)[2:]}" for y in range(y0, y1 + 1)]


def compute_la_cumulative_gap(engine_la_year: pd.DataFrame, ctsop_la_year: pd.DataFrame, variant: str = "variant1") -> pd.DataFrame:
    """Per LA: cumulative GBP gap over the whole headline period (sum of
    each year's already-total gap - see module docstring), alongside the
    dwelling-year-weighted per-dwelling-per-year figure for the SAME LA
    over the SAME years, so both units sit side by side rather than
    requiring a second lookup.

    `engine_la_year` is keyed on 2025-resolved target codes throughout
    (Barnsley/Sheffield included, since engine.build resolves every row
    to its 2025 target before returning). `ctsop_la_year` is raw VOA
    data and keeps Barnsley/Sheffield under their PRE-2025 codes in
    every year including 2025-26 (checked directly, not assumed - VOA
    never switches) - the same code-scheme mismatch already found and
    fixed in engine/build.py's own CTSOP join and in
    parsers/settlement/parse.py, appearing here for a third time.
    Applying the same substitution rather than a fourth different fix."""
    years = _headline_years()
    gap_col = f"{variant}_gap"
    eng = engine_la_year[engine_la_year["financial_year"].isin(years)]
    dwell = ctsop_la_year[ctsop_la_year["financial_year"].isin(years)][["ons_code", "financial_year", "all_properties", "authority"]].copy()
    dwell["ons_code"] = dwell["ons_code"].replace({"E08000016": "E08000038", "E08000019": "E08000039"})

    merged = eng.merge(dwell, on=["ons_code", "financial_year"], how="left")
    out = merged.groupby("ons_code", as_index=False).agg(
        cumulative_gap_gbp=(gap_col, "sum"),
        dwelling_years=("all_properties", "sum"),
    )
    names = dwell.drop_duplicates("ons_code")[["ons_code", "authority"]]
    out = out.merge(names, on="ons_code", how="left")
    out["cumulative_gap_gbp_m"] = out["cumulative_gap_gbp"] / 1_000_000
    out["per_dwelling_per_year_gbp"] = out["cumulative_gap_gbp"] / out["dwelling_years"]
    out["region"] = out["ons_code"].map(REGION)
    return out[["ons_code", "authority", "region", "cumulative_gap_gbp", "cumulative_gap_gbp_m", "dwelling_years", "per_dwelling_per_year_gbp"]]


def compute_region_cumulative_gap(la_cumulative: pd.DataFrame) -> pd.DataFrame:
    """Per ONS region: cumulative GBP gap (sum of constituent LAs'
    cumulative gaps - each already correctly built up year by year, see
    module docstring), alongside the region's own dwelling-year-weighted
    per-dwelling-per-year figure."""
    out = la_cumulative.groupby("region", as_index=False).agg(
        cumulative_gap_gbp=("cumulative_gap_gbp", "sum"),
        dwelling_years=("dwelling_years", "sum"),
    )
    out["cumulative_gap_gbp_m"] = out["cumulative_gap_gbp"] / 1_000_000
    out["cumulative_gap_gbp_bn"] = out["cumulative_gap_gbp"] / 1_000_000_000
    out["per_dwelling_per_year_gbp"] = out["cumulative_gap_gbp"] / out["dwelling_years"]
    return out.sort_values("cumulative_gap_gbp")


def compute_london_robustness_check(la_cumulative: pd.DataFrame) -> dict:
    """London's aggregate WITH and WITHOUT the five single-pot-flagged
    LAs (module docstring) - not a footnote. Reports how much of the
    London total depends on the cells Phase 4 already told readers are
    inflated, so a reader can see directly whether the London figure is
    robust to dropping them."""
    london = la_cumulative[la_cumulative["region"] == "London"]
    flagged = london[london["ons_code"].isin(SINGLE_POT_FLAGGED_LAS)]
    unflagged = london[~london["ons_code"].isin(SINGLE_POT_FLAGGED_LAS)]

    london_total = london["cumulative_gap_gbp"].sum()
    unflagged_total = unflagged["cumulative_gap_gbp"].sum()

    return {
        "london_total_gbp_bn": london_total / 1_000_000_000,
        "london_total_excl_flagged_gbp_bn": unflagged_total / 1_000_000_000,
        "flagged_five_share_of_london_total": 1 - (unflagged_total / london_total) if london_total else float("nan"),
        "flagged_five_total_gbp_bn": flagged["cumulative_gap_gbp"].sum() / 1_000_000_000,
    }


def compute_naive_aggregate(engine_la_year: pd.DataFrame, ctsop_la_year: pd.DataFrame, ons_code: str, current_year: str = "2025-26", variant: str = "variant1") -> float:
    """The WRONG method, computed only so its error can be measured and
    pinned in a test (see module docstring) - never used for a reported
    figure. Multiplies the panel-wide dwelling-year-weighted per-dwelling
    average by the CURRENT year's dwelling count and the number of
    headline years, silently assuming today's dwelling stock existed
    throughout 2009-2026."""
    years = _headline_years()
    gap_col = f"{variant}_gap"
    ctsop_code = {"E08000038": "E08000016", "E08000039": "E08000019"}.get(ons_code, ons_code)  # see compute_la_cumulative_gap
    eng = engine_la_year[(engine_la_year["ons_code"] == ons_code) & (engine_la_year["financial_year"].isin(years))]
    dwell = ctsop_la_year[(ctsop_la_year["ons_code"] == ctsop_code) & (ctsop_la_year["financial_year"].isin(years))]

    merged = eng.merge(dwell[["financial_year", "all_properties"]], on="financial_year")
    per_dwelling_per_year = merged[gap_col].sum() / merged["all_properties"].sum()

    current_dwellings = dwell[dwell["financial_year"] == current_year]["all_properties"]
    if len(current_dwellings) == 0:
        raise ValueError(f"no dwelling count for {ons_code} in {current_year}")
    return per_dwelling_per_year * current_dwellings.iloc[0] * len(years)
