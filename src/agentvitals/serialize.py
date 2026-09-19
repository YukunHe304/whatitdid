"""The shape the browser gets.

`Report.to_dict` deliberately carries no step text — it is the record that goes into
summary.jsonl, and a benchmark's worth of observations would make those files enormous.
But a person looking at a timeline needs to see the actual command. This adds it back,
clipped, along with the few things `to_dict` drops because only a human needs them:
which finding each turn belongs to, and whether the agent kept its word on that turn.

Still no display strings. The browser holds the language table and does the wording.
"""

from __future__ import annotations

import json
from typing import Any

WEB_OBSERVATION = 800
WEB_NARRATION = 600
WEB_COMMAND = 300


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def command_of(actions: list[dict]) -> str:
    """One line standing for what the step did.

    Agents name their shell tool six different ways and bury the command under six
    different argument keys, so this looks for the usual suspects before falling back to
    dumping the arguments.
    """
    if not actions:
        return ""
    first = actions[0]
    args = first.get("args") or {}
    for key in ("command", "cmd", "input", "script", "query", "path", "file_path", "pattern"):
        if args.get(key):
            return _clip(str(args[key]), WEB_COMMAND)
    if not args:
        return _clip(str(first.get("tool") or ""), WEB_COMMAND)
    return _clip(json.dumps(args, ensure_ascii=False), WEB_COMMAND)


def to_web_dict(report) -> dict[str, Any]:
    base = report.to_dict()
    rows = {r["turn"]: r for r in report.turns}
    kept = (report.truthfulness or {}).get("per_turn", {}) or {}

    # Which findings point at each turn, so the timeline can mark them without the browser
    # having to re-derive the rules.
    marks: dict[int, list[str]] = {}
    for finding in report.findings.get("findings", []):
        for turn in finding.get("turns", []):
            marks.setdefault(turn, []).append(finding["kind"])

    per_turn = []
    for entry in base["per_turn"]:
        turn = entry["turn"]
        row = rows.get(turn, {})
        probs = entry["phase"]
        top = max(probs, key=probs.get) if probs else None
        observation = row.get("observation") or ""
        narration = row.get("narration") or ""
        per_turn.append({
            **entry,
            "top": top,
            "top_p": probs.get(top) if top else None,
            "tool": (row.get("actions") or [{}])[0].get("tool") if row.get("actions") else None,
            "command": command_of(row.get("actions") or []),
            "n_actions": len(row.get("actions") or []),
            "observation": _clip(observation, WEB_OBSERVATION),
            "observation_len": len(observation),
            "narration": _clip(narration, WEB_NARRATION),
            "narration_len": len(narration),
            "kept_word": kept.get(turn),
            "marks": marks.get(turn, []),
        })

    return {**base, "per_turn": per_turn,
            "truthfulness_per_turn": {str(k): v for k, v in kept.items()}}


def to_summary_row(rep, **extra) -> dict[str, Any]:
    """One line of summary.jsonl.

    Drops `per_turn` entirely. It was embedded before, which made a 21-problem summary file
    carry every label for every step — fine at that size, unworkable at benchmark scale, and
    `compare` never reads it.

    The first parameter is `rep`, not `report`: callers pass `report="x.html"` as extra.
    """
    row = rep.to_dict()
    row.pop("per_turn", None)
    row.update(extra)
    return row
