# Sensitivity sweep results, against the pre-registered thresholds

Reports the Phase 5 sweep against [SENSITIVITY_PREREGISTRATION.md](SENSITIVITY_PREREGISTRATION.md),
committed before any grid point beyond the base case was computed. That
file is **not** edited to fit what follows — this is a separate, dated
document, per its own stated rule. Where the pre-registered *prediction*
turned out wrong, that is reported as a finding in its own right, not
quietly corrected.

All results computed by `src/council_tax_freeze/sensitivity/sweep.py`,
pinned by `tests/test_sensitivity.py` (10/10 passing). Base case: North
East +£227.63/dwelling/year, London −£394.92/dwelling/year (Variant 1,
dwelling-year-weighted, 2009-10 to 2025-26).

## Axis 1: midpoint grid (12 cells) — thresholds pass, but the predicted *direction* was wrong

| band_a_ratio | band_h_ratio | North East | London |
|---|---|---|---|
| 0.60 | 1.25 | 201.81 | −388.46 |
| 0.60 | 1.50 | 200.94 | −384.55 |
| 0.60 | 2.00 | 200.23 | −381.32 |
| 0.60 | 3.00 | 199.73 | −379.05 |
| 0.75 | 1.25 | 228.48 | −398.85 |
| **0.75** | **1.50 (base)** | **227.63** | **−394.92** |
| 0.75 | 2.00 | 226.93 | −391.69 |
| 0.75 | 3.00 | 226.44 | −389.41 |
| 0.90 | 1.25 | 287.27 | −421.37 |
| 0.90 | 1.50 | 286.46 | −417.41 |
| 0.90 | 2.00 | 285.79 | −414.16 |
| 0.90 | 3.00 | 285.31 | −411.86 |

**Threshold 1b (sign, hard failure if crossed): PASS.** North East is
positive in all 12 cells (min 199.73); London is negative in all 12
(max −379.05).

**Threshold 1c (worst cell > £50): PASS, by a wide margin.** True minimum
across the grid is £199.73 — 4x the floor.

**Threshold 1d (best cell < 2.5x base): PASS, not close.** True maximum is
£287.27 — 1.26x base, nowhere near the 2.5x ceiling.

**Threshold 1a (monotonicity, hard/structural): PASS — but in the
*opposite* direction from the pre-registered prediction on both axes.**
Pre-registered: North East increasing in `BAND_A_RATIO`... no — pre-
registered: North East **decreasing** in `BAND_A_RATIO`, **increasing** in
`BAND_H_RATIO`. Actual: North East is monotonically **increasing** in
`BAND_A_RATIO` (200.94 → 227.63 → 286.46 at `BAND_H_RATIO=1.5`) and
monotonically **decreasing** in `BAND_H_RATIO` (228.48 → 227.63 → 226.93 →
226.44 at `BAND_A_RATIO=0.75`, though this second effect is small, under
1% end to end). Monotonicity itself — the actual structural claim — holds
exactly, checked over all 4×3 fixed-slices; only the *sign* of my a priori
reasoning was backwards.

**Why the prediction was wrong, worked out after seeing the result (not
before — flagged as such).** The pre-registered reasoning treated the
compressed-multiplier curve as fixed and asked only how a changed midpoint
moves the *input* to it. It isn't fixed: `_multiplier_control_points`
rebuilds the whole curve from the same `band_a_ratio`/`band_h_ratio` being
swept, because the curve is defined to pass through each band's real
statutory multiplier *at that band's own midpoint*. Raising
`BAND_A_RATIO` moves both the value fed into the curve **and** the curve's
own anchor point simultaneously — a LA whose relative HPI trajectory sits
close to the national average lands close to that anchor almost
regardless of the ratio, so the ratio's effect runs almost entirely
through LAs whose relative HPI diverges from the national average (which,
by the thesis this whole repository is testing, is exactly what
Northern LAs do), via the local slope of the curve near Band A rather
than a simple "more assumed value → bigger tax base" level effect. That
interaction wasn't in the pre-registered mechanical reasoning, and it
should have been — this is a modelling subtlety worth being explicit
about, not a footnote.

**Resolved directly, jointly, not axis-by-axis: is the base case still a
floor on the North/South gap?** The correction already flagged above
(that 0.75 sits in the *middle* of its own grid, not the extreme) stands,
but the deeper question is whether 0.75/1.5 still sits at or below the
minimum of the *plausible* parameter region — not the swept grid's
arbitrary endpoints (0.6/0.9, 1.25/3.0), but the region the Price Paid
calibration actually supports. That calibration has two trusted corners
(thousands of sales each, not the 1-3-sale Blackpool-H/Easington-H
figures): Easington (0.64) and Blackpool (0.77) for Band A; Westminster
(1.78) and Kensington and Chelsea (2.06) for Band H. Run through the
actual engine at all four corners of that empirical box — not
interpolated from the swept grid, computed directly:

| band_a_ratio | band_h_ratio | source | North East £/dwelling/year |
|---|---|---|---|
| 0.64 | 1.78 | Easington, Westminster | 206.07 |
| 0.64 | 2.06 | Easington, Kensington and Chelsea | **205.79** |
| 0.77 | 1.78 | Blackpool, Westminster | **232.30** |
| 0.77 | 2.06 | Blackpool, Kensington and Chelsea | 232.03 |

