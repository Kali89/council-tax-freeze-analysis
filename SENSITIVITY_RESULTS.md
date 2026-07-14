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

**Consequence for the "conservative corner" language.** The correction
already flagged in the pre-registration (that 0.75 sits in the *middle*
of its own grid, not the extreme) stands. But the specific claim I made
about which direction is more conservative was built on the same wrong
mechanical reasoning and is therefore also wrong: raising `BAND_A_RATIO`
toward 0.9 does not shrink the reported effect, it **grows** it (286.46
vs base's 227.63). So 0.75 is not "less conservative than the true
extreme (0.9)" as I wrote before running the sweep — if anything, 0.9
would have produced a *larger* headline claim, and 0.75 sits closer to
the smaller (0.6-side) end of the axis's actual effect range than my
pre-registered note implied. `config.py`'s "conservative corner" comment
needs revising to reflect the *measured* direction, not the predicted
one — tracked as a follow-up, not done silently as part of this report.

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
actual movement is close to a null result for both regions. Read
literally, this says LA-level HPI granularity is not doing much
independent work in this pipeline — the North East and London *regional*
trends are close enough to their constituent LAs' own trends that
swapping one for the other barely moves the headline metric. That is
itself informative (the finding is not an artefact of using fine-grained
HPI data), but it means my stated reason for expecting a bigger London
effect specifically was wrong, and should not be repeated in the
write-up as if confirmed.

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

## What moved more than expected, stated directly (per the instruction this responds to)

Nothing crossed a failure threshold. Two things moved by more than the
pre-registered reasoning anticipated, in opposite directions:

- **The midpoint grid's direction was flipped**, not just "more than
  expected" — a genuine miss in the mechanical model, corrected above.
  The numeric thresholds (which didn't depend on getting the direction
  right, only on bounding the actual min/max) still hold.
- **The HPI-geography axis moved far less than expected** — a near-null
  result where a real, if modest, effect was anticipated.

Both are reported as findings, not smoothed into "robustness confirmed."
The overall conclusion — the headline North East effect survives every
swept axis, with the largest observed movement (16.3%, 10-year
revaluation) still leaving the finding at 84% of its base-case size — is
real and was not fitted to arrive at that answer after the fact.
