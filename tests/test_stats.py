"""Stats tests: Wilson interval and the exact McNemar paired test."""

import pytest

from injectlab import mcnemar_exact, wilson_interval


# --- Wilson interval ----------------------------------------------------------

def test_wilson_no_data_makes_no_claim():
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_wilson_brackets_the_point_estimate():
    lo, hi = wilson_interval(50, 100)
    assert lo < 0.5 < hi
    # Near 50%, half-width ~ 1/sqrt(n) = 0.1, so ~[0.40, 0.60].
    assert abs(lo - 0.40) < 0.02 and abs(hi - 0.60) < 0.02


def test_wilson_stays_in_unit_interval_at_extremes():
    lo0, hi0 = wilson_interval(0, 20)
    lo1, hi1 = wilson_interval(20, 20)
    assert lo0 == 0.0 and hi0 < 1.0      # zero successes: lower bound pinned at 0
    assert hi1 == 1.0 and lo1 > 0.0      # all successes: upper bound pinned at 1


def test_wilson_shrinks_as_n_grows():
    narrow = wilson_interval(500, 1000)
    wide = wilson_interval(5, 10)
    assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


def test_wilson_rejects_impossible_counts():
    with pytest.raises(ValueError):
        wilson_interval(5, 3)


# --- exact McNemar ------------------------------------------------------------

def test_mcnemar_no_discordant_pairs_is_inconclusive():
    assert mcnemar_exact(0, 0) == 1.0


def test_mcnemar_is_symmetric():
    assert mcnemar_exact(7, 2) == mcnemar_exact(2, 7)


def test_mcnemar_one_sided_evidence_is_significant():
    # All 10 discordant pairs favour one arm: strong evidence.
    assert mcnemar_exact(10, 0) < 0.01


def test_mcnemar_small_discordance_not_significant():
    # Two vs one is nowhere near significant.
    assert mcnemar_exact(2, 1) > 0.05


def test_mcnemar_known_value():
    # b=5, c=0: two-sided tail = 2 * (1/2^5) = 0.0625.
    assert mcnemar_exact(5, 0) == pytest.approx(0.0625)
