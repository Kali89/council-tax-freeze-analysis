"""
The counterfactual engine. Joins Band D (rates), CTSOP (band counts) and
HPI (revaluation factors) into actual and counterfactual liability per
2025-vintage LA per headline financial year (config.HEADLINE_FIRST_YEAR to
LAST_YEAR - see config.py and DATA.md for why the 2000-09 backward
extension is handled separately and is NOT built here).

**Resolution design - liabilities are summed, never rates blended.**
Band D preserves predecessor-level rows for the 2019/2020/2021/2023 reorg
waves throughout the WHOLE headline period (Band D only switches a given
LA to its successor code once that wave's own reorg date passes). CTSOP,
once de-duplicated (see parsers/ctsop/parse.py), retains real
predecessor-level band counts for exactly the same predecessors
(`predecessor_weights`), for the whole 1993-2024 span - checked directly
before writing this module (East Dorset, FY2015-16, has real band-level
CTSOP data, a decade before its 2019 abolition). So for every headline
year, every Band D row - predecessor or successor - has a matching CTSOP
row at the SAME resolution. Actual liability is computed at whichever
resolution Band D provides, THEN SUMMED (not averaged, not weighted-blended)
to 2025-vintage geography via the Phase 1 crosswalk. This sidesteps the
"what weight to use" question entirely, because liability is additive and
rates never need to be combined into a single blended figure.

The ONLY place this doesn't hold is the 2009 reorg wave, where CTSOP has
NO predecessor-level rows at all (unlike the 2019+ waves) - but by
construction, Band D ALSO only shows successor-code rows for the 2009-wave
LAs from FY2009-10 onward, i.e. from the very first headline year. There is
no year in the headline period where a 2009-wave predecessor row needs
matching and none exists.

HPI factors are computed only at 2025-vintage LA level (Land Registry's
own HPI methodology retroactively applies current LA boundaries - see
hpi/build.py). A predecessor's stock-value calculation therefore uses its
eventual 2025-successor's HPI trajectory, not a predecessor-specific one -
the finest geography HPI data actually offers, noted as an approximation,
not hidden.

**Variant 1 (freeze only, keep multipliers)**, unlike Variant 2, needs a
band REASSIGNMENT, not just a value: which 1991-basis band would a dwelling
be in if bands were redrawn using year-t values, while keeping the existing
6/9-18/9 multiplier structure? Property-level data (what IFS used) isn't
available here, only band-level counts - so a coarse but stated
approximation is used: every dwelling in a given 1991 band is assumed to
sit at that band's assumed 1991 midpoint (config.band_midpoints_1991 - the
same reference value the stock-value calculation already uses); that
midpoint is inflated by the row's own (2025-target) HPI factor to estimate
a year-t value; band thresholds are rescaled by the NATIONAL AVERAGE HPI
factor for that year (not each LA's own factor - the whole point is to
isolate relative movement); and the dwelling-count cohort is reassigned
whole to whichever rescaled band its estimated value falls into. This
means a band's dwellings all move together rather than partially - a
genuine approximation, stated here rather than left implicit.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from council_tax_freeze.boundaries.crosswalk import AmbiguousBoundaryChange, UnmappedLocalAuthorityCode, resolve
from council_tax_freeze.boundaries.lad_2025 import LAD_2025_CODES
from council_tax_freeze.config import (
    BAND_MULTIPLIER,
    BAND_THRESHOLD_1991,
    COLLECTION_FACTOR,
    ENGLAND_BANDS,
    HEADLINE_FIRST_YEAR,
    LAST_YEAR,
    band_midpoints_1991,
)

BANDS = ENGLAND_BANDS  # ["A", ..., "H"]


class UnresolvedLiabilityRow(Exception):
    """Raised when a Band D row has no matching CTSOP band-count row, or no
    HPI factor, at the same (code, year) - per this module's docstring,
    this should not occur anywhere in the headline period. If it does,
    that is a finding to report, not a gap to paper over with an
    assumption. See build_engine's `unresolved` output."""


