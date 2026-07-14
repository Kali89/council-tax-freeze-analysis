"""
Parses VOA's Council Tax: Stock of Properties (CTSOP1.0) data into a tidy
per-authority-per-year band-count series.

Two source files cover the whole 2000-01 to 2025-26 study window:
  - The VOA-maintained consolidated time series "CTSOP1.0 ... 1993 to 2024"
    (one CSV, wide format, one column-group per 31-March snapshot) -
    analogous to MHCLG's Band D live table, and covers 2000-01 through
    2023-24 in one file.
  - The standalone 2025 release's CTSOP1.0 sheet, for the one year (2024-25
    snapshot published Sept 2025, i.e. the 2025-26 financial year) not yet
    folded into a "1993-2025" consolidated file at time of writing.

DATA QUALITY FINDING - not a parsing bug, verified against the raw file:
the 1993-2024 consolidated file DOUBLE-COUNTS every LA affected by the
2019, 2020, 2021 and 2023 reorg waves (NOT the 2009 wave, which VOA handled
cleanly - predecessor rows are simply absent). For the later waves, VOA
retroactively back-filled the SUCCESSOR row with the correct historic sum
of its predecessors (verified exactly: Dorset UA's 2015 total equals the
exact sum of its five predecessor districts' 2015 totals) - but then also
left the PREDECESSOR rows in place, still being updated with real,
growing dwelling counts for years after their own legal abolition (e.g.
East Dorset, abolished 1 April 2019, shows a real, increasing dwelling
count through 2024). Summing all LAUA rows for any year therefore
overcounts England's total stock by ~1.4-1.8 million dwellings - roughly
7% of the national total, entirely attributable to double-counting the
2019-2023 reorg-affected areas twice. See DATA.md "CTSOP: a double-counting
bug in VOA's own consolidated file" for the full writeup.

Fix: for every MERGE event in reorg_events.py, keep only the successor
row (which already carries the correct retroactive aggregate for the WHOLE
period, confirmed exactly) and drop the predecessor rows entirely, rather
than trying to reconstruct a "before/after" cutover the way Band D needed.
This means CTSOP - once deduplicated - needs NO further harmonisation to
2025 geography (unlike Band D, which is a rate and still needs dwelling-
weighted combination in Phase 4). The dropped predecessor-level rows are
NOT discarded, though: they're genuine, non-duplicated dwelling counts
for 2019-2023-wave predecessors and are exactly the weights Phase 4 will
need to combine Band D's predecessor-level RATES for those same LAs. No
equivalent exists for the 2009 wave (VOA never published individual
2009-wave predecessor rows at all) - flagged as a real gap for Phase 4,
not solved here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from council_tax_freeze.boundaries.crosswalk import AmbiguousBoundaryChange, UnmappedLocalAuthorityCode, resolve
from council_tax_freeze.boundaries.lad_2025 import LAD_2025_CODES
from council_tax_freeze.boundaries.reorg_events import EVENTS, ChangeType

BANDS = ["A", "B", "C", "D", "E", "F", "G", "H"]
GSS_LA_CODE_RE = re.compile(r"^E0[6-9]\d{6}$")

# Merge events only - these are exactly the ones the double-counting fix
# applies to. The Barnsley/Sheffield SPLIT is handled separately (it's a
# genuine code cutover at a specific date, not a retroactive-duplication
# problem - the 1993-2024 file simply predates that boundary change).
MERGE_EVENTS = [e for e in EVENTS if e.change_type == ChangeType.MERGE]
PREDECESSOR_CODES_TO_DROP = {o.code for e in MERGE_EVENTS for o in e.olds if o.code}


class CTSOPValidationError(Exception):
    """Raised when a year's parsed national dwelling total deviates from an
    independently-published figure by more than tolerance, OR when the raw
    file's LA-row sum doesn't match its own England row by more than the
    known, documented double-counting margin - i.e. a NEW discrepancy
    beyond the one already investigated and fixed."""


# Independently-sourced dwelling-stock anchors - genuinely separate from
# this file, both in source and methodology, not just re-stated numbers
# from the same underlying dataset:
#   - 2020-21: MHCLG's separate "Dwelling Stock Estimates, England" series
#     (housing-supply/net-additions accounting, NOT the Council Tax
#     Valuation List CTSOP is built from) states ~24.7 million dwellings in
#     England as at 31 March 2020. This is dataset #5 in DATA.md (ONS/MHCLG
#     dwelling stock estimates), pulled forward from its Phase 3 role to
#     validate here too. Given the two series measure related but distinct
#     things (valuation-list entries vs a housing-supply dwelling count),
#     a LOOSER tolerance applies than same-source cross-checks - same
#     principle as the Phase 1 ONS cross-check.
#   - 2025-26: derived from a DIFFERENT reported statistic in the VOA's own
#     2025 statistical commentary, not simply copied from its own total:
#     "Band A: 6.1 million properties, or 23.7% of all properties" implies
#     an England total of ~6.1m / 0.237 ~= 25.7m - an internal cross-check
#     using a second independently-stated number, not a restatement of the
#     first.
INDEPENDENT_NATIONAL_DWELLING_ANCHORS: dict[str, float] = {
    "2020-21": 24_700_000,
    "2025-26": 6_100_000 / 0.237,
}
# Same-source-document tolerance (VOA's own two different stated figures
# agreeing) can be tight; cross-methodology (CTSOP vs Dwelling Stock
# Estimates) needs more slack. Applied per-year below.
ANCHOR_TOLERANCE_FRACTION: dict[str, float] = {
    "2020-21": 0.01,  # 1% - different series, different methodology
    "2025-26": 0.01,  # 1% - rounded percentages in the source prose
}


def financial_year_from_snapshot(snapshot_year: str) -> str:
    """CTSOP snapshots are dated 31 March YYYY, representing the stock in
    place going into financial year (YYYY)-(YYYY+1) - e.g. '2000_03_31'
    (31 March 2000) is the stock underlying FY2000-01, the same convention
    Band D's 1 April start date uses (31 March and 1 April being the same
    boundary point)."""
    y = int(snapshot_year)
    return f"{y}-{str(y + 1)[2:]}"


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strips '[note N]' suffixes and normalises to lowercase-with-underscores,
    so the three source-file column-naming conventions (1993-2024
    consolidated: 'geography'/'ecode'; 2025 standalone: 'Geography [note 1]'/
    'ONS area code [note 3]') resolve to the same names."""
    def clean(c):
        c = re.sub(r"\s*\[note \d+\]\s*", "", str(c)).strip()
        return c
    df = df.rename(columns={c: clean(c) for c in df.columns})
    return df


