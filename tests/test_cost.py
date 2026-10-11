"""Cost-estimator tests. Pure arithmetic — no network, no API."""

from injectlab import (
    ARMS,
    build_cells,
    estimate_cost,
    format_estimate,
    load_corpus,
)


def _estimate(model="claude-haiku-4-5"):
    carrier, seeds = load_corpus()
    cells = build_cells(carrier, seeds)
    return estimate_cost(carrier, cells, ARMS, model), cells


def test_counts_runs_as_cells_times_arms():
    est, cells = _estimate()
    assert est.n_runs == len(cells) * len(ARMS)
    assert est.calls == est.n_runs * est.avg_steps


def test_known_model_has_positive_dollar_estimate():
    est, _ = _estimate("claude-haiku-4-5")
    assert est.usd is not None and est.usd > 0
    assert est.input_tokens > est.output_tokens  # input dominates here


def test_unknown_model_has_no_price_but_still_counts_tokens():
    est, _ = _estimate("some-unreleased-model")
    assert est.usd is None
    assert est.input_tokens > 0
    assert "verify" in est.note


def test_format_marks_it_as_an_estimate_with_no_api_call():
    est, _ = _estimate()
    text = format_estimate(est)
    assert "$" in text
    assert "No API call" in text
