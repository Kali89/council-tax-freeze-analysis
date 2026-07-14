"""
Processes the UK House Price Index full file into LA-level and region-level
revaluation factors, anchored to the January 1995 baseline (see
config.HPI_BASELINE and README Framing - the 1991-1995 gap is real and
deliberately unbridged, not this module's problem to solve).

Two things this module found worth recording:

1. **Date parsing is not optional to get right.** The source file's dates
   are DD/MM/YYYY. Pandas' default date inference reads day-values 1-12 as
   month-first (US convention) and silently corrupts roughly half of every
   year's rows without raising - e.g. "01/11/2019" (1 November) becomes
   2019-01-11 (11 January) instead of 2019-11-01. This does not error; it
   produces a plausible-looking wrong date. Every date column in this
   module is parsed with an explicit `format="%d/%m/%Y"`, never inferred.
2. **English LA-level coverage is complete except Isles of Scilly**
   (E06000053, entirely absent, consistent with the low-transaction-volume
   caveat already in DATA.md) - checked directly against all 296 current
   LA codes, not assumed. City of London (E09000001), often assumed thin,
   in fact has a complete, ungapped series - low sales volume, not missing
   data.

Validation: reproduces IFS (2020)'s own stated regional ratios (London
>6x, North East "barely three times" their January 1995 level, as at
November 2019 - see notebooks/02_method.ipynb "This is not a novel
mechanism") directly from this file, independently of anything already
computed elsewhere in this pipeline. Both checks pass.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from council_tax_freeze.boundaries.lad_2025 import LAD_2025_CODES
from council_tax_freeze.config import EXTENSION_FIRST_YEAR, LAST_YEAR

LA_CODE_RE = r"^E0[6-9]\d{6}$"
REGION_CODE_RE = r"^E12\d{6}$"

# LA -> region, for the fallback used when an LA's own series is absent or
# too thin (currently: Isles of Scilly only - see module docstring). Scilly
# sits within the South West region.
REGIONAL_FALLBACK: dict[str, str] = {
    "E06000053": "E12000009",  # Isles of Scilly -> South West
}

# Independent validation anchors: IFS (2020) Figure 2.4, "Average property
# price in November 2019 as a multiple of January 1995, by region" - stated
# in the report's own text, not read from this file. London ">six times";
# North East "barely three times".
IFS_REGIONAL_RATIO_ANCHORS = {
    "E12000007": {"name": "London", "min_ratio": 6.0},
    "E12000001": {"name": "North East", "min_ratio": 2.9, "max_ratio": 3.3},
}
IFS_ANCHOR_DATE = "2019-11-01"


class HPIValidationError(Exception):
    """Raised when the IFS regional-ratio anchors don't reproduce - the
    published national average is external ground truth, same standard
    used for Band D and CTSOP."""


def _load_hpi(path) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        usecols=["Date", "RegionName", "AreaCode", "AveragePrice"],
        dtype={"AreaCode": str},
    )
    df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y")  # NOT inferred - see module docstring
    return df


@dataclass
class HPIResult:
    la_factors: pd.DataFrame  # ons_code, financial_year, hpi_factor_la (regional fallback applied where needed)
    region_factors: pd.DataFrame  # region_code, financial_year, hpi_factor_region
    coverage: pd.DataFrame  # financial_year, n_la, n_fallback
    validation: pd.DataFrame  # region_code, name, ratio, anchor_min, anchor_max, within_tolerance


def _financial_year_hpi_date(financial_year: str) -> str:
    """Sample HPI at 1 April of the financial year's start - i.e. as close
    as possible to the same instant Band D/CTSOP snapshot, without
    inventing a different convention for a third dataset."""
    year = financial_year.split("-")[0]
    return f"{year}-04-01"


def _financial_years(first: str, last: str) -> list[str]:
    y0, y1 = int(first[:4]), int(last[:4])
    return [f"{y}-{str(y + 1)[2:]}" for y in range(y0, y1 + 1)]


def build_hpi(path) -> HPIResult:
    df = _load_hpi(path)
    baseline_date = pd.Timestamp("1995-01-01")

    la = df[df["AreaCode"].str.match(LA_CODE_RE)].copy()
    region = df[df["AreaCode"].str.match(REGION_CODE_RE)].copy()

    la_baseline = la[la["Date"] == baseline_date].set_index("AreaCode")["AveragePrice"]
    region_baseline = region[region["Date"] == baseline_date].set_index("AreaCode")["AveragePrice"]

    fys = _financial_years(EXTENSION_FIRST_YEAR, LAST_YEAR)
    la_rows = []
    region_rows = []
    coverage_rows = []

    for fy in fys:
        sample_date = pd.Timestamp(_financial_year_hpi_date(fy))

        region_snap = region[region["Date"] == sample_date].set_index("AreaCode")["AveragePrice"]
        region_factor = (region_snap / region_baseline).dropna()
        for code, factor in region_factor.items():
            region_rows.append({"region_code": code, "financial_year": fy, "hpi_factor_region": factor})

        la_snap = la[la["Date"] == sample_date].set_index("AreaCode")["AveragePrice"]
        la_factor = (la_snap / la_baseline).dropna()

        n_fallback = 0
        factors_for_year = dict(la_factor)
        for la_code in LAD_2025_CODES:
            if la_code not in factors_for_year:
                fallback_region = REGIONAL_FALLBACK.get(la_code)
                if fallback_region is None:
                    continue  # genuinely unmapped - surfaced by the coverage check below
                region_factor_value = region_factor.get(fallback_region)
                if region_factor_value is not None:
                    factors_for_year[la_code] = region_factor_value
                    n_fallback += 1

        for code, factor in factors_for_year.items():
            la_rows.append({"ons_code": code, "financial_year": fy, "hpi_factor_la": factor})

        coverage_rows.append(
            {
                "financial_year": fy,
                "n_la": len(factors_for_year),
                "n_fallback": n_fallback,
                "n_missing": len(LAD_2025_CODES) - len(factors_for_year),
            }
        )

    la_factors = pd.DataFrame(la_rows).sort_values(["financial_year", "ons_code"])
    region_factors = pd.DataFrame(region_rows).sort_values(["financial_year", "region_code"])
    coverage = pd.DataFrame(coverage_rows)

    validation = _validate_against_ifs(df)
    failures = validation[validation["within_tolerance"] == False]  # noqa: E712
    if len(failures):
        raise HPIValidationError(f"IFS regional-ratio anchor(s) failed to reproduce:\n{failures.to_string(index=False)}")

    return HPIResult(la_factors=la_factors, region_factors=region_factors, coverage=coverage, validation=validation)


def _validate_against_ifs(df: pd.DataFrame) -> pd.DataFrame:
    baseline_date = pd.Timestamp("1995-01-01")
    anchor_date = pd.Timestamp(IFS_ANCHOR_DATE)
    rows = []
    for code, spec in IFS_REGIONAL_RATIO_ANCHORS.items():
        base = df[(df["AreaCode"] == code) & (df["Date"] == baseline_date)]["AveragePrice"].values[0]
        at_anchor = df[(df["AreaCode"] == code) & (df["Date"] == anchor_date)]["AveragePrice"].values[0]
        ratio = at_anchor / base
        min_r = spec.get("min_ratio", float("-inf"))
        max_r = spec.get("max_ratio", float("inf"))
        rows.append(
            {
                "region_code": code,
                "name": spec["name"],
                "ratio": round(ratio, 2),
                "anchor_min": min_r,
                "anchor_max": max_r,
                "within_tolerance": min_r <= ratio <= max_r,
            }
        )
    return pd.DataFrame(rows)
