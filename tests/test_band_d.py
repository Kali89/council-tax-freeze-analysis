"""
Tests for the Band D live-table parser. The full-pipeline tests need the
real MHCLG file (data/band_d/Band_D_1993_onwards.ods, fetched by `make
data` / council_tax_freeze.download.fetch_mhclg_band_d) and skip cleanly if
it's absent, matching the pattern used for Phase 1's deferred tests - this
is real external data, not committed to the repo.
"""

import pytest

from council_tax_freeze.boundaries.reorg_events import EVENTS
from council_tax_freeze.config import DATA_DIR
from council_tax_freeze.parsers.band_d.parse import (
    KNOWN_BAND_D_GAPS,
    BandDValidationError,
    build_band_d,
    financial_year_label,
    financial_year_start_date,
)

BAND_D_FILE = DATA_DIR / "band_d" / "Band_D_1993_onwards.ods"
requires_band_d_file = pytest.mark.skipif(
    not BAND_D_FILE.exists(), reason=f"{BAND_D_FILE} not present - run `make data` first"
)


def test_financial_year_label():
    assert financial_year_label("2000 to 2001") == "2000-01"
    assert financial_year_label("1999 to 2000") == "1999-00"


def test_financial_year_start_date():
    assert financial_year_start_date("2000-01") == "2000-04-01"
    assert financial_year_start_date("2025-26") == "2025-04-01"


@requires_band_d_file
def test_national_validation_passes_against_independent_anchors():
    # This is the fail-loud check the user asked for: build_band_d() raises
    # BandDValidationError itself if any anchored year is out of tolerance,
    # so simply not raising here IS the test.
    result = build_band_d(BAND_D_FILE)
    anchored = result.validation[result.validation["independent_anchor"].notna()]
    assert len(anchored) >= 15, "expected at least 15 independently-anchored years to have been checked"
    assert anchored["within_tolerance"].all()


@requires_band_d_file
def test_validation_raises_on_a_genuine_mismatch():
    import council_tax_freeze.parsers.band_d.parse as parse_module

    original = dict(parse_module.INDEPENDENT_NATIONAL_ANCHORS)
    try:
        parse_module.INDEPENDENT_NATIONAL_ANCHORS["2010-11"] = 99_999
        with pytest.raises(BandDValidationError):
            parse_module.build_band_d(BAND_D_FILE)
    finally:
        parse_module.INDEPENDENT_NATIONAL_ANCHORS.clear()
        parse_module.INDEPENDENT_NATIONAL_ANCHORS.update(original)


@requires_band_d_file
def test_coverage_matches_phase1_active_identity_counts():
    """Cross-checks Phase 2's parsed coverage against Phase 1's
    independently-derived boundary reconstruction - two separate pieces of
    logic, built at different times, agreeing is a real check, not a
    tautology (this is what caught the Barnsley/Sheffield retro-coding
    pattern and the three genuine data gaps in the first place)."""
    from test_boundaries import _active_units_as_of

    result = build_band_d(BAND_D_FILE)
    cov = result.coverage.set_index("financial_year")["n_la_rows"]

    for fy, as_of in [("2000-01", "2000-04-01"), ("2019-20", "2019-04-01"), ("2023-24", "2023-04-01")]:
        expected_active = len(_active_units_as_of(as_of))
        # Band D coverage should be within the known documented gaps (5) of
        # the Phase 1 reconstruction - exactly equal once the 2 retro-coded
        # (not missing) identities are accounted for, short by the 3
        # genuine gaps for any year those 3 predecessors were still live.
        assert cov[fy] <= expected_active
        assert cov[fy] >= expected_active - len(KNOWN_BAND_D_GAPS)


@requires_band_d_file
def test_predecessor_gaps_are_all_previously_documented():
    """Fails loudly if the live table (or a future re-download of it)
    turns out to be missing a predecessor we haven't already investigated
    and explained - the same 'no new undocumented gap' standard as Phase 1's
    ambiguity checks."""
    result = build_band_d(BAND_D_FILE)
    undocumented = result.predecessor_gaps[~result.predecessor_gaps["is_documented"]]
    assert undocumented.empty, f"New, undocumented Band D gap(s) found:\n{undocumented}"
    assert set(result.predecessor_gaps["ons_code"]) == set(KNOWN_BAND_D_GAPS)


@requires_band_d_file
def test_no_ambiguous_resolutions():
    result = build_band_d(BAND_D_FILE)
    assert (result.coverage["n_ambiguous"] == 0).all()


def test_every_reorg_events_predecessor_code_is_a_real_gss_code():
    # Sanity check independent of the Band D file: every predecessor code
    # registered in Phase 1 should look like a real GSS code, since
    # KNOWN_BAND_D_GAPS keys against them directly.
    import re

    gss_re = re.compile(r"^E0[6-9]\d{6}$")
    for e in EVENTS:
        for o in e.olds:
            if o.code:
                assert gss_re.match(o.code), f"{e.event_id}: {o.name} has a malformed code {o.code!r}"
