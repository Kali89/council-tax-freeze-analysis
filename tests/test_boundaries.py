"""
Tests written against the Phase 1 acceptance criteria (see project log), not
retrofitted to whatever the code happens to produce:

  1. Crosswalk weights sum to 1.0 per source unit (tolerance 1e-9).
  2. Dwelling counts are preserved EXACTLY through a MERGE (tolerance 0).
  3. An unknown/unmapped LA code raises rather than silently drops.
  4. A SPLIT event is structurally impossible to construct without an
     explicit, cited Apportionment (enforced in reorg_events.py, not just
     convention).
  5. Harmonised national totals match published figures - deferred until
     Phase 2 real CTSOP data exists; skipped with a clear reason, not
     invented now to match placeholder code.
  6. Every LA identity valid at any point in 2000-01 to 2025-26 resolves to
     exactly one 2025 successor, zero unmapped, zero ambiguous, reported
     per financial year - see test_full_2000_2025_coverage below.
"""

import pytest

from council_tax_freeze.boundaries.crosswalk import (
    AmbiguousBoundaryChange,
    UnmappedLocalAuthorityCode,
    build_crosswalk,
    harmonise,
    resolve,
)
from council_tax_freeze.boundaries.lad_2025 import LAD_2025_CODES
from council_tax_freeze.boundaries.precepting_groups import PRECEPTING_GROUP
from council_tax_freeze.boundaries.reorg_events import (
    EVENTS,
    Apportionment,
    ChangeType,
    LAUnit,
    ReorgEvent,
)

import pandas as pd


# ---------------------------------------------------------------------------
# 1. Weights sum to 1.0
# ---------------------------------------------------------------------------


def test_cornwall_districts_each_resolve_with_full_weight():
    for district in ["Penwith", "Kerrier", "Carrick", "Restormel", "Caradon", "North Cornwall"]:
        results = resolve(None, district, "2000-01-01")
        total_weight = sum(w for _, _, w in results)
        assert total_weight == pytest.approx(1.0, abs=1e-9)
        assert results == [("E06000052", "Cornwall", pytest.approx(1.0))]


def test_barnsley_sheffield_split_weights_sum_to_one():
    year_totals = {"Barnsley": 100_000}
    results = resolve("E08000016", "Barnsley", "2024-01-01", year_totals=year_totals)
    total_weight = sum(w for _, _, w in results)
    assert total_weight == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 2. Chaining across waves (Somerset: 2019 merge -> 2023 merge)
# ---------------------------------------------------------------------------


def test_somerset_chains_across_two_reorg_waves():
    # Taunton Deane existed until the 2019 merge into Somerset West and
    # Taunton, which was itself absorbed into Somerset Council in 2023.
    # A source unit dated before 2019 must chain through BOTH events.
    results = resolve(None, "Taunton Deane", "2015-01-01")
    assert results == [("E06000066", "Somerset", pytest.approx(1.0))]


def test_somerset_west_and_taunton_as_of_2020_chains_through_only_the_2023_event():
    # Dated after the 2019 merge (so it IS Somerset West and Taunton already)
    # but before 2023 - should only need to hop once, not twice.
    results = resolve("E07000246", "Somerset West and Taunton", "2020-01-01")
    assert results == [("E06000066", "Somerset", pytest.approx(1.0))]


# ---------------------------------------------------------------------------
# 3. Dwelling counts preserved exactly through a MERGE
# ---------------------------------------------------------------------------


def test_merge_preserves_dwelling_counts_exactly():
    # Synthetic CTSOP-like fixture: Cornwall's six predecessor districts,
    # each with a distinct, exactly-representable dwelling count.
    df = pd.DataFrame(
        {
            "code": [None] * 6,
            "name": ["Penwith", "Kerrier", "Carrick", "Restormel", "Caradon", "North Cornwall"],
            "date": ["2005-01-01"] * 6,
            "dwellings": [12_345, 23_456, 18_901, 20_202, 15_678, 9_999],
        }
    )
    out = harmonise(df, "code", "name", "date", ["dwellings"])
    assert len(out) == 1
    assert out.iloc[0]["target_name"] == "Cornwall"
    assert out.iloc[0]["dwellings"] == df["dwellings"].sum()  # exact, not approx


def test_cheshire_regrouping_matches_documented_facts():
    # Verified against search (Cheshire East / Cheshire West and Chester
    # Wikipedia pages): Congleton + Crewe and Nantwich + Macclesfield ->
    # Cheshire East; Chester + Ellesmere Port and Neston + Vale Royal ->
    # Cheshire West and Chester. Neither old district appears in both.
    east = {resolve(None, n, "2005-01-01")[0][1] for n in ["Congleton", "Crewe and Nantwich", "Macclesfield"]}
    west = {resolve(None, n, "2005-01-01")[0][1] for n in ["Chester", "Ellesmere Port and Neston", "Vale Royal"]}
    assert east == {"Cheshire East"}
    assert west == {"Cheshire West and Chester"}
    assert east.isdisjoint(west)


