"""HTML report tests.

The page is a presentation layer, so these pin the things that keep it HONEST
rather than its exact markup: the simulation banner keys on the model name,
every rate carries its interval, the limitations travel with the page, and a
real model gets the findings framing instead of the SIMULATION banner.
"""

import pytest

from injectlab import (
    breakdown,
    build_cells,
    format_html,
    load_corpus,
    run_grid,
    summarise,
)


@pytest.fixture(scope="module")
def data():
    carrier, seeds = load_corpus()
    outcomes = run_grid(carrier, build_cells(carrier, seeds))
    return summarise(outcomes), breakdown(outcomes, by="technique")


def test_standalone_is_a_full_document(data):
    reports, rows = data
    html = format_html(reports, rows, model_name="mock")
    assert html.startswith("<!doctype html>")
    assert "<title>" in html and "</html>" in html
    assert 'charset=' in html


def test_fragment_has_no_document_scaffold(data):
    reports, rows = data
    frag = format_html(reports, rows, model_name="mock", standalone=False)
    assert "<!doctype" not in frag and "<body" not in frag
    assert frag.lstrip().startswith("<style>")  # embeddable (e.g. an Artifact)


def test_mock_gets_a_loud_simulation_banner(data):
    reports, rows = data
    html = format_html(reports, rows, model_name="mock")
    assert "SIMULATION" in html
    assert "not findings" in html.lower() or "not findings about" in html.lower()


def test_real_model_gets_findings_framing_not_simulation(data):
    reports, rows = data
    html = format_html(reports, rows, model_name="claude-haiku-4-5",
                       when="2026-10-11", temperature=0.0)
    assert "SIMULATION" not in html
    assert "Real-model results" in html
    assert "claude-haiku-4-5" in html and "2026-10-11" in html


def test_every_rate_carries_an_interval(data):
    reports, rows = data
    html = format_html(reports, rows, model_name="mock")
    # Wilson intervals render as "[lo%, hi%]"; at least one per arm, and the
    # aggregate n is present.
    assert html.count("[") >= len(reports)
    assert "%," in html  # e.g. "[96%, 100%]"


def test_limitations_travel_with_the_page(data):
    reports, rows = data
    html = format_html(reports, rows, model_name="mock")
    for phrase in ("Static attacker", "lower bound", "native tool calling"):
        assert phrase in html


def test_heatmap_lists_every_technique_and_arm(data):
    reports, rows = data
    html = format_html(reports, rows, model_name="mock")
    for technique in ("urgency", "social-proof", "fake-system-note"):
        assert technique in html
    for arm in ("baseline", "least_privilege", "stacked"):
        assert arm in html


def test_dark_is_the_default_theme_with_light_available(data):
    reports, rows = data
    html = format_html(reports, rows, model_name="mock")
    # Base color-scheme leads with dark; light exists only as an explicit override.
    assert "color-scheme:dark" in html
    assert "data-theme=light" in html


def test_theme_toggle_is_standalone_only(data):
    reports, rows = data
    doc = format_html(reports, rows, model_name="mock", standalone=True)
    frag = format_html(reports, rows, model_name="mock", standalone=False)
    assert "id='themer'" in doc and "<script" in doc
    # The embed fragment leaves theme control to its host: no toggle, no script.
    assert "id='themer'" not in frag and "<script" not in frag


def test_aggregate_chart_renders_both_series(data):
    reports, rows = data
    html = format_html(reports, rows, model_name="mock")
    # The at-a-glance bars: one SVG, both series labelled, CI whiskers noted.
    assert "class='barsvg'" in html
    assert "executed &mdash; the secret left" in html
    assert "attempted &mdash; the model tried" in html
    assert "95% Wilson interval" in html
    # A bar per arm per series (executed + attempted) => >= 2 bars per arm.
    assert html.count("class='bar ") >= 2 * len(reports)
    # The chart adds no scroll box, so it must not disturb the table balance.
    assert html.count("<div class='scroll'>") == 2


def test_each_table_is_balanced_in_its_own_scroll_box(data):
    reports, rows = data
    html = format_html(reports, rows, model_name="mock")
    # Both tables wrapped; opening/closing scroll divs must balance (regression:
    # a global replace once appended an orphan </div> after the heatmap).
    assert html.count("<div class='scroll'>") == 2
    assert html.count("</table></div>") == 2
