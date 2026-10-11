"""Render a measurement run as one self-contained HTML page.

This is a PRESENTATION layer only: it reads the ArmReports and BreakdownRows
that measure.py already computes and lays them out. It runs nothing and invents
no numbers. Three honesty guarantees are baked into the markup so the page
cannot mislead on its own:

  - a loud SIMULATION banner whenever model_name == "mock" (the mock's numbers
    are never findings about any real model);
  - every rate is shown with its n and 95% Wilson interval, never a bare %;
  - the standing caveats travel with the page (small per-cell n, static
    attacker, JSON text protocol rather than native tool calling).

The page is fully self-contained (inline CSS, no external assets, UTF-8) so it
renders from a file:// open or embedded in an Artifact. format_html(...,
standalone=True) returns a complete document for results/report.html;
standalone=False returns a style+markup fragment for embedding.
"""

from html import escape

from .measure import ArmReport, BreakdownRow, breakdown, build_cells, run_grid, summarise

# Primary endpoint for the heatmap colour. High = bad (the secret left), so the
# hue runs green (0%) -> red (100%).
_HEATMAP_METRIC = "executed"


def _pct(k: int, n: int) -> str:
    return f"{(k / n if n else 0.0):.0%}"


def _ci(ci: tuple[float, float]) -> str:
    return f"[{ci[0]:.0%}, {ci[1]:.0%}]"


def _rate_cell(k: int, n: int, ci: tuple[float, float]) -> str:
    """A table cell: big rate, k/n and Wilson interval beneath it."""
    return (f'<div class="rate">{_pct(k, n)}</div>'
            f'<div class="sub">{k}/{n} &middot; {_ci(ci)}</div>')


def _heat_style(rate: float) -> str:
    # Green (safe, 0%) to red (danger, 100%) for an "executed" rate.
    hue = (1.0 - rate) * 120
    return f"background:hsl({hue:.0f},62%,42%);color:#fff"


def _aggregate_table(reports: list[ArmReport]) -> str:
    head = (
        "<tr><th>arm</th><th>n</th><th>executed</th><th>attempted</th>"
        "<th>structural</th><th>benign task</th><th>paired p vs baseline</th></tr>"
    )
    rows = []
    for r in reports:
        p = "&mdash;" if r.p_value is None else f"{r.p_value:.4f}"
        benign = ('<span class="ok">ok</span>' if r.benign_completed
                  else '<span class="broken">BROKEN</span>')
        rows.append(
            f"<tr><td class='arm'>{escape(r.arm)}</td><td>{r.n}</td>"
            f"<td class='primary'>{_rate_cell(r.executed, r.n, r.executed_ci)}</td>"
            f"<td>{_rate_cell(r.attempted, r.n, r.attempted_ci)}</td>"
            f"<td>{_rate_cell(r.attempted_structural, r.n, r.structural_ci)}</td>"
            f"<td>{benign}</td><td>{p}</td></tr>")
    return f"<table class='agg'><thead>{head}</thead><tbody>{''.join(rows)}</tbody></table>"


def _heatmap(rows: list[BreakdownRow]) -> str:
    if not rows:
        return "<p>No breakdown rows.</p>"
    labels, arms = _ordered(r.label for r in rows), _ordered(r.arm for r in rows)
    cell = {(r.label, r.arm): r for r in rows}
    n_per = rows[0].n
    by = rows[0].by

    head = "<tr><th></th>" + "".join(f"<th>{escape(a)}</th>" for a in arms) + "</tr>"
    body = []
    for label in labels:
        tds = [f"<th class='rowhead'>{escape(label)}</th>"]
        for arm in arms:
            r = cell.get((label, arm))
            if r is None:
                tds.append("<td>&mdash;</td>")
                continue
            rate = r.executed / r.n if r.n else 0.0
            title = f"executed {r.executed}/{r.n} {_ci(r.executed_ci)}"
            tds.append(f"<td class='heat' style='{_heat_style(rate)}' "
                       f"title='{escape(title)}'>{_pct(r.executed, r.n)}</td>")
        body.append(f"<tr>{''.join(tds)}</tr>")
    caption = (f"executed rate by {escape(by)} &times; arm &middot; "
               f"n={n_per} per cell (each interval is wide &mdash; read the "
               "pattern, not a single cell)")
    return (f"<table class='heat'><thead>{head}</thead>"
            f"<tbody>{''.join(body)}</tbody></table>"
            f"<p class='caption'>{caption}</p>")


