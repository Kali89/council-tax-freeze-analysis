# Data provenance

All datasets are free and public. None are committed to this repository —
`data/` is gitignored. Run `python -m council_tax_freeze.download` (or
`make data`) to fetch what can be fetched automatically; it prints
instructions for the rest.

Nothing in this file is a substitute for reading the publisher's own
documentation for a dataset before relying on it. Where we know of a
specific gotcha, it's noted below so the next reader doesn't rediscover it
the hard way.

| # | Dataset | Source | Purpose | Fetch |
|---|---|---|---|---|
| 1 | MHCLG's live table "Band D council tax figures 1993-94 to 2026-27" — ONE continuously-maintained file, not 26 separate releases (see below) | [gov.uk live tables on Council Tax](https://www.gov.uk/government/statistical-data-sets/live-tables-on-council-tax) | Band D council tax, total incl. an averaged parish contribution (primary series) and a constructed excl.-parish variant | Automatic — stable direct-download URL |
| 2 | VOA CTSOP1.0 — two files: a consolidated "1993 to 2024" time series plus the standalone 2025 release, covering 2000-01 to 2025-26 between them (see below) | [gov.uk council tax: stock of properties, 2025](https://www.gov.uk/government/statistics/council-tax-stock-of-properties-2025) | Band distribution (dwelling counts per band per LA per year) | Automatic — both are stable direct-download URLs |
| 3 | UK House Price Index, full file | [gov.uk HPI downloads](https://www.gov.uk/government/statistical-data-sets/uk-house-price-index-data-downloads) | LA-level appreciation series, Jan 1995 onward | Automatic (single large CSV) |
| 4 | ONS LAD boundaries (May 2025) + historic LAD change lookups | [ONS Open Geography Portal](https://geoportal.statistics.gov.uk/) | Boundary harmonisation to 2025 geography; mapping | Automatic via ONS API where available; manual for lookups not exposed via API |
| 5 | ONS mid-year population / dwelling stock estimates | [ONS](https://www.ons.gov.uk/) | Per-dwelling and per-capita denominators | Automatic |
| 6 | HM Land Registry Price Paid Data — 1995 and 1996 annual files only | [gov.uk price-paid downloads](https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads) | One-off calibration check on the Band A/H midpoint imputation (not used in the main pipeline) | Automatic — annual files are small; we do not use the multi-GB complete file |
| 7 | MHCLG Core Spending Power table, final 2025-26 settlement — ONE maintained file with one sheet per year back to 2015-16, not per-vintage releases (see Phase 6 below; pre-2015-16, Revenue Support Grant / early Settlement Funding Assessment, is out of scope by design) | [Core Spending Power table: final local government finance settlement 2025 to 2026](https://www.gov.uk/government/publications/core-spending-power-table-final-local-government-finance-settlement-2025-to-2026) | Control variable for the Variant 3 regression (did councils adjust rates as their implicit base grew?) | Automatic — stable direct-download URL |
| 8 | IFS published LA-level revaluation-day results, from Adam, Hodge, Phillips & Xu (2020), *Revaluation and reform: bringing council tax in England into the 21st century*, IFS Report R169 | [ifs.org.uk/research/english-council-tax](https://www.ifs.org.uk/research/english-council-tax) | Known-answer validation for the Phase 4 counterfactual engine (see below) — not an input to the pipeline itself | Manual — ifs.org.uk returns 403 to automated fetch; the report PDF itself is mirrored by the [Nuffield Foundation](https://www.nuffieldfoundation.org/wp-content/uploads/2020/03/R169-Revaluation-and-reform-bringing-council-tax-in-England-into-the-21st-century.pdf) |

## Prior literature

This is not the first analysis of this mechanism, and the README says so
prominently. Two references matter enough to flag here because they
constrain how Phase 4 validates the engine and how the Variant 3 regression
is framed:

- **Adam, Hodge, Phillips & Xu (2020), IFS Report R169.** Establishes that
  council tax has become more regressive since 1991 because values rose
  fastest where they were already highest (their Figure 2.4: London prices
  November 2019 were >6x January 1995, vs ~3x in the North East), and —
  the point that matters most for Variant 3 — that because central
  government funding to LAs still references relative 1991 property
  values, "councils in the North East must now levy more tax on a property
  worth (say) £250,000 than councils in London, if both are to deliver the
  spending on services deemed necessary by central government." That is a
  published statement that the unfairness could in principle be corrected
  through the funding settlement alone, without touching council tax bands
  — the strongest form of the objection Variant 3 exists to test.
- **Breach (2024), Centre for Cities, "Towards fiscal devolution."** Models
  revaluation plus additional top/bottom bands and hits the same open-band
  imputation problem we solved in `config.py` (their footnote: "more
  conservative values have been used for the modelling for these bands") —
  cited as precedent for our approach, not just a coincidence. Also argues
  revaluation without fiscal devolution risks "minimal or zero improvement
  to incentives, resource, and fairness... despite huge political costs" —
  relevant context for why Variant 3's answer matters politically, not just
  statistically.

**What's actually new here:** both are snapshot counterfactuals — what
happens if we revalue *now*, with distributional analysis of winners and
losers on revaluation day. Neither publishes the cumulative magnitude of
the freeze's redistributive effect as an LA-level time series. "London
would pay £X more after revaluation" is a different claim from "London has
underpaid £Y per dwelling cumulatively since 2000." We are quantifying the
accumulated stock, not re-discovering the flow.

## Known issues by dataset

**MHCLG Band D (#1): one live table, not 26 parsers.** The brief anticipated
26 separate annual releases needing 26 separate parsers. In fact MHCLG
maintains a single continuously-updated file — "Band D council tax figures
1993-94 to 2026-27" — with one row per historic LA identity and one column
group per year, back to 1993-94. `src/council_tax_freeze/parsers/band_d/parse.py`
reads this directly. Two bases are extracted:

- `band_d_incl_parish` (Table 5, "Area council tax"): the district's own
  precept (itself including an averaged parish contribution) plus
  county/police/fire. This IS the standard published headline figure —
  verified to the pound against a completely separate, frozen 2013 MHCLG
  PDF for 20 straight years (2000-01 to 2012-13), and against contemporaneous
  standalone releases for 2017-18, 2018-19, 2022-23, 2024-25 and 2025-26 (18
  of 26 study years independently checked; the rest are unchecked but
  produced by the identical, already-verified mechanism). This is the
  PRIMARY series.
- `band_d_excl_parish`: constructed as `band_d_incl_parish` minus the
  district's own parish component (Table 1 minus Table 3, both
  district-precept-only, so their difference IS the parish component).
  Carried as a documented robustness variant per the parish-basis decision
  (see project log) — the North/South gap is reported on both bases in
  03_results.ipynb, and the delta between them is itself a finding, not
  assumed to be immaterial.

**Known gaps in the Band D live table**, found by cross-referencing every
Phase 1 predecessor code against it (`predecessor_gaps` in `BandDResult`,
enforced by a test that fails if a NEW undocumented gap appears): five
predecessor codes have zero data anywhere in the file.
Barnsley (E08000016) and Sheffield (E08000019) are **not gaps** — MHCLG
applies their current codes (E08000038/E08000039) retroactively across the
whole 1993-2027 span, since neither had a real boundary change until the
small 2025 one. Durham City (E07000056), Crewe and Nantwich (E07000015),
and Shrewsbury and Atcham (E07000185) **are genuine gaps**: real
predecessor billing authorities with zero data despite every other member
of their 2009 merger group being fully present. No explanation found;
recorded as an unexplained limitation, not smoothed over.

**VOA CTSOP (#2): a genuine double-counting bug in VOA's own consolidated
file, found and fixed.** Like Band D, VOA maintains a consolidated time
series ("CTSOP1.0 ... 1993 to 2024") rather than requiring 26 separate
parsers — but unlike Band D's live table, it has a real data-quality
problem. Checked, not assumed: for the 2009 reorg wave, VOA retroactively
aggregated predecessor districts under their current successor code and
correctly dropped the predecessor rows entirely (e.g. no separate "Penwith"
row exists after 2009 — Cornwall's row alone carries the full history back
to 1993, and its pre-2009 figures **exactly** equal the sum of its six
predecessors — verified). But for the 2019, 2020, 2021 and 2023 waves, VOA
did the first half of this (the successor row correctly carries the
retroactive sum — Dorset UA's 2015 total exactly equals the sum of its five
predecessor districts' 2015 totals) but **not the second half**: the
predecessor rows were never dropped, and continued to be updated with real,
growing dwelling counts for years after their own legal abolition. East
Dorset (abolished 1 April 2019) shows a real, increasing dwelling count
every year through 2024, five years after it ceased to exist.

Consequence: summing every LAUA row in the raw file overcounts England's
total stock by roughly 1.4-1.8 million dwellings a year (about 7%), growing
over time as the double-counted areas' own stock grows — confirmed against
the file's own England ("NATL") row, which does NOT show this inflation
(`duplication_check` in `CTSOPResult`). The standalone 2025 release, built
differently, shows no comparable excess (~250 dwellings, immaterial).

**Fix, in `src/council_tax_freeze/parsers/ctsop/parse.py`:** for every
`MERGE` event in `reorg_events.py`, keep only the successor row (already
correct for the whole period) and drop every predecessor row entirely,
rather than trying to reconstruct a before/after cutover. Post-fix, the LA
row sum matches the file's own national row to within a few hundred
dwellings out of tens of millions (<0.01%) for every year 2000-01 to
2025-26 — down from the ~7% raw excess. The dropped predecessor rows are
NOT discarded: they are genuine, non-duplicated dwelling counts for
2019-2023-wave predecessors, kept in `CTSOPResult.predecessor_weights`,
because they're exactly the weights Phase 4 will need to combine Band D's
predecessor-level RATES for those same LAs. No equivalent exists for the
2009 wave (VOA never published individual predecessor rows for it at all)
— a real, flagged gap for Phase 4's weighting approach, not solved here.

**Cross-series disagreement (Band D vs CTSOP), as expected and requested to
be logged rather than smoothed over:** the two source series handle
historic identity completely differently. MHCLG's Band D live table mostly
*preserves* historic predecessor rows (only relabelling the two pure-RECODE
cases, Bedford and Barnsley/Sheffield, under their current code) — which is
why Band D coverage genuinely *declines* over time as predecessor rows
disappear at each reorg (354 in 2000-01, falling to 296 from 2023-24). VOA's
CTSOP does the opposite: it *retroactively aggregates* merge-affected LAs
under their current code for the whole 1993-2024 span (once the
double-counting bug above is fixed), so CTSOP coverage is a flat 296 for
every single year 2000-01 to 2025-26, with no time variation at all. Same
underlying history, two structurally opposite representations. Neither is
"wrong" for its own stated purpose, but it means the two series cannot be
joined naively on (code, year) for the pre-2009 or 2019-2023 periods without
going through the Phase 1 crosswalk, and it's the reason Band D's dwelling
weights for those predecessor rates have to come from a different source
than CTSOP for the 2009 wave specifically (see above).

**The 2009-wave dwelling-count gap: quantified, and NOT resolved here —
this is an open decision for Phase 4, not something to decide implicitly
inside a parser.** Band D preserves the six-to-seven separate predecessor
rates for each 2009-wave county (e.g. six different Durham district rates
pre-2009); CTSOP retroactively aggregates them into one successor dwelling
count with no predecessor-level breakdown. Every band-weighted calculation
in the counterfactual engine needs `count[i,b,t]` at the same resolution as
the rate — for the 2009-wave areas pre-2009, we don't have that.

*Exposure*, cross-checked from two independent sources so the number isn't
an artefact of one methodology: the seven 2009-wave areas (Cornwall,
County Durham, Northumberland, Shropshire, Wiltshire, Bedfordshire,
Cheshire) held **~6.3% of England's dwelling stock** throughout 2000-2008 —
6.29-6.34% from VOA CTSOP's own retroactively-aggregated totals (2000, 2005,
2008), 6.32-6.37% from MHCLG's separately-sourced Dwelling Stock Estimates
summed across the real predecessor rows (2001, 2005, 2008). This is
materially above a "~5%, live with it" threshold. It also isn't uniform
risk: predecessor-level Band D rates within a county are not always close
together — Cornwall's six 2000-01 rates span £804.57-£832.93 (a tight
~3.5% range, where an unweighted average would barely differ from a
dwelling-weighted one), but County Durham's six available predecessor rates
(missing Durham City, per the Band D gap above) span £867.69-£1,009.34 (a
~16% range, where the weighting choice materially changes the answer). Durham
and Northumberland are North East authorities — exactly the low-appreciation
end of the North/South comparison this project exists to measure, so a
weighting bias here does not average out harmlessly elsewhere.

*Does the granular historic data exist?* Checked directly, not assumed:

- **Individual historic VOA CTSOP releases (2000-2009) with predecessor
  rows intact: not found**, despite real archival research, not just a
  cursory check. Queried the UK Government Web Archive's CDX API across the
  entire `voa.gov.uk` domain for 2000-2009 (`/publications/*`,
  `/council_tax/*`, `/publications/statistical_releases/*` — the last of
  these has no captures before April 2010 at all), tried every plausible
  filename pattern (`stock`, `band`, `dwelling`, `ctsop`, `valuation-list`,
  `banding`), and fetched several promising pages directly (the archived
  "Council Tax Valuation Lists 1993 England" page, dated September 2010,
  shows only post-2009 geography). Also checked whether the local
  government department (ODPM/CLG, MHCLG's predecessors) published this
  independently of VOA in that era — no evidence found. The 2009-wave's
  retroactive aggregation in the modern CTSOP file may be a reconstruction
  VOA did once, internally, at the time of the 2009 reorg, rather than a
  republishing of previously-separate published figures — consistent with
  VOA's own statistics publishing function appearing to have solidified
  around 2010 (see "VOA has moved its Council Tax work onto a new, modern
  operating system", noted earlier in this file for the 2025 release).
- **The ONS/MHCLG fallback DOES exist, partially**: MHCLG's "Live Table
  125: Dwelling Stock Estimates by Local Authority District"
  (`src/council_tax_freeze/download.py:fetch_mhclg_dwelling_stock_estimates`,
  `data/dwelling_stock/LiveTable125.ods`) carries real, predecessor-level
  **total** dwelling counts (not banded) for all 37 predecessor districts
  across all seven 2009-wave counties, back to **2001** (one year short of
  our 2000-01 start), with an "Old ONS code" / "New ONS code" pair per row.
  Those old codes (e.g. Penwith = `15UF`) and new codes (Penwith =
  `E07000023`) independently cross-validate the Phase 1 predecessor codes
  resolved against the ONS Code History Database — an unplanned but genuine
  second confirmation of that earlier work, from a completely different
  MHCLG series.

*What this means concretely*: real predecessor-level dwelling-count
**weights** exist (Table 125, unbanded, 2001-2008 - the fallback the brief
anticipated), but predecessor-level **band distributions** do not exist
anywhere found. The only way to get band-level predecessor counts is
imputation - e.g. applying each county's earliest observed post-2009 CTSOP
band-share percentages back onto each predecessor's own Table 125 total, on
the assumption that the relative band mix within a county was similar
across its predecessor districts and stable over 2000-2009. That is a real,
named assumption, not a neutral default, and it is likely wrong in a
predictable direction (e.g. Penwith, historically a lower-value part of
Cornwall, almost certainly has a poorer band mix than Carrick).

**Decision (resolved, not deferred): headline series 2009-10 to 2025-26,
zero imputation; a separately-labelled backward extension to 2000-01.**
The deciding fact was not the 6.3% area share on its own but County
Durham's ~16% intra-county rate spread: a blended dwelling count there
would materially move a North East authority's liability, and Durham/
Northumberland sit directly on the North/South treatment variable this
analysis measures — error there does not average out against the South, it
lands on the comparison.

- `config.HEADLINE_FIRST_YEAR = "2009-10"` through `LAST_YEAR`: every LA on
  observed CTSOP band counts. This is the load-bearing claim, and it is
  clean — 17 years is still comfortably the longest cumulative estimate of
  this mechanism anyone has published (see "Prior literature" above; both
  IFS 2020 and Centre for Cities are snapshots, not time series at all).
- `config.EXTENSION_FIRST_YEAR = "2000-01"` through the year before
  `HEADLINE_FIRST_YEAR`: Table 125 predecessor dwelling-count weights +
  imputed band shares (`config.BAND_SHARE_IMPUTATION_METHOD_GRID`),
  reported ONLY as an explicitly labelled addition — "extending backward on
  imputed band shares adds a further £X per dwelling" — never silently
  folded into the headline figure.
- **Bias direction stated plainly, same framing as the Band A/H midpoint
  choice** (`config.BAND_SHARE_IMPUTATION_IS_CONSERVATIVE`): assigning
  Easington or Penwith their county's post-2009 average band mix gives them
  a BETTER mix than they likely really had (poorer areas pull the true
  county average down). A better band mix means a higher imputed 1991-basis
  stock value, which means a higher counterfactual liability, which means a
  SMALLER measured gap. The imputation therefore understates the finding it
  contributes to — the backward extension is a floor on 2000-09, not a
  central estimate. 02_method.ipynb states this using the same "conservative
  corner" language as the midpoint sensitivity, not a separate framing.
- **Sensitivity on the imputation, not just a single imputed number**:
  `BAND_SHARE_IMPUTATION_METHOD_GRID` varies the back-projected shares
  across county-average (base case), successor's-earliest-observed
  (distinguishes multi-successor counties, Bedfordshire and Cheshire, from
  the base case), and a deliberately pessimistic skew for low-value
  predecessors. Reported in 02_method.ipynb/03_results.ipynb regardless of
  outcome — if the extension barely moves across methods, that is itself a
  reported finding and strengthens it; if it moves a lot, that is reported
  too.
- **Option "coarsen the weighting scheme everywhere" was considered and
  dropped**: it would worsen resolution across all 26 years to avoid one
  imputation confined to 9, and introduces a pre/post-2009 methodological
  inconsistency in exchange - two problems for the price of one.

The structural point of this split: a hostile reader can reject the
2000-09 extension outright and the headline survives completely untouched —
it just gets shorter. Contestable material (the imputation) sits outside
the load-bearing claim, which is where contestable material belongs.

**Corroboration, noted for the record**: Table 125's Old/New ONS code
columns independently cross-validate the Phase 1 boundary crosswalk's GSS
codes (e.g. Penwith: old `15UF`, new `E07000023`, matching the ONS Code
History Database resolution exactly) - unplanned, from a completely
separate MHCLG series never used for that purpose. Free evidence the
boundary harmonisation work is right, not just internally self-consistent.

**UK HPI (#3).** LA-level series start January 1995, not April 1991 — see
the README's Framing section. A handful of LAs have suppressed or
sparse series due to low transaction volumes (City of London, Isles of
Scilly, and a few others in some periods); these fall back to their region's
HPI series regardless of which HPI-geography sensitivity variant is active,
since there is no LA-level alternative to fall back to.

**Boundary harmonisation (#4).** No single ONS lookup spans 2000-2025.
The crosswalk is built by chaining vintage-to-vintage lookups across five
reorganisation waves, dates and constituent districts verified against
Wikipedia/legislation.gov.uk rather than assumed:

- **2009**: Cornwall, County Durham, Northumberland, Shropshire, Wiltshire
  (whole ex-county mergers); Bedfordshire → Bedford + Central Bedfordshire;
  Cheshire → Cheshire East + Cheshire West and Chester.
- **2019**: Dorset + Poole + Bournemouth → Dorset + Bournemouth,
  Christchurch and Poole; Suffolk → West Suffolk + East Suffolk.
- **2020**: Buckinghamshire → Buckinghamshire Council.
- **2021**: Northamptonshire → North Northamptonshire + West Northamptonshire.
- **2023**: Cumbria → Cumberland + Westmorland and Furness; North Yorkshire
  → North Yorkshire Council; Somerset → Somerset Council.

Every one of these, checked individually, is a **clean regrouping**: each
predecessor district's territory goes wholly into exactly one successor
authority — none of them split a single old district's territory between
two different new authorities. That means every merge in this period is
dwelling-count-preserving by construction (summation, not apportionment) —
encoded and tested in `src/council_tax_freeze/boundaries/reorg_events.py`
and `crosswalk.py`.

There is exactly one genuine exception in the whole 2000-2025 period, and
it demonstrates why the "fail loudly, don't guess" design matters: the
**Barnsley and Sheffield (Boundary Change) Order 2024** (in force 1 April
2025) transferred the Oughtibridge Mill development — 12 existing dwellings,
284 further planned — from Barnsley (E08000016 → E08000038) to Sheffield
(E08000019 → E08000039). CTSOP's LA-level totals can't tell us which band(s)
those 12 dwellings sit in; we apply the Order's own fixed count and flag the
band-distribution assumption explicitly (see `reorg_events.py`) rather than
inventing a proportional split with no basis. This is encoded as a `SPLIT`
event, which the module's own validation refuses to construct without a
cited `Apportionment` — see `tests/test_boundaries.py`.

Every GSS code in every event — predecessor and successor alike, all 22
events — is now verified against an authoritative source: successors
against ONS or a maintained names-and-codes reference, and the 2009-wave
predecessors (Cornwall's six former districts, Durham's seven, etc.) — the
gap flagged after Phase 1 as higher-risk than "should resolve itself
naturally," since 2000-2009 is a third of the whole study window and the
affected areas are disproportionately rural, low-appreciation ones the
headline result depends on — against the **ONS Code History Database (CHD),
July 2024 release**, `ChangeHistory.csv` (all terminated 31/03/2009, "GSS
re-coding strategy", correct county PARENTCD for each). Downloaded directly
from ONS's ArcGIS Hub (item `d7be63c8bd144ae0a26c6593eb5e00b7`), since the
Hub dataset page itself is JS-rendered and exposes no static link. The
current 296 English LA codes and names (`src/council_tax_freeze/boundaries/lad_2025.py`)
are committed too, for the same reason `reorg_events.py` is committed
rather than downloaded: tests need ground truth to check resolutions
against without a full raw-data download first.

Cross-checking every 2000-01–2025-26 financial year's reconstructed LA
identity set against this ground truth (`tests/test_boundaries.py::test_full_2000_2025_coverage`)
caught one further real gap: Sheffield's own pre-2025 code (E08000019) was
never listed as a predecessor anywhere, since the Barnsley/Sheffield SPLIT
event only accounted for Barnsley's side of the 2025 boundary change. Fixed
by adding `SHEFFIELD_RECODE_2025`. The per-year counts this test reports
(354 in 2000-01, falling in exact lockstep with each wave's district count,
to 296 from 2023-24 onward) match the known number of predecessor districts
in every wave exactly - a genuine cross-check, not just "no exception was
raised."

**Price Paid calibration slice (#6) — run, with results.** Not a promise
to check later; this ran in Phase 3. 1995-97 Price Paid sales in four
local authorities (Kensington and Chelsea, City of Westminster — high
value; Blackpool, Easington — low value; Easington used directly as a real
predecessor district rather than the ambiguously-labelled "COUNTY DURHAM"
field that also appears in the raw file) were deflated to an
April-1991-equivalent value using a single *national* quarterly deflator
(Nationwide's "UK house prices since 1952" series, Q2 1991 = baseline) —
a much smaller, self-contained assumption than LA-level 1991-1995 bridging,
which remains deliberately unbridged for the main pipeline (see README
Framing). A non-market-transaction filter (floor + fraction-of-local-median,
following Tax Policy Associates' published approach) was applied before
drawing any conclusion from the tail.

Result: `src/council_tax_freeze/calibration/price_paid.py`,
`tests/test_price_paid_calibration.py`.

| District | Band H empirical ratio (assumed 1.5) | n sales | Band A empirical ratio (assumed 0.75) | n sales |
|---|---|---|---|---|
| Kensington and Chelsea | **2.06** | 3,860 | n/a (0 sales below £40k) | 0 |
| City of Westminster | **1.78** | 2,287 | n/a (0 sales below £40k) | 0 |
| Blackpool | 2.66 (n too thin to trust) | 3 | **0.77** | 3,799 |
| Easington | 1.06 (n too thin to trust) | 1 | **0.64** | 2,092 |

The two high-value areas have thick samples (thousands of sales) and both
show the true empirical Band H tail running well above the assumed 1.5x
ratio; the two low-value areas' Band A ratios sit at or below the assumed
0.75x (Easington notably below, at 0.64x). These four numbers are real and
unaffected by anything below — the calibration measures where the true
tails sit, independent of how the model responds to the parameter.

**What is affected: the conclusion this repo drew from them.** Through
Phase 4, both findings were read as pointing the same direction — "the
assumed ratios make the measured gap smaller than a more
empirically-grounded set would, not larger" — i.e. that 0.75/1.5 sat at
the conservative corner of the plausible range. **Phase 5's sensitivity
sweep found that reasoning was wrong** (see SENSITIVITY_RESULTS.md "Axis
1"): the liability curve (`engine.build._compressed_multiplier`) is
rebuilt from these same two ratios every time it's evaluated, so a higher
`BAND_A_RATIO` moves both the assumed value *and* the curve's own shape,
and the curve effect dominates — measured directly, the North East
headline metric *increases* with `BAND_A_RATIO` and *decreases* (weakly)
with `BAND_H_RATIO`, the opposite of what was assumed when this section
was first written.

Run through the actual engine at the two empirical corners these four
numbers define (not interpolated): `band_a_ratio=0.64, band_h_ratio=2.06`
(Easington + Kensington and Chelsea) gives a North East headline of
**£205.79/dwelling/year**; the opposite corner, `band_a_ratio=0.77,
band_h_ratio=1.78` (Blackpool + Westminster), gives **£232.30**. The base
case (0.75, 1.5) gives £227.63 — inside this range, but near its *top*
(82% of the way from £205.79 to £232.30), not its floor. **The Price Paid
calibration still constrains the plausible range of true midpoint values —
that part is unaffected. It no longer supports the claim that the base
case sits at the conservative end of that range.** The honest
characterisation is a central estimate (£227.63) with an
empirically-anchored band of roughly £206-232, not a demonstrated lower
bound. Blackpool and Easington's own Band H figures (2.66x, 1.06x) are
quoted for completeness but are statistically worthless (3 and 1 sales) —
exactly what you'd expect in areas with almost no genuinely high-value
1990s stock, not a data error.

**Settlement data (#7).** The naming and structure of this series changes
more than council tax data does — Revenue Support Grant (pre-2013-ish),
Settlement Funding Assessment, and more recently Core Spending Power are
not directly comparable line items. The Variant 3 regression documents
which series is used in which years and treats this as a genuine
limitation on how far back a clean settlement control can be pushed.

**Collection factor.** Applied as a single constant (default 0.83,
following Tax Policy Associates) across all LAs and all years, per
`config.py`. This does not vary by LA or year in the base case, despite
real collection rates, single-person-discount prevalence, and council tax
support generosity (especially post-2013 localisation) all varying over the
period. Exposed as a sensitivity parameter; not re-derived per LA/year in
this analysis. Note this is *not* the published in-year collection rate
(~97%) — it is a broader effective discount factor reflecting exemptions,
discounts, and support as well as non-collection, calibrated so aggregate
net receipts match published totals.

## Phase 4: two more resolution mismatches found while joining Band D to CTSOP

Building the engine surfaced two further cross-series join problems beyond
the ones already documented above — both found by the engine's own
unresolved-row diagnostics, neither anticipated in advance.

**Barnsley/Sheffield code alias (bug, fixed).** Band D applies Barnsley's
and Sheffield's *post-2025* codes retroactively across their whole history
(same pattern as Bedford, see above) - but CTSOP's consolidated file uses
the *pre-2025* codes until 2025. Same real-world geography, two different
code labels, for every year before 2025. Not a data gap: fixed in
`engine/build.py` (`_recode_aliases`) by indexing the CTSOP lookup under
both codes for the affected years.

**Suffolk/Somerset 2019 predecessors: no CTSOP row at any resolution.**
Unlike every other merge event (including the rest of the 2019 wave -
Dorset, BCP), West Suffolk, East Suffolk and Somerset West and Taunton's
predecessors (Forest Heath, St Edmundsbury, Suffolk Coastal, Waveney,
Taunton Deane, West Somerset) have NO row in CTSOP at all, at any
resolution - VOA retroactively aggregated them the same way it did the
2009 wave, rather than leaving real predecessor rows the way it did for
Dorset/BCP. Quantified before deciding treatment, using the same framework
as the County Durham decision above: combined, these six predecessors
held ~0.8% of England's dwelling stock in 2015-16 (vs 6.3% for the 2009
wave - an order of magnitude smaller), and their Band D rates differ by
0-3.7% within each merging pair (vs ~16% for Durham's predecessors - also
an order of magnitude smaller). Neither Suffolk (East of England) nor
Somerset (South West) sits on the North/South fault line this analysis
measures. By the same decision logic as the 2009-wave gap: this is a
documented limitation, not a second backward-extension case. Fixed with an
**equal split** of the immediate successor's real combined CTSOP count
across its sibling predecessors, each then charged at its OWN real Band D
rate (not an averaged rate) — `engine/build.py` (`_equal_split_fallback`).
Result: zero unresolved rows across the entire headline period
(2009-10 to 2025-26, 296 LAs × 17 years = 5,032 rows), confirmed by test.

## Phase 4: the IFS gate, and what it caught

Per the project's own methodology standard: the engine's implied FY2018-19
LA-level redistribution was checked against IFS (2020)'s own published
Table 4.1/4.2/4.4 figures for named local authorities **before** the
cumulative headline series was trusted, run as a gate — fail and stop, not
fail and tune. Result: pass on sign (Variant 1: 14/15 named LAs; Variant 2:
8/8), but sign alone was not treated as sufficient, and that turned out to
matter.

**Checking magnitudes, not just signs, on the same data found a real,
systematic error**, not just a discrepancy to note and move past. Both
Kensington and Chelsea and Westminster's Variant 2 gaps came out 2-3x
larger than IFS's own published figures — a large miss on real LAs, not an
edge case, and one a sign-only gate would have missed entirely.

**Investigated, not assumed.** Two candidate causes were ruled out first:
Westminster's Band D rate (£712.09, 2018-19) was verified directly against
Westminster's own published council tax guide — correct. Our implied
average property value for Westminster (£1,253,118) was checked against
IFS's own independent Table 4.1 estimate (£1,176,000, Q1 2019) — within
7%, not the source of a 2-3x error. The actual cause: this engine
reallocates each year's total actual revenue against value share in a
**single national pot** — literally the brief's own specified formula, and
the real system does not work that way. Most of a London borough's bill
(the GLA precept — mayoral, police, fire) is identical across all 33
boroughs and was never value-proportional; in reality it reallocates
*within* London, not against the whole of England. Checked directly, not
via the England average: Westminster's own Band D rate (£712) is uniquely
low even against its own precepting-group peers (City of London £933,
Kensington and Chelsea £1,139, Hackney £1,375, Camden £1,489, Lewisham
£1,498, Richmond upon Thames £1,707) — a genuine, large, LOCAL anomaly
(business-rate income, historic reserves), which single-pot reallocation
amplifies against the whole of England rather than confining to its own
tier. The ratio between an LA's stock-value share and its actual-revenue
share (what single-pot reallocation uses directly) is 6.25x for
Westminster, 4.10x for Kensington and Chelsea, 2.28x for Camden — a clean
gradient tracking exactly how far each borough's own rate diverges from
its shared-tier peers, confirming the mechanism rather than a
London-wide effect.

**Nesting was fixed first** (per instruction — a rewrite of existing code,
not blocked on new data acquisition). The original Variant 1 reassigned
whole band cohorts to a new discrete band via nationally-rescaled
thresholds; Variant 2 used a separate, continuous stock-value sum — two
different approximation methods, checked across all 296 LAs and found to
disagree on sign for 62 LAs (80% agreement, not the near-100% a properly
nested pair should show). Rewritten so both variants share one calculation:
a single relative value per dwelling cohort (`band midpoint × LA HPI
factor / national HPI factor`), passed through either a smooth compressed-
multiplier curve (Variant 1, fit exactly through the real system's 8
band-multiplier points, piecewise-linear in log-value) or a plain
proportional line (Variant 2 — literally "Variant 1 with the compression
removed"), both feeding the same reallocation step. Verified: the two
curves cross exactly once, at Band D's own midpoint (checked numerically
over a 500-point grid). Verified separately: Variant 2's actual computed
numbers are unchanged by this rewrite (a mathematical necessity — dividing
by a common per-year constant doesn't move a share-based reallocation).
Raw sign-agreement only rose to 244/296, which looked like a non-fix —
until the remaining 52 disagreements were checked directly and found to be
a genuine finding, not residual noise: they are concentrated in
tail-skewed Surrey commuter towns (Elmbridge 40.4% of stock in Bands F-H
vs 9.2% England-wide), where Variant 1's valuation-date-only effect is
small but Variant 2's compression effect is large enough to dominate and
flip the sign — exactly what "V2 = V1 + compression" predicts when the
compression term dominates. Confirmed with a correlation check (r = -0.69
between the V2-V1 gap and F-H band share across all 296 LAs). **Variant 1
is reported as the headline; Variant 2 is reported as a separate,
secondary finding about compression, concentrated in wealthy commuter
areas that cut across the North/South axis — never summed or averaged
with Variant 1.** See `notebooks/02_method.ipynb` "Variant 1 is the
headline" and `tests/test_engine.py`.

**Tiers were scoped, not built**, and the GLA-only shortcut (fix London,
leave the rest single-pot) was explicitly considered and rejected: it
would make the North/South comparison itself a comparison between two
different calculations, worse than one method applied uniformly.
Confirmed by checking, not assuming: MHCLG publishes individual
precept-tier rates (police, fire, county, each with GSS codes) in a clean,
structured format back to **2011-12** — verified directly, real files, real
numbers (Avon and Somerset Police: £168.03 in 2011-12, rising to £251.20 by
2022-23, a plausible trajectory). **2009-10 and 2010-11 are not available
in that form** — the gov.uk pages for those years return 404 (same
platform-migration pattern already found for VOA in Phase 3); the only
likely source is an unstructured, multi-hundred-page DCLG statistical
digest, a materially larger and different extraction task than anything
else in this pipeline. Not pursued, per the explicit decision this
triggered: single-pot reallocation stays for the whole headline period,
the bias quantified rather than corrected.

**The quantified bound**: `engine.build.compute_shared_tier_exposure`
computes, per LA per year, `shared_tier_share = 1 - (own district
precept / area total)`, using Band D data already in the pipeline (no new
source needed — `own_precept_incl_parish`, from Table 1, is now exposed
alongside the area total specifically for this purpose). This is
structurally bimodal, checked directly, not assumed: unitary and London
authorities cluster at 6-40% (their own precept already absorbs what would
be county-level services elsewhere; ~120 LAs in this band for FY2018-19),
ordinary two-tier shire districts cluster at 83-92% (~200+ LAs) — a
function of England's actual local government structure, North and South
alike, not a London-specific artefact. Hartlepool, County Durham and
Blackpool — the Northern LAs this analysis' headline rests on — are all
unitary authorities in the LOW-exposure band (14-16%), consistent with
their own rates not diverging sharply from their (small) set of
shared-tier peers, unlike Westminster's. This is a bound on exposure, not
proof of the absence of bias, and is reported alongside every gap rather
than used to silently adjust any of them — see
`tests/test_engine.py::test_westminster_high_exposure_hartlepool_low_exposure`
and `test_exposure_is_bimodal_by_authority_type`.

**Exposure alone can't say whether a gap IS distorted, only whether it
COULD be** — that needs the LA's own precept to actually diverge, in cash
terms, from its precepting-group peers (`boundaries/precepting_groups.py`:
shire county / metropolitan county / Greater London, sourced from ONS's
real "LAD to County (December 2024)" lookup — 63 standalone unitary
authorities have no such peer group and get `NaN`, not a false zero).
`engine.build.compute_single_pot_bias_risk` computes this second
condition. **First version was a ratio (own precept ÷ peer-group median)
and it was wrong**: it ranked ordinary shire districts above Westminster —
Oxford scored higher because its own precept (£303.80) is ~50% above its
Oxfordshire peers' (£202.86 median), a large ratio on a small base (£101
cash, on a ~£1,900 bill), while Westminster's own precept (£417.86) is 64%
*below* its Greater London peers' (a smaller ratio, 0.36) but on a much
larger base (a £755.97 cash gap, on a £712.09 bill). Since the reallocation
this explains sums actual pounds, the distortion it produces is a pound
quantity, not a percentage — a ratio measures how proportionally unusual
an LA's spending is, a real fact about Oxford irrelevant to whether
single-pot mangles its gap. **Replaced outright**, not kept alongside:
`single_pot_bias_risk = |own precept − peer-group median own precept| ÷
own area-total bill`.

This independently reproduces, from a completely different starting point,
the same five LAs the original Westminster investigation found by hand —
Westminster (1.06), Wandsworth (1.03), Hammersmith and Fulham (0.44), City
of London (0.34), Kensington and Chelsea (0.29). Westminster and
Wandsworth form a genuinely distinct top tier (risk > 1.0 — their cash
divergence from peers exceeds their own entire discounted bill — roughly
2.4x the next-highest LA), so the caveat names two severity tiers rather
than one flat list of five. Checked directly, not assumed: Wandsworth's
computed gap is inflated the same way Westminster's is, not just its risk
score — both variants' percentage gaps sit within a few points of each
other (Variant 1: −64.7% vs −63.8%; Variant 2: −84.0% vs −75.2%).

**A NaN here cannot vindicate an LA, only fail to indict it.** Hartlepool,
County Durham and Blackpool get `NaN` (no real peer group), so this
statistic says nothing about them either way. What actually supports "the
Northern headline figures are largely clean" remains `shared_tier_share`
alone (14-16%, above) — a real, independent bound unaffected by this gap.
02_method.ipynb states this distinction explicitly rather than letting a
NaN read as a pass. See
`tests/test_engine.py::test_single_pot_bias_risk_reproduces_westminster_investigation_outlier_set`,
`test_westminster_and_wandsworth_are_a_severe_tier_above_the_rest`,
`test_wandsworth_gap_is_inflated_the_same_way_as_westminster`, and
`test_headline_northern_las_get_unmeasured_not_clean_risk_score`.

**A real bug was found and fixed while building this, not a modelling
choice.** CTSOP suppresses small band counts as blank cells (disclosure
control), parsed as `NaN`. The original liability code used `count or 0`
to default missing counts to zero — but `NaN` is truthy in Python, so
`nan or 0` evaluates to `nan`, and pandas' default skip-NaN group-sum then
silently collapsed an all-`NaN` group to exactly `0.0`. City of London —
one of the five LAs above — read as **£0 actual revenue for 2017-18
onward** before the fix; found only because its risk score looked wrong.
Fixed (`engine.build._safe_count`) and pinned with a regression test
(`test_ctsop_suppressed_band_counts_do_not_silently_zero_an_las_revenue`).
Scope checked directly: 13 (LA, year) cells across the whole headline
period, 2 LAs total (City of London, 2017-18 onward; Tamworth, 2009-10 to
2012-13) — small in aggregate, but not a coincidence that finding it
mattered exactly where a named outlier's number was being reported.

Both variants correctly show the headline direction throughout: Kensington
and Chelsea's cumulative gap is negative (paid less than a
value-proportional counterfactual) and Hartlepool's is positive (paid
more), under both variants, over the whole headline period.

## Phase 5: sensitivity sweep

Run against thresholds pre-registered before any sweep cell beyond the
base case was computed — see
[SENSITIVITY_PREREGISTRATION.md](SENSITIVITY_PREREGISTRATION.md) (committed
first) and [SENSITIVITY_RESULTS.md](SENSITIVITY_RESULTS.md) (results,
reported as a separate, dated document per the pre-registration's own
rule not to edit it after the fact). Headline: nothing crossed a failure
threshold, but the midpoint grid's predicted DIRECTION was backwards on
both ratios, which broke the "our midpoint choices are the conservative
corner" claim carried since Phase 3 — resolved explicitly (not deferred):
the base case (0.75, 1.5) is a central estimate with an
empirically-anchored range of roughly £206-232/dwelling/year for the
North East, sitting near the top of that range, not its floor. See
`config.py`'s Band A/H section, corrected in the same pass, for the full
account.

## Phase 6: does rate-setting already offset the freeze? (Variant 3)

The strongest form of the objection this whole repository exists to
test — IFS (2020) themselves note the cross-LA unfairness could in
principle be corrected through the funding settlement alone, without
touching council tax bands (see "Prior literature", above). Tested
directly with a real regression, not left as a caveat — full account and
every specification choice in `src/council_tax_freeze/regression/
variant3.py`'s module docstring and `notebooks/02_method.ipynb`
"Variant 3". Summary:

**Panel: 2015-16 to 2025-26, not the full headline window** — Core
Spending Power (the settlement control) doesn't exist as a concept before
2015-16; reconstructing an equivalent from Revenue Support Grant / early
Settlement Funding Assessment sources would need the Web Archive, not
pursued (same decision logic as the tier-data scoping in Phase 4, applied
to a genuinely different kind of gap - Variant 3 tests a BEHAVIOURAL
REGULARITY across 296 LAs and 11 years, not a cumulative total, so it
doesn't need to span the headline window to be informative).

**Settlement data source, found and parsed
(`parsers/settlement/parse.py`)**: MHCLG's Core Spending Power table for
the 2025-26 settlement republishes the whole 2015-16-2025-26 series in
one maintained file (same "live table" pattern as Band D), with real
`ons_code` rows. Checked, not assumed: each sheet has FOUR row tiers
(district/unitary/borough E06-E09 — the same 296-LA set as everywhere
else in this pipeline; county E10; a single Greater London Authority row;
a single Greater Manchester Combined Authority row from 2019-20) — the
upper tiers are apportioned to their 2025-vintage constituent LAs by
dwelling share, reusing `boundaries.precepting_groups.PRECEPTING_GROUP`
from Phase 4, because they are NOT a rounding error: Cambridgeshire's own
county row is 7.1x its five districts' own CSP combined, and the GLA's
own row is 31.7% of the 33 London boroughs' own rows combined — the same
"own precept is a small slice of the area total" structure Phase 4
quantified for Band D. A known, quantified gap: `PRECEPTING_GROUP`
reflects only the CURRENT tiering structure, so the 5 counties that
unitarised DURING this window (Dorset 2019, Northamptonshire 2021,
Cumbria/North Yorkshire/Somerset 2023) don't get their county CSP
apportioned for years before their own reorg — 206 of 3,256 LA-year
cells (6.3%), concentrated in ~25 predecessor LAs, understating their
settlement control for those specific cells. Documented, not fixed —
same decision framework as the Suffolk/Somerset 2019 CTSOP gap in Phase 4
(small, bounded, quantified).

**Specification**: year-on-year log growth in Band D rate, regressed on
`relative_hpi` (`hpi_factor_la / hpi_factor_national` — the exact same
quantity Variants 1/2 use, not a second definition), controlling for
year-on-year change in Core Spending Power per dwelling, LA and year
fixed effects, standard errors clustered by LA. Every choice — dependent
variable, contemporaneous vs lagged relative_hpi, the settlement control,
fixed effects, the era split — decided explicitly with the project owner
before running anything.

**Result: pooled significant, entirely a London effect, and the
diagnosis is the same mechanism Phase 4 already found.**

| | coefficient | 95% CI | p | n |
|---|---|---|---|---|
| Pooled, 296 LAs | -0.0243 | [-0.0318, -0.0167] | <0.0001 | 2,875 |
| Non-London, 263 LAs | -0.0063 | [-0.0143, +0.0017] | 0.125 | 2,545 |
| London only, 33 LAs | -0.0020 | [-0.0157, +0.0117] | 0.778 | 330 |

The decisive diagnostic (`regression.variant3.within_la_correlation`) is
not a regression p-value but the within-LA correlation between an LA's
own year-to-year relative appreciation and its own rate growth: **-0.57
in London, +0.08 in the rest of England** — not a weaker version of the
same relationship, effectively zero with the wrong sign outside London.
London boroughs' year-to-year relative_hpi swings are ~2.7x larger than
elsewhere (within-LA std 0.107 vs 0.039), giving them outsized leverage
on the pooled coefficient. Region-level average rate growth is nearly
flat across all nine regions (North East 4.27%, London 4.20%) - this was
never a simple cross-region gradient.

**Diagnosis, not just observation**: the mechanism producing London's
-0.57 is almost certainly the one Phase 4 already found and investigated
(the Westminster IFS-gate investigation, above) - boroughs holding their
own-tier rate artificially low on business-rate income and reserves, a
local fiscal anomaly uncorrelated with (not caused by) the valuation
freeze, which happens to correlate with London's high, volatile relative
appreciation. Confounding, not compensation. Two independent
investigations (a hand investigation in Phase 4, this regression's
robustness check in Phase 6) landed on the same mechanism from two
different directions.

**The finding: the IFS objection is tested and does not hold outside
London.** Across 263 non-London LAs and eleven years, no behavioural
regularity exists between an LA's relative appreciation and its rate
growth. The non-London specification is the PRIMARY result — a tight
null (CI narrow enough to rule out an economically meaningful offset),
not a noisy one. At the ceiling of what the non-London data supports
(`interpret_offset`, `bound="ceiling"` — computed for each LA as
whichever CI endpoint actually maximises the implied offset, since which
raw numerical bound is "favourable to the objection" flips sign for a
below-average-relative_hpi LA, a subtlety caught and fixed during
development, not assumed away): Hartlepool 1.7%, County Durham 1.7%,
Blackpool 2.3% of their measured Variant 1 gap.

**The pooled/London-driven coefficient must never be applied to a
non-London LA** — extrapolating London's -0.57 relationship onto
Hartlepool (measured relationship: +0.08) would be the single most
misleading number this analysis could produce. `interpret_offset` refuses
to compute it: it raises if the requested LA's region doesn't match the
regression's own subsample, rather than silently extrapolating across the
boundary the data itself drew — enforced in code
(`tests/test_variant3.py::test_pooled_result_cannot_be_applied_to_a_non_london_la`),
not just in the write-up. Applied instead to where the relationship IS
measured — Westminster and Kensington and Chelsea, both already flagged
with the single-pot exposure caveat in Phase 4 — the pooled ceiling
implies a sizeable apparent offset (27% and 36% of their measured gaps).
Reported prominently, not buried, with the confound diagnosis attached.

**Net effect on the headline: strengthens it.** Three independent lines
of evidence — the single-pot exposure bound (Phase 4), the Westminster
rate-anomaly investigation (Phase 4), and this regression's London/
non-London decomposition (Phase 6) — all land on London as the place
this pipeline's estimates are weakest, and none of them touch the North,
which is where the headline number comes from.

## Phase 7: presentation — where a technically correct finding could still mislead

Nothing in Phase 7 is a modelling change; every risk here is in how the
already-checked numbers are shown. Full account in
`notebooks/03_results.ipynb`.

**Aggregates (LA-total, region-total), added per explicit instruction
before the presentation layer was built.** `src/council_tax_freeze/
aggregates.py`. `engine.build`'s `variant1_gap`/`variant2_gap` are
ALREADY total-£ figures per (LA, year), not per-dwelling — confirmed, not
assumed: `test_revenue_neutrality_by_construction` already pins that gap
sums to ~0 across all 296 LAs every year, only possible for a real £
transfer figure. The cumulative LA-total is therefore `Σ_t gap[i,t]`,
built up year by year from each year's own real dwelling stock — NOT the
panel-average per-dwelling figure multiplied by a CURRENT dwelling count,
which would silently assume today's (larger) housing stock existed
throughout 2009-2026. `compute_naive_aggregate` exists only to measure
this error (6.0% for Hartlepool) and is pinned in
`tests/test_aggregates.py` so the two methods cannot later be
"simplified" together. A real bug found while building this: CTSOP never
switches Barnsley/Sheffield to their 2025 codes (unlike `engine.build`'s
own output, which always does), so an unaliased merge produced `inf`
per-dwelling figures for both — fixed with the same substitution already
used twice elsewhere in this pipeline for the same reason, pinned with a
regression test.

**"Per dwelling" is ambiguous unless every figure states whose rate and
over what base — found on review, not before publishing.** An early draft
of the README stated "Hartlepool has overpaid roughly £5,900 per dwelling
since 2009-10" next to the North East's £227.63/dwelling/year region
figure, reading as if they were the same quantity at different precision.
They are not: £227.63 is the North East's region-average rate across its
12 LAs, dwelling-year-weighted; Hartlepool's own rate is £365.52/dwelling/
year — the highest of the 12, despite carrying only 3.6% of the region's
dwelling stock, pulled down in the weighted average by larger, lower-rate
LAs (Newcastle £162/year, Sunderland £55/year). A THIRD figure briefly
appeared too: "region-average rate × 17 years" (≈£3,870), which is close
to but not equal to the correct "region cumulative total ÷ current
dwelling stock" figure (£3,677) — dropped entirely, not just labelled,
since it added a fourth confusable number for no benefit the other two
didn't already cover (see `aggregates.py`'s naive-vs-correct distinction,
above, which is the same underlying principle). Fixed throughout
(README, both notebooks, this file) by always stating explicitly which of
three DIFFERENT quantities a number is — a RATE (£/dwelling/year, region
average or one LA's own), a cumulative TOTAL (£, not per-dwelling at
all), or a cumulative total ÷ CURRENT dwelling stock (always said as
"per CURRENT dwelling") — and pinning the exact values of all four
headline figures (Hartlepool's own rate, the North East region-average
rate, and both cumulative-per-current-dwelling figures) with their full
definitions written into the assertion messages themselves in
`tests/test_aggregates.py::test_headline_figures_are_pinned_with_their_exact_definitions`,
so a future copy-edit that reuses one figure's wording for a different
quantity fails a test, not just a proofread.

**Region totals, 2009-10 to 2025-26 (Variant 1): North East +£4.7bn.**
**London: −£24.0bn across all 33 boroughs, of which −£15.8bn excludes the
five single-pot-exposed boroughs (Westminster, Wandsworth, Hammersmith and
Fulham, City of London, Kensington and Chelsea) — the second figure, not
the first, is the one to lead with**, since 34.2% of the headline −£24.0bn
sits in cells already flagged as inflated upper bounds, and a reader
should not have to do that subtraction themselves to find the load-bearing
number. The North East total carries no equivalent caveat (none of the
five flagged LAs are Northern; shared-tier exposure there is 14-16%;
Variant 3 found no rate-setting compensation effect to worry about for
non-London LAs either) — an asymmetry stated explicitly, not left for a
reader to infer.

**Framing, because a £-billions figure walks directly onto the turf of
the regional net-fiscal-transfer literature.** The claim is that
council tax's frozen 1991 valuation base has transferred billions from
low- to high-appreciation regions THROUGH THE TAX SYSTEM ITSELF, in the
opposite direction to the standard "London subsidises the regions"
narrative, and that this has never been counted in the regional-transfer
figures everyone cites — a missing ledger entry, not a competing ledger.
`03_results.ipynb` states explicitly that this is not a claim about
London's net fiscal position (which also depends on income tax, VAT,
corporation tax, and spending allocation, none of which this pipeline
touches) — the "but net transfers" rebuttal is answered by narrowing the
claim, not by ignoring it.

**Choropleth design — checked by rendering the map and looking at it, not
assumed to be correct from the code.** `src/council_tax_freeze/viz/
choropleth.py`. Boundary geometry: ONS "Local Authority Districts (May
2025) Boundaries UK BGC (V2)" (ArcGIS item
0b8528fb4132495181d82bb65c5e370a), same sourcing pattern as every other
reference file in this pipeline — confirmed the 296 English features match
`LAD_2025_CODES` exactly. Two real defects were caught only by rendering
and inspecting the output image, not by reading the code:

- **The colour direction was backwards.** Matplotlib's plain `"RdBu"`
  maps LOW values to red, HIGH to blue — the opposite of every legend
  label in this module ("red = overpaid" = positive = high). The first
  rendered map showed the North in blue and London in red. Fixed with
  `"RdBu_r"`.
- **A black hatch pattern is nearly invisible against the darkest cells**
  — exactly where the five flagged LAs sit, since they are also the most
  extreme values. Fixed two ways: a fixed, saturated border colour
  (`#39FF14`) that never blends into the diverging colour scale at either
  end, and a zoomed London inset (the flagged LAs are geographically tiny
  on an England-wide map regardless of colour), since inspecting a crop
  of the first version showed the hatching alone was not legible at that
  scale.

The colour scale itself is clipped to the 2nd/98th percentile of the
UNFLAGGED data, not the raw min/max — a handful of extreme values would
otherwise saturate the scale and make every other LA look pale, which
would happen to work against "lead with the North" even though it is a
purely cartographic problem, which is exactly why it is named here rather
than adjusted quietly.

**What was deliberately not built.** No choropleth of the 2000-09
backward-extension period — it uses imputed, not observed, band shares,
and sharing a colour scale or figure with the observed 2009-26 headline
period would present two different evidentiary standards in one visual
register. If ever added, `viz/choropleth.py`'s module docstring requires
it to be visually distinct (e.g. diagonal stripes across the whole map),
never share a colour scale with the headline map, and never appear
side-by-side implying equivalence.
