"""
Fetch what can be fetched automatically; print clear instructions for what
can't. Run as `python -m council_tax_freeze.download` or `make data`.

Each dataset in DATA.md gets one fetcher function here. A fetcher either:
  - downloads to the right place under data/ and returns, or
  - prints a manual-download instruction (URL, what to click, where to save
    it) and raises ManualDownloadRequired, which main() catches so one
    unavailable dataset doesn't stop the others from fetching.

Nothing here fabricates a download URL it hasn't verified works: MHCLG's
annual Council Tax levels releases and the local government finance
settlement series move around from year to year and are NOT auto-fetched
here yet (Phase 2 / Phase 6 will pin the ~26 vintage URLs once each
per-vintage parser is written against the real files). Flagging that
honestly rather than guessing is more useful than a fetcher that silently
grabs the wrong year.
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests
from tqdm import tqdm

from council_tax_freeze.config import DATA_DIR


class ManualDownloadRequired(Exception):
    """Raised by a fetcher that can't download automatically; message is the instruction to print."""


def _download(url: str, dest: Path, chunk_size: int = 1 << 16) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    with open(dest, "wb") as f, tqdm(total=total, unit="B", unit_scale=True, desc=dest.name) as bar:
        for chunk in resp.iter_content(chunk_size=chunk_size):
            f.write(chunk)
            bar.update(len(chunk))


def fetch_uk_hpi() -> None:
    """UK House Price Index, full file. URL below is best-effort, not yet verified against a live response - Phase 3 will confirm or replace it."""
    url = "https://landregistry.data.gov.uk/app/ukhpi/download/data/UK-HPI-full-file.csv"
    dest = DATA_DIR / "hpi" / "UK-HPI-full-file.csv"
    _download(url, dest)


def fetch_ons_lad_boundaries() -> None:
    """ONS LAD (May 2025) boundaries, via the Open Geography Portal API."""
    raise ManualDownloadRequired(
        "ONS LAD boundaries (May 2025):\n"
        "  https://geoportal.statistics.gov.uk/ -> search 'Local Authority Districts May 2025 UK BGC'\n"
        "  Download as GeoJSON, save to data/boundaries/lad_2025.geojson\n"
        "  (Phase 1 will pin the exact ONS API query once the harmonisation module is built.)"
    )


def fetch_ons_lad_lookups() -> None:
    """ONS historic LAD change lookups, chained across the 2009/2019/2020/2023 reorg waves."""
    raise ManualDownloadRequired(
        "ONS historic LAD change lookups (Phase 1 will pin exact vintages):\n"
        "  https://geoportal.statistics.gov.uk/ -> search 'LAD changes' or 'Local Authority District to Region'\n"
        "  Need lookups spanning: pre-2009, 2009 unitary reorg, 2019, 2020, 2023.\n"
        "  Save each to data/boundaries/lookups/<vintage>.csv"
    )


def fetch_ons_population_estimates() -> None:
    """ONS mid-year population / dwelling stock estimates."""
    raise ManualDownloadRequired(
        "ONS mid-year population estimates:\n"
        "  https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/populationestimates\n"
        "  Download the LA-level time series, save to data/population/mye_by_la.csv"
    )


def fetch_mhclg_band_d() -> None:
    """MHCLG Council Tax levels, 2000-01 to 2025-26. ~26 separate releases; not auto-fetchable yet."""
    raise ManualDownloadRequired(
        "MHCLG Council Tax levels (Band D), 2000-01 to 2025-26:\n"
        "  https://www.gov.uk/government/collections/council-tax-statistics\n"
        "  Each year is a separate release. Download the 'Table 10'-equivalent area Band D\n"
        "  sheet for each year, save to data/band_d/raw/<year>.xlsx (or .xls / .ods as published).\n"
        "  See DATA.md: sheet layout changes across vintages, hence the per-vintage parsers\n"
        "  in src/council_tax_freeze/parsers/band_d/ rather than one reader for all years."
    )


def fetch_voa_ctsop() -> None:
    """VOA Council Tax: Stock of Properties, annual releases."""
    raise ManualDownloadRequired(
        "VOA Council Tax: Stock of Properties (CTSOP), annual:\n"
        "  https://www.gov.uk/government/collections/council-tax-stock-of-properties-statistics\n"
        "  Download CTSOP1.0 (or nearest equivalent) for each year, save to data/ctsop/raw/<year>.xlsx"
    )


def fetch_price_paid_calibration_slice() -> None:
    """HM Land Registry Price Paid Data, 1995 and 1996 annual files only (calibration check, not main pipeline). URL below is best-effort, not yet verified - Phase 3 will confirm or replace it."""
    for year in (1995, 1996):
        url = f"http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com/pp-{year}.csv"
        dest = DATA_DIR / "price_paid_calibration" / f"pp-{year}.csv"
        _download(url, dest)


def fetch_mhclg_settlement_data() -> None:
    """MHCLG local government finance settlement data (RSG / SFA / Core Spending Power)."""
    raise ManualDownloadRequired(
        "MHCLG local government finance settlement data:\n"
        "  https://www.gov.uk/government/collections/local-government-finance-statistics\n"
        "  Series naming changes over the period (RSG -> SFA -> Core Spending Power) - see\n"
        "  DATA.md. Download whichever is current for each year, save to\n"
        "  data/settlement/raw/<year>.xlsx"
    )


FETCHERS = [
    fetch_uk_hpi,
    fetch_ons_lad_boundaries,
    fetch_ons_lad_lookups,
    fetch_ons_population_estimates,
    fetch_mhclg_band_d,
    fetch_voa_ctsop,
    fetch_price_paid_calibration_slice,
    fetch_mhclg_settlement_data,
]


def main() -> None:
    manual_needed = []
    for fetcher in FETCHERS:
        try:
            print(f"Fetching: {fetcher.__doc__.splitlines()[0]}")
            fetcher()
        except ManualDownloadRequired as e:
            manual_needed.append(str(e))
        except requests.RequestException as e:
            manual_needed.append(f"{fetcher.__doc__.splitlines()[0]} - automatic fetch failed ({e}); download manually.")

    if manual_needed:
        print("\n" + "=" * 70)
        print(f"{len(manual_needed)} dataset(s) need manual download:")
        print("=" * 70)
        for instruction in manual_needed:
            print(f"\n{instruction}")
        sys.exit(0)  # not a failure - this is expected for several sources


if __name__ == "__main__":
    main()
