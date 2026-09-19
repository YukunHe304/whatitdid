"""Command line: profile one run, profile a benchmark as it goes, compare two rounds."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

from .compare import compare, format_compare
from .core import DEFAULT_TASK, profile
from .i18n import DEFAULT_LANG, LANGS, finding_headline, metric_name
from .labeler import ChatModel, Jev


def make_labeler(args):
    if args.labeler == "jev":
        return Jev(model=args.jev_model)
    return ChatModel(model=args.chat_model, thinking=args.thinking)


def add_labeler_args(ap):
    ap.add_argument("--labeler", choices=["jev", "chat"], default="jev")
    ap.add_argument("--jev-model", default="jev-latest")
    ap.add_argument("--chat-model", default="deepseek-flash")
    ap.add_argument("--thinking", action="store_true",
                    help="let the chat model think (12x slower, not obviously better labels)")
    ap.add_argument("--questions", default="sre.v1", help="question set name or path")
    ap.add_argument("--task", default=DEFAULT_TASK)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--no-narration-check", action="store_true",
                    help="skip the narration pass and the said-and-did check; halves the calls")


def add_lang(ap):
    ap.add_argument("--lang", choices=list(LANGS), default=DEFAULT_LANG)


def load_summary(path: pathlib.Path) -> dict:
    """A summary.jsonl, or a directory that contains one."""
    if path.is_dir():
        path = path / "summary.jsonl"
    out = {}
    for line in path.open():
        if not line.strip():
            continue
        row = json.loads(line)
        key = row.get("problem") or row.get("task") or pathlib.Path(row.get("source", "")).stem
        out[key] = row
    return out


def cmd_run(args) -> int:
    out = args.out or pathlib.Path(f"{args.session.stem}_report.html")
    started = time.monotonic()
    rep = profile(args.session, labeler=make_labeler(args), questions=args.questions, task=args.task,
                  workers=args.concurrency, check_narration=not args.no_narration_check,
                  progress=lambda d, n: print(f"\r  {d}/{n}", end="", file=sys.stderr))
    print("", file=sys.stderr)
    summary = "" if args.no_prose else write_summary(rep, args)
    rep.to_html(out, title=args.title, summary=summary, lang=args.lang)
    if args.json:
        rep.to_json(args.json)
    d = rep.to_dict()
    print(f"{out}  ({rep.agent}, {d['n_turns']} steps, {time.monotonic()-started:.0f}s)", file=sys.stderr)
    if d["truthfulness"] is not None:
        print(f"  {metric_name('truthfulness', args.lang)} {d['truthfulness']:.0%} "
              f"({d['carried']}/{d['stated']})", file=sys.stderr)
    failed = (d.get("label_failures") or {}).get("total", 0)
    if failed:
        print(f"  {failed} label calls failed: {d['label_failures']['by_cause']}", file=sys.stderr)
    for f in d["findings"]:
        print(f"  - {finding_headline(f, args.lang)}", file=sys.stderr)
    return 0


def write_summary(rep, args) -> str:
    """The numbers come from the labeler; a chat model only puts them into a sentence."""
    try:
        model = ChatModel(model=args.chat_model)
    except Exception:  # noqa: BLE001  no chat key configured is not an error here
        return ""
    d = rep.to_dict()
    facts = {"agent": d["agent"], "model": d["model"], "steps": d["n_turns"],
             "behaviour_mix": {k: round(v, 2) for k, v in d["mix"].items()},
             "metrics": {k: round(v, 2) for k, v in d["stats"].items()},
             "findings": [finding_headline(f, "en") for f in d["findings"]]}
    if d["truthfulness"] is not None:
        facts["said_and_did"] = f"{d['carried']}/{d['stated']} = {d['truthfulness']:.0%}"
    return _chat(model, facts, args.lang)


PROSE_PROMPT = {
    "en": "You are writing the opening note of a checkup on one AI agent run. Three or four "
          "sentences, plain English, no jargon. Do not restate the numbers. Say what this run's "
          "character was and the single thing most worth fixing. No bullet points, no preamble.",
    "zh": "你在给一次 AI agent 的运行写体检小结。用中文，三到四句，白话，不用术语，"
          "不要复述数字，要说出这次运行的性格和最该改的一件事。不分点，不客套。",
}


def _chat(model: ChatModel, facts: dict, lang: str) -> str:
    import urllib.request
    body = {"model": model.model, "max_tokens": 700, "thinking": {"type": "disabled"},
            "messages": [{"role": "system", "content": PROSE_PROMPT.get(lang, PROSE_PROMPT["en"])},
                         {"role": "user", "content": json.dumps(facts, ensure_ascii=False)}]}
    request = urllib.request.Request(
        model.base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {model.api_key}"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read())
        message = payload["choices"][0]["message"]
        return (message.get("content") or message.get("reasoning_content") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def cmd_compare(args) -> int:
    repeats = [load_summary(p) for p in (args.repeat or [])]
    result = compare(load_summary(args.before), load_summary(args.after), seed=args.seed,
                     repeats=repeats or None)
    print(format_compare(result, args.lang))
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    return 0


def cmd_serve(args) -> int:
    from .server import serve
    return serve(host=args.host, port=args.port, lang=args.lang, open_browser=not args.no_browser,
                 reports_dir=args.reports, demo_only=False)


def cmd_demo(args) -> int:
    from .server import serve
    return serve(host=args.host, port=args.port, lang=args.lang, open_browser=not args.no_browser,
                 reports_dir=None, demo_only=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="agentvitals", description="See what an agent run actually did, not just its score.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="profile one trajectory")
    run.add_argument("session", type=pathlib.Path)
    run.add_argument("--out", type=pathlib.Path)
    run.add_argument("--json", type=pathlib.Path, help="also write the machine-readable JSON")
    run.add_argument("--title")
    run.add_argument("--no-prose", action="store_true", help="skip the written summary")
    add_labeler_args(run)
    add_lang(run)
    run.set_defaults(func=cmd_run)

    watch = sub.add_parser("watch", help="profile each task as the benchmark finishes it")
    watch.add_argument("root", type=pathlib.Path)
    watch.add_argument("--out", type=pathlib.Path, required=True)
    watch.add_argument("--poll", type=int, default=15)
    watch.add_argument("--parallel-tasks", type=int, default=2)
    watch.add_argument("--once", action="store_true")
    add_labeler_args(watch)
    add_lang(watch)
    watch.set_defaults(func=lambda a: __import__("agentvitals.watch", fromlist=["run"]).run(a))

    cmp_ = sub.add_parser("compare", help="two rounds: what did the change actually change")
    cmp_.add_argument("before", type=pathlib.Path)
    cmp_.add_argument("after", type=pathlib.Path)
    cmp_.add_argument("--repeat", type=pathlib.Path, action="append",
                      help="another run of the SAME config as 'before'; repeat the flag. "
                           "Used to measure the repeat-noise floor from your own runs.")
    cmp_.add_argument("--json", type=pathlib.Path)
    cmp_.add_argument("--seed", type=int, default=0)
    add_lang(cmp_)
    cmp_.set_defaults(func=cmd_compare)

    serve_ = sub.add_parser("serve", help="open the web app in a browser")
    serve_.add_argument("--host", default="127.0.0.1")
    serve_.add_argument("--port", type=int, default=8321)
    serve_.add_argument("--reports", type=pathlib.Path, help="a directory of existing reports to load")
    serve_.add_argument("--no-browser", action="store_true")
    add_lang(serve_)
    serve_.set_defaults(func=cmd_serve)

    demo = sub.add_parser("demo", help="open the web app on bundled sample data — no API key needed")
    demo.add_argument("--host", default="127.0.0.1")
    demo.add_argument("--port", type=int, default=8321)
    demo.add_argument("--no-browser", action="store_true")
    add_lang(demo)
    demo.set_defaults(func=cmd_demo)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