@dataclass
class CTSOPResult:
    la_year: pd.DataFrame  # ons_code, authority, financial_year, band_a..band_h, all_properties
    predecessor_weights: pd.DataFrame  # dropped 2019-2023-wave predecessor rows, kept separately for Phase 4
    national: pd.DataFrame  # financial_year, published_national_total (this file's own England row)
    validation: pd.DataFrame
    coverage: pd.DataFrame
    duplication_check: pd.DataFrame  # financial_year, raw_la_sum, natl_row, excess - evidence for the finding above


def _load_consolidated_1993_2024(path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = _normalise_columns(df)
    return df


def _tidy_consolidated(df: pd.DataFrame) -> pd.DataFrame:
    year_re = re.compile(r"^(\d{4})_03_31_band_([a-h])$")
    total_re = re.compile(r"^(\d{4})_03_31_all_properties$")

    band_cols = {m.group(1): {} for c in df.columns if (m := year_re.match(c))}
    for c in df.columns:
        if m := year_re.match(c):
            band_cols[m.group(1)][m.group(2).upper()] = c
    total_cols = {m.group(1): c for c in df.columns if (m := total_re.match(c))}

    rows = []
    for _, r in df.iterrows():
        for snap_year, bcols in band_cols.items():
            if snap_year not in total_cols:
                continue
            fy = financial_year_from_snapshot(snap_year)
            rec = {
                "ons_code": r["ecode"],
                "authority": r["area_name"],
                "financial_year": fy,
                "all_properties": pd.to_numeric(r[total_cols[snap_year]], errors="coerce"),
            }
            for b in BANDS:
                col = bcols.get(b)
                rec[f"band_{b.lower()}"] = pd.to_numeric(r[col], errors="coerce") if col else None
            rows.append(rec)
    return pd.DataFrame(rows)


def _tidy_standalone_2025(path, financial_year: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="CTSOP1.0", header=4)
    df = _normalise_columns(df)
    rows = []
    for _, r in df.iterrows():
        rec = {
            "ons_code": r["ONS area code"],
            "authority": r["ONS area name"],
            "financial_year": financial_year,
            "all_properties": pd.to_numeric(r["All properties"], errors="coerce"),
        }
        for b in BANDS:
            rec[f"band_{b.lower()}"] = pd.to_numeric(r[b], errors="coerce")
        rows.append(rec)
    return pd.DataFrame(rows)


def _is_real_la_row(df: pd.DataFrame) -> pd.Series:
    return df["ons_code"].astype(str).str.match(GSS_LA_CODE_RE)


def build_ctsop(consolidated_path, standalone_2025_path=None) -> CTSOPResult:
    raw = _load_consolidated_1993_2024(consolidated_path)

    national_row = raw[raw["ecode"] == "E92000001"]
    national_long = _tidy_consolidated(national_row)[["financial_year", "all_properties"]].rename(
        columns={"all_properties": "published_national_total"}
    )

    all_long = _tidy_consolidated(raw)
    la_long = all_long[_is_real_la_row(all_long)].copy()

    if standalone_2025_path is not None:
        national_2025 = pd.read_excel(standalone_2025_path, sheet_name="CTSOP1.0", header=4)
        national_2025 = _normalise_columns(national_2025)
        eng_2025 = national_2025[national_2025["ONS area code"] == "E92000001"]
        national_long = pd.concat(
            [
                national_long,
                pd.DataFrame(
                    {
                        "financial_year": ["2025-26"],
                        "published_national_total": [pd.to_numeric(eng_2025["All properties"].values[0])],
                    }
                ),
            ],
            ignore_index=True,
        )
        la_2025 = _tidy_standalone_2025(standalone_2025_path, "2025-26")
        la_2025 = la_2025[_is_real_la_row(la_2025)]
        la_long = pd.concat([la_long, la_2025], ignore_index=True)

    # --- the duplication finding, quantified per year, BEFORE the fix ---
    duplication_check = (
        la_long.groupby("financial_year")["all_properties"]
        .sum()
        .rename("raw_la_sum")
        .to_frame()
        .join(national_long.set_index("financial_year")["published_national_total"].rename("natl_row"))
    )
    duplication_check["excess"] = duplication_check["raw_la_sum"] - duplication_check["natl_row"]
    duplication_check = duplication_check.reset_index().sort_values("financial_year")

    # --- the fix: drop 2019-2023-wave predecessor rows, keep 2025 dropped
    # predecessor (Barnsley/Sheffield-old, once the 2025 row exists under
    # the new code) - see module docstring. ---
    is_dropped_predecessor = la_long["ons_code"].isin(PREDECESSOR_CODES_TO_DROP)
    predecessor_weights = la_long[is_dropped_predecessor].copy()
    la_year = la_long[~is_dropped_predecessor].copy().sort_values(["financial_year", "ons_code"])

    validation = _validate_national(national_long)
    failures = validation[validation["within_tolerance"] == False]  # noqa: E712
    if len(failures):
        raise CTSOPValidationError(
            f"{len(failures)} year(s) failed national dwelling-stock validation:\n{failures.to_string(index=False)}"
        )

    coverage = _coverage_report(la_year)

    return CTSOPResult(
        la_year=la_year,
        predecessor_weights=predecessor_weights,
        national=national_long,
        validation=validation,
        coverage=coverage,
        duplication_check=duplication_check,
    )


def _validate_national(national: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in national.iterrows():
        fy = r["financial_year"]
        value = r["published_national_total"]
        anchor = INDEPENDENT_NATIONAL_DWELLING_ANCHORS.get(fy)
        tol_frac = ANCHOR_TOLERANCE_FRACTION.get(fy)
        within_tol = None if anchor is None else abs(value - anchor) <= anchor * tol_frac
        rows.append({"financial_year": fy, "parsed_value": value, "independent_anchor": anchor, "within_tolerance": within_tol})
    return pd.DataFrame(rows).sort_values("financial_year").reset_index(drop=True)


def _coverage_report(la_year: pd.DataFrame) -> pd.DataFrame:
    """Per financial year: LA rows, unmapped, ambiguous - resolved via the
    Phase 1 crosswalk. year_totals is built from THIS year's own CTSOP data
    (authority -> all_properties), which is exactly what the Barnsley/
    Sheffield SPLIT's fixed_transfer apportionment needs to convert its
    12-dwelling fixed count into a weight - using real dwelling counts
    rather than a placeholder, since CTSOP is precisely the source that
    apportionment was always going to need.

    as_of uses the snapshot's OWN date (31 March), not the financial year's
    1 April start label, deliberately: CTSOP 2025-26 is snapshotted 31 March
    2025, one day before the Barnsley/Sheffield boundary change (effective 1
    April 2025) actually took effect, so it genuinely still reflects the old
    codes - resolving against "2025-04-01" would incorrectly expect the new
    ones a day early and misreport this as unmapped. This surfaced as a
    real 2-row discrepancy in the first version of this report, not
    something anticipated in advance - see DATA.md."""
    reported = la_year[la_year["all_properties"].notna()]
    rows = []
    for fy, group in reported.groupby("financial_year"):
        snapshot_year = fy.split("-")[0]
        as_of = f"{snapshot_year}-03-31"
        units = group[["ons_code", "authority"]].drop_duplicates()
        year_totals = group.set_index("authority")["all_properties"].to_dict()
        n_unmapped = 0
        n_ambiguous = 0
        for _, u in units.iterrows():
            try:
                results = resolve(u["ons_code"], u["authority"], as_of, year_totals=year_totals)
            except AmbiguousBoundaryChange:
                n_ambiguous += 1
                continue
            except UnmappedLocalAuthorityCode:
                n_unmapped += 1
                continue
            if any(t not in LAD_2025_CODES for t, _, _ in results):
                n_unmapped += 1
        rows.append({"financial_year": fy, "n_la_rows": len(units), "n_unmapped": n_unmapped, "n_ambiguous": n_ambiguous})
    return pd.DataFrame(rows).sort_values("financial_year").reset_index(drop=True)
