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
| 1 | MHCLG Council Tax levels set by local authorities, annual releases, 2000-01 to 2025-26 | [gov.uk statistics releases](https://www.gov.uk/government/collections/council-tax-statistics) | Band D council tax (total, excl. parish precepts) per LA per year | Automatic where a stable URL pattern exists; manual instructions printed otherwise (early-2000s releases move around) |
| 2 | VOA Council Tax: Stock of Properties (CTSOP), annual | [gov.uk statistics](https://www.gov.uk/government/collections/council-tax-stock-of-properties-statistics) | Band distribution (dwelling counts per band per LA per year) | Automatic where linked directly; manual otherwise |
| 3 | UK House Price Index, full file | [gov.uk HPI downloads](https://www.gov.uk/government/statistical-data-sets/uk-house-price-index-data-downloads) | LA-level appreciation series, Jan 1995 onward | Automatic (single large CSV) |
| 4 | ONS LAD boundaries (May 2025) + historic LAD change lookups | [ONS Open Geography Portal](https://geoportal.statistics.gov.uk/) | Boundary harmonisation to 2025 geography; mapping | Automatic via ONS API where available; manual for lookups not exposed via API |
| 5 | ONS mid-year population / dwelling stock estimates | [ONS](https://www.ons.gov.uk/) | Per-dwelling and per-capita denominators | Automatic |
| 6 | HM Land Registry Price Paid Data — 1995 and 1996 annual files only | [gov.uk price-paid downloads](https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads) | One-off calibration check on the Band A/H midpoint imputation (not used in the main pipeline) | Automatic — annual files are small; we do not use the multi-GB complete file |
| 7 | MHCLG local government finance settlement data (Revenue Support Grant / Settlement Funding Assessment / Core Spending Power, by vintage) | [gov.uk local government finance statistics](https://www.gov.uk/government/collections/local-government-finance-statistics) | Control variable for the Variant 3 regression (did councils adjust rates as their implicit base grew?) | Manual — no stable single series across the full period; instructions printed |
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

**MHCLG Band D releases (#1).** Sheet naming, column layout, and LA coding
change between years — there is no single reader that works across all ~26
vintages. Each vintage gets its own parser in
`src/council_tax_freeze/parsers/band_d/`, all validated against the
publisher's own headline national average Band D figure for that year.
A parser that can't reproduce the published national average fails loudly
rather than silently producing a plausible-looking wrong number.

**CTSOP (#2).** Some vintages may carry Barnsley/Sheffield under their
pre-2025 codes (E08000016/E08000019 rather than E08000038/E08000039) — see
the boundary harmonisation note below. This is a genuine small
partial-territory transfer (12 dwellings), not a South Yorkshire-wide
reorganisation — an earlier draft of this file wrongly described it as a
"2023 South Yorkshire unitary change." Handled by the boundary
harmonisation module (Phase 1), not patched ad hoc in the CTSOP parser.

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

**Price Paid calibration slice (#6).** Used only to sanity-check the
Band A/H midpoint imputation ratios (see `notebooks/02_method.ipynb`) in a
handful of local authorities. 1995-97 sale prices are deflated to an
April-1991-equivalent using a single *national* HPI factor — a much smaller,
self-contained assumption than doing this at LA level for the whole pipeline,
and used only as a spot check, not as an input to the main counterfactual.

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