Since North East is monotonically increasing in `BAND_A_RATIO` and
(weakly) decreasing in `BAND_H_RATIO`, the box's true minimum is at
(0.64, 2.06) = £205.79 and its true maximum at (0.77, 1.78) = £232.30 —
both computed directly, not assumed from the corners' individual axis
behaviour. **The base case (£227.63) sits inside this range, but 82% of
the way from floor to ceiling — near the top, not the bottom.**

**We lose the floor framing.** The claim that has been carried since the
Price Paid calibration section was written — "our midpoint choices
understate the gap, so the reported figure is a floor" — depended
entirely on the predicted direction, which measured backwards. The Price
Paid calibration itself is unaffected: it is empirical evidence about
where the true Band A/H tails sit, independent of how the model responds
to the parameter, and it still constrains the plausible range to roughly
£206-232/dwelling/year for the North East. What it no longer supports is
that our specific choice sits at that range's conservative edge. **The
finding this pipeline is entitled to report is a central estimate
(£227.63/dwelling/year) with an empirically-anchored range of
£206-232, not "at least £206."** `config.py`, DATA.md, README.md and
`notebooks/02_method.ipynb` have all been corrected in this same commit —
not deferred, per the instruction this section responds to.

## Axis 2: collection factor — exact algebraic identity confirmed, as predicted

| collection_factor | North East | London | ratio vs base |
|---|---|---|---|
| 0.78 | 213.92 | −371.13 | 0.939759 (exact) |
| 0.83 (base) | 227.63 | −394.92 | 1.000000 |
| 0.88 | 241.35 | −418.71 | 1.060241 (exact) |

**Threshold 2: PASS, to 6 decimal places**, both regions. Confirms
`COLLECTION_FACTOR` is applied as a pure uniform scalar with no leak
elsewhere in the pipeline — this axis was pre-registered as a bug
detector, not a substantive robustness question, and it detected no bug.

## Axis 3: HPI geography (LA-level vs region-level) — moved far less than expected

| | North East | London |
|---|---|---|
| LA-level (base) | 227.63 | −394.92 |
| Region-level | 228.82 | −398.44 |
| change | **+0.5%** | **+0.9%** (more negative) |

**Threshold 3a (sign): PASS.** **Threshold 3b (North East > 50% of base):
PASS, trivially** — the actual movement (0.5%) is two orders of magnitude
inside the 50% threshold.

**This is the axis that moved least, and by far — worth flagging
precisely because I predicted the opposite.** The pre-registered
qualitative expectation was that region-level HPI would *meaningfully
dampen* London specifically, on the reasoning that Westminster/Kensington
and Chelsea plausibly diverge a lot from the London regional average. The
actual movement (+0.5% / +0.9%) is a near-null result for both regions.
**A <1% movement does not confirm that prediction — it shows something
weaker and different: that the finding is not an artefact of using
LA-level HPI granularity.** That is a real, useful robustness result, but
it is not the result predicted, and the write-up says the weaker thing
rather than letting a null quietly get promoted to a confirmation.

## Axis 4: revaluation frequency — matched the prediction exactly, the one axis that did

| frequency | North East | change vs continuous |
|---|---|---|
| continuous (base) | 227.63 | — |
| 5-year | 211.32 | −7.2% |
| 10-year | 190.60 | −16.3% |

**Threshold 4a (sign): PASS.** **Threshold 4b (10-year > 60% of base):
PASS, comfortably** — 190.60 is 83.7% of base, well inside the 40%-drop
ceiling. **Monotonic dampening as predicted**: continuous > 5-year >
10-year, exactly the shape argued for (periodic revaluation lags
continuous tracking) before running anything. This is the one axis where
the a priori mechanical reasoning and the empirical result agree, which
is worth noting alongside the two axes where they didn't — matching a
prediction is not more "correct" just because it was predicted; it's
reported the same way, checked the same way.

## What actually matters here, stated directly

Not "nothing crossed a threshold" — that is the least interesting result
this sweep could have produced, and the easiest to get by accident. Two
things matter more:

1. **The midpoint grid's predicted direction was backwards on both
   ratios**, and that is a real finding about the model, not a rounding
   error. It broke the framing this whole project has leaned on since
   the Price Paid calibration was first run: that our midpoint choices
   are conservative and the reported gap is therefore a floor. Resolved
   jointly above, computed directly rather than assumed: **the base case
   is not at or below the minimum of the empirically-plausible parameter
   region — it sits at 82% of the way to that region's ceiling.** The
   claim this pipeline is entitled to make changes from "at least
   £206/dwelling/year" to "a central estimate of £227.63/dwelling/year,
   with an empirically-anchored range of roughly £206-232." That
   correction has been made everywhere the old claim appeared
   (`config.py`, DATA.md, README.md, `notebooks/02_method.ipynb`), not
   left as a follow-up.
2. **The HPI-geography axis produced a near-null result (<1% movement),
   which is a weaker and different finding than the meaningful
   London-specific dampening that was predicted.** It shows the headline
   is not an artefact of LA-level HPI granularity — real, worth keeping —
   but it does not confirm the predicted mechanism, and is not written up
   as if it does.

Both are reported as findings, not smoothed into "robustness confirmed."
Separately, and now correctly subordinate to the above: no sign flip
anywhere, worst midpoint-grid cell still £199.73/dwelling/year, and the
largest observed movement anywhere in the whole sweep (16.3%, 10-year
revaluation) still leaves the finding at 84% of its base-case size. That
the finding survives every swept axis is real and was not fitted to
arrive at that answer after the fact — it is simply not the headline of
this document.
