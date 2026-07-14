"""
Central configuration for the council tax freeze analysis.

Every modelling assumption that isn't structurally forced by the data lives
here, so it can be reviewed, cited, and swept in `sensitivity/` from one
place. See DATA.md for the provenance of each input this config points at,
and notebooks/02_method.ipynb for the reasoning behind each assumption below.

Every constant here was an explicit decision made with the project owner,
not a silent default — see the conversation history / commit that introduced
this file for the reasoning, and QUESTION comments below for anything still
open.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
OUTPUTS_DIR = ROOT / "outputs"

# ---------------------------------------------------------------------------
# Study period
#
# Split into a HEADLINE series and a BACKWARD EXTENSION, not one uniform
# 2000-01 to 2025-26 run - see DATA.md "2009-wave dwelling-count gap" for
# the full reasoning. In short: the seven 2009 reorg-wave counties (Cornwall,
# Durham, Northumberland, Shropshire, Wiltshire, Bedfordshire, Cheshire)
# held ~6.3% of England's dwelling stock pre-2009, and Band D rates within
# at least one of them (County Durham) vary by ~16% across predecessor
# districts - meaning the counterfactual engine's weighting choice would
# materially move Durham's liability, and Durham/Northumberland sit
# directly on the North/South treatment variable this whole analysis
# measures. No real predecessor-level BAND distribution exists for those
# years (checked, not assumed - see DATA.md); only unbanded total dwelling
# weights (MHCLG Live Table 125) plus an imputed band split. That
# imputation is a real, directionally-biased assumption, not a neutral
# default, so it does not belong inside the headline number.
#
# HEADLINE_FIRST_YEAR to LAST_YEAR: every LA on observed CTSOP band counts,
# zero imputation. This is the load-bearing claim.
# EXTENSION_FIRST_YEAR to HEADLINE_FIRST_YEAR (exclusive): reported
# separately as "extending backward on imputed band shares adds a further
# £X per dwelling" - never folded into the headline. The imputation
# understates the gap (see BAND_SHARE_IMPUTATION_IS_CONSERVATIVE below), so
# this is a floor on the pre-2009 period, not a central estimate.
# ---------------------------------------------------------------------------
EXTENSION_FIRST_YEAR = "2000-01"
HEADLINE_FIRST_YEAR = "2009-10"
LAST_YEAR = "2025-26"
FIRST_YEAR = EXTENSION_FIRST_YEAR  # full study window, extension + headline combined
TARGET_BOUNDARY_VINTAGE = "2025"  # harmonise everything to 2025 LAD geography

# Imputed band shares for the 2000-01..2008-09 backward extension, applied
# to each 2009-wave predecessor district's Table 125 total dwelling count.
# Base case: each county's earliest observed post-2009 CTSOP band-share
# percentages, applied uniformly to all of that county's predecessors -
# assumes a stable, county-uniform band mix, which is very likely wrong in
# a predictable direction (e.g. Penwith's true mix was almost certainly
# poorer than Cornwall's post-2009 average). Because a poorer band mix
# would mean LOWER imputed stock value and therefore a SMALLER measured
# gap, this bias runs the same direction as the Band A/H midpoint choice:
# conservative, understating rather than overstating the finding. Stated
# plainly in 02_method.ipynb, not left implicit.
BAND_SHARE_IMPUTATION_IS_CONSERVATIVE = True
BAND_SHARE_IMPUTATION_METHOD_GRID = [
    "county_average_earliest_observed",  # base case, described above
    "successor_earliest_observed",  # equivalent for single-successor counties; distinguishes multi-successor ones (Bedfordshire, Cheshire)
    "pessimistic_for_low_value_districts",  # deliberately skews poorer predecessors' imputed mix further down, to bound how much the base case could be understating the extension
]

# ---------------------------------------------------------------------------
# Council tax bands (England: A-H). Multiplier is fraction of Band D.
# Statutory, not a modelling choice.
# ---------------------------------------------------------------------------
ENGLAND_BANDS = ["A", "B", "C", "D", "E", "F", "G", "H"]
BAND_MULTIPLIER = {
    "A": 6 / 9, "B": 7 / 9, "C": 8 / 9, "D": 9 / 9,
    "E": 11 / 9, "F": 13 / 9, "G": 15 / 9, "H": 18 / 9,
}

# 1991 band thresholds (lower bound of each band), England, GBP.
# Band A has no lower bound; Band H has no upper bound.
BAND_THRESHOLD_1991 = {
    "A": 0, "B": 40_000, "C": 52_000, "D": 68_000,
    "E": 88_000, "F": 120_000, "G": 160_000, "H": 320_000,
}

# ---------------------------------------------------------------------------
# Band A / H midpoint imputation.
#
# Both bands are open-ended, so "midpoint" requires an assumed ratio to the
# threshold. Base case: Band A = 0.75x its upper threshold (£40k), i.e. an
# assumed typical value of £30k; Band H = 1.5x its lower threshold (£320k),
# i.e. an assumed typical value of £480k.
#
# This is deliberately the CONSERVATIVE corner of the plausible range, not a
# best guess: Band H's true tail is fattest in the South (where Band H is a
# large share of stock and includes very high-value property), so
# understating it understates Southern 1991 stock value and therefore
# understates the counterfactual gap. The mirror argument applies to Band A
# in the North. See notebooks/02_method.ipynb for the 12-combination
# sensitivity grid (BAND_H_RATIO_GRID x BAND_A_RATIO_GRID below) that
# demonstrates the headline gap's sign is robust across this whole range.
#
# CHECKED, not just argued: src/council_tax_freeze/calibration/price_paid.py
# deflates 1995-97 Price Paid sales to April-1991-equivalent values in four
# LAs. Kensington and Chelsea / Westminster (thousands of sales each) show
# a true empirical Band H tail at 2.06x / 1.78x - both ABOVE the assumed
# 1.5x, confirming the assumption understates high-value stock. Blackpool /
# Easington show Band A tails at 0.77x / 0.64x - AT OR BELOW the assumed
# 0.75x, confirming the mirror argument independently. See DATA.md for the
# full table and sample sizes (some cells are 1-3 sales and not to be
# trusted; the two findings above are load-bearing, at thousands of sales
# each).
# ---------------------------------------------------------------------------
BAND_A_RATIO = 0.75
BAND_H_RATIO = 1.5
BAND_A_RATIO_GRID = [0.6, 0.75, 0.9]
BAND_H_RATIO_GRID = [1.25, 1.5, 2.0, 3.0]


def band_midpoints_1991(band_a_ratio: float = BAND_A_RATIO, band_h_ratio: float = BAND_H_RATIO) -> dict[str, float]:
    """1991 GBP midpoint value assumed for each band, given open-band ratios.

    Bands B-G are genuinely bounded, so their midpoint is just the mean of
    the lower and upper threshold — not a modelling choice.
    """
    thresholds = BAND_THRESHOLD_1991
    upper = {  # upper threshold of each band, band H excluded (unbounded)
        "A": thresholds["B"], "B": thresholds["C"], "C": thresholds["D"],
        "D": thresholds["E"], "E": thresholds["F"], "F": thresholds["G"],
        "G": thresholds["H"],
    }
    midpoints = {b: (thresholds[b] + upper[b]) / 2 for b in ENGLAND_BANDS if b not in ("A", "H")}
    midpoints["A"] = thresholds["B"] * band_a_ratio
    midpoints["H"] = thresholds["H"] * band_h_ratio
    return midpoints


# ---------------------------------------------------------------------------
# Effective collection factor: actual receipts as a share of the gross
# "every dwelling pays its full band charge" total, reflecting single-person
# discounts, exemptions, council tax support, and non-collection combined.
# NOT the published in-year collection rate (~97%) - see DATA.md.
# Following Tax Policy Associates' calibration (github.com/DanNeidle/lvt_model_2026).
# Applied uniformly across LAs and years in the base case; swept in sensitivity.
# ---------------------------------------------------------------------------
COLLECTION_FACTOR = 0.83
COLLECTION_FACTOR_GRID = [0.78, 0.83, 0.88]

# ---------------------------------------------------------------------------
# Band D scope: total council tax (district + county + police + fire),
# EXCLUDING parish/town council precepts. Parish coverage is uneven across
# LAs (concentrated in rural districts; absent in London boroughs and most
# metropolitan districts), so including it would inject a confound unrelated
# to the 1991-freeze mechanism this analysis tests. Matches MHCLG's own
# standard published "Band D council tax" headline figure.
# ---------------------------------------------------------------------------
BAND_D_INCLUDES_PARISH = False

# ---------------------------------------------------------------------------
# HPI baseline. LA-level UK HPI starts January 1995, not April 1991 (the
# actual valuation date). We do NOT attempt to bridge 1991-1995 - see
# README Framing and DATA.md. The revaluation factor is anchored to Jan 1995
# throughout; this analysis measures relative-value divergence since 1995.
# ---------------------------------------------------------------------------
HPI_BASELINE = "1995-01"

# HPI geography sensitivity: use LA-level series by default, fall back to
# region for LAs with suppressed/thin series regardless of variant (no
# LA-level alternative exists for those), and offer region-only as an
# explicit sensitivity variant.
HPI_GEOGRAPHY_GRID = ["la", "region"]

# ---------------------------------------------------------------------------
# Revaluation frequency sensitivity: how often the counterfactual stock
# valuation is refreshed. "continuous" updates every year (the base case in
# the brief's formula); 5/10-yearly hold the valuation flat between
# revaluation points, as an actual revaluation cycle would.
# ---------------------------------------------------------------------------
REVALUATION_FREQUENCY_GRID = ["continuous", 5, 10]

# ---------------------------------------------------------------------------
# Reallocation method: SINGLE-POT, not tiered. This is a decided, quantified
# limitation, not an oversight - see DATA.md "Single-pot reallocation:
# decision and quantified bound" for the full reasoning. In brief: the
# brief's own formula (and this engine) reallocates each year's TOTAL actual
# revenue against value share across all 296 LAs in one pot. The real system
# reallocates separately per precepting tier (district/county/police/fire/
# GLA), each within its own geography - a genuinely more accurate model,
# but one that needs precept-tier-level Band D data we do not have for the
# full headline period. Checked, not assumed: MHCLG publishes individual
# precept-tier rates (police/fire/county), with GSS codes, in a clean,
# structured format back to 2011-12 - confirmed directly. 2009-10 and
# 2010-11 are NOT available in that form; the only likely source is an
# unstructured, multi-hundred-page DCLG statistical digest, a materially
# different (and much larger) extraction task than anything else in this
# pipeline, not pursued.
#
# Decision: single-pot for the whole headline period, WITH the bias
# quantified per LA rather than corrected. The mechanism (confirmed via the
# Westminster investigation - see project log): single-pot incorrectly
# reallocates the SHARED-tier portion of a bill (county/police/fire/GLA -
# which in reality does not vary property-value-proportionally WITHIN its
# own precepting group) against value share across the whole of England.
# The resulting bias is largest for LAs whose OWN (district-tier) rate
# diverges most from its shared-tier peers (Westminster's district rate is
# £712 in 2018-19 against £933-1,707 for every other London borough sharing
# the same GLA/police/fire tier) - it is not simply "London is biased,
# the North is not": Hartlepool, County Durham and Blackpool are UNITARY
# authorities with LOW exposure on this measure (14-16% of their bill is
# set by tiers other than their own), consistent with their own rates not
# diverging sharply from peers. Ordinary two-tier shire DISTRICTS - a large
# share of England, North and South alike - have HIGH exposure by this same
# measure (85-90%), though whether that translates into REALISED bias
# depends on whether their COUNTY (not district) rate diverges from ITS
# peers, which has not been separately checked.
#
# `parsers.band_d.parse.build_band_d` exposes `own_precept_incl_parish`
# (the district's own precept, from Table 1) alongside the area total for
# exactly this purpose: `shared_tier_share = 1 - own_precept/area_total` is
# a per-LA, per-year BOUND on single-pot exposure - not a correction, a
# documented, quantified caveat to report alongside every gap.
TIERED_REALLOCATION_IMPLEMENTED = False
