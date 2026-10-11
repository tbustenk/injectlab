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
renders from a file:// open or embedded in an Artifact. It is DARK BY DEFAULT:
the dark palette is the base, light is reached only via :root[data-theme=light]
(the standalone document ships a toggle; the embed fragment leaves theme control
to its host). format_html(..., standalone=True) returns a complete document for
results/report.html; standalone=False returns a style+markup fragment.
"""

from html import escape

from .measure import ArmReport, BreakdownRow, breakdown, build_cells, run_grid, summarise


def _pct(k: int, n: int) -> str:
    return f"{(k / n if n else 0.0):.0%}"


def _ci(ci: tuple[float, float]) -> str:
    return f"[{ci[0]:.0%}, {ci[1]:.0%}]"


def _rate_cell(k: int, n: int, ci: tuple[float, float]) -> str:
    """A table cell: big rate, k/n and Wilson interval beneath it."""
    return (f'<div class="rate">{_pct(k, n)}</div>'
            f'<div class="sub">{k}/{n} &middot; {_ci(ci)}</div>')


def _bars_chart(reports: list[ArmReport]) -> str:
    """A screenshot-first view of the aggregate: executed vs attempted per arm,
    each with its 95% Wilson interval drawn as a whisker.

    The gap between the two bars IS the containment story -- a long attempted bar
    over a zero executed bar means the model was fully fooled yet nothing left
    (filter / egress_dlp); a flat executed bar on a structural arm is the whole
    point of the project. Pure inline SVG, themed through the CSS vars, no assets.
    """
    if not reports:
        return ""
    W, padL, padR, padT, rowH, barH, gap = 720, 138, 18, 34, 44, 12, 6
    plotW = W - padL - padR
    H = padT + len(reports) * rowH + 6

    def x(rate: float) -> float:
        return padL + max(0.0, min(1.0, rate)) * plotW

    parts = []
    for g in (0, 0.25, 0.5, 0.75, 1.0):
        gx = x(g)
        parts.append(f"<line x1='{gx:.1f}' y1='{padT - 6}' x2='{gx:.1f}' "
                     f"y2='{H - 6}' stroke='var(--line)' stroke-width='1'/>")
        parts.append(f"<text x='{gx:.1f}' y='{padT - 12}' text-anchor='middle' "
                     f"class='gx'>{int(g * 100)}%</text>")

    for i, r in enumerate(reports):
        top = padT + i * rowH
        parts.append(f"<text x='4' y='{top + 21}' dominant-baseline='middle' "
                     f"class='ylabel'>{escape(r.arm)}</text>")
        series = [
            (r.executed, r.n, r.executed_ci, "exec", top + 6),
            (r.attempted, r.n, r.attempted_ci, "att", top + 6 + barH + gap),
        ]
        for k, n, ci, cls, by0 in series:
            rate = k / n if n else 0.0
            bx, cy = x(rate), by0 + barH / 2
            parts.append(f"<rect x='{padL}' y='{by0}' width='{plotW}' "
                         f"height='{barH}' rx='3' class='track'/>")
            parts.append(f"<rect x='{padL}' y='{by0}' width='{bx - padL:.1f}' "
                         f"height='{barH}' rx='3' class='bar {cls}'/>")
            lo, hi = x(ci[0]), x(ci[1])
            if hi - lo > 0.5:
                parts.append(f"<line x1='{lo:.1f}' y1='{cy:.1f}' x2='{hi:.1f}' "
                             f"y2='{cy:.1f}' class='whisk'/>")
                for cap in (lo, hi):
                    parts.append(f"<line x1='{cap:.1f}' y1='{cy - 3:.1f}' "
                                 f"x2='{cap:.1f}' y2='{cy + 3:.1f}' class='whisk'/>")
            if rate >= 0.82:
                parts.append(f"<text x='{bx - 5:.1f}' y='{cy + 3.5:.1f}' "
                             f"text-anchor='end' class='blab on'>{_pct(k, n)}</text>")
            else:
                parts.append(f"<text x='{bx + 5:.1f}' y='{cy + 3.5:.1f}' "
                             f"text-anchor='start' class='blab'>{_pct(k, n)}</text>")

    svg = (f"<svg viewBox='0 0 {W} {H}' class='barsvg' role='img' "
           f"aria-label='Executed versus attempted exfiltration rate per arm, "
           f"with 95% confidence whiskers'>{''.join(parts)}</svg>")
    legend = (
        "<div class='clegend'>"
        "<span><i class='sw exec'></i>executed &mdash; the secret left</span>"
        "<span><i class='sw att'></i>attempted &mdash; the model tried</span>"
        "<span class='whisknote'>whisker = 95% Wilson interval</span></div>")
    return f"<figure class='chart'>{svg}{legend}</figure>"


def _heat_hue(rate: float) -> float:
    # Green (safe, 0%) through yellow to red (danger, 100%) for an executed rate.
    return (1.0 - rate) * 120


def _aggregate_table(reports: list[ArmReport]) -> str:
    head = (
        "<tr><th>arm</th><th>n</th><th>executed</th><th>attempted</th>"
        "<th>structural</th><th>benign task</th><th>paired p vs&nbsp;baseline</th></tr>"
    )
    rows = []
    for r in reports:
        p = "&mdash;" if r.p_value is None else f"{r.p_value:.4f}"
        benign = ('<span class="ok">ok</span>' if r.benign_completed
                  else '<span class="broken">BROKEN</span>')
        rows.append(
            f"<tr><td class='arm'>{escape(r.arm)}</td><td class='n'>{r.n}</td>"
            f"<td class='primary'>{_rate_cell(r.executed, r.n, r.executed_ci)}</td>"
            f"<td>{_rate_cell(r.attempted, r.n, r.attempted_ci)}</td>"
            f"<td>{_rate_cell(r.attempted_structural, r.n, r.structural_ci)}</td>"
            f"<td>{benign}</td><td class='pval'>{p}</td></tr>")
    return (f"<div class='scroll'><table class='agg'><thead>{head}</thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>")


def _legend() -> str:
    # The gradient mirrors _heat_hue exactly: green(120) -> yellow(60) -> red(0).
    bar = ("linear-gradient(90deg,"
           "hsl(120,58%,42%),hsl(60,58%,42%),hsl(0,58%,42%))")
    return (f"<div class='legend'><span class='lkey'>executed rate</span>"
            f"<span class='bar' style='background:{bar}' aria-hidden='true'></span>"
            f"<span class='lends'><span>0% &middot; blocked</span>"
            f"<span>100% &middot; leaked</span></span></div>")


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
            tds.append(
                f"<td class='heat' style='background:hsl({_heat_hue(rate):.0f},58%,42%)' "
                f"title='{escape(title)}'>{_pct(r.executed, r.n)}</td>")
        body.append(f"<tr>{''.join(tds)}</tr>")
    caption = (f"executed rate by {escape(by)} &times; arm &middot; "
               f"n={n_per} per cell (each interval is wide &mdash; read the "
               "pattern, not a single cell)")
    return (f"{_legend()}"
            f"<div class='scroll'><table class='heat'><thead>{head}</thead>"
            f"<tbody>{''.join(body)}</tbody></table></div>"
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
        f"model <b>{escape(model_name)}</b>",
        f"{escape(when)}" if when else "",
        f"temperature {escape(str(temperature))}" if temperature is not None else "",
        f"n={reports[0].n} attack cells/arm" if reports else "",
    ]))
    return f"""\