def _ordered(items):
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _body(reports, rows, *, model_name, when, temperature):
    is_mock = model_name == "mock"
    banner = (
        '<div class="banner sim">SIMULATION &mdash; labelled mock model. These '
        'numbers are NOT findings about any real model; they exist only to '
        'exercise the pipeline.</div>' if is_mock else
        '<div class="banner real">Real-model results. Read with the limitations '
        'at the foot of this page.</div>'
    )
    meta = " &middot; ".join(filter(None, [
        f"model: <b>{escape(model_name)}</b>",
        f"date: {escape(when)}" if when else "",
        f"temperature: {escape(str(temperature))}" if temperature is not None else "",
        f"n (attack cells per arm): {reports[0].n}" if reports else "",
    ]))
    return f"""\
<main>
  <h1>injectlab &mdash; indirect prompt injection measurement</h1>
  {banner}
  <p class="meta">{meta}</p>

  <h2>By defense (aggregate)</h2>
  <p>Primary endpoint is <b>executed</b> (the secret left the environment).
     <b>attempted</b> and <b>structural</b> are shown beside it: a defense that
     merely <i>contains</i> a still-fooled model is not the same as one that
     stops it being fooled. Rates carry a 95% Wilson interval; the paired column
     is an exact McNemar test vs baseline.</p>
  {_aggregate_table(reports)}

  <h2>By technique</h2>
  <p>The same paired cells, sliced by injection technique. This is descriptive:
     per-cell n is small, so no paired test is run here &mdash; it maps where to
     look, it does not render a verdict.</p>
  {_heatmap(rows)}

  <h2>Limitations</h2>
  <ul class="limits">
    <li><b>Static attacker.</b> A fixed corpus; an adaptive attacker usually does
        better. These are a floor, not a ceiling.</li>
    <li><b>Encoding coverage is a lower bound.</b> The oracle checks a fixed list
        of encodings; anything not enumerated is under-counted.</li>
    <li><b>JSON text protocol, not native tool calling.</b> Results may not
        transfer to native function-calling APIs.</li>
    <li><b>Small per-technique n.</b> Each heatmap cell is noisy; lead with the
        aggregate and treat cells as hypotheses.</li>
    <li><b>Multiple comparisons.</b> Several arms vs baseline inflate false
        positives; lead with effect size.</li>
  </ul>
</main>"""


