"""
One-off calibration check on the Band A/H midpoint imputation ratios in
config.py (BAND_A_RATIO=0.75, BAND_H_RATIO=1.5). NOT part of the main
pipeline - see config.py's comment on those constants and
notebooks/02_method.ipynb.

Method: take HM Land Registry Price Paid sales for 1995-97 in a handful of
local authorities spanning high- and low-value England, deflate each sale
to an April-1991-equivalent value using a single NATIONAL quarterly
house-price factor (Nationwide's "UK house prices since 1952" series,
Q2 1991 = the quarter containing 1 April 1991), and see where the actual
empirical tail sits relative to the assumed Band A/H thresholds (£40k,
£320k in 1991 terms).

Deliberately a SINGLE NATIONAL deflator, not LA-level: bridging the
1991-1995 HPI gap at LA level was explicitly ruled out for the main
pipeline (see README Framing / DATA.md - the 1991-1995 gap is real and
left unbridged there). Doing it once, nationally, for a handful of LAs as
a bounded spot-check is a much smaller, self-contained assumption, and is
not used anywhere except this calibration.

1995-97 sales in this era include a meaningful share of non-market
transactions (family transfers, right-to-buy at deep discount, etc.) that
are not representative full-market values - the same "category B" problem
Tax Policy Associates flag in their own methodology (see reorg_events.py
module docstring's precedent-citing pattern). A floor + local-median-
fraction filter, following their approach, is applied before drawing any
conclusion from the tail.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass

import pandas as pd

# Nationwide "UK house prices since 1952", All Houses (UK), quarterly £.
# Q2 1991 is the quarter containing 1 April 1991 - our deflation baseline.
# Read directly from data/price_paid_calibration/UK_house_price_since_1952.xlsx
# each run (see build_deflators), not hardcoded, so a re-download can't
# silently drift from what's actually used.

PRICE_PAID_COLUMNS = [
    "transaction_id", "price", "date", "postcode", "property_type", "new_build",
    "duration", "paon", "saon", "street", "locality", "town_city", "district",
    "county", "ppd_category_type", "record_status",
]

# The four calibration areas: two high-value (expected thick Band H tail),
# two low-value (expected thick Band A base). Durham and Cheshire's own
# 2009-successor geography didn't exist in 1995-97, so a real predecessor
# district is used directly - Easington, a poorer part of what's now County
# Durham - rather than an ambiguous "COUNTY DURHAM" label that also
# appears in the raw file (unclear provenance, not used here).
CALIBRATION_DISTRICTS = {
    "KENSINGTON AND CHELSEA": "high",
    "CITY OF WESTMINSTER": "high",
    "EASINGTON": "low",
    "BLACKPOOL": "low",
}

BAND_A_THRESHOLD = 40_000
BAND_H_THRESHOLD = 320_000

# Non-market transaction filter, following Tax Policy Associates' approach
# (github.com/DanNeidle/lvt_model_2026, cited in reorg_events.py precedent
# fashion): drop sales below both an absolute floor AND a fraction of the
# area's own median deflated price - targets sub-market transfers without
# discarding genuinely cheap 1990s homes.
MIN_VALUE_FLOOR = 10_000  # 1991-equivalent terms; lower than TPA's 30k since 1991 prices are much lower than 2026
MIN_VALUE_FRAC_OF_LOCAL_MEDIAN = 0.30


def load_national_deflators(path) -> dict[str, float]:
    """Returns {quarter_label: deflator}, where deflator = Q2-1991-price / that-quarter's-price.
    Multiplying a sale price by its quarter's deflator gives an April-1991-equivalent value."""
    df = pd.read_excel(path, sheet_name="UK HP Since 1952", header=4)
    df.columns = [str(c).strip() for c in df.columns]
    label_col, price_col = df.columns[0], "Price"
    df = df[[label_col, price_col]].dropna()
    q2_1991 = df.loc[df[label_col] == "Q2 1991", price_col].values[0]
    return {row[label_col]: q2_1991 / row[price_col] for _, row in df.iterrows()}


def _quarter_label(date_str: str) -> str:
    year = int(date_str[:4])
    month = int(date_str[5:7])
    q = (month - 1) // 3 + 1
    return f"Q{q} {year}"


def load_calibration_sales(paths: list) -> pd.DataFrame:
    """Reads raw Price Paid CSVs (no header row in the source files),
    filtered to CALIBRATION_DISTRICTS only - these files are 700k-1M rows
    each and this is a spot check, not a full-file pipeline stage."""
    rows = []
    for path in paths:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                district = row[12].strip('"')
                if district in CALIBRATION_DISTRICTS:
                    rows.append(
                        {
                            "price": int(row[1].strip('"')),
                            "date": row[2].strip('"'),
                            "district": district,
                            "category": row[14].strip('"'),
                        }
                    )
    df = pd.DataFrame(rows)
    df["quarter"] = df["date"].apply(_quarter_label)
    return df


@dataclass
class CalibrationResult:
    sales: pd.DataFrame  # per-sale, with deflated_1991_value and area_type
    band_a_summary: pd.DataFrame  # district, empirical_ratio_vs_threshold, n_sales_below_threshold
    band_h_summary: pd.DataFrame  # district, empirical_ratio_vs_threshold, n_sales_above_threshold


def run_calibration(price_paid_paths: list, nationwide_path) -> CalibrationResult:
    deflators = load_national_deflators(nationwide_path)
    sales = load_calibration_sales(price_paid_paths)
    sales["deflator"] = sales["quarter"].map(deflators)
    sales = sales.dropna(subset=["deflator"])
    sales["deflated_1991_value"] = sales["price"] * sales["deflator"]

    # non-market transaction filter, applied per district using that
    # district's own median deflated value
    filtered = []
    for district, group in sales.groupby("district"):
        median = group["deflated_1991_value"].median()
        floor = max(MIN_VALUE_FLOOR, median * MIN_VALUE_FRAC_OF_LOCAL_MEDIAN)
        filtered.append(group[group["deflated_1991_value"] >= floor])
    sales = pd.concat(filtered)
    sales["area_type"] = sales["district"].map(CALIBRATION_DISTRICTS)

    band_a_rows = []
    band_h_rows = []
    for district, group in sales.groupby("district"):
        below_a = group[group["deflated_1991_value"] < BAND_A_THRESHOLD]
        above_h = group[group["deflated_1991_value"] >= BAND_H_THRESHOLD]
        band_a_rows.append(
            {
                "district": district,
                "n_sales_below_threshold": len(below_a),
                "mean_value_below_threshold": below_a["deflated_1991_value"].mean() if len(below_a) else None,
                "empirical_ratio_vs_threshold": (below_a["deflated_1991_value"].mean() / BAND_A_THRESHOLD) if len(below_a) else None,
            }
        )
        band_h_rows.append(
            {
                "district": district,
                "n_sales_above_threshold": len(above_h),
                "mean_value_above_threshold": above_h["deflated_1991_value"].mean() if len(above_h) else None,
                "empirical_ratio_vs_threshold": (above_h["deflated_1991_value"].mean() / BAND_H_THRESHOLD) if len(above_h) else None,
            }
        )

    return CalibrationResult(
        sales=sales,
        band_a_summary=pd.DataFrame(band_a_rows).sort_values("district"),
        band_h_summary=pd.DataFrame(band_h_rows).sort_values("district"),
    )