<main>
  <header class="masthead">
    <p class="eyebrow">Indirect prompt injection &middot; measurement harness</p>
    <h1>injectlab</h1>
    <p class="lede">How often does an attacker get a tool-using agent to
       exfiltrate a secret it was never asked to touch &mdash; and which defenses
       actually move that number?</p>
  </header>
  {banner}
  <p class="meta">{meta}</p>

  <section>
    <h2>By defense <span class="h2note">aggregate</span></h2>
    <p>Primary endpoint is <b>executed</b> (the secret left the environment).
       <b>attempted</b> and <b>structural</b> sit beside it: a defense that merely
       <i>contains</i> a still-fooled model is not the same as one that stops it
       being fooled. Every rate carries a 95% Wilson interval; the paired column
       is an exact McNemar test vs baseline.</p>
    {_bars_chart(reports)}
    {_aggregate_table(reports)}
  </section>

  <section>
    <h2>By technique <span class="h2note">descriptive</span></h2>
    <p>The same paired cells, sliced by injection technique. No paired test runs
       here &mdash; per-cell n is small, so this maps <i>where to look</i>, it does
       not render a verdict.</p>
    {_heatmap(rows)}
  </section>

  <section>
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
  </section>
</main>"""


def _css() -> str:
    # Dark is the BASE (the designed, screenshot-ready look); light is an opt-in
    # override only. Boldness is spent on the green->red heatmap; the chrome is
    # quiet cool-slate with a restrained indigo accent.
    return """\
