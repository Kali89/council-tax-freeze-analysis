# Sensitivity pre-registration (Phase 5)

Written and committed **before** the sensitivity sweep is run. The purpose of
a sensitivity sweep is to show the headline is robust and the base case is
conservative — which is exactly the answer everyone wants, and exactly the
condition under which nobody scrutinises the result. A clean sweep is the
least informative possible outcome and the easiest one to produce by
accident (by setting thresholds loose enough, post hoc, that nothing can
fail). This document states numeric, falsifiable thresholds first. The
sweep is run after this file is committed, not before. If the sweep result
changes what looks reasonable in hindsight, that becomes a new, dated
document — this file is not edited to fit the answer.

## The metric being tested

**Population-weighted mean Variant 1 gap per dwelling per year**, summed
over the whole headline period (2009-10 to 2025-26, 17 years), for two ONS
regions (`boundaries/regions.py`, real ONS Dec-2024 lookup):

```
metric(region) = Σ_{LA in region, year in headline} variant1_gap[LA, year]
                 ────────────────────────────────────────────────────────
                 Σ_{LA in region, year in headline} all_properties[LA, year]
```

Variant 1 only (the headline variant — see 02_method.ipynb "Variant 1 is
the headline"). Denominator is dwelling-*years* (each LA's dwelling count
counted once per headline year), not a single-year snapshot, so the metric
is directly interpretable as "extra/less pounds paid per dwelling per year,
averaged over the whole period."

**Current base-case value, computed today, before any sensitivity
parameter is touched:**

| Region | Cumulative V1 gap | Dwelling-years | £ / dwelling / year |
|---|---|---|---|
| North East | +£4,735,657,386 | 20,803,840 | **+£227.63** |
| London | −£23,981,648,123 | 60,725,070 | **−£394.92** |

North East is the primary anchor for these thresholds — it is the region
the headline claim rests on and the one flagged for the hardest stress
test. London is tracked alongside it because it is exposed to a different
risk (the single-pot bias, already quantified separately — this sweep is
about parameter uncertainty, not that mechanism).

## Axis 1: the midpoint grid (BAND_A_RATIO × BAND_H_RATIO, 12 combinations)

**Mechanical prediction, derived from the reallocation formula before
running anything**, not fitted to a result: `cf[i] = national_actual_revenue
× tax_base[i] / Σ_j tax_base[j]`. Band A stock is concentrated in the North
East; Band H stock is concentrated in London/the South.

- Raising `BAND_A_RATIO` raises Band A's assumed value, which raises
  Northern LAs' tax-base *share* (Band A is a large fraction of their own
  stock) more than it raises the national total — this raises their `cf`,
  which **shrinks** their measured gap. So the North East metric should be
  **monotonically decreasing in `BAND_A_RATIO`**.
- Raising `BAND_H_RATIO` raises Band H's assumed value, which raises
  Southern LAs' tax base and therefore the national total, without
  changing Northern LAs' own tax base — this *dilutes* Northern LAs'
  share, lowering their `cf`, which **grows** their measured gap. So the
  North East metric should be **monotonically increasing in
  `BAND_H_RATIO`**.

**Threshold 1a — monotonicity (hard, structural).** The North East metric
must be monotonic in each parameter, holding the other fixed, across all 4
`BAND_H_RATIO` values and all 3 `BAND_A_RATIO` values. Any reversal is
either a genuinely interesting nonlinearity (the compressed-multiplier
curve is piecewise, so a reversal near a band boundary is conceivable) or a
bug. **Report either way** — do not silently smooth over a reversal by
picking a different summary statistic.

**Threshold 1b — sign (hard failure if crossed).** The North East metric
must stay **positive** and the London metric must stay **negative** across
*all 12* combinations, including the most adverse cell for each region
(North East minimised at `BAND_A_RATIO=0.9, BAND_H_RATIO=1.25`; London's
magnitude minimised at the mirror-opposite cell). If either sign flips
anywhere in the grid, the headline claim itself — not just a caveat —
needs to be revisited.

**Threshold 1c — the most-adverse North East cell must stay economically
non-trivial.** At `BAND_A_RATIO=0.9, BAND_H_RATIO=1.25` (the combination
predicted to minimise the North East gap), the metric must remain **above
£50/dwelling/year**. Positive-but-negligible would mean the entire
headline number depends on a specific, non-robust parameter choice — a
materially worse problem than mislabelling which corner is "conservative."

**Threshold 1d — the most-aggressive North East cell must not blow past a
sane ceiling.** At `BAND_A_RATIO=0.6, BAND_H_RATIO=3.0` (predicted
maximum), the metric should not exceed roughly **2.5x the base case**
(≈£570/dwelling/year). A larger jump would mean the reported base case sits
in an unrepresentatively thin slice of the plausible range, not a
defensibly central-to-conservative one.

