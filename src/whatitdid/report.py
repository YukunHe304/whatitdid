"""One Report, one self-contained HTML page.

No scripts, no external assets, no fonts to fetch — a report has to still open in two years
from a directory someone tarred up, and it has to open with the network off. The web app is
the richer view; this is the one you can email.
"""

from __future__ import annotations

import html

from .fit import explain
from .i18n import DEFAULT_LANG, finding_headline, metric_name, phase_name, ui
from .serialize import command_of

# Named colours for the shipped vocabularies; anything else cycles through the spares, so a
# question set we have never seen still renders sensibly.
BAR_COLORS = {"survey": "#7c9cbf", "localize": "#6aa9a0", "inspect": "#d4a06a", "probe": "#c0797c",
              "repair": "#a88bc4", "verify": "#7fb27a", "report": "#c9b073", "other": "#9a9a9a",
              "read": "#d4a06a", "reproduce": "#c0797c", "edit": "#a88bc4", "test": "#7fb27a",
              "revert": "#b08968"}
SPARE_COLORS = ["#7c9cbf", "#6aa9a0", "#d4a06a", "#c0797c", "#a88bc4", "#7fb27a", "#c9b073"]

WASTE_REVISIT = 0.6
WASTE_NEW_INFO = 0.45
CHANGED = 0.5
UNSURE = 0.45


def color_for(phase: str, order: list[str]) -> str:
    if phase in BAR_COLORS:
        return BAR_COLORS[phase]
    return SPARE_COLORS[order.index(phase) % len(SPARE_COLORS)] if phase in order else "#9a9a9a"


