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

## Known issues by dataset

**MHCLG Band D releases (#1).** Sheet naming, column layout, and LA coding
change between years — there is no single reader that works across all ~26
vintages. Each vintage gets its own parser in
`src/council_tax_freeze/parsers/band_d/`, all validated against the
publisher's own headline national average Band D figure for that year.
A parser that can't reproduce the published national average fails loudly
rather than silently producing a plausible-looking wrong number.

**CTSOP (#2).** Some vintages use pre-reorganisation LA codes — e.g. the
2023 South Yorkshire unitary changes mean older releases carry Barnsley and
Sheffield under codes that predate the current ones. These are handled by
the boundary harmonisation module (Phase 1), not patched ad hoc in the
CTSOP parser.

**UK HPI (#3).** LA-level series start January 1995, not April 1991 — see
the README's Framing section. A handful of LAs have suppressed or
sparse series due to low transaction volumes (City of London, Isles of
Scilly, and a few others in some periods); these fall back to their region's
HPI series regardless of which HPI-geography sensitivity variant is active,
since there is no LA-level alternative to fall back to.

**Boundary harmonisation (#4).** No single ONS lookup spans 2000-2025.
The crosswalk is built by chaining vintage-to-vintage lookups across four
reorganisation waves: 2009 (Cornwall, Wiltshire, Shropshire, etc. unitary),
2019 (Buckinghamshire, Dorset/BCP unitary), 2020 (West Suffolk, West
Northamptonshire etc.), and 2023 (North Yorkshire, Somerset, Cumbria split
into Cumberland/Westmorland). Where an old LA maps to more than one new LA
or vice versa, dwelling counts are apportioned rather than duplicated or
dropped — tested in `tests/` to confirm total dwelling counts are preserved
through the chain.

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