def _financial_years(first: str, last: str) -> list[str]:
    y0, y1 = int(first[:4]), int(last[:4])
    return [f"{y}-{str(y + 1)[2:]}" for y in range(y0, y1 + 1)]


HEADLINE_YEARS = _financial_years(HEADLINE_FIRST_YEAR, LAST_YEAR)


def _recode_aliases() -> dict[str, str]:
    """old_code -> new_code for pure RECODE events (e.g. Sheffield 2025).
    Band D applies the new code RETROACTIVELY across its whole history;
    CTSOP's consolidated file uses the old code until 2025. Same real-world
    geography, two different code labels for the same years - not a data
    gap, a join-key mismatch, found by the engine's own unresolved-row
    diagnostics rather than anticipated in advance.

    Barnsley's own old->new transition is modelled as part of the
    BARNSLEY_SHEFFIELD_2025 SPLIT event, not a separate RECODE (its
    boundary genuinely changed, however slightly) - but for the SAME
    reason as Sheffield, Band D still applies Barnsley's new code
    retroactively while CTSOP uses the old one pre-2025, so the alias is
    needed here too. Found the same way: an engine unresolved-row
    diagnostic, not anticipated when Phase 1 built the SPLIT event."""
    from council_tax_freeze.boundaries.reorg_events import EVENTS, ChangeType

    aliases = {o.code: n.code for e in EVENTS if e.change_type == ChangeType.RECODE for o, n in zip(e.olds, e.news) if o.code and n.code}
    aliases["E08000016"] = "E08000038"  # Barnsley old -> new, see docstring
    return aliases


def _ctsop_lookup(ctsop_la_year: pd.DataFrame, ctsop_predecessor_weights: pd.DataFrame) -> dict:
    """(ons_code, financial_year) -> {band: count}, preferring the
    de-duplicated successor/current table and falling back to the
    preserved predecessor rows - both are real, non-imputed CTSOP data.
    Also indexed under each RECODE event's NEW code (see _recode_aliases),
    so a Band D row keyed by the new code still finds the matching CTSOP
    row keyed by the old one, for years before the code changed."""
    aliases = _recode_aliases()
    lookup = {}
    for df in (ctsop_predecessor_weights, ctsop_la_year):  # la_year second so it takes precedence on overlap
        for _, row in df.iterrows():
            band_counts = {b: row[f"band_{b.lower()}"] for b in BANDS}
            lookup[(row["ons_code"], row["financial_year"])] = band_counts
            alias = aliases.get(row["ons_code"])
            if alias:
                lookup.setdefault((alias, row["financial_year"]), band_counts)
    return lookup


def _rescaled_thresholds(national_hpi_factor: float) -> dict[str, float]:
    return {b: t * national_hpi_factor for b, t in BAND_THRESHOLD_1991.items()}


def _assign_band(value: float, thresholds: dict[str, float]) -> str:
    band = "A"
    for b in BANDS:
        if value >= thresholds[b]:
            band = b
        else:
            break
    return band


def _reassign_bands(counts: dict[str, float], la_hpi_factor: float, thresholds: dict[str, float], midpoints: dict[str, float]) -> dict[str, float]:
    """Variant 1's band reassignment - see module docstring for the method
    and its stated approximation (whole-cohort movement, no within-band
    dispersion)."""
    new_counts = {b: 0.0 for b in BANDS}
    for old_band, count in counts.items():
        if not count:
            continue
        estimated_value = midpoints[old_band] * la_hpi_factor
        new_band = _assign_band(estimated_value, thresholds)
        new_counts[new_band] += count
    return new_counts


