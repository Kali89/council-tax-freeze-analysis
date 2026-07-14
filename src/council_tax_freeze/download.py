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
    """UK House Price Index, full file. The Phase 0 URL guess was wrong (404) - confirmed and fixed in Phase 3. The real file lives on publicdata.landregistry.gov.uk with the release month in the filename, so this discovers the current month's page via the UK HPI reports COLLECTION page (which links to it directly) rather than hardcoding a URL that goes stale every month, or relying on gov.uk free-text search, which turned out to rank the actual page too low to find reliably."""
    import re

    collection = requests.get(
        "https://www.gov.uk/api/content/government/collections/uk-house-price-index-reports", timeout=30
    ).json()
    page_paths = sorted(
        set(re.findall(r"/government/statistical-data-sets/uk-house-price-index-data-downloads-[a-z0-9-]+", str(collection))),
        reverse=True,  # sorts most recent month first, given the -month-year suffix
    )
    content = requests.get(f"https://www.gov.uk/api/content{page_paths[0]}", timeout=30).json()
    body = content["details"]["body"]
    csv_url = next(m for m in re.findall(r'href="([^"]+UK-HPI-full-file-[^"]+\.csv)[^"]*"', body))
    dest = DATA_DIR / "hpi" / csv_url.rsplit("/", 1)[-1]
    _download(csv_url, dest)


def fetch_ons_lad_boundaries() -> None:
    """ONS LAD (May 2025) boundary GEOMETRY, for Phase 7 choropleths - names/
    codes (no geometry) are already committed, see boundaries/lad_2025.py.
    "Local Authority Districts (May 2025) Boundaries UK BGC (V2)" (ArcGIS
    item 0b8528fb4132495181d82bb65c5e370a, FeatureServer LAD_MAY_2025_UK_BGC_V2),
    same sourcing pattern as lad_2025.py/precepting_groups.py/regions.py -
    queried directly as GeoJSON. Confirmed directly: all 361 UK features,
    296 with an "E" prefix, match boundaries.lad_2025.LAD_2025_CODES exactly."""
    _download(
        "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
        "LAD_MAY_2025_UK_BGC_V2/FeatureServer/0/query?where=1%3D1&outFields=LAD25CD,LAD25NM&outSR=4326&f=geojson",
        DATA_DIR / "boundaries" / "lad_2025.geojson",
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
    """ONS mid-year population estimates - LA-level time series."""
    raise ManualDownloadRequired(
        "ONS mid-year population estimates:\n"
        "  https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/populationestimates\n"
        "  Download the LA-level time series, save to data/population/mye_by_la.csv"
    )


def fetch_mhclg_dwelling_stock_estimates() -> None:
    """MHCLG Live Table 125, Dwelling Stock Estimates by LA District - predecessor-level (Old ONS code) rows back to 2001, unbanded. See DATA.md '2009-wave dwelling-count gap' for why this matters."""
    _download(
        "https://assets.publishing.service.gov.uk/media/6a0dcbf65c3c79da61662e39/LiveTable125.ods",
        DATA_DIR / "dwelling_stock" / "LiveTable125.ods",
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
    """HM Land Registry Price Paid Data, 1995-97 annual files (calibration check, not main pipeline) + Nationwide's national quarterly HPI back to 1952, for the single-national-deflator baseline. Phase 0's best-effort Price Paid URL was verified correct in Phase 3 - unlike the HPI and Band D URLs, this one worked first try."""
    for year in (1995, 1996, 1997):
        url = f"http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com/pp-{year}.csv"
        dest = DATA_DIR / "price_paid_calibration" / f"pp-{year}.csv"
        _download(url, dest)
    _download(
        "https://www.nationwide.co.uk/media/hpi/download/uk-house-price-since-1952",
        DATA_DIR / "price_paid_calibration" / "UK_house_price_since_1952.xlsx",
    )


def fetch_mhclg_settlement_data() -> None:
    """MHCLG Core Spending Power table, final 2025-26 settlement - ONE file with
    one sheet per year back to 2015-16, not 11 separate per-vintage releases
    (same "maintained live table" pattern as Band D). Pre-2015-16 (Revenue
    Support Grant / early Settlement Funding Assessment era) is NOT in this
    file and is out of scope for Phase 6 by design - see DATA.md "Variant 3"."""
    _download(
        "https://assets.publishing.service.gov.uk/media/67a0c9554731769befb047a3/CSP_information_table_LGFS_2025-26.xlsx",
        DATA_DIR / "settlement" / "CSP_information_table_LGFS_2025-26.xlsx",
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
    fetch_mhclg_dwelling_stock_estimates,
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
