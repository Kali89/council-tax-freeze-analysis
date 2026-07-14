"""
Builds a (source LA, source year) -> [(2025 LA code, weight)] crosswalk by
walking each source unit forward through reorg_events.EVENTS, and applies it
to harmonise a year's LA-level data onto 2025 geography.

By construction there is no code path that resolves a boundary change without
either (a) an exact-match MERGE/RECODE event, or (b) a SPLIT event carrying an
explicit, cited Apportionment (see reorg_events.py). Anything else raises.
This is deliberate per the Phase 1 acceptance criteria: a merge that can't be
proven dwelling-count-preserving must fail loudly, not silently absorb into
whichever successor is convenient.
"""

from __future__ import annotations

import pandas as pd

from council_tax_freeze.boundaries.reorg_events import EVENTS, ChangeType, LAUnit, ReorgEvent


class UnmappedLocalAuthorityCode(Exception):
    """Raised when a source (code, name) at a given date matches no known unit and no known event."""


class AmbiguousBoundaryChange(Exception):
    """Raised when more than one event could apply to the same unit at the same date."""


def _matches(unit: LAUnit, code: str | None, name: str) -> bool:
    if unit.code is not None and code is not None:
        return unit.code == code
    return unit.name == name


def _find_applicable_events(code: str | None, name: str, as_of_date: str, events: tuple[ReorgEvent, ...]) -> list[ReorgEvent]:
    return [
        e
        for e in events
        if e.effective_date > as_of_date and any(_matches(o, code, name) for o in e.olds)
    ]


def resolve(
    code: str | None,
    name: str,
    as_of_date: str,
    events: tuple[ReorgEvent, ...] = EVENTS,
    year_totals: dict[str, float] | None = None,
    _weight: float = 1.0,
) -> list[tuple[str | None, str, float]]:
    """Resolve one (code, name) as of a date to a list of (2025_code, 2025_name, weight).

    `year_totals`: optional {old unit name -> that unit's total value for the
    year being resolved} - required only if the chain passes through a SPLIT
    event using `fixed_transfer` apportionment, to convert an absolute count
    into a fraction of that year's actual total. If such an event is hit and
    `year_totals` doesn't have the figure needed, raises rather than guessing.

    Terminal units (no further applicable event) are returned as-is - this
    function does not itself validate that a terminal code is a real, current
    2025 LA code; pass `known_2025_codes` to `build_crosswalk` for that check.
    """
    applicable = _find_applicable_events(code, name, as_of_date, events)
    if not applicable:
        return [(code, name, _weight)]
    if len(applicable) > 1:
        raise AmbiguousBoundaryChange(
            f"{name} ({code}) as of {as_of_date} matches {len(applicable)} events: "
            f"{[e.event_id for e in applicable]}. Each source unit must resolve unambiguously - "
            "add a disambiguating rule rather than picking one silently."
        )
    event = applicable[0]

    results: list[tuple[str | None, str, float]] = []
    if event.change_type in (ChangeType.RECODE, ChangeType.MERGE):
        new = event.news[0]
        results.extend(
            resolve(new.code, new.name, event.effective_date, events, year_totals, _weight)
        )
    elif event.change_type == ChangeType.SPLIT:
        appt = event.apportionment
        if appt.weights is not None:
            for new in event.news:
                w = appt.weights[new.name]
                results.extend(
                    resolve(new.code, new.name, event.effective_date, events, year_totals, _weight * w)
                )
        else:  # fixed_transfer
            old_name = event.olds[0].name
            if year_totals is None or old_name not in year_totals or not year_totals[old_name]:
                raise UnmappedLocalAuthorityCode(
                    f"{event.event_id}: fixed_transfer apportionment for '{old_name}' needs that "
                    f"year's actual total (via year_totals) to convert the fixed count into a "
                    f"weight - none was supplied. This is intentional: we will not guess a total."
                )
            total = year_totals[old_name]
            transferred_total = 0.0
            for new in event.news:
                count = appt.fixed_transfer.get(new.name, 0)
                w = count / total
                transferred_total += w
                if count:
                    results.extend(
                        resolve(new.code, new.name, event.effective_date, events, year_totals, _weight * w)
                    )
            # whichever new unit shares the old unit's name (or is otherwise the
            # continuing identity) gets the untransferred remainder
            remainder_w = 1.0 - transferred_total
            continuing = next((n for n in event.news if n.name == old_name), event.news[0])
            results.extend(
                resolve(continuing.code, continuing.name, event.effective_date, events, year_totals, _weight * remainder_w)
            )
    return results


def build_crosswalk(
    source_units: list[tuple[str | None, str, str]],  # (code, name, as_of_date)
    known_2025_codes: set[str] | None = None,
    year_totals: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Build the full crosswalk for a batch of (code, name, as_of_date) source units.

    Returns columns: source_code, source_name, source_date, target_code,
    target_name, weight. Raises UnmappedLocalAuthorityCode if a resolved
    terminal code isn't in `known_2025_codes` (when supplied).
    """
    rows = []
    for code, name, as_of_date in source_units:
        for target_code, target_name, weight in resolve(code, name, as_of_date, year_totals=year_totals):
            if known_2025_codes is not None and target_code not in known_2025_codes:
                raise UnmappedLocalAuthorityCode(
                    f"{name} ({code}) as of {as_of_date} resolved to '{target_name}' ({target_code}), "
                    "which is not in the supplied set of known 2025 LA codes. Either the chain is "
                    "incomplete or the source unit was misidentified - not something to paper over."
                )
            rows.append(
                {
                    "source_code": code,
                    "source_name": name,
                    "source_date": as_of_date,
                    "target_code": target_code,
                    "target_name": target_name,
                    "weight": weight,
                }
            )
    return pd.DataFrame(rows)


def harmonise(
    df: pd.DataFrame,
    code_col: str,
    name_col: str,
    date_col: str,
    value_cols: list[str],
    known_2025_codes: set[str] | None = None,
    year_totals: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Apply the crosswalk to a dataframe, apportioning value_cols by weight
    and aggregating to 2025-vintage codes. `date_col` should hold the as-of
    date for each row (e.g. the financial year's start date)."""
    source_units = list(
        df[[code_col, name_col, date_col]].drop_duplicates().itertuples(index=False, name=None)
    )
    crosswalk = build_crosswalk(source_units, known_2025_codes=known_2025_codes, year_totals=year_totals)

    merged = df.merge(
        crosswalk,
        left_on=[code_col, name_col, date_col],
        right_on=["source_code", "source_name", "source_date"],
        how="left",
    )
    if merged["weight"].isna().any():
        missing = merged.loc[merged["weight"].isna(), [code_col, name_col, date_col]].drop_duplicates()
        raise UnmappedLocalAuthorityCode(f"No crosswalk weight found for:\n{missing}")

    for c in value_cols:
        merged[c] = merged[c] * merged["weight"]

    return merged.groupby(["target_code", "target_name"], as_index=False)[value_cols].sum()
