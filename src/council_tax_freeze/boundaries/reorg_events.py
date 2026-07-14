"""
Every English local authority structural change 2000-2025, as an explicit,
hand-reviewed, cited data structure - not something inferred at runtime from
whatever ONS lookup happens to be on disk.

Why hand-encoded rather than parsed from an ONS lookup file: there is no
single ONS lookup spanning 2000-2025 (see DATA.md), and the four/five
reorganisation waves in this period are a small, finite, well-documented set
of events (verified individually below against Wikipedia / legislation.gov.uk
/ ONS's own "explore local statistics" pages, not asserted from memory) - that
makes them more reliably correct as reviewed data than as the output of code
parsing N heterogeneous vintage files whose schemas we haven't all seen yet.

GSS code coverage: every NEW (successor) code below is verified against
either ONS's own site or a maintained names-and-codes reference (see each
event's `source`). Several OLD (predecessor) codes for the 2009 wave are
NOT verified - the reference dataset used for verification only covers
abolitions from 2015 onward, so we could not confirm the exact pre-2009
district GSS codes (e.g. Cornwall's six predecessor districts) against an
authoritative source. Those units are stored as name-only (code=None) with
a TODO. This is deliberate: guessing a plausible-looking E07 code would be
worse than leaving it unresolved, since the crosswalk would then silently
join on a wrong code instead of falling back to name matching or failing
loudly. Phase 2 should fill these in once the actual historic MHCLG/CTSOP
source files are on disk and we can see what codes (or names) they used for
that era - which is the only way to know for certain what needs to join
against what.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ChangeType(Enum):
    RECODE = "recode"  # same geography, code relabelled only
    MERGE = "merge"  # N old whole units -> 1 new unit; weight 1.0 each, exact by construction
    SPLIT = "split"  # 1 old unit -> N new units; requires an explicit, cited Apportionment


@dataclass(frozen=True)
class LAUnit:
    name: str
    code: str | None = None  # None where not yet verified - see module docstring


@dataclass(frozen=True)
class Apportionment:
    """How a SPLIT event divides its one old unit's value among its new units.

    Exactly one of `weights` or `fixed_transfer` must be set:
      - `weights`: new unit name -> fraction of the old unit's value, summing to 1.0.
        Use when the split is genuinely proportional and a defensible weighting
        source exists (e.g. population share).
      - `fixed_transfer`: new unit name -> count of dwellings known to have moved,
        for well-documented small transfers (e.g. a named development moving
        between LAs). The remainder is assumed to stay with whichever new unit
        continues the old unit's identity (same name, or the larger successor).
        Resolved into a weight at apply time against that year's actual total,
        not baked in here as a static fraction - the count is fixed, the
        fraction it represents depends on the year's dwelling stock.
    """

    method: str
    source: str
    weights: dict[str, float] | None = None
    fixed_transfer: dict[str, int] | None = None

    def __post_init__(self):
        has_weights = self.weights is not None
        has_fixed = self.fixed_transfer is not None
        if has_weights == has_fixed:  # both or neither
            raise ValueError("Apportionment needs exactly one of weights or fixed_transfer")
        if has_weights and abs(sum(self.weights.values()) - 1.0) > 1e-9:
            raise ValueError(f"Apportionment weights must sum to 1.0, got {sum(self.weights.values())}")


@dataclass(frozen=True)
class ReorgEvent:
    event_id: str
    effective_date: str  # ISO YYYY-MM-DD. Source data dated before this uses `olds`; on/after uses `news`.
    change_type: ChangeType
    olds: tuple[LAUnit, ...]
    news: tuple[LAUnit, ...]
    source: str
    apportionment: Apportionment | None = None

    def __post_init__(self):
        if self.change_type == ChangeType.RECODE:
            if not (len(self.olds) == 1 and len(self.news) == 1):
                raise ValueError(f"{self.event_id}: RECODE must have exactly one old and one new unit")
            if self.apportionment is not None:
                raise ValueError(f"{self.event_id}: RECODE must not carry an apportionment")
        elif self.change_type == ChangeType.MERGE:
            if not (len(self.olds) >= 2 and len(self.news) == 1):
                raise ValueError(f"{self.event_id}: MERGE must have >=2 old units and exactly one new unit")
            if self.apportionment is not None:
                raise ValueError(f"{self.event_id}: MERGE is exact by construction, must not carry an apportionment")
        elif self.change_type == ChangeType.SPLIT:
            if not (len(self.olds) == 1 and len(self.news) >= 2):
                raise ValueError(f"{self.event_id}: SPLIT must have exactly one old unit and >=2 new units")
            if self.apportionment is None:
                raise ValueError(
                    f"{self.event_id}: SPLIT requires an explicit, cited Apportionment - "
                    "this is enforced at construction so an unreconcilable split can't silently "
                    "default to an even or convenient allocation."
                )
            new_names = {n.name for n in self.news}
            if self.apportionment.weights is not None and set(self.apportionment.weights) != new_names:
                raise ValueError(f"{self.event_id}: apportionment weight keys must exactly match new unit names")
            if self.apportionment.fixed_transfer is not None and not set(self.apportionment.fixed_transfer) <= new_names:
                raise ValueError(f"{self.event_id}: apportionment fixed_transfer keys must be a subset of new unit names")


# ---------------------------------------------------------------------------
# 2025 boundary change (in effect, but relevant here because CTSOP and other
# sources lag): the ONLY event in the whole 2000-2025 period we could confirm
# is a genuine partial-territory transfer, not a whole-district regrouping.
# 12 existing dwellings (296 once the associated development completes) moved
# from Barnsley to Sheffield. This is exactly the "many-to-many merge that
# cannot be made dwelling-count-preserving from LA-level aggregate data alone"
# case flagged in the Phase 1 acceptance criteria: CTSOP reports one number
# per LA per band, not per-development, so we cannot ourselves verify which
# band(s) those 12 dwellings sit in - we can only apply the Order's own count.
# ---------------------------------------------------------------------------
BARNSLEY_SHEFFIELD_2025 = ReorgEvent(
    event_id="barnsley_sheffield_boundary_change_2025",
    effective_date="2025-04-01",
    change_type=ChangeType.SPLIT,
    olds=(LAUnit("Barnsley", "E08000016"),),
    news=(LAUnit("Barnsley", "E08000038"), LAUnit("Sheffield", "E08000039")),
    source=(
        "The Barnsley and Sheffield (Boundary Change) Order 2024 (in force 1 April 2025); "
        "LGBCE PABR Barnsley and Sheffield. Transfers the Oughtibridge Mill development "
        "(12 existing, 284 further planned dwellings) from Barnsley to Sheffield."
    ),
    apportionment=Apportionment(
        method=(
            "Fixed count from the Order itself, not a proportional estimate: 12 dwellings "
            "move from Barnsley to Sheffield; the remainder of Barnsley's stock is unaffected. "
            "Which CTSOP band(s) those 12 dwellings fall in is NOT known from LA-level aggregate "
            "data - assumed to match Barnsley's LA-wide band distribution for that year, which is "
            "a documented approximation, not a verified fact. Flagged in DATA.md."
        ),
        source="Barnsley and Sheffield (Boundary Change) Order 2024, LGBCE final recommendation.",
        fixed_transfer={"Sheffield": 12},
    ),
)

# Note: we deliberately do NOT also register a plain RECODE for
# E08000016->E08000038 / E08000019->E08000039 alongside the SPLIT above.
# They cover the same (code, effective_date) pair, and registering both
# would create a genuine ambiguity - which is exactly the kind of case the
# crosswalk builder must raise on, not silently resolve by picking one. The
# SPLIT is the more accurate single source of truth for this transition; a
# vintage that only needs the code relabel gets a weight of ~1.0 to Barnsley
# and ~0.0 to Sheffield anyway once real dwelling totals are applied.

# ---------------------------------------------------------------------------
# 2009-04-01: seven non-metropolitan counties reformed. Verified against
# Wikipedia's "2009 structural changes to local government in England" and,
# for new-unit codes only, cross-checked against a maintained GSS names-and-
# codes reference. Every one of these is a clean whole-district regrouping -
# no predecessor district's territory was split between two successors.
# ---------------------------------------------------------------------------
REORG_2009 = (
    ReorgEvent(
        event_id="cornwall_2009",
        effective_date="2009-04-01",
        change_type=ChangeType.MERGE,
        olds=tuple(LAUnit(n) for n in ["Penwith", "Kerrier", "Carrick", "Restormel", "Caradon", "North Cornwall"]),
        news=(LAUnit("Cornwall", "E06000052"),),
        source="Wikipedia: 2009 structural changes to local government in England (Cornwall).",
    ),
    ReorgEvent(
        event_id="county_durham_2009",
        effective_date="2009-04-01",
        change_type=ChangeType.MERGE,
        olds=tuple(
            LAUnit(n)
            for n in ["Durham City", "Easington", "Sedgefield", "Teesdale", "Wear Valley", "Derwentside", "Chester-le-Street"]
        ),
        news=(LAUnit("County Durham", "E06000047"),),
        source="Wikipedia: 2009 structural changes to local government in England (County Durham).",
    ),
    ReorgEvent(
        event_id="northumberland_2009",
        effective_date="2009-04-01",
        change_type=ChangeType.MERGE,
        olds=tuple(
            LAUnit(n) for n in ["Blyth Valley", "Wansbeck", "Castle Morpeth", "Tynedale", "Alnwick", "Berwick-upon-Tweed"]
        ),
        news=(LAUnit("Northumberland", "E06000057"),),  # archaic code E06000048 seen in some early releases
        source="Wikipedia: 2009 structural changes to local government in England (Northumberland).",
    ),
    ReorgEvent(
        event_id="shropshire_2009",
        effective_date="2009-04-01",
        change_type=ChangeType.MERGE,
        olds=tuple(
            LAUnit(n) for n in ["North Shropshire", "Oswestry", "Shrewsbury and Atcham", "South Shropshire", "Bridgnorth"]
        ),
        news=(LAUnit("Shropshire", "E06000051"),),
        source="Wikipedia: 2009 structural changes to local government in England (Shropshire).",
    ),
    ReorgEvent(
        event_id="wiltshire_2009",
        effective_date="2009-04-01",
        change_type=ChangeType.MERGE,
        olds=tuple(LAUnit(n) for n in ["Salisbury", "West Wiltshire", "Kennet", "North Wiltshire"]),
        news=(LAUnit("Wiltshire", "E06000054"),),
        source="Wikipedia: 2009 structural changes to local government in England (Wiltshire).",
    ),
    ReorgEvent(
        event_id="bedfordshire_central_2009",
        effective_date="2009-04-01",
        change_type=ChangeType.MERGE,
        olds=(LAUnit("Mid Bedfordshire"), LAUnit("South Bedfordshire")),
        news=(LAUnit("Central Bedfordshire", "E06000056"),),
        source="Wikipedia: 2009 structural changes to local government in England (Bedfordshire).",
    ),
    ReorgEvent(
        event_id="bedford_2009",
        effective_date="2009-04-01",
        change_type=ChangeType.RECODE,  # unchanged boundary, becomes unitary
        olds=(LAUnit("Bedford"),),
        news=(LAUnit("Bedford", "E06000055"),),
        source="Wikipedia: 2009 structural changes to local government in England (Bedfordshire).",
    ),
    ReorgEvent(
        event_id="cheshire_east_2009",
        effective_date="2009-04-01",
        change_type=ChangeType.MERGE,
        olds=(LAUnit("Congleton"), LAUnit("Crewe and Nantwich"), LAUnit("Macclesfield")),
        news=(LAUnit("Cheshire East", "E06000049"),),
        source="Wikipedia: 2009 structural changes to local government in England (Cheshire).",
    ),
    ReorgEvent(
        event_id="cheshire_west_2009",
        effective_date="2009-04-01",
        change_type=ChangeType.MERGE,
        olds=(LAUnit("Chester"), LAUnit("Ellesmere Port and Neston"), LAUnit("Vale Royal")),
        news=(LAUnit("Cheshire West and Chester", "E06000050"),),
        source="Wikipedia: 2009 structural changes to local government in England (Cheshire).",
    ),
)

# ---------------------------------------------------------------------------
# 2019-04-01. All codes (old and new) verified against a maintained GSS
# names-and-codes reference.
# ---------------------------------------------------------------------------
REORG_2019 = (
    ReorgEvent(
        event_id="dorset_2019",
        effective_date="2019-04-01",
        change_type=ChangeType.MERGE,
        olds=(
            LAUnit("East Dorset", "E07000049"),
            LAUnit("North Dorset", "E07000050"),
            LAUnit("Purbeck", "E07000051"),
            LAUnit("West Dorset", "E07000052"),
            LAUnit("Weymouth and Portland", "E07000053"),
        ),
        news=(LAUnit("Dorset", "E06000059"),),
        source="uk_local_authority_names_and_codes (ajparsons); Wikipedia 2019-2023 structural changes.",
    ),
    ReorgEvent(
        event_id="bcp_2019",
        effective_date="2019-04-01",
        change_type=ChangeType.MERGE,
        olds=(LAUnit("Bournemouth", "E06000028"), LAUnit("Poole", "E06000029"), LAUnit("Christchurch", "E07000048")),
        news=(LAUnit("Bournemouth, Christchurch and Poole", "E06000058"),),
        source="uk_local_authority_names_and_codes (ajparsons); Wikipedia 2019-2023 structural changes.",
    ),
    ReorgEvent(
        event_id="west_suffolk_2019",
        effective_date="2019-04-01",
        change_type=ChangeType.MERGE,
        olds=(LAUnit("Forest Heath", "E07000201"), LAUnit("St Edmundsbury", "E07000204")),
        news=(LAUnit("West Suffolk", "E07000245"),),
        source="uk_local_authority_names_and_codes (ajparsons); Wikipedia 2019-2023 structural changes.",
    ),
    ReorgEvent(
        event_id="east_suffolk_2019",
        effective_date="2019-04-01",
        change_type=ChangeType.MERGE,
        olds=(LAUnit("Suffolk Coastal", "E07000205"), LAUnit("Waveney", "E07000206")),
        news=(LAUnit("East Suffolk", "E07000244"),),
        source="uk_local_authority_names_and_codes (ajparsons); Wikipedia 2019-2023 structural changes.",
    ),
    ReorgEvent(
        event_id="somerset_west_taunton_2019",
        effective_date="2019-04-01",
        change_type=ChangeType.MERGE,
        olds=(LAUnit("Taunton Deane", "E07000190"), LAUnit("West Somerset", "E07000191")),
        news=(LAUnit("Somerset West and Taunton", "E07000246"),),
        source="uk_local_authority_names_and_codes (ajparsons); Wikipedia 2019-2023 structural changes.",
    ),
)

# ---------------------------------------------------------------------------
# 2020-04-01 and 2021-04-01. Fully verified both sides.
# ---------------------------------------------------------------------------
REORG_2020 = (
    ReorgEvent(
        event_id="buckinghamshire_2020",
        effective_date="2020-04-01",
        change_type=ChangeType.MERGE,
        olds=(
            LAUnit("Aylesbury Vale", "E07000004"),
            LAUnit("Chiltern", "E07000005"),
            LAUnit("South Bucks", "E07000006"),
            LAUnit("Wycombe", "E07000007"),
        ),
        news=(LAUnit("Buckinghamshire", "E06000060"),),
        source="uk_local_authority_names_and_codes (ajparsons); Wikipedia 2019-2023 structural changes.",
    ),
)

REORG_2021 = (
    ReorgEvent(
        event_id="north_northamptonshire_2021",
        effective_date="2021-04-01",
        change_type=ChangeType.MERGE,
        olds=(
            LAUnit("Corby", "E07000150"),
            LAUnit("East Northamptonshire", "E07000152"),
            LAUnit("Kettering", "E07000153"),
            LAUnit("Wellingborough", "E07000156"),
        ),
        news=(LAUnit("North Northamptonshire", "E06000061"),),
        source="uk_local_authority_names_and_codes (ajparsons); Wikipedia 2019-2023 structural changes.",
    ),
    ReorgEvent(
        event_id="west_northamptonshire_2021",
        effective_date="2021-04-01",
        change_type=ChangeType.MERGE,
        olds=(
            LAUnit("Daventry", "E07000151"),
            LAUnit("Northampton", "E07000154"),
            LAUnit("South Northamptonshire", "E07000155"),
        ),
        news=(LAUnit("West Northamptonshire", "E06000062"),),
        source="uk_local_authority_names_and_codes (ajparsons); Wikipedia 2019-2023 structural changes.",
    ),
)

# ---------------------------------------------------------------------------
# 2023-04-01. Fully verified both sides (ONS explore-local-statistics pages).
# Somerset here is a genuine two-step chain: Taunton Deane + West Somerset
# merged into Somerset West and Taunton in 2019 (see REORG_2019), which is
# then itself absorbed into Somerset Council in 2023 below - a real test of
# whether the crosswalk builder correctly chains across waves.
# ---------------------------------------------------------------------------
REORG_2023 = (
    ReorgEvent(
        event_id="cumberland_2023",
        effective_date="2023-04-01",
        change_type=ChangeType.MERGE,
        olds=(LAUnit("Allerdale", "E07000026"), LAUnit("Carlisle", "E07000028"), LAUnit("Copeland", "E07000029")),
        news=(LAUnit("Cumberland", "E06000063"),),
        source="ONS explore-local-statistics E06000063 Cumberland.",
    ),
    ReorgEvent(
        event_id="westmorland_furness_2023",
        effective_date="2023-04-01",
        change_type=ChangeType.MERGE,
        olds=(LAUnit("Barrow-in-Furness", "E07000027"), LAUnit("Eden", "E07000030"), LAUnit("South Lakeland", "E07000031")),
        news=(LAUnit("Westmorland and Furness", "E06000064"),),
        source="ONS explore-local-statistics E06000064 Westmorland and Furness.",
    ),
    ReorgEvent(
        event_id="north_yorkshire_2023",
        effective_date="2023-04-01",
        change_type=ChangeType.MERGE,
        olds=tuple(
            LAUnit(n, c)
            for n, c in [
                ("Craven", "E07000163"),
                ("Hambleton", "E07000164"),
                ("Harrogate", "E07000165"),
                ("Richmondshire", "E07000166"),
                ("Ryedale", "E07000167"),
                ("Scarborough", "E07000168"),
                ("Selby", "E07000169"),
            ]
        ),
        news=(LAUnit("North Yorkshire", "E06000065"),),
        source="ONS explore-local-statistics E06000065 North Yorkshire.",
    ),
    ReorgEvent(
        event_id="somerset_2023",
        effective_date="2023-04-01",
        change_type=ChangeType.MERGE,
        olds=(
            LAUnit("Mendip", "E07000187"),
            LAUnit("Sedgemoor", "E07000188"),
            LAUnit("South Somerset", "E07000189"),
            LAUnit("Somerset West and Taunton", "E07000246"),  # itself a 2019 successor - the chain
        ),
        news=(LAUnit("Somerset", "E06000066"),),
        source="ONS explore-local-statistics E06000066 Somerset.",
    ),
)

EVENTS: tuple[ReorgEvent, ...] = (
    (BARNSLEY_SHEFFIELD_2025,)
    + REORG_2009
    + REORG_2019
    + REORG_2020
    + REORG_2021
    + REORG_2023
)