def _equal_split_fallback() -> dict[str, tuple[str, int]]:
    """predecessor_code -> (immediate merge-successor code, sibling count),
    for the three 2019 merge events whose predecessors have NO row anywhere
    in CTSOP (unlike every other merge event in reorg_events.py, where real
    predecessor-level CTSOP data exists throughout - see engine module
    docstring). Quantified before use, not assumed: West Suffolk + East
    Suffolk + Somerset West and Taunton together hold ~0.8% of England's
    dwelling stock (vs 6.3% for the 2009 wave), and the affected predecessor
    pairs' Band D rates differ by 0-3.7% (vs ~16% for County Durham) - an
    order of magnitude smaller on both the exposure and heterogeneity axes
    that made the 2009-wave gap material. Neither Suffolk nor Somerset sits
    on the North/South fault line this analysis measures. By the same
    decision framework, this is a documented limitation, not a second
    backward-extension case: an EQUAL split of the immediate successor's
    real combined CTSOP count across its sibling predecessors, each then
    charged at ITS OWN real Band D rate - not an unweighted AVERAGE rate
    applied once, so the small (0-3.7%) rate difference between siblings is
    still reflected, just not weighted by a dwelling count neither source
    provides at this resolution."""
    from council_tax_freeze.boundaries.reorg_events import EVENTS, ChangeType

    fallback = {}
    for e in EVENTS:
        if e.change_type == ChangeType.MERGE and e.effective_date == "2019-04-01" and len(e.olds) == 2:
            names = {o.name for o in e.olds}
            if names & {"Forest Heath", "St Edmundsbury", "Suffolk Coastal", "Waveney", "Taunton Deane", "West Somerset"}:
                for o in e.olds:
                    fallback[o.code] = (e.news[0].code, len(e.olds))
    return fallback


@dataclass
class RowLiability:
    ons_code: str
    financial_year: str
    target_code: str
    weight: float
    actual: float
    stock_value_1991_basis: float  # Variant 2's proportional reallocation base
    variant1_tax_base: float  # Variant 1's reassigned-band tax base


def _compute_row_liabilities(
    band_d_la_year: pd.DataFrame,
    ctsop_lookup: dict,
    hpi_factor_lookup: dict,
    national_hpi_factor_lookup: dict,
) -> tuple[list[RowLiability], list[dict]]:
    """One row per Band D (ons_code, financial_year) present in the
    headline period. Returns (resolved rows, unresolved-row diagnostics)."""
    band_d = band_d_la_year[band_d_la_year["financial_year"].isin(HEADLINE_YEARS)]
    band_d = band_d[band_d["band_d_incl_parish"].notna()]

    midpoints = band_midpoints_1991()
    equal_split = _equal_split_fallback()
    rows: list[RowLiability] = []
    unresolved: list[dict] = []

    for _, r in band_d.iterrows():
        code, name, fy = r["ons_code"], r["authority"], r["financial_year"]
        counts = ctsop_lookup.get((code, fy))
        split_divisor = 1
        if counts is None and code in equal_split:
            successor_code, n_siblings = equal_split[code]
            successor_counts = ctsop_lookup.get((successor_code, fy))
            if successor_counts is not None:
                counts = successor_counts
                split_divisor = n_siblings
        if counts is None:
            unresolved.append({"ons_code": code, "authority": name, "financial_year": fy, "reason": "no matching CTSOP row"})
            continue
        if split_divisor > 1:
            counts = {b: (v / split_divisor if v is not None else v) for b, v in counts.items()}

        national_hpi_factor = national_hpi_factor_lookup.get(fy)
        if national_hpi_factor is None:
            unresolved.append({"ons_code": code, "authority": name, "financial_year": fy, "reason": "no national HPI factor"})
            continue
        thresholds = _rescaled_thresholds(national_hpi_factor)

        as_of = f"{fy.split('-')[0]}-04-01"
        try:
            resolved = resolve(code, name, as_of)
        except (AmbiguousBoundaryChange, UnmappedLocalAuthorityCode) as e:
            unresolved.append({"ons_code": code, "authority": name, "financial_year": fy, "reason": str(e)})
            continue

        band_d_rate = r["band_d_incl_parish"]
        tax_base_actual = sum((counts[b] or 0) * BAND_MULTIPLIER[b] for b in BANDS)
        actual = band_d_rate * tax_base_actual * COLLECTION_FACTOR

        for target_code, _target_name, weight in resolved:
            if target_code not in LAD_2025_CODES:
                unresolved.append({"ons_code": code, "authority": name, "financial_year": fy, "reason": f"resolved to non-2025 code {target_code}"})
                continue
            hpi_factor = hpi_factor_lookup.get((target_code, fy))
            if hpi_factor is None:
                unresolved.append({"ons_code": code, "authority": name, "financial_year": fy, "reason": f"no HPI factor for target {target_code}"})
                continue

            stock_value = sum((counts[b] or 0) * midpoints[b] for b in BANDS) * hpi_factor

            reassigned = _reassign_bands(counts, hpi_factor, thresholds, midpoints)
            variant1_tax_base = sum(reassigned[b] * BAND_MULTIPLIER[b] for b in BANDS)

            rows.append(
                RowLiability(
                    ons_code=code,
                    financial_year=fy,
                    target_code=target_code,
                    weight=weight,
                    actual=actual * weight,
                    stock_value_1991_basis=stock_value * weight,
                    variant1_tax_base=variant1_tax_base * weight,
                )
            )

    return rows, unresolved


