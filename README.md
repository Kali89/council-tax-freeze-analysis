# Council Tax Freeze Analysis

**Status: work in progress.** This README describes the intended scope and
framing. Headline figures will be filled in as the pipeline is built —
see `notebooks/03_results.ipynb` for current results, if present, before
citing anything from here.

## What this is

Council tax in England is levied on property bands fixed at 1 April 1991
valuations, never revalued since. Property values have diverged enormously by
region over that period — London and the South East appreciated far faster
than the North and Midlands — while the band multipliers that convert a
1991 valuation into a bill are compressed (Band H pays only 3x Band A, far
narrower than the true spread in property values).

This repository estimates, for each English local authority: **if council
tax bands had been periodically revalued since 2000, how much more or less
would that authority have paid, cumulatively, per dwelling?**

The output is a *redistributive gap* — the divergence between what an
authority actually paid and what a value-proportional benchmark would have
charged it — not a claim about subsidy, and not a claim about house prices.
See **Framing**, below, before drawing conclusions from any number in this
repo.

## Prior literature

This mechanism is not novel — a reader who knows the field will spot it
immediately if we don't say so ourselves.

**Adam, Hodge, Phillips & Xu (2020), *Revaluation and reform: bringing
council tax in England into the 21st century*, IFS Report R169** (funded
by the Nuffield Foundation) established that council tax has become more
regressive since 1991 because property values rose fastest where they were
already highest — an explicitly North/South story (London prices in
November 2019 were over six times their January 1995 level; barely three
times in the North East). Crucially, they also established that because
central government's funding allocation to local authorities still
references relative 1991 property values, "councils in the North East must
now levy more tax on a property worth (say) £250,000 than councils in
London, if both are to deliver the spending on services deemed necessary
by central government." That is our mechanism, stated in print in 2020.

**Breach (2024), Centre for Cities, "Towards fiscal devolution"** (in
*Devolution Solution*) independently models revaluation plus additional
bands and hits the same open-band imputation problem this repo solves in
`config.py` (cited as precedent for treating the open bands as something
to calibrate against real evidence rather than an unconstrained guess —
see DATA.md and SENSITIVITY_RESULTS.md for how our own choice was
checked). It also argues revaluation without fiscal devolution risks
delivering little fairness gain for large political cost.

**What this repo adds:** both of the above are snapshot counterfactuals —
what happens if bands are revalued *now*, with distributional analysis of
winners and losers on revaluation day. Neither publishes the cumulative
magnitude of the freeze's redistributive effect as a local-authority-level
time series. "London would pay £X more after revaluation" is a different
claim from "London has underpaid £Y per dwelling cumulatively since 2000."
This repo quantifies the accumulated stock, not the flow IFS and Centre for
Cities already described. See DATA.md's "Prior literature" section for the
full citations and how they shape the Variant 3 validation below.

## Framing — read this before the results

**The claim this analysis supports is narrow and descriptive:** because
council tax bands are frozen at 1991 values, local authorities in
high-appreciation areas have paid a declining share of national council tax
revenue relative to the market value of their housing stock. Cumulatively
since 2000, this amounts to some £X per dwelling in high-appreciation areas,
and some -£Y per dwelling in low-appreciation areas.

**What it does not support:**

- **Not a causal claim about house prices.** Low property taxes are
  capitalised into prices in principle, but the effect is small relative to
  supply constraints, interest rates, and (for London specifically) labour
  market dynamics. We do not estimate that channel and this analysis must
  not be read as implying it.
- **"Subsidy" is a normative word we avoid.** It presumes tax ought to track
  asset value — the premise of a property tax, and a defensible one, but a
  premise, not a finding. This repo prefers *redistributive gap* or
  *divergence from a value-proportional benchmark*.
- **Revenue-neutrality is a load-bearing assumption, tested (not assumed) by
  Variant 3 — and it strengthens the headline.** Did councils in
  high-appreciation areas actually set lower Band D rates as their implicit
  tax base grew? This is the strongest form of the objection IFS (2020)
  themselves raise: they note the cross-LA unfairness could in principle be
  corrected entirely through the funding settlement, without reforming
  council tax bands at all. Tested directly (panel regression, 2015-16 to
  2025-26, LA and year fixed effects): across 263 non-London LAs, no such
  relationship exists — a tight null, not a noisy one. A pooled coefficient
  across all 296 LAs *is* significant, but it is driven entirely by London
  (within-LA correlation −0.57 in London vs +0.08 elsewhere), and the
  mechanism is almost certainly the same business-rate/reserves anomaly
  already found and investigated for individual London boroughs earlier in
  the pipeline — confounding, not compensation. See DATA.md "Phase 6" and
  `notebooks/02_method.ipynb` "Variant 3" for the full account, including
  why the pooled coefficient must never be applied to a non-London LA.
- **Band-midpoint reconstruction is an approximation.** We do not observe
  1991 property values, only 1991 bands, several of which are open-ended
  (Band A below £40k, Band H above £320k with no upper bound). Midpoint
  imputation introduces error that is not random across regions. The
  headline figure is a **central estimate with an empirically-anchored
  range of roughly £206-232 per dwelling per year** for the North East
  (Price Paid calibration corners run through the actual model, not a
  demonstrated floor — an earlier belief that the base case sat at the
  conservative end of this range turned out to be wrong once the
  sensitivity sweep was run, and is corrected, not hidden, in
  `notebooks/02_method.ipynb` and SENSITIVITY_RESULTS.md).
- **The 1991-1995 HPI gap is real and unbridged.** Local-authority-level UK
  HPI data starts in January 1995, not April 1991. This analysis measures
  divergence in relative property values since January 1995, not April
  1991. That four-year gap is a named limitation, not something we've
  papered over — see DATA.md.

## Attribution

This analysis was prompted by [Tax Policy Associates' 2026 LVT
model](https://github.com/DanNeidle/lvt_model_2026) (MIT licence) and uses
two of the same public datasets (VOA CTSOP, MHCLG Council Tax levels). It
asks a different question — historical redistribution under the actual
frozen-band system, not a prospective land value tax — and is a separate
analysis, not a fork. No endorsement by Tax Policy Associates is implied.

## Data

See [`DATA.md`](DATA.md) for full provenance, what `download.py` fetches
automatically vs what requires manual download, and known data quality
issues per source. Raw data is not committed to this repository.

## Method

See [`notebooks/02_method.ipynb`](notebooks/02_method.ipynb) for the full
explanation, written for an intelligent non-specialist, with the objections
stated up front. In brief: three counterfactual variants, isolating (1) the
effect of the frozen 1991 valuation date, (2) the added effect of compressed
band multipliers, and (3) whether rate-setting behaviour already offsets
(1)-(2).

## Repository structure

```
notebooks/       Public-facing notebooks: 01_data, 02_method, 03_results
src/              Importable, tested pipeline modules — notebooks import from here
tests/            Parser validation, structural invariants, known-answer checks
data/             Raw + intermediate data (gitignored; see DATA.md)
outputs/          Tidy CSV (LA x year x variant -> gap) and choropleth maps
```

## Reproducing

```
uv sync
make all       # raw downloads -> parsed data -> counterfactuals -> maps
```

`make all` will pause with instructions wherever a dataset requires manual
download (see `DATA.md`) rather than failing silently on missing files.

## Licence

MIT — see [LICENSE](LICENSE). Underlying data remains under the Open
Government Licence / respective publishers' terms; see DATA.md.
