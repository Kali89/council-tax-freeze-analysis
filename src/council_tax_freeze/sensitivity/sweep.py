"""
Phase 5 sensitivity sweep. Every function here re-runs the SAME engine
(`engine.build.build_engine`) with exactly one input changed - never a
parallel or reimplemented calculation - so a result here is directly
comparable to the base case rather than an approximation of it.

Thresholds this module is checked against were written down and committed
BEFORE this module existed - see SENSITIVITY_PREREGISTRATION.md at the
repo root for what each axis is predicted to do and what would count as a
failure. Do not add new thresholds here after seeing a result; if a result
demands a new question, that is a new, separately dated document.
"""

from __future__ import annotations

import pandas as pd

from council_tax_freeze.boundaries.regions import REGION, REGION_CODE
from council_tax_freeze.config import (
    BAND_A_RATIO_GRID,
    BAND_H_RATIO_GRID,
    COLLECTION_FACTOR_GRID,
    HEADLINE_FIRST_YEAR,
)
from council_tax_freeze.engine.build import EngineResult, build_engine


def region_metric(engine_result: EngineResult, ctsop_la_year: pd.DataFrame, variant: str = "variant1") -> dict[str, float]:
    """£ / dwelling / year, dwelling-year-weighted, per ONS region - the
    metric defined in SENSITIVITY_PREREGISTRATION.md `metric(region)`.
    `ctsop_la_year` supplies `all_properties` as the weight; it is always
    the BASE-CASE dwelling count table regardless of which axis is being
    swept (dwelling counts don't depend on any of the four swept
    parameters), so callers pass the same one table throughout."""
    dwell = ctsop_la_year[["ons_code", "financial_year", "all_properties"]]
    la_year = engine_result.la_year.merge(dwell, on=["ons_code", "financial_year"], how="left")
    la_year["region"] = la_year["ons_code"].map(REGION)
    out = {}
    for region, sub in la_year.groupby("region"):
        out[region] = sub[f"{variant}_gap"].sum() / sub["all_properties"].sum()
    return out


def run_midpoint_grid(
    band_d_la_year: pd.DataFrame,
    ctsop_la_year: pd.DataFrame,
    ctsop_predecessor_weights: pd.DataFrame,
    hpi_la_factors: pd.DataFrame,
    hpi_national_factors: pd.DataFrame,
) -> pd.DataFrame:
    """All 12 BAND_A_RATIO_GRID x BAND_H_RATIO_GRID combinations. One row
    per combination: the resulting North East and London £/dwelling/year
    metrics (Variant 1)."""
    rows = []
    for a in BAND_A_RATIO_GRID:
        for h in BAND_H_RATIO_GRID:
            eng = build_engine(band_d_la_year, ctsop_la_year, ctsop_predecessor_weights, hpi_la_factors, hpi_national_factors, band_a_ratio=a, band_h_ratio=h)
            metrics = region_metric(eng, ctsop_la_year)
            rows.append({"band_a_ratio": a, "band_h_ratio": h, "north_east": metrics["North East"], "london": metrics["London"]})
    return pd.DataFrame(rows)


def run_collection_factor_grid(
    band_d_la_year: pd.DataFrame,
    ctsop_la_year: pd.DataFrame,
    ctsop_predecessor_weights: pd.DataFrame,
    hpi_la_factors: pd.DataFrame,
    hpi_national_factors: pd.DataFrame,
) -> pd.DataFrame:
    """All 3 COLLECTION_FACTOR_GRID values. Predicted (see
    SENSITIVITY_PREREGISTRATION.md Axis 2) to move the £ gap EXACTLY
    linearly with the factor - this is an algebraic identity check, not a
    substantive robustness question."""
    rows = []
    for c in COLLECTION_FACTOR_GRID:
        eng = build_engine(band_d_la_year, ctsop_la_year, ctsop_predecessor_weights, hpi_la_factors, hpi_national_factors, collection_factor=c)
        metrics = region_metric(eng, ctsop_la_year)
        rows.append({"collection_factor": c, "north_east": metrics["North East"], "london": metrics["London"]})
    return pd.DataFrame(rows)


def region_broadcast_hpi_la_factors(hpi_region_factors: pd.DataFrame) -> pd.DataFrame:
    """Builds an la_factors-shaped table (ons_code, financial_year,
    hpi_factor_la) using each LA's REGION-level HPI factor in place of its
    own LA-level one - same shape `build_engine` already expects for
    `hpi_la_factors`, so no core engine change is needed for this axis,
    only a different input table."""
    rf = hpi_region_factors.rename(columns={"hpi_factor_region": "hpi_factor_la"})
    rows = []
    for ons_code, region_code in REGION_CODE.items():
        sub = rf[rf["region_code"] == region_code]
        for _, r in sub.iterrows():
            rows.append({"ons_code": ons_code, "financial_year": r["financial_year"], "hpi_factor_la": r["hpi_factor_la"]})
    return pd.DataFrame(rows)


def _revaluation_effective_year(fy: str, frequency: int, first_year: str = HEADLINE_FIRST_YEAR) -> str:
    """Which year's HPI factor an LA's counterfactual valuation actually
    uses under a periodic (every `frequency` years) revaluation cycle,
    starting from `first_year` - holds flat between revaluation points
    rather than tracking every year, the way a real periodic revaluation
    would."""
    y0 = int(first_year[:4])
    y = int(fy[:4])
    n = y - y0
    eff = y0 + (n // frequency) * frequency
    return f"{eff}-{str(eff + 1)[2:]}"


def apply_revaluation_frequency(factors: pd.DataFrame, frequency: str | int, factor_col: str, code_cols: list[str]) -> pd.DataFrame:
    """Replaces each row's `factor_col` value with the value from its
    `_revaluation_effective_year` - i.e. holds the counterfactual valuation
    flat between periodic revaluation points. `frequency="continuous"` is
    a no-op (return unchanged) - the base case already revalues every
    year. Works on either the LA-level or national-level factors table by
    varying `code_cols` (`["ons_code"]` or `[]`)."""
    if frequency == "continuous":
        return factors
    df = factors.copy()
    df["_effective_year"] = df["financial_year"].apply(lambda fy: _revaluation_effective_year(fy, frequency))
    lookup = df.set_index([*code_cols, "financial_year"])[factor_col]
    key_cols = [*code_cols, "_effective_year"]
    df[factor_col] = list(lookup.reindex(pd.MultiIndex.from_frame(df[key_cols].rename(columns={"_effective_year": "financial_year"}))))
    return df.drop(columns="_effective_year")
