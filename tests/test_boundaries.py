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
"""

import pytest

from council_tax_freeze.boundaries.crosswalk import (
    AmbiguousBoundaryChange,
    UnmappedLocalAuthorityCode,
    build_crosswalk,
    harmonise,
    resolve,
)
from council_tax_freeze.boundaries.reorg_events import (
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
# 5. National-total validation - deferred until real CTSOP data exists
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Needs a real CTSOP year on disk - Phase 2. Criterion codified now: harmonised national dwelling total must match the published VOA total within 0.1%.")
def test_harmonised_national_total_matches_published_voa_total():
    pass


@pytest.mark.skip(reason="Needs ONS mid-year dwelling estimates on disk - Phase 3. Criterion codified now: within 1% of the ONS estimate, looser than the VOA check since definitions differ.")
def test_harmonised_total_within_one_percent_of_ons_estimate():
    pass