:root{color-scheme:dark light;
--bg:#0e0f14;--fg:#e8eaf1;--muted:#8a90a2;--line:#23252f;--head:#171922;
--card:#14161d;--accent:#9d8cff;--ok:#49cb84;--bad:#ff6b7a;--shadow:rgba(0,0,0,.45);
--mono:ui-monospace,SFMono-Regular,"Cascadia Mono",Consolas,Menlo,monospace;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
:root[data-theme=light]{color-scheme:light;
--bg:#fbfbfd;--fg:#1b1d24;--muted:#5e6470;--line:#e4e6ec;--head:#f2f3f7;
--card:#f6f7fb;--accent:#5b4bf0;--ok:#1f9d57;--bad:#d1374b;--shadow:rgba(0,0,0,.14)}
:root[data-theme=dark]{color-scheme:dark;
--bg:#0e0f14;--fg:#e8eaf1;--muted:#8a90a2;--line:#23252f;--head:#171922;
--card:#14161d;--accent:#9d8cff;--ok:#49cb84;--bad:#ff6b7a;--shadow:rgba(0,0,0,.45)}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 var(--sans);
-webkit-font-smoothing:antialiased}
main{max-width:980px;margin:0 auto;padding:clamp(28px,5vw,56px) 20px 80px}
.masthead{margin-bottom:22px}
.eyebrow{margin:0 0 10px;font:600 .72rem/1.2 var(--mono);text-transform:uppercase;
letter-spacing:.14em;color:var(--accent)}
h1{font-size:clamp(1.9rem,5vw,2.6rem);line-height:1.02;margin:0 0 12px;
letter-spacing:-.025em;text-wrap:balance;font-weight:720}
.lede{margin:0;color:var(--muted);max-width:60ch;font-size:1.02rem;text-wrap:pretty}
h2{display:flex;align-items:baseline;gap:10px;font-size:1.08rem;margin:42px 0 8px;
padding-bottom:7px;border-bottom:1px solid var(--line);text-wrap:balance}
.h2note{font:600 .62rem/1 var(--mono);text-transform:uppercase;letter-spacing:.1em;
color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:3px 8px}
p{margin:8px 0;max-width:68ch}
b{font-weight:640}
.meta{color:var(--muted);font:.84rem/1.5 var(--mono)}
.banner{padding:12px 15px;border-radius:10px;font-weight:600;margin:16px 0;
border:1px solid transparent}
.banner.sim{background:linear-gradient(180deg,#7c1522,#64101b);color:#ffe9ec;
border-color:#9c2230}
.banner.real{background:linear-gradient(180deg,#13462d,#0f3a26);color:#e6fff1;
border-color:#1c6440}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:12px;
background:var(--card);margin:14px 0}
table{border-collapse:collapse;width:100%;font-size:.9rem}
.agg th,.agg td{border-bottom:1px solid var(--line);padding:11px 13px;
text-align:center;vertical-align:middle}
.agg thead th{background:var(--head);font:600 .66rem/1.2 var(--sans);
text-transform:uppercase;letter-spacing:.07em;color:var(--muted);white-space:nowrap}
.agg tbody tr:last-child td{border-bottom:0}
.agg tbody tr:hover td{background:color-mix(in srgb,var(--accent) 7%,transparent)}
.agg td.arm{text-align:left;font-weight:650;font-family:var(--mono);font-size:.85rem}
.agg td.n,.agg td.pval{font-family:var(--mono);font-variant-numeric:tabular-nums;
color:var(--muted)}
.agg td.primary{box-shadow:inset 3px 0 var(--accent)}
.rate{font:700 1.02rem/1.1 var(--mono);font-variant-numeric:tabular-nums}
.sub{color:var(--muted);font:.7rem/1.2 var(--mono);margin-top:3px;
font-variant-numeric:tabular-nums}
.ok{color:var(--ok);font-weight:700}
.broken{color:var(--bad);font-weight:700}
.legend{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:16px 0 4px;
font:.75rem/1 var(--mono);color:var(--muted)}
.legend .lkey{text-transform:uppercase;letter-spacing:.08em}
.legend .bar{height:10px;width:min(260px,42vw);border-radius:999px;
border:1px solid var(--line)}
.legend .lends{display:flex;justify-content:space-between;
width:min(260px,42vw);gap:12px}
table.heat td,table.heat th{border:1px solid var(--line);padding:11px 8px;
text-align:center}
table.heat thead th,table.heat .rowhead{background:var(--head)}
table.heat thead th{font:600 .66rem/1.2 var(--sans);text-transform:uppercase;
letter-spacing:.06em;color:var(--muted)}
table.heat .rowhead{text-align:left;font-family:var(--mono);font-size:.82rem;
font-weight:650}
td.heat{font:700 .95rem/1.1 var(--mono);font-variant-numeric:tabular-nums;
color:#fff;text-shadow:0 1px 2px var(--shadow)}
.caption{color:var(--muted);font-size:.82rem}
.chart{margin:16px 0}
.barsvg{width:100%;height:auto;display:block;background:var(--card);
border:1px solid var(--line);border-radius:12px;padding:8px 10px 10px}
.barsvg .gx{fill:var(--muted);font:600 9px var(--mono)}
.barsvg .ylabel{fill:var(--fg);font:650 11px var(--mono)}
.barsvg .track{fill:var(--line);opacity:.5}
.barsvg .bar.exec{fill:var(--bad)}
.barsvg .bar.att{fill:var(--accent)}
.barsvg .whisk{stroke:var(--fg);stroke-width:1.4;opacity:.5}
.barsvg .blab{fill:var(--fg);font:700 10px var(--mono)}
.barsvg .blab.on{fill:#fff}
.clegend{display:flex;gap:16px;flex-wrap:wrap;margin:8px 2px 0;
font:.76rem/1.3 var(--mono);color:var(--muted)}
.clegend .sw{display:inline-block;width:11px;height:11px;border-radius:3px;
margin-right:6px;vertical-align:-1px}
.clegend .sw.exec{background:var(--bad)}
.clegend .sw.att{background:var(--accent)}
.clegend .whisknote{opacity:.85}
.limits{padding-left:20px}
.limits li{margin:6px 0;max-width:66ch}
#themer{position:fixed;top:14px;right:14px;z-index:9;background:var(--card);
color:var(--fg);border:1px solid var(--line);border-radius:999px;
padding:7px 14px;font:600 .74rem/1 var(--mono);cursor:pointer}
#themer:hover{border-color:var(--accent)}
#themer:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}"""


# Standalone-only: a dark-default page that can be flipped to light. The embed
# fragment omits this so its host keeps sole control of the theme.
_TOGGLE = (
    "<button id='themer' type='button' "
    "aria-label='Switch between light and dark theme'>Light</button>"
    "<script>(function(){var r=document.documentElement,"
    "b=document.getElementById('themer');"
    "b.addEventListener('click',function(){"
    "var toLight=r.getAttribute('data-theme')!=='light';"
    "r.setAttribute('data-theme',toLight?'light':'dark');"
    "b.textContent=toLight?'Dark':'Light';});})();</script>"
)


def format_html(reports: list[ArmReport], rows: list[BreakdownRow], *,
                model_name: str = "mock", when: str | None = None,
                temperature: float | None = None, standalone: bool = True) -> str:
    """Render one measurement run as HTML.

    standalone=True returns a complete, dark-by-default document (for
    results/report.html) carrying its own light/dark toggle; standalone=False
    returns `<style>...</style>` + body markup, for embedding in a host that
    supplies its own <head>/<body> and theme control (e.g. an Artifact).
    """
    body = _body(reports, rows, model_name=model_name, when=when,
                 temperature=temperature)
    content = f"<style>{_css()}</style>\n{body}"
    if not standalone:
        return content
    title = f"injectlab measurement &mdash; {escape(model_name)}"
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{title}</title></head><body>{_TOGGLE}{content}</body></html>")


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
