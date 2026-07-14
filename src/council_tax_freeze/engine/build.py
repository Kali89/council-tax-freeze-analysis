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
hpi/build.py). A predecessor's revalued-value calculation therefore uses
its eventual 2025-successor's HPI trajectory, not a predecessor-specific
one - the finest geography HPI data actually offers, noted as an
approximation, not hidden.

**Variant 1 and Variant 2 are one calculation, not two.** This is a
rewrite: an earlier version computed Variant 1 by reassigning whole band
COHORTS to a new discrete band via nationally-rescaled thresholds, and
Variant 2 separately via a raw stock-value sum - two different
approximation methods that turned out NOT to nest properly (checked
across all 296 LAs for FY2018-19: only 80% sign agreement between the two,
concentrated in mid-value commuter-belt LAs sitting near band-threshold
edges, where the old Variant 1's whole-cohort discretisation produced
step-function jumps uncorrelated with Variant 2's continuous calculation).

The fix: for every (LA, band) cohort, compute one RELATIVE value -
`relative_value = band_midpoint_1991[b] * (hpi_factor_la / hpi_factor_national)`
- how this cohort's assumed 1991 value has moved relative to the NATIONAL
AVERAGE since the baseline (not relative to its own LA, which is what
Variant 2 originally used - see below for why this doesn't change Variant
2's result). This is then passed through ONE of two liability-multiplier
functions:

  - Variant 1 (freeze only, keep the existing 6/9-18/9 multiplier
    structure): `_compressed_multiplier(v)`, a smooth, monotonic function
    built from the SAME eight (band midpoint, multiplier) control points
    as the real system, piecewise-linear in log(value), linearly
    extrapolated beyond Band A and Band H. It exactly reproduces today's
    multiplier when `relative_value` equals a band's own midpoint (i.e.
    zero relative movement gives zero change), and varies smoothly
    in between and beyond - no discrete band reassignment, no
    whole-cohort jumps.
  - Variant 2 (freeze + compression, fully proportional to value):
    `_proportional_multiplier(v) = v / band_D_midpoint_1991` - literally
    "Variant 1 with the compression removed": the same relative_value,
    the same reallocation mechanism, a different (linear, uncompressed)
    multiplier function in place of the compressed one.

Both then feed the SAME reallocation step:
`cf[i,t] = national_actual_revenue[t] * tax_base[i,t] / sum_j(tax_base[j,t])`
- literally the same code, run twice with a different multiplier function.
This is what "V2 = V1 minus compression" means concretely, and it is why a
future tiered reallocation (district/county/police/fire/GLA reallocated
separately - see DATA.md "Westminster" finding) only needs to be built
once, against this shared reallocation step, not twice against two
divergent calculations.

Using relative-to-national value (rather than each LA's own absolute HPI
factor) for BOTH variants is deliberate, not just for Variant 1: dividing
every LA's estimated value by the SAME per-year national factor is a
common scalar that cancels out in Variant 2's SHARE-based reallocation
(linear function: m(v/k) = m(v)/k for constant k) - so Variant 2's
computed gap is numerically IDENTICAL to the old absolute-value version.
For Variant 1's genuinely nonlinear compressed-multiplier function this
choice is NOT cosmetic: relative-to-national value is what correctly
isolates "the effect of the frozen valuation date" (the brief's own
framing) rather than conflating it with nationwide nominal appreciation,
and matches IFS's own stated methodology of redrawing band thresholds to
preserve NATIONAL band-population shares, not each LA's own.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from council_tax_freeze.boundaries.crosswalk import AmbiguousBoundaryChange, UnmappedLocalAuthorityCode, resolve
from council_tax_freeze.boundaries.lad_2025 import LAD_2025_CODES
from council_tax_freeze.boundaries.precepting_groups import PRECEPTING_GROUP
from council_tax_freeze.config import (
    BAND_MULTIPLIER,
    COLLECTION_FACTOR,
    ENGLAND_BANDS,
    HEADLINE_FIRST_YEAR,
    LAST_YEAR,
    band_midpoints_1991,
)

BANDS = ENGLAND_BANDS  # ["A", ..., "H"]


def _safe_count(v: float | None) -> float:
    """CTSOP suppresses small band counts as blank cells, parsed as NaN, not
    0 (parsers/ctsop/parse.py). `v or 0` looks like it handles this but does
    not: NaN is truthy in Python, so `nan or 0` evaluates to `nan`, not 0,
    and that NaN then silently zeroes an LA's ENTIRE actual/counterfactual
    liability for that year once pandas' skipna groupby-sum collapses an
    all-NaN group to 0.0 - found via City of London (E09000001) reading as
    exactly GBP0 actual revenue for 2017-18 onward, while investigating the
    single-pot bias risk statistic; also affects Tamworth (E07000199),
    2009-10 to 2012-13. 13 (LA, year) cells total in the headline period,
    2 LAs - small, but City of London is one of the named single-pot
    outliers, so silently wrong there specifically mattered."""
    return 0.0 if v is None or (isinstance(v, float) and math.isnan(v)) else v


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


def _multiplier_control_points() -> tuple[list[float], list[float]]:
    """(log(band midpoint), multiplier) control points, sorted ascending -
    the real system's own eight points, used to build the smooth
    compressed-multiplier curve. Not re-derived per call."""
    midpoints = band_midpoints_1991()
    pairs = sorted((midpoints[b], BAND_MULTIPLIER[b]) for b in BANDS)
    log_points = [math.log(v) for v, _m in pairs]
    mult_points = [m for _v, m in pairs]
    return log_points, mult_points


_LOG_POINTS, _MULT_POINTS = _multiplier_control_points()
_D_MIDPOINT = band_midpoints_1991()["D"]


def _compressed_multiplier(value: float) -> float:
    """Smooth, monotonic interpolation of the real 6/9-18/9 multiplier
    structure as a continuous function of value - piecewise-linear in
    log(value) between the eight band-midpoint control points, linearly
    extrapolated (same slope as the nearest segment) beyond Band A and
    Band H. See module docstring for why this replaces discrete band
    reassignment."""
    if value <= 0:
        return _MULT_POINTS[0]
    logv = math.log(value)
    if logv <= _LOG_POINTS[0]:
        slope = (_MULT_POINTS[1] - _MULT_POINTS[0]) / (_LOG_POINTS[1] - _LOG_POINTS[0])
        return _MULT_POINTS[0] + slope * (logv - _LOG_POINTS[0])
    if logv >= _LOG_POINTS[-1]:
        slope = (_MULT_POINTS[-1] - _MULT_POINTS[-2]) / (_LOG_POINTS[-1] - _LOG_POINTS[-2])
        return _MULT_POINTS[-1] + slope * (logv - _LOG_POINTS[-1])
    for i in range(len(_LOG_POINTS) - 1):
        if _LOG_POINTS[i] <= logv <= _LOG_POINTS[i + 1]:
            frac = (logv - _LOG_POINTS[i]) / (_LOG_POINTS[i + 1] - _LOG_POINTS[i])
            return _MULT_POINTS[i] + frac * (_MULT_POINTS[i + 1] - _MULT_POINTS[i])
    raise AssertionError("unreachable - log_points must be sorted and cover logv by the checks above")


def _proportional_multiplier(value: float) -> float:
    """Variant 2: 'Variant 1 with the compression removed' - the same
    relative value, a linear (uncompressed) multiplier in place of
    `_compressed_multiplier`. See module docstring."""
    return value / _D_MIDPOINT


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
    variant1_tax_base: float
    variant2_tax_base: float


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

        as_of = f"{fy.split('-')[0]}-04-01"
        try:
            resolved = resolve(code, name, as_of)
        except (AmbiguousBoundaryChange, UnmappedLocalAuthorityCode) as e:
            unresolved.append({"ons_code": code, "authority": name, "financial_year": fy, "reason": str(e)})
            continue

        band_d_rate = r["band_d_incl_parish"]
        tax_base_actual = sum(_safe_count(counts[b]) * BAND_MULTIPLIER[b] for b in BANDS)
        actual = band_d_rate * tax_base_actual * COLLECTION_FACTOR

        for target_code, _target_name, weight in resolved:
            if target_code not in LAD_2025_CODES:
                unresolved.append({"ons_code": code, "authority": name, "financial_year": fy, "reason": f"resolved to non-2025 code {target_code}"})
                continue
            hpi_factor = hpi_factor_lookup.get((target_code, fy))
            if hpi_factor is None:
                unresolved.append({"ons_code": code, "authority": name, "financial_year": fy, "reason": f"no HPI factor for target {target_code}"})
                continue

            v1_base = 0.0
            v2_base = 0.0
            for b in BANDS:
                count = _safe_count(counts[b])
                if not count:
                    continue
                relative_value = midpoints[b] * (hpi_factor / national_hpi_factor)
                v1_base += count * _compressed_multiplier(relative_value)
                v2_base += count * _proportional_multiplier(relative_value)

            rows.append(
                RowLiability(
                    ons_code=code,
                    financial_year=fy,
                    target_code=target_code,
                    weight=weight,
                    actual=actual * weight,
                    variant1_tax_base=v1_base * weight,
                    variant2_tax_base=v2_base * weight,
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
    la_year = row_df.groupby(["target_code", "financial_year"], as_index=False)[["actual", "variant1_tax_base", "variant2_tax_base"]].sum()
    la_year = la_year.rename(columns={"target_code": "ons_code"})

    national = la_year.groupby("financial_year", as_index=False)["actual"].sum().rename(columns={"actual": "national_actual_revenue"})
    la_year = la_year.merge(national, on="financial_year")

    for variant in ("variant1", "variant2"):
        totals = la_year.groupby("financial_year")[f"{variant}_tax_base"].transform("sum")
        la_year[f"{variant}_cf"] = la_year["national_actual_revenue"] * la_year[f"{variant}_tax_base"] / totals
        la_year[f"{variant}_gap"] = la_year["actual"] - la_year[f"{variant}_cf"]

    return EngineResult(la_year=la_year, national=national, unresolved=unresolved_df)


def compute_shared_tier_exposure(band_d_la_year: pd.DataFrame) -> pd.DataFrame:
    """Per (LA, financial year): what share of the area-total Band D bill is
    set by tiers OTHER than the billing authority's own (district) precept -
    county, police, fire, GLA. NOT a correction to the single-pot
    reallocation (see config.TIERED_REALLOCATION_IMPLEMENTED); this is the
    documented, quantified BOUND on how exposed a given LA's computed gap is
    to the single-pot bias found via the Westminster investigation. A high
    share means a large fraction of the bill flows through tiers that, in
    reality, do not reallocate against property value the way this engine's
    single national pot assumes - it does not by itself mean the gap IS
    biased (that additionally requires the LA's own rate, or its
    precepting group's rate, to diverge from peers), only that it COULD be.

    Structurally bimodal (checked, not assumed): unitary and London
    authorities typically show 6-40% (their 'own' precept already absorbs
    what would be county-level services elsewhere), ordinary two-tier shire
    districts typically show 83-92% (their own precept is a small slice
    next to the county's), because that is how English local government is
    actually structured, not an artefact of this calculation."""
    df = band_d_la_year[band_d_la_year["financial_year"].isin(HEADLINE_YEARS)].copy()
    df = df[df["band_d_incl_parish"].notna() & df["own_precept_incl_parish"].notna()]
    df["shared_tier_share"] = 1 - (df["own_precept_incl_parish"] / df["band_d_incl_parish"])
    return df[["ons_code", "authority", "financial_year", "shared_tier_share"]]


def compute_single_pot_bias_risk(band_d_la_year: pd.DataFrame) -> pd.DataFrame:
    """The Westminster mechanism needs an LA's own (district/unitary)
    precept to diverge from its peers - other LAs sharing the same
    non-own tiers (boundaries.precepting_groups.PRECEPTING_GROUP: shire
    county, metropolitan county, or Greater London). compute_shared_tier_
    exposure alone cannot show this: it only bounds how much of a bill
    COULD be mis-reallocated, not whether it actually is.

    First built and shipped as a RATIO (own precept / peer median own
    precept), per an interaction-statistic request phrased as "exposure x
    divergence". Run against real data, it ranked ordinary shire districts
    (Oxford, Ipswich, Pendle...) above Westminster - because shire own-
    precepts are small in cash terms (GBP150-300), so an ordinary,
    undistorting difference in service levels between neighbouring
    councils produces a large ratio, while Westminster's own precept is
    large (GBP400+), so its genuinely enormous cash gap from peers produces
    a comparatively smaller one. Wrong statistic for a mechanism that is
    denominated in pounds, not percent: the reallocation formula sums
    actual GBP revenue, so the distortion it produces is a GBP quantity,
    and a proportional measure answers "how unusual is this LA," not "how
    many pounds does that unusualness move" - the two come apart exactly
    when denominators differ by an order of magnitude, i.e. precisely the
    shire-district-vs-London-borough case. Replaced, not patched over -
    see the project log for the ratio version and why it was dropped
    rather than kept alongside.

    `abs_divergence_gbp` = an LA's own precept minus the MEDIAN own precept
    among LAs in the same precepting group that same year (signed: negative
    means below peers, as for Westminster).

    `single_pot_bias_risk` = |abs_divergence_gbp| / band_d_incl_parish (the
    LA's own full area-total bill) - the cash divergence expressed as a
    share of what that LA actually charges. Can exceed 1.0 (the divergence
    is worth more than the LA's whole discounted bill) - not a bug, and in
    fact the clearest way this statistic has of flagging an extreme case:
    both Westminster and Wandsworth do, at 1.06 and 1.03 respectively.
    Independently reproduces the same outlier set the original Westminster
    investigation found by hand (Westminster, Wandsworth, Hammersmith and
    Fulham, City of London, Kensington and Chelsea) - two different routes
    to the same answer.

    63 standalone unitary authorities (Cornwall, County Durham, Hartlepool,
    etc. - see precepting_groups.py) have no real peer group in this
    lookup and get `abs_divergence_gbp = NaN`, `single_pot_bias_risk = NaN`
    - UNMEASURED, not zero. This statistic cannot vindicate them; it can
    only fail to indict them. Their exposure share (compute_shared_tier_
    exposure) is what actually carries any claim that they are clean, and
    is unaffected by this gap."""
    exposure = compute_shared_tier_exposure(band_d_la_year)
    own = band_d_la_year[band_d_la_year["financial_year"].isin(HEADLINE_YEARS)][["ons_code", "financial_year", "own_precept_incl_parish", "band_d_incl_parish"]]
    df = exposure.merge(own, on=["ons_code", "financial_year"])
    df["precepting_group"] = df["ons_code"].map(PRECEPTING_GROUP)

    group_size = df.groupby(["precepting_group", "financial_year"])["ons_code"].transform("nunique")
    peer_median = df.groupby(["precepting_group", "financial_year"])["own_precept_incl_parish"].transform("median")
    df["abs_divergence_gbp"] = df["own_precept_incl_parish"] - peer_median
    df.loc[group_size <= 1, "abs_divergence_gbp"] = float("nan")
    df["single_pot_bias_risk"] = df["abs_divergence_gbp"].abs() / df["band_d_incl_parish"]

    return df[["ons_code", "authority", "financial_year", "shared_tier_share", "abs_divergence_gbp", "single_pot_bias_risk"]]