def render(rep, title: str, summary: str = "", lang: str = DEFAULT_LANG) -> str:
    report, rows, labels = rep.findings, rep.turns, rep.labels
    agent, model, truth = rep.agent, rep.model, rep.truthfulness
    phases = rep.phases or list(report["mix"])
    by_turn = {r["turn"]: r for r in labels}
    esc = html.escape

    def bar(mix):
        cells = "".join(
            f'<div class="seg" style="width:{mix[p]*100:.2f}%;background:{color_for(p, phases)}" '
            f'title="{esc(phase_name(p, lang))} {mix[p]*100:.0f}%"></div>'
            for p in phases if mix.get(p, 0) > 0.004)
        legend = "".join(
            f'<span class="key"><i style="background:{color_for(p, phases)}"></i>'
            f'{esc(phase_name(p, lang))} {mix[p]*100:.0f}%</span>'
            for p in phases if mix.get(p, 0) >= 0.02)
        return f'<div class="bar">{cells}</div><div class="legend">{legend}</div>'

    cards = ""
    for f in report["findings"]:
        anchors = "".join(f'<a href="#t{t}">{t}</a>' for t in f["turns"][:40])
        more = "…" if len(f["turns"]) > 40 else ""
        cards += (f'<div class="finding"><div class="h">{esc(finding_headline(f, lang))}</div>'
                  f'{f"<div class=turns>{anchors}{more}</div>" if anchors else ""}</div>')

    timeline = ""
    for row in rows:
        lab = by_turn.get(row["turn"])
        if not lab:
            continue
        a = lab["answers"]
        dist = a["phase"]["probabilities"]
        top = sorted(dist.items(), key=lambda x: -x[1])[:2]
        chips = "".join(
            f'<span class="chip" style="background:{color_for(p, phases)}22;'
            f'border-color:{color_for(p, phases)}">{esc(phase_name(p, lang))} {v*100:.0f}%</span>'
            for p, v in top if v > 0.08)
        flags = []
        if a["revisits"]["noul"] > WASTE_REVISIT and a["new_information"]["noul"] < WASTE_NEW_INFO:
            flags.append((ui("flag_waste", lang), "warn"))
        if a["changes_system"]["noul"] > CHANGED:
            flags.append((ui("flag_changed", lang), "warn"))
        if max(dist.values()) < UNSURE:
            flags.append((ui("flag_other", lang), "warn"))
        told = lab.get("answers_with_narration")
        if told and told["phase"]["choice"] != a["phase"]["choice"]:
            kept = truth.get("per_turn", {}).get(row["turn"])
            note = f' ({ui("kept_word", lang)})' if kept is True else \
                   f' ({ui("broke_word", lang)})' if kept is False else ""
            flags.append((f'{ui("flag_narration", lang)} → '
                          f'{phase_name(told["phase"]["choice"], lang)}{note}', "narr"))
        flag_html = "".join(f'<span class="flag {cls}">{esc(text)}</span>' for text, cls in flags)
        timeline += (f'<div class="turn" id="t{row["turn"]}"><div class="n">{row["turn"]}</div>'
                     f'<div class="body"><div class="cmd">{esc(command_of(row["actions"]))}</div>'
                     f'<div class="chips">{chips}{flag_html}</div></div></div>')

    stats = "".join(
        f'<div class="stat"><b>{v:.2f}</b><span>{esc(metric_name(k, lang))}</span></div>'
        for k, v in report["stats"].items())

    if truth.get("rate") is None:
        trust_html = f'<div class="trust">{esc(ui("trust_none", lang))}</div>'
    else:
        rate = truth["rate"]
        judge = ui("trust_high", lang) if rate >= 0.8 else \
            ui("trust_mid", lang) if rate >= 0.65 else ui("trust_low", lang)
        trust_html = (
            f'<div class="trust"><b>{esc(metric_name("truthfulness", lang))} {rate:.0%}</b> — '
            f'{esc(ui("trust_line", lang, stated=truth["stated"], carried=truth["carried"], rate=rate))} '
            f'{esc(judge)}.</div>')

    misfit = explain(rep.fit, rep.questions, lang) if rep.fit else None
    misfit_html = (f'<div class="trust" style="border-left-color:#c9b073">{esc(misfit)}</div>'
                   if misfit else "")

    failed = (rep.label_failures or {}).get("total", 0)
    failed_html = ""
    if failed:
        note = {"en": f"{failed} label calls failed and those steps are missing from this report.",
                "zh": f"有 {failed} 次标注调用失败，这些步子没有进入本报告。"}[lang]
        failed_html = f'<div class="trust" style="border-left-color:#c0797c">{esc(note)}</div>'

    subline = (f'{esc(agent)}{f" · {esc(model)}" if model else ""} · '
               f'{report["n_turns"]} {esc(ui("steps", lang))} · {esc(rep.labeler)} · '
               f'{esc(ui("questions", lang))} {esc(rep.questions)}')

    return f"""<!DOCTYPE html><html lang="{lang}"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><style>
:root{{--bg:#fbfaf8;--fg:#23201c;--mut:#6b655d;--line:#e6e1d8;--card:#fff}}
@media(prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#171614;--fg:#eae6de;--mut:#9a9389;--line:#2e2b26;--card:#1f1d1a}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB",sans-serif}}
.wrap{{max-width:880px;margin:0 auto;padding:40px 16px 80px}}
h1{{font-size:24px;margin:0 0 4px}}.sub{{color:var(--mut);font-size:13px;margin-bottom:28px}}
.summary{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px 20px;margin-bottom:26px}}
.bar{{display:flex;height:26px;border-radius:6px;overflow:hidden;margin:14px 0 8px}}
.seg{{height:100%}}.legend{{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--mut);margin-bottom:26px}}
.key i{{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px}}
.stats{{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:28px}}
.stat{{flex:1 1 110px;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:11px 13px}}
.stat b{{display:block;font-size:19px}}.stat span{{font-size:12px;color:var(--mut)}}
h2{{font-size:15px;margin:32px 0 12px;color:var(--mut);font-weight:600}}
.finding{{background:var(--card);border:1px solid var(--line);border-left:3px solid #c0797c;
border-radius:8px;padding:13px 16px;margin-bottom:9px}}
.finding .h{{font-weight:600}}.turns{{font-size:12px;color:var(--mut);margin-top:5px}}
.turns a{{color:inherit;text-decoration:none;border-bottom:1px dotted var(--mut);margin-right:5px}}
.turn{{display:flex;gap:12px;padding:9px 0;border-bottom:1px solid var(--line)}}
.turn .n{{flex:0 0 28px;color:var(--mut);font-size:12px;text-align:right;padding-top:2px}}
.turn .body{{flex:1;min-width:0}}
.cmd{{font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;
word-break:break-all;color:var(--fg);opacity:.85}}
.chips{{margin-top:5px;display:flex;flex-wrap:wrap;gap:5px}}
.chip,.flag{{font-size:11px;padding:1px 7px;border-radius:10px;border:1px solid}}
.flag.warn{{background:#c0797c22;border-color:#c0797c}}
.flag.narr{{background:#7c9cbf22;border-color:#7c9cbf;color:var(--mut)}}
.trust{{background:var(--card);border:1px solid var(--line);border-left:3px solid #7c9cbf;
border-radius:8px;padding:13px 16px;margin-bottom:22px;font-size:13px}}
.trust b{{font-size:17px}}
.foot{{margin-top:36px;font-size:12px;color:var(--mut);border-top:1px solid var(--line);padding-top:14px}}
</style><div class="wrap">
<h1>{esc(title)}</h1>
<div class="sub">{subline}</div>
{f'<div class="summary">{esc(summary)}</div>' if summary else ''}
{misfit_html}{failed_html}{trust_html}
<h2>{esc(ui("where_steps_went", lang))}</h2>{bar(report['mix'])}
<div class="stats">{stats}</div>
<h2>{esc(ui("worth_acting_on", lang))}</h2>{cards or f'<div class="finding"><div class="h">{esc(ui("nothing_found", lang))}</div></div>'}
<h2>{esc(ui("step_by_step", lang))}</h2>{timeline}
<div class="foot">{esc(ui("foot", lang))}</div></div></html>"""
