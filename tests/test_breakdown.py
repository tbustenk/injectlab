"""Per-technique / per-position breakdown tests.

A breakdown is a different group-by over the SAME paired outcomes, so these pin
two things: the slicing arithmetic (counts, denominators, exclusions) and the
honest fact that under the technique-blind mock every technique row is identical
by construction -- the breakdown's value is the plumbing now, the real model later.
"""

import pytest

from injectlab import (
    breakdown,
    build_cells,
    format_breakdown,
    load_corpus,
    run_grid,
)


@pytest.fixture(scope="module")
def outcomes():
    carrier, seeds = load_corpus()
    return run_grid(carrier, build_cells(carrier, seeds))


# --- shape and denominators ---------------------------------------------------

def test_technique_breakdown_shape(outcomes):
    rows = breakdown(outcomes, by="technique")
    # 5 test techniques x 6 arms = 30 rows; each slice is 6 mutations x 3 positions.
    assert len(rows) == 30
    assert all(r.n == 18 for r in rows)
    assert {r.label for r in rows} == {
        "urgency", "pretext", "distraction", "social-proof", "fake-system-note"}


def test_position_breakdown_shape(outcomes):
    rows = breakdown(outcomes, by="position")
    # 3 positions x 6 arms = 18 rows; each slice is 5 techniques x 6 mutations.
    assert len(rows) == 18
    assert all(r.n == 30 for r in rows)
    assert {r.label for r in rows} == {"start", "middle", "end"}


def test_slices_sum_to_the_aggregate(outcomes):
    # Every attack cell lands in exactly one technique slice per arm: the slice
    # denominators for one arm must total that arm's aggregate n (90).
    rows = [r for r in breakdown(outcomes, by="technique") if r.arm == "baseline"]
    assert sum(r.n for r in rows) == 90


def test_benign_control_is_excluded(outcomes):
    # The benign cell has technique=None/position=None and must not appear.
    for by in ("technique", "position"):
        assert all(r.label is not None for r in breakdown(outcomes, by=by))


# --- the mock's flat-by-construction result ----------------------------------

def test_every_technique_row_is_identical_under_the_mock(outcomes):
    rows = breakdown(outcomes, by="technique")
    baseline = [r for r in rows if r.arm == "baseline"]
    filt = [r for r in rows if r.arm == "filter"]
    # Technique-blind mock: baseline leaks every technique, filter neutralises every one.
    assert all(r.executed == r.n for r in baseline)
    assert all(r.executed == 0 for r in filt)


# --- guard rails --------------------------------------------------------------

def test_unknown_key_and_metric_raise(outcomes):
    with pytest.raises(ValueError, match="unknown breakdown key"):
        breakdown(outcomes, by="mutation")
    with pytest.raises(ValueError, match="unknown metric"):
        format_breakdown(breakdown(outcomes), metric="nonsense")


# --- rendering ----------------------------------------------------------------

def test_format_flags_simulation_and_lists_techniques(outcomes):
    text = format_breakdown(breakdown(outcomes, by="technique"))
    assert "SIMULATION" in text
    assert "urgency" in text and "fake-system-note" in text
    assert "baseline" in text and "filter" in text