@dataclass
class EngineResult:
    la_year: pd.DataFrame  # ons_code, financial_year, actual, variant1_cf, variant1_gap, variant2_cf, variant2_gap
    national: pd.DataFrame  # financial_year, national_actual_revenue
    unresolved: pd.DataFrame  # diagnostic - should be empty for the headline period


def build_engine(
    band_d_la_year: pd.DataFrame,
    ctsop_la_year: pd.DataFrame,
    ctsop_predecessor_weights: pd.DataFrame,
    hpi_la_factors: pd.DataFrame,
    hpi_national_factors: pd.DataFrame,
) -> EngineResult:
    ctsop_lookup = _ctsop_lookup(ctsop_la_year, ctsop_predecessor_weights)
    hpi_factor_lookup = {(r["ons_code"], r["financial_year"]): r["hpi_factor_la"] for _, r in hpi_la_factors.iterrows()}
    national_hpi_factor_lookup = {r["financial_year"]: r["hpi_factor_national"] for _, r in hpi_national_factors.iterrows()}

    rows, unresolved = _compute_row_liabilities(band_d_la_year, ctsop_lookup, hpi_factor_lookup, national_hpi_factor_lookup)
    unresolved_df = pd.DataFrame(unresolved)

    row_df = pd.DataFrame([r.__dict__ for r in rows])
    la_year = row_df.groupby(["target_code", "financial_year"], as_index=False)[
        ["actual", "stock_value_1991_basis", "variant1_tax_base"]
    ].sum()
    la_year = la_year.rename(columns={"target_code": "ons_code"})

    national = la_year.groupby("financial_year", as_index=False)["actual"].sum().rename(columns={"actual": "national_actual_revenue"})
    la_year = la_year.merge(national, on="financial_year")

    stock_totals = la_year.groupby("financial_year")["stock_value_1991_basis"].transform("sum")
    la_year["variant2_cf"] = la_year["national_actual_revenue"] * la_year["stock_value_1991_basis"] / stock_totals
    la_year["variant2_gap"] = la_year["actual"] - la_year["variant2_cf"]

    v1_totals = la_year.groupby("financial_year")["variant1_tax_base"].transform("sum")
    la_year["variant1_cf"] = la_year["national_actual_revenue"] * la_year["variant1_tax_base"] / v1_totals
    la_year["variant1_gap"] = la_year["actual"] - la_year["variant1_cf"]

    return EngineResult(la_year=la_year, national=national, unresolved=unresolved_df)