# ---------------------------------------------------------------------------
# 4. Unknown codes raise, don't silently drop
# ---------------------------------------------------------------------------


def test_unmapped_code_raises_when_checked_against_known_2025_codes():
    known = {"E06000052"}  # Cornwall only, for this test
    with pytest.raises(UnmappedLocalAuthorityCode):
        build_crosswalk(
            [("E99999999", "Not A Real Authority", "2010-01-01")],
            known_2025_codes=known,
        )


def test_harmonise_raises_on_completely_unseen_source_unit():
    # A row in the data that build_crosswalk was never asked to resolve
    # must not be silently excluded from the aggregation.
    df = pd.DataFrame({"code": ["E06000052"], "name": ["Cornwall"], "date": ["2010-01-01"], "dwellings": [1000]})
    # Deliberately pass an empty crosswalk scenario by asking for a code
    # that isn't Cornwall's real target, to force the merge to miss.
    with pytest.raises(UnmappedLocalAuthorityCode):
        harmonise(df, "code", "name", "date", ["dwellings"], known_2025_codes={"E06000047"})  # only Durham


# ---------------------------------------------------------------------------
# 4b. SPLIT structurally requires a documented Apportionment
# ---------------------------------------------------------------------------


def test_split_without_apportionment_cannot_be_constructed():
    with pytest.raises(ValueError, match="requires an explicit, cited Apportionment"):
        ReorgEvent(
            event_id="fake_split",
            effective_date="2030-01-01",
            change_type=ChangeType.SPLIT,
            olds=(LAUnit("Fakeshire"),),
            news=(LAUnit("Fake North"), LAUnit("Fake South")),
            source="test",
        )


def test_apportionment_weights_must_sum_to_one():
    with pytest.raises(ValueError, match="must sum to 1.0"):
        Apportionment(method="bad", source="test", weights={"Fake North": 0.4, "Fake South": 0.4})


def test_apportionment_requires_exactly_one_of_weights_or_fixed_transfer():
    with pytest.raises(ValueError):
        Apportionment(method="bad", source="test")  # neither
    with pytest.raises(ValueError):
        Apportionment(
            method="bad", source="test", weights={"a": 1.0}, fixed_transfer={"a": 1}
        )  # both


def test_fixed_transfer_apportionment_needs_year_totals():
    # Resolving a fixed_transfer SPLIT without supplying that year's actual
    # total must raise, not silently assume some default total.
    with pytest.raises(UnmappedLocalAuthorityCode):
        resolve("E08000016", "Barnsley", "2024-01-01")  # no year_totals passed


def test_fixed_transfer_apportionment_gives_correct_split_with_year_totals():
    results = resolve("E08000016", "Barnsley", "2024-01-01", year_totals={"Barnsley": 1_000})
    weights = {name: w for _, name, w in results}
    assert weights["Sheffield"] == pytest.approx(12 / 1_000)
    assert weights["Barnsley"] == pytest.approx(1 - 12 / 1_000)


# ---------------------------------------------------------------------------
# 4c. Ambiguity raises rather than picking silently
# ---------------------------------------------------------------------------


def test_ambiguous_matching_events_raise():
    conflicting = (
        ReorgEvent(
            event_id="a",
            effective_date="2010-01-01",
            change_type=ChangeType.RECODE,
            olds=(LAUnit("Fakeshire"),),
            news=(LAUnit("Fake A", "E06999991"),),
            source="test",
        ),
        ReorgEvent(
            event_id="b",
            effective_date="2010-01-01",
            change_type=ChangeType.RECODE,
            olds=(LAUnit("Fakeshire"),),
            news=(LAUnit("Fake B", "E06999992"),),
            source="test",
        ),
    )
    with pytest.raises(AmbiguousBoundaryChange):
        resolve(None, "Fakeshire", "2005-01-01", events=conflicting)


# ---------------------------------------------------------------------------
# 6. Full 2000-01 to 2025-26 coverage, reported per financial year.
#
# We don't have real MHCLG/CTSOP files yet (that's Phase 2), so this doesn't
# check real per-vintage LA lists - it checks the structural universe the
# crosswalk is responsible for getting right, independent of which dataset
# later references it: reconstruct, for each financial year, every LA
# identity that must have existed at that date (by reversing EVENTS
# backwards from the 2025 target set), and confirm every single one resolves
# cleanly to a real 2025 code with weight 1.0, zero unmapped, zero ambiguous.
# This is what actually caught the Sheffield gap below (see reorg_events.py
# SHEFFIELD_RECODE_2025) - Sheffield's pre-2025 code was never listed as a
# predecessor anywhere, so it would have silently resolved to itself, a code
# absent from lad_2025.py, and only been caught here.
# ---------------------------------------------------------------------------

FINANCIAL_YEAR_STARTS = [f"{y}-04-01" for y in range(2000, 2026)]  # 2000-01 .. 2025-26


