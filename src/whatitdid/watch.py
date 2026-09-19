"""Profile each task as the benchmark finishes it, instead of waiting for the whole run.

Not a single line of the benchmark changes. This watches the disk: a `*_results.csv`
appearing in a run directory means that task is done and its session file is on disk.
Profiling is pure network I/O — it touches neither the cluster nor a GPU — so it runs
alongside the next task rather than after it.

One task takes about six seconds at ten-way concurrency while the task itself takes
minutes, so the only wall-clock the whole round pays is the last task's few seconds.
Measured: 21 problems profiled in 4m47s against a benchmark that ran for 4.2 hours.
"""

from __future__ import annotations

import concurrent.futures as futures
import html
import json
import pathlib
import sys
import threading
import time

from .core import profile
from .i18n import DEFAULT_LANG, finding_headline, phase_name, ui
from .report import color_for
from .serialize import to_summary_row

DONE_MARKER = "*_results.csv"
SKIP_DIRS = {"steps", "trajectory", "__pycache__"}


def session_in(run_dir: pathlib.Path) -> pathlib.Path | None:
    """Which file in this run directory is the agent's session log. The converter decides."""
    from .formats import detect_agent

    candidates = []
    for path in run_dir.rglob("*"):
        if not path.is_file() or path.suffix not in {".json", ".jsonl"}:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(run_dir).parts[:-1]):
            continue
        if path.name.endswith("_results.csv") or "results_" in path.name:
            continue
        candidates.append(path)
    for path in sorted(candidates, key=lambda p: -p.stat().st_size):
        try:
            detect_agent(path)
            return path
        except Exception:  # noqa: BLE001
            continue
    return None


def finished_runs(root: pathlib.Path) -> list[tuple[str, pathlib.Path]]:
    """Tasks that are done: the directory already holds that task's results CSV."""
    out = []
    for csv in root.rglob(DONE_MARKER):
        if csv.name.endswith("_ALL_results.csv"):  # whole-suite rollup, not a per-task signal
            continue
        run_dir = csv.parent
        problem = run_dir.name if not run_dir.name.startswith("run") else run_dir.parent.name
        out.append((problem, run_dir))
    # A task can have results CSVs at both the problem and the run_N level; take the deepest,
    # because that is where the session file lives.
    deepest: dict[str, pathlib.Path] = {}
    for problem, run_dir in out:
        if problem not in deepest or len(run_dir.parts) > len(deepest[problem].parts):
            deepest[problem] = run_dir
    return sorted(deepest.items())


def index_html(rows: list[dict], root: str, started: float, lang: str = DEFAULT_LANG) -> str:
    esc = html.escape
    rows = sorted(rows, key=lambda r: r["problem"])
    phases: list[str] = []
    for row in rows:
        for phase in row.get("mix", {}):
            if phase not in phases:
                phases.append(phase)

    def bar(mix, width=160):
        return "".join(
            f'<span style="display:inline-block;height:12px;width:{mix[p]*width:.1f}px;'
            f'background:{color_for(p, phases)}" title="{esc(phase_name(p, lang))} {mix[p]*100:.0f}%"></span>'
            for p in phases if mix.get(p, 0) > 0.01)

    body = ""
    for r in rows:
        rate = r.get("truthfulness")
        cell = f"{rate:.0%}" if rate is not None else "—"
        cls = "bad" if rate is not None and rate < 0.65 else ""
        finds = "".join(f'<span class="f">{esc(finding_headline(f, lang))}</span>'
                        for f in r.get("findings", [])[:3])
        body += (f'<tr><td><a href="{esc(r["report"])}">{esc(r["problem"])}</a></td>'
                 f'<td class="num">{r.get("n_turns", 0)}</td>'
                 f'<td>{bar(r.get("mix", {}))}</td>'
                 f'<td class="num {cls}">{cell}</td>'
                 f'<td class="finds">{finds}</td></tr>')

    n = len(rows)
    total_turns = sum(r.get("n_turns", 0) for r in rows)
    truth = [r["truthfulness"] for r in rows if r.get("truthfulness") is not None]
    avg_truth = f"{sum(truth)/len(truth):.0%}" if truth else "—"
    legend = "".join(f'<span class="key"><i style="background:{color_for(p, phases)}"></i>'
                     f'{esc(phase_name(p, lang))}</span>' for p in phases)
    elapsed = (time.time() - started) / 60
    title = ui("index_title", lang)
    refresh = {"en": "page refreshes every 30s", "zh": "页面每 30 秒自动刷新"}[lang]
    foot = {"en": "Profiling runs alongside the benchmark and uses no cluster time.",
            "zh": "体检与 benchmark 并行，不占集群。"}[lang]
    return f"""<!DOCTYPE html><html lang="{lang}"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="30">
<title>{esc(title)}</title><style>
:root{{--bg:#fbfaf8;--fg:#23201c;--mut:#6b655d;--line:#e6e1d8;--card:#fff}}
@media(prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#171614;--fg:#eae6de;--mut:#9a9389;--line:#2e2b26;--card:#1f1d1a}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}
.wrap{{max-width:1080px;margin:0 auto;padding:36px 16px 70px}}
h1{{font-size:22px;margin:0 0 4px}}.sub{{color:var(--mut);font-size:13px;margin-bottom:24px}}
.cards{{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:22px}}
.card{{flex:1 1 130px;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 14px}}
.card b{{display:block;font-size:20px}}.card span{{font-size:12px;color:var(--mut)}}
.legend{{display:flex;flex-wrap:wrap;gap:11px;font-size:12px;color:var(--mut);margin-bottom:16px}}
.key i{{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px}}
table{{width:100%;border-collapse:collapse}}
th{{text-align:left;font-size:12px;color:var(--mut);font-weight:600;padding:6px 8px;border-bottom:1px solid var(--line)}}
td{{padding:9px 8px;border-bottom:1px solid var(--line);vertical-align:top}}
td a{{color:inherit}}.num{{text-align:right;white-space:nowrap}}.bad{{color:#c0797c;font-weight:600}}
.finds{{font-size:12px;color:var(--mut)}}.f{{display:block}}
.foot{{margin-top:26px;font-size:12px;color:var(--mut)}}
</style><div class="wrap">
<h1>{esc(title)}</h1>
<div class="sub">{esc(root)} · {n} · {refresh}</div>
<div class="cards">
<div class="card"><b>{n}</b><span>{esc(ui("problems", lang))}</span></div>
<div class="card"><b>{total_turns}</b><span>{esc(ui("total_steps", lang))}</span></div>
<div class="card"><b>{avg_truth}</b><span>{esc(ui("avg_truthfulness", lang))}</span></div>
<div class="card"><b>{sum(len(r.get("findings", [])) for r in rows)}</b><span>{esc(ui("total_findings", lang))}</span></div>
<div class="card"><b>{elapsed:.0f}</b><span>{esc(ui("elapsed_min", lang))}</span></div>
</div>
<div class="legend">{legend}</div>
<table><tr><th>{esc(ui("problem", lang))}</th><th class="num">{esc(ui("steps", lang))}</th>
<th>{esc(ui("where_steps_went", lang))}</th><th class="num">{esc(ui("avg_truthfulness", lang))}</th>
<th>{esc(ui("main_issues", lang))}</th></tr>
{body}</table>
<div class="foot">{foot}</div>
</div></html>"""


