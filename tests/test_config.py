from council_tax_freeze.config import (
    BAND_THRESHOLD_1991,
    ENGLAND_BANDS,
    band_midpoints_1991,
)


def test_band_midpoints_bounded_bands_are_threshold_mean():
    # Bounded bands (B-G) aren't a modelling choice - the midpoint is just
    # arithmetic. Pin it so a future edit can't silently change it.
    midpoints = band_midpoints_1991()
    assert midpoints["D"] == (BAND_THRESHOLD_1991["D"] + BAND_THRESHOLD_1991["E"]) / 2


def test_band_midpoints_monotonic():
    midpoints = band_midpoints_1991()
    values = [midpoints[b] for b in ENGLAND_BANDS]
    assert values == sorted(values)


def test_band_h_ratio_changes_only_band_h():
    base = band_midpoints_1991()
    swept = band_midpoints_1991(band_h_ratio=3.0)
    for b in ENGLAND_BANDS:
        if b == "H":
            assert swept[b] != base[b]
        else:
            assert swept[b] == base[b]
