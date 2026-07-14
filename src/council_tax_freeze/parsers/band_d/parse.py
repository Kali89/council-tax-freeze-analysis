"""
Parses MHCLG's live table "Band D council tax figures 1993-94 to 2026-27"
(one continuously-maintained file - see DATA.md "Band D: one live table, not
26 parsers" for why this supersedes the per-vintage-parser design originally
anticipated) into a tidy per-authority-per-year series, on two bases:

  - band_d_incl_parish: Table 5 ("Area_CT"), the district's own precept
    (which itself includes an averaged parish contribution where
    applicable) plus county/police/fire. This is THE standard published
    headline "average Band D council tax" figure - verified against it
    below - and is the PRIMARY series the counterfactual engine uses.
  - band_d_excl_parish: constructed as band_d_incl_parish minus the
    district's own parish component (Table 1 "inc_PP" minus Table 3
    "exc_PP", both district-precept-only, so their difference IS the
    parish component). Carried as a documented robustness variant, not
    the headline - see README Framing and 03_results.ipynb for the
    incl./excl. delta this exists to answer.

Both bases are computed at each row's OWN historic vintage geography (the
ONS Code as MHCLG itself recorded it for that LA in that year) - this
module does NOT harmonise to 2025 geography. That's deliberately deferred:
Band D is a RATE (£ per Band D dwelling), and combining several predecessor
districts' rates into one successor's rate requires dwelling-count
weighting, which needs CTSOP data this module doesn't have. Averaging (or
worse, summing) rates the way crosswalk.harmonise() sums counts would be
wrong. What this module DOES check now is that every historic LA identity
it encounters actually RESOLVES via the Phase 1 crosswalk - existence and
uniqueness, not value combination.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from council_tax_freeze.boundaries.crosswalk import (
    AmbiguousBoundaryChange,
    UnmappedLocalAuthorityCode,
    resolve,
)
from council_tax_freeze.boundaries.lad_2025 import LAD_2025_CODES
from council_tax_freeze.boundaries.reorg_events import EVENTS

# Predecessor codes that have ZERO Band D data anywhere in the live table -
# found by cross-referencing every Phase 1 predecessor code against this
# dataset (see DATA.md "Band D live table: known gaps"), not assumed. Two
# kinds:
#   - "recoded, not a gap": Barnsley (E08000016) and Sheffield (E08000019)
#     have no historic rows because MHCLG's live table applies their
#     CURRENT code (E08000038/E08000039) retroactively across the table's
#     whole 1993-2027 span - both are RECODE events in reorg_events.py (no
#     real boundary change until the tiny 2025 one), so this is a
#     reasonable choice on MHCLG's part, not missing data.
#   - "genuine gap": Durham City (E07000056), Crewe and Nantwich
#     (E07000015), and Shrewsbury and Atcham (E07000185) are absent despite
#     every OTHER predecessor in their respective 2009 merger groups being
#     fully present with real data. No explanation found; flagged as a real
#     limitation, not smoothed over. These are the three "principal town"
#     districts in their counties (county town / largest town), which may
#     be relevant if MHCLG re-publishes a correction, but that's a
#     speculation, not a finding - recorded as unexplained.
KNOWN_BAND_D_GAPS: dict[str, str] = {
    "E08000016": "recoded, not a gap - MHCLG applies Barnsley's current code (E08000038) retroactively",
    "E08000019": "recoded, not a gap - MHCLG applies Sheffield's current code (E08000039) retroactively",
    "E07000056": "genuine gap - Durham City has zero Band D data in the live table for any year, unexplained",
    "E07000015": "genuine gap - Crewe and Nantwich has zero Band D data in the live table for any year, unexplained",
    "E07000185": "genuine gap - Shrewsbury and Atcham has zero Band D data in the live table for any year, unexplained",
}

class BandDValidationError(Exception):
    """Raised when a year's parsed national average Band D deviates from an
    independently-published figure by more than ANCHOR_TOLERANCE. The
    published national average is external ground truth, same role the
    district-count cross-check played in Phase 1 - a mismatch means
    something is broken upstream (wrong sheet, wrong row, wrong year
    alignment) and must be surfaced, not quietly reconciled away."""


GSS_LA_CODE_RE = re.compile(r"^E0[6-9]\d{6}$")
YEAR_LABEL_RE = re.compile(r"^(\d{4}) to (\d{4})$")

# Independently-sourced anchor figures for the national validation check -
# NOT read from the live table itself, so this is a genuine external check,
# not internal consistency. Three separate sources, none of them the live
# table:
#   - 2000-01 to 2012-13: a separate, frozen MHCLG PDF ("Average band D
#     Council Tax bills in England 1993 to 2013",
#     assets.publishing.service.gov.uk/media/5a78b80bed915d07d35b1e36/),
#     matches the live table's England row to the pound for all 20 years
#     it covers (1993-94 to 2012-13; only 2000-01 onward is in scope here).
#   - 2017-18, 2018-19: that year's own standalone statistical release
#     ("Council tax levels set by local authorities: England 2018-19 -
#     revised", assets.publishing.service.gov.uk/media/5ad72126.../), which
#     states both its own year and the prior year's figure for comparison.
#   - 2022-23, 2024-25, 2025-26: contemporaneous headline figures as
#     independently reported (see DATA.md).
# 2013-14 to 2016-17, 2019-20 to 2021-22, and 2023-24 remain UNCHECKED
# against an independent source - flagged honestly rather than implied
# covered. The mechanism producing them (the same MHCLG live table) is
# identical to the mechanism proven correct on both sides of every one of
# those gaps, which bounds the risk, but "bounded risk" is not "checked".
INDEPENDENT_NATIONAL_ANCHORS: dict[str, float] = {
    "2000-01": 847,
    "2001-02": 901,
    "2002-03": 976,
    "2003-04": 1102,
    "2004-05": 1167,
    "2005-06": 1214,
    "2006-07": 1268,
    "2007-08": 1321,
    "2008-09": 1373,
    "2009-10": 1414,
    "2010-11": 1439,
    "2011-12": 1439,
    "2012-13": 1444,
    "2017-18": 1591,
    "2018-19": 1671,
    "2022-23": 1966,
    "2024-25": 2170.99,
    "2025-26": 2280.21,
}
# Anchors are rounded to the nearest pound for 2000-01..2012-13 (that's how
# the source PDF reports them); allow half a pound either way plus a little
# slack for the rounding itself.
ANCHOR_TOLERANCE = 0.55


def financial_year_label(year_range_label: str) -> str:
    """'2000 to 2001' -> '2000-01'."""
    m = YEAR_LABEL_RE.match(year_range_label)
    if not m:
        raise ValueError(f"Unrecognised year column label: {year_range_label!r}")
    y0, y1 = m.group(1), m.group(2)
    return f"{y0}-{y1[2:]}"


def financial_year_start_date(financial_year: str) -> str:
    """'2000-01' -> '2000-04-01' (financial years run 1 April - 31 March)."""
    year = financial_year.split("-")[0]
    return f"{year}-04-01"


def _load_sheet(path, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet, engine="odf", header=2)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _year_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if YEAR_LABEL_RE.match(str(c))]


def _is_real_la_row(df: pd.DataFrame) -> pd.Series:
    """Real billing authorities have a proper GSS code; national/regional
    aggregate rows (England, London boroughs excl. GLA, shire counties as a
    class, etc.) have ONS Code == '[z]' and are excluded here - handled
    separately as the validation target, not treated as an LA."""
    return df["ONS Code"].astype(str).str.match(GSS_LA_CODE_RE)


def _tidy(df: pd.DataFrame, value_name: str) -> pd.DataFrame:
    year_cols = _year_columns(df)
    long = df.melt(
        id_vars=["ONS Code", "Authority"],
        value_vars=year_cols,
        var_name="year_label",
        value_name=value_name,
    )
    long["financial_year"] = long["year_label"].map(financial_year_label)
    # "[z]" (not applicable - didn't exist that year) and "[x]" (suppressed)
    # both coerce to NaN here, which is correct: both mean "no value", and
    # which one applies is a data-quality distinction the Notes sheet
    # documents, not one this pipeline needs to act on differently.
    long[value_name] = pd.to_numeric(long[value_name], errors="coerce")
    return long.drop(columns="year_label")


@dataclass
class BandDResult:
    la_year: pd.DataFrame  # ons_code, authority, financial_year, band_d_incl_parish, band_d_excl_parish
    national: pd.DataFrame  # financial_year, published_national_band_d (from the live table's England row)
    validation: pd.DataFrame  # financial_year, live_table_value, independent_anchor, within_tolerance
    coverage: pd.DataFrame  # financial_year, n_la_rows, n_unmapped, n_ambiguous
    predecessor_gaps: pd.DataFrame  # ons_code, name, explanation, is_documented


def _predecessor_coverage(la_year: pd.DataFrame) -> pd.DataFrame:
    """Cross-references every Phase 1 predecessor code (reorg_events.py)
    against whether the Band D live table has ANY reported value for it, in
    ANY year. A predecessor with zero data anywhere is a gap in MHCLG's own
    dataset, not something this parser can resolve - reported explicitly,
    classified against KNOWN_BAND_D_GAPS so a NEW, previously undocumented
    gap is distinguishable from the ones already understood."""
    codes_with_any_data = set(la_year.loc[la_year["band_d_incl_parish"].notna(), "ons_code"])
    predecessor_units = {(o.code, o.name) for e in EVENTS for o in e.olds if o.code}

    rows = []
    for code, name in sorted(predecessor_units):
        if code in codes_with_any_data:
            continue
        rows.append(
            {
                "ons_code": code,
                "name": name,
                "explanation": KNOWN_BAND_D_GAPS.get(code, "UNDOCUMENTED - new gap, not previously seen"),
                "is_documented": code in KNOWN_BAND_D_GAPS,
            }
        )
    return pd.DataFrame(rows, columns=["ons_code", "name", "explanation", "is_documented"])


def build_band_d(path) -> BandDResult:
    area_ct = _load_sheet(path, "Area_CT")
    inc_pp = _load_sheet(path, "inc_PP")
    exc_pp = _load_sheet(path, "exc_PP")

    national_row = area_ct[area_ct["Code"] == "Eng"]
    national = _tidy(national_row, "published_national_band_d")[["financial_year", "published_national_band_d"]]

    area_la = _tidy(area_ct[_is_real_la_row(area_ct)], "band_d_incl_parish")
    inc_la = _tidy(inc_pp[_is_real_la_row(inc_pp)], "own_precept_incl_parish")
    exc_la = _tidy(exc_pp[_is_real_la_row(exc_pp)], "own_precept_excl_parish")

    merged = area_la.merge(
        inc_la.drop(columns="Authority"), on=["ONS Code", "financial_year"], how="left"
    ).merge(exc_la.drop(columns="Authority"), on=["ONS Code", "financial_year"], how="left")

    merged["parish_component"] = merged["own_precept_incl_parish"] - merged["own_precept_excl_parish"]
    merged["band_d_excl_parish"] = merged["band_d_incl_parish"] - merged["parish_component"]

    la_year = merged.rename(columns={"ONS Code": "ons_code", "Authority": "authority"})[
        ["ons_code", "authority", "financial_year", "band_d_incl_parish", "band_d_excl_parish"]
    ].sort_values(["financial_year", "ons_code"])

    validation = _validate_national(national)
    failures = validation[validation["within_tolerance"] == False]  # noqa: E712 - explicit False, not just falsy/NaN
    if len(failures):
        raise BandDValidationError(
            f"{len(failures)} year(s) failed national Band D validation against an "
            f"independent published figure (tolerance +/-£{ANCHOR_TOLERANCE}):\n"
            f"{failures.to_string(index=False)}"
        )

    coverage = _coverage_report(la_year)
    predecessor_gaps = _predecessor_coverage(la_year)

    return BandDResult(
        la_year=la_year, national=national, validation=validation, coverage=coverage, predecessor_gaps=predecessor_gaps
    )


def _validate_national(national: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in national.iterrows():
        fy = r["financial_year"]
        live_value = r["published_national_band_d"]
        anchor = INDEPENDENT_NATIONAL_ANCHORS.get(fy)
        within_tol = None if anchor is None else abs(live_value - anchor) <= ANCHOR_TOLERANCE
        rows.append(
            {
                "financial_year": fy,
                "live_table_value": live_value,
                "independent_anchor": anchor,
                "within_tolerance": within_tol,
            }
        )
    return pd.DataFrame(rows).sort_values("financial_year").reset_index(drop=True)


def _coverage_report(la_year: pd.DataFrame) -> pd.DataFrame:
    """Per financial year: how many distinct LA identities actually
    reported a value, and how many fail to resolve via the Phase 1
    crosswalk (unmapped/ambiguous). This checks EXISTENCE/RESOLUTION only -
    see module docstring for why value harmonisation is deferred to when
    CTSOP dwelling weights exist.

    The live table carries a row for every LA that EVER existed across its
    whole 1993-2027 span, with NaN ("[z]" - not applicable) for years
    outside that LA's lifetime - e.g. Alnwick's row still exists in
    2009-10, just empty, since it was absorbed into Northumberland on
    2009-04-01. Coverage must count only rows with an actual reported
    value; counting every row regardless would incorrectly flag every
    discontinued predecessor as "unmapped" in every year after its own
    abolition, when in truth it simply isn't present that year at all."""
    reported = la_year[la_year["band_d_incl_parish"].notna()]
    rows = []
    for fy, group in reported.groupby("financial_year"):
        as_of = financial_year_start_date(fy)
        units = group[["ons_code", "authority"]].drop_duplicates()
        n_unmapped = 0
        n_ambiguous = 0
        for _, u in units.iterrows():
            try:
                results = resolve(u["ons_code"], u["authority"], as_of)
            except AmbiguousBoundaryChange:
                n_ambiguous += 1
                continue
            except UnmappedLocalAuthorityCode:
                n_unmapped += 1
                continue
            if any(target_code not in LAD_2025_CODES for target_code, _, _ in results):
                n_unmapped += 1
        rows.append(
            {
                "financial_year": fy,
                "n_la_rows": len(units),
                "n_unmapped": n_unmapped,
                "n_ambiguous": n_ambiguous,
            }
        )
    return pd.DataFrame(rows).sort_values("financial_year").reset_index(drop=True)
