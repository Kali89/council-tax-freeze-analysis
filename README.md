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
- **Revenue-neutrality is a load-bearing assumption**, tested (not assumed)
  by Variant 3: did councils in high-appreciation areas actually set lower
  Band D rates as their implicit tax base grew, which would make the
  redistribution smaller than Variants 1-2 imply on their own? See
  `notebooks/02_method.ipynb` and the Variant 3 regression results for the
  honest answer, including if it undermines the headline.
- **Band-midpoint reconstruction is an approximation.** We do not observe
  1991 property values, only 1991 bands, several of which are open-ended
  (Band A below £40k, Band H above £320k with no upper bound). Midpoint
  imputation introduces error that is not random across regions — see
  `notebooks/02_method.ipynb` for why the chosen imputation is a
  *conservative* corner of the plausible range, and the sensitivity grid
  that demonstrates it.
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