def _active_units_as_of(as_of_date: str, events=EVENTS) -> set[tuple[str | None, str]]:
    """Reconstruct the (code, name) LA identities valid at as_of_date by
    reversing every event with effective_date > as_of_date: successor ->
    its predecessor(s). Processed latest-date-first, and events sharing the
    same effective_date are reversed together against a single snapshot of
    `active` rather than one at a time - otherwise the second of two events
    that both reference the same successor (Sheffield 2025: BOTH the
    Barnsley/Sheffield SPLIT and Sheffield's own RECODE list Sheffield's new
    code in `news`) finds nothing left to reverse, since the first event
    already removed it. This bug was caught by this test's own count-shape
    assertion, not inferred in advance."""
    from council_tax_freeze.boundaries.lad_2025 import LAD_2025

    active: set[tuple[str | None, str]] = {(code, name) for code, name in LAD_2025.items()}
    events_by_date: dict[str, list[ReorgEvent]] = {}
    for e in events:
        if e.effective_date > as_of_date:
            events_by_date.setdefault(e.effective_date, []).append(e)

    for date in sorted(events_by_date, reverse=True):
        to_remove: set[tuple[str | None, str]] = set()
        to_add: set[tuple[str | None, str]] = set()
        for event in events_by_date[date]:
            new_keys = {(n.code, n.name) for n in event.news}
            if new_keys & active:
                to_remove |= new_keys
                to_add |= {(o.code, o.name) for o in event.olds}
        active = (active - to_remove) | to_add
    return active


def test_full_2000_2025_coverage():
    year_totals_stub = {"Barnsley": 1_000_000}  # only the one fixed_transfer SPLIT needs this
    coverage_by_year: dict[str, int] = {}
    unmapped: list[tuple] = []
    ambiguous: list[tuple] = []

    for as_of in FINANCIAL_YEAR_STARTS:
        active = _active_units_as_of(as_of)
        coverage_by_year[as_of] = len(active)
        for code, name in active:
            try:
                results = resolve(code, name, as_of, year_totals=year_totals_stub)
            except AmbiguousBoundaryChange:
                ambiguous.append((as_of, code, name))
                continue
            except UnmappedLocalAuthorityCode as e:
                unmapped.append((as_of, code, name, str(e)))
                continue
            total_weight = sum(w for _, _, w in results)
            assert total_weight == pytest.approx(1.0, abs=1e-9), (as_of, code, name, results)
            for target_code, target_name, _weight in results:
                if target_code not in LAD_2025_CODES:
                    unmapped.append((as_of, code, name, f"resolved to {target_name} ({target_code}), not a 2025 LA"))

    print("\nPer-vintage LA identity coverage, 2000-01 to 2025-26:")
    for as_of, count in coverage_by_year.items():
        print(f"  {as_of}: {count} active LA identities")

    assert not unmapped, f"{len(unmapped)} unmapped resolution(s), e.g. {unmapped[:5]}"
    assert not ambiguous, f"{len(ambiguous)} ambiguous resolution(s), e.g. {ambiguous[:5]}"

    # Sanity check the shape of the series: mergers only ever reduce the
    # count of distinct identities (2009/2019/2020/2021/2023), and the one
    # SPLIT (2025) doesn't change the count (1 old <-> 2 new via the SPLIT,
    # but Sheffield's own RECODE means the net identity count is unchanged
    # across that transition too) - so coverage must be non-increasing.
    counts = list(coverage_by_year.values())
    assert counts == sorted(counts, reverse=True), f"coverage should be non-increasing over time: {coverage_by_year}"
    assert counts[0] > counts[-1], "expected strictly more LA identities in 2000-01 than in 2025-26"
    assert counts[-1] == 296, f"2025-26 should show exactly the 296 current LAs, got {counts[-1]}"


def test_precepting_group_covers_every_2025_la_exactly_once():
    assert set(PRECEPTING_GROUP.keys()) == LAD_2025_CODES

    from collections import Counter

    sizes = Counter(PRECEPTING_GROUP.values())
    standalone = [g for g in sizes if g.startswith("__standalone__")]
    grouped = [g for g in sizes if not g.startswith("__standalone__")]

    # every standalone group is a singleton by construction
    assert all(sizes[g] == 1 for g in standalone)
    assert len(standalone) == 63, f"expected 63 standalone unitary LAs, got {len(standalone)}"

    # every real (non-singleton) precepting group has at least 2 members,
    # or it isn't doing anything a singleton wouldn't
    assert all(sizes[g] >= 2 for g in grouped)
    assert sizes["Greater London"] == 33, "32 boroughs + City of London"


# ---------------------------------------------------------------------------
# 5. National-total validation - deferred until real CTSOP data exists
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Needs a real CTSOP year on disk - Phase 2. Criterion codified now: harmonised national dwelling total must match the published VOA total within 0.1%.")
def test_harmonised_national_total_matches_published_voa_total():
    pass


@pytest.mark.skip(reason="Needs ONS mid-year dwelling estimates on disk - Phase 3. Criterion codified now: within 1% of the ONS estimate, looser than the VOA check since definitions differ.")
def test_harmonised_total_within_one_percent_of_ons_estimate():
    pass