def run(args) -> int:
    from .cli import make_labeler

    labeler = make_labeler(args)
    lang = getattr(args, "lang", DEFAULT_LANG)
    check_narration = not getattr(args, "no_narration_check", False)
    args.out.mkdir(parents=True, exist_ok=True)
    summary_path = args.out / "summary.jsonl"
    seen: set[str] = set()
    rows: list[dict] = []
    if summary_path.exists():
        for line in summary_path.open():
            if not line.strip():
                continue
            row = json.loads(line)
            seen.add(row["problem"])
            rows.append(row)
    lock = threading.Lock()
    started = time.time()

    def handle(problem: str, run_dir: pathlib.Path) -> None:
        session = session_in(run_dir)
        if session is None:
            print(f"  {problem}: no recognisable session file, skipping", file=sys.stderr)
            return
        t0 = time.monotonic()
        try:
            rep = profile(session, labeler=labeler, questions=args.questions, task=args.task,
                          workers=args.concurrency, check_narration=check_narration)
            rep.to_html(args.out / f"{problem}.html", title=ui("report_title", lang, agent=problem),
                        lang=lang)
            summary = to_summary_row(rep, report=f"{problem}.html", problem=problem,
                                     seconds=round(time.monotonic() - t0, 1))
        except Exception as exc:  # noqa: BLE001  a failed checkup must never affect the benchmark
            print(f"  {problem}: checkup failed, {type(exc).__name__}: {exc}", file=sys.stderr)
            return
        with lock:
            rows.append(summary)
            with summary_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(summary, ensure_ascii=False) + "\n")
            (args.out / "index.html").write_text(index_html(rows, str(args.root), started, lang),
                                                 encoding="utf-8")
        rate = summary.get("truthfulness")
        print(f"  ok {problem}  {summary['n_turns']} steps  {summary['seconds']}s  "
              f"said-and-did {f'{rate:.0%}' if rate is not None else '—'}  "
              f"{len(summary['findings'])} findings", file=sys.stderr)

    print(f"watching {args.root}, writing reports to {args.out}", file=sys.stderr)
    pool = futures.ThreadPoolExecutor(max_workers=args.parallel_tasks)
    try:
        while True:
            for problem, run_dir in finished_runs(args.root):
                if problem in seen:
                    continue
                seen.add(problem)
                print(f"  -> {problem} finished, profiling", file=sys.stderr)
                pool.submit(handle, problem, run_dir)
            if args.once:
                break
            time.sleep(args.poll)
    except KeyboardInterrupt:
        print("\nstopping; finishing the checkups already in flight…", file=sys.stderr)
    pool.shutdown(wait=True)
    if rows:
        (args.out / "index.html").write_text(index_html(rows, str(args.root), started, lang),
                                             encoding="utf-8")
        print(f"\n{len(rows)} reports and an index at {args.out / 'index.html'}", file=sys.stderr)
    return 0