def _css() -> str:
    return """\
:root{color-scheme:light dark;
--bg:#fbfbfd;--fg:#1b1d24;--muted:#5e6470;--line:#e4e6ec;--head:#f2f3f7;
--card:#f6f7fb;--accent:#5b4bf0;--ok:#1f9d57;--bad:#d1374b;
--mono:ui-monospace,SFMono-Regular,"Cascadia Mono",Consolas,Menlo,monospace;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
@media(prefers-color-scheme:dark){:root{--bg:#14151a;--fg:#e7e8ec;--muted:#969aa8;
--line:#282a32;--head:#1c1e26;--card:#191b22;--accent:#9d8cff;--ok:#43c37e;--bad:#ff6b7a}}
:root[data-theme=dark]{--bg:#14151a;--fg:#e7e8ec;--muted:#969aa8;--line:#282a32;
--head:#1c1e26;--card:#191b22;--accent:#9d8cff;--ok:#43c37e;--bad:#ff6b7a}
:root[data-theme=light]{--bg:#fbfbfd;--fg:#1b1d24;--muted:#5e6470;--line:#e4e6ec;
--head:#f2f3f7;--card:#f6f7fb;--accent:#5b4bf0;--ok:#1f9d57;--bad:#d1374b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 var(--sans)}
main{max-width:980px;margin:0 auto;padding:40px 20px 72px}
h1{font-size:1.5rem;line-height:1.25;margin:0 0 14px;text-wrap:balance;letter-spacing:-.01em}
h2{font-size:1.05rem;margin:40px 0 8px;padding-bottom:6px;border-bottom:1px solid var(--line);text-wrap:balance}
p{margin:8px 0;max-width:68ch}
b{font-weight:650}
.meta{color:var(--muted);font:.84rem/1.5 var(--mono)}
.banner{padding:11px 14px;border-radius:9px;font-weight:600;margin:14px 0;
border:1px solid transparent}
.banner.sim{background:#7a1420;color:#fff;border-color:#9c2230}
.banner.real{background:#12402a;color:#eafff2;border-color:#1c6440}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:10px;margin:12px 0}
table{border-collapse:collapse;width:100%;font-size:.9rem}
.agg th,.agg td{border-bottom:1px solid var(--line);padding:10px 12px;text-align:center;vertical-align:middle}
.agg thead th{background:var(--head);font:600 .68rem/1.2 var(--sans);
text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.agg tbody tr:last-child td{border-bottom:0}
.agg td.arm{text-align:left;font-weight:650;font-family:var(--mono);font-size:.84rem}
.agg td.primary{background:var(--card);box-shadow:inset 3px 0 var(--accent)}
.rate{font:700 1rem/1.1 var(--mono);font-variant-numeric:tabular-nums}
.sub{color:var(--muted);font:.7rem/1.2 var(--mono);margin-top:3px;font-variant-numeric:tabular-nums}
.ok{color:var(--ok);font-weight:700}
.broken{color:var(--bad);font-weight:700}
table.heat{border:1px solid var(--line);border-radius:10px;overflow:hidden}
table.heat td,table.heat th{border:1px solid var(--line);padding:10px 8px;text-align:center}
table.heat thead th,table.heat .rowhead{background:var(--head)}
table.heat thead th{font:600 .68rem/1.2 var(--sans);text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
table.heat .rowhead{text-align:left;font-family:var(--mono);font-size:.82rem;font-weight:650}
td.heat{font:700 .95rem/1.1 var(--mono);font-variant-numeric:tabular-nums}
.caption{color:var(--muted);font-size:.82rem}
.limits{padding-left:20px}
.limits li{margin:5px 0;max-width:66ch}"""


def format_html(reports: list[ArmReport], rows: list[BreakdownRow], *,
                model_name: str = "mock", when: str | None = None,
                temperature: float | None = None, standalone: bool = True) -> str:
    """Render one measurement run as HTML.

    standalone=True returns a complete document (for results/report.html);
    standalone=False returns `<style>...</style>` + body markup, for embedding
    (e.g. an Artifact, which supplies its own <head>/<body>).
    """
    body = _body(reports, rows, model_name=model_name, when=when,
                 temperature=temperature)
    style = f"<style>{_css()}</style>"
    # Tables can be wide; let them scroll inside their own box, never the page.
    content = f"{style}\n{body}".replace(
        "<table class='agg'>", "<div class='scroll'><table class='agg'>").replace(
        "</tbody></table>", "</tbody></table></div>")
    if not standalone:
        return content
    title = f"injectlab measurement &mdash; {escape(model_name)}"
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{title}</title></head><body>{content}</body></html>")


def main() -> None:  # pragma: no cover - convenience entry point
    from datetime import date
    from pathlib import Path

    from .corpus import load_corpus

    carrier, seeds = load_corpus()
    outcomes = run_grid(carrier, build_cells(carrier, seeds))
    html = format_html(summarise(outcomes), breakdown(outcomes, by="technique"),
                       model_name="mock", when=date.today().isoformat())
    out = Path("results") / "report.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out} ({len(html)} bytes). Open it in a browser.")


if __name__ == "__main__":  # pragma: no cover
    main()