**A correction to make regardless of what the sweep shows.** `config.py`
currently calls the base case (0.75, 1.5) "the conservative corner of the
plausible range." Given the derivation above, that is imprecise on the
`BAND_A_RATIO` axis specifically: 0.75 sits in the *middle* of its grid
(0.6/0.75/0.9), and 0.9 — not 0.75 — is the value that minimises the
measured gap within the swept grid. The actual basis for calling 0.75
conservative is the Price Paid calibration check (Easington's empirical
Band A ratio, 0.64, is *below* 0.75, implying the true Northern gap is
probably larger than what 0.75 reports), not grid-extremity. The writeup
must say this precisely — "conservative relative to the calibration
evidence," not "the extreme corner of the swept grid" — independent of
whatever the sweep itself shows.

## Axis 2: collection factor (0.78 / 0.83 / 0.88)

`COLLECTION_FACTOR` is applied as one uniform scalar to every LA's actual
revenue (`engine/build.py`). Because it multiplies both `actual[i]` and
(via `national_actual_revenue`) every `cf[i]` by the identical constant,
`gap[i] = C × (Z[i] − Y[i])` for a `C`-independent `Z, Y` — the gap is
**exactly linear in `C`** by construction, not approximately. This is an
algebraic identity, not a modelling-robustness question: this axis cannot
meaningfully test whether the finding "survives" a different collection
assumption, only whether the code does what `config.py` claims.

**Threshold 2 (bug detector, not a robustness check).** `gap(0.78) /
gap(0.83)` must equal `0.78 / 0.83 = 0.93976...` and `gap(0.88) /
gap(0.83)` must equal `0.88 / 0.83 = 1.06024...`, both to at least 3
decimal places. **Any deviation beyond floating-point tolerance means
`COLLECTION_FACTOR` is not being applied uniformly somewhere in the
pipeline** (e.g. leaking into the CTSOP or HPI stage asymmetrically) — a
bug to find and fix, not a sensitivity finding to report as "the headline
is collection-factor-robust." State this plainly in the writeup rather
than presenting a null result on this axis as if it were informative about
the real world.

## Axis 3: HPI geography (LA-level vs region-level)

No closed-form prediction here — this is the axis with genuine
uncertainty, because it depends on how much each LA's own HPI trajectory
diverges from its region's average, which isn't derivable from the
formula alone. Qualitative expectation, stated before running: London has
substantial *within-region* heterogeneity (Westminster/Kensington and
Chelsea plausibly appreciated faster than the London average), so
region-level HPI should **dampen** the London-side effect more than the
North East side (North East is a smaller, more internally homogeneous
region).

**Threshold 3a (hard failure).** Neither region's sign may flip when
switching from LA-level to region-level HPI.

**Threshold 3b.** The North East metric must not fall by more than **50%**
under region-level HPI (i.e. must stay above ≈£114/dwelling/year). The
North East figure is the one being reported as most robust and least
entangled with other caveats (unlike London, which already carries the
single-pot flag) — if the LA-vs-region HPI choice alone moves it by more
than half, that is a first-order finding, not a footnote, and must be
reported as such regardless of whether it counts as a "failure."

## Axis 4: revaluation frequency (continuous / 5-year / 10-year)

Periodic revaluation holds the counterfactual valuation flat between
refresh points, lagging continuous relative-value tracking — this should
**dampen**, not reverse, the measured effect. Predicted: North East metric
monotonically non-increasing in magnitude from continuous → 5-year →
10-year.

**Threshold 4a (hard failure).** Sign must not flip at either 5-year or
10-year frequency.

**Threshold 4b.** The North East metric at 10-year frequency must not fall
by more than **40%** from the continuous base case (must stay above
≈£137/dwelling/year). Real English revaluation practice is, in effect,
"never" (34+ years and counting) — continuous is already the *most
favourable* assumption for showing a large effect from infrequent
revaluation generically, as opposed to the specific 1991 freeze. If even a
modest 10-year periodic assumption erases more than 40% of the effect,
that undercuts the claim that the freeze specifically — not merely
infrequent revaluation as a category — is what drives the result, and
must be reported as a substantive qualification, not smoothed into "robust
to revaluation-frequency assumptions."

## What "this doesn't survive" means, stated once, plainly

The finding does not survive if any of: (a) the North East or London sign
flips anywhere in the 12-cell midpoint grid; (b) either region's sign
flips under region-level HPI or under 5- or 10-year revaluation; (c) the
North East metric drops below ~£50/dwelling/year at the most adverse
midpoint cell; (d) the North East metric drops by more than 50% under
region-level HPI or more than 40% under 10-year revaluation. Anything
inside these bounds is a real, reportable result. Anything outside them —
including a movement that is large but does not technically cross a
threshold — gets reported as "moved more than expected," per the explicit
instruction this document is responding to: report what moves the number,
not just whether it crosses a pre-agreed line.
