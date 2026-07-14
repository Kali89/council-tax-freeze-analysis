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
    """ONS LAD (2025) boundary GEOMETRY, for Phase 7 choropleths - names/codes are already committed, see below."""
    raise ManualDownloadRequired(
        "ONS LAD boundary GEOMETRY (for choropleth maps, Phase 7):\n"
        "  https://geoportal.statistics.gov.uk/ -> search 'Local Authority Districts May 2025 UK BGC'\n"
        "  Download as GeoJSON, save to data/boundaries/lad_2025.geojson\n"
        "  NOTE: the 296 LA CODES AND NAMES (no geometry) needed for boundary harmonisation\n"
        "  are already committed at src/council_tax_freeze/boundaries/lad_2025.py - fetched\n"
        "  via the ArcGIS FeatureServer directly (item 5779a9578f0e48ccacef6af41546b56b), see\n"
        "  DATA.md. This function is only for the polygon geometry Phase 7 needs to draw maps."
    )


def fetch_ons_lad_lookups() -> None:
    """Historic LAD reorg events: RESOLVED, not a manual download - see note below."""
    raise ManualDownloadRequired(
        "Historic LAD reorg/change lookups are NOT a manual-download gap any more.\n"
        "  All five reorg waves (2009, 2019, 2020, 2021, 2023) plus the 2025 Barnsley/\n"
        "  Sheffield boundary change are hand-encoded and cited in\n"
        "  src/council_tax_freeze/boundaries/reorg_events.py, with every GSS code (predecessor\n"
        "  and successor) verified against the ONS Code History Database (July 2024) or a\n"
        "  maintained names-and-codes reference - see DATA.md 'Boundary harmonisation'.\n"
        "  This function is kept as a placeholder in case Phase 2's real MHCLG/CTSOP files\n"
        "  turn up an LA identity reorg_events.py doesn't yet cover; if that happens, add it\n"
        "  there with a citation, following the existing pattern - don't patch around it here."
    )


def fetch_ons_population_estimates() -> None:
    """ONS mid-year population / dwelling stock estimates."""
    raise ManualDownloadRequired(
        "ONS mid-year population estimates:\n"
        "  https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/populationestimates\n"
        "  Download the LA-level time series, save to data/population/mye_by_la.csv"
    )


def fetch_mhclg_band_d() -> None:
    """MHCLG's maintained live table, "Band D council tax figures 1993-94 to 2026-27" - ONE continuously-updated file, not 26 separate releases. See DATA.md."""
    url = "https://assets.publishing.service.gov.uk/media/69e8ab2d9ca985145673b826/Band_D_2026-27.ods"
    dest = DATA_DIR / "band_d" / "Band_D_1993_onwards.ods"
    _download(url, dest)


def fetch_voa_ctsop() -> None:
    """VOA CTSOP1.0, two files covering 2000-01 to 2025-26: a consolidated 1993-2024 time series, plus the standalone 2025 release for the one year not yet folded in. See DATA.md for the double-counting bug in the consolidated file's 2019-2023 reorg-wave rows, fixed in the parser, not here."""
    _download(
        "https://assets.publishing.service.gov.uk/media/6685468cab5fc5929851b928/CTSOP1-0-1993-2024.zip",
        DATA_DIR / "ctsop" / "CTSOP1_0_1993_2024.zip",
    )
    import zipfile

    with zipfile.ZipFile(DATA_DIR / "ctsop" / "CTSOP1_0_1993_2024.zip") as zf:
        zf.extractall(DATA_DIR / "ctsop" / "CTSOP1_0_1993_2024")
    _download(
        "https://assets.publishing.service.gov.uk/media/6a0c5ee5c510c3913d826863/2025_CT_SoP_Summary_Tables.xlsx",
        DATA_DIR / "ctsop" / "2025_summary.xlsx",
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


def fetch_ifs_r169_validation_data() -> None:
    """IFS R169 published LA-level revaluation results - Phase 4 known-answer validation, not a pipeline input."""
    raise ManualDownloadRequired(
        "IFS R169 LA-level revaluation-day results (Adam, Hodge, Phillips & Xu, 2020):\n"
        "  https://www.ifs.org.uk/research/english-council-tax\n"
        "  (returns 403 to automated fetch; open in a browser)\n"
        "  Used only to validate Phase 4's counterfactual engine against a published,\n"
        "  independently-produced result - see DATA.md 'Prior literature'.\n"
        "  If the LA-level data table isn't downloadable from that page, the full report PDF\n"
        "  is mirrored at:\n"
        "  https://www.nuffieldfoundation.org/wp-content/uploads/2020/03/"
        "R169-Revaluation-and-reform-bringing-council-tax-in-England-into-the-21st-century.pdf\n"
        "  Save whatever is obtained to data/validation/ifs_r169/"
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
    fetch_ifs_r169_validation_data,
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
