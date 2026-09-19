"""Rebuild the bundled demo data from the original research run.

The demo has to work with no API key, so the labels are baked in. They are real Jev
labels from 2026-09-19, not fabricated: seven CLI agents on the same SRE problem
(`service_port_conflict_hotel_reservation`), 153 steps, each labelled twice — once from
the actions alone and once with the agent's own narration added.

This is a build script, not part of the package. It reads from a local research directory
that is not in this repository; the output it produces is committed.

    python scripts/build_demo.py
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from whatitdid.core import Report  # noqa: E402
from whatitdid.findings import findings  # noqa: E402
from whatitdid.labeler import load_question_set  # noqa: E402

RESEARCH = pathlib.Path("/Users/yukun/Documents/ChatGPT/research/output/sregym-traj-profile-20260919")
OUT = pathlib.Path(__file__).resolve().parent.parent / "src" / "whatitdid" / "data" / "demo"

# The stats keys the original run wrote, before ids were stabilised.
LEGACY_STATS = {
    "验具体怀疑": "hypothesis_driven", "带来新信息": "new_information", "在重看": "revisits",
    "改动系统": "changes_system", "瞄得多准": "targeting", "标注器把握": "labeler_confidence",
}
# Headlines were baked strings then; map them back to the kind that produced them.
LEGACY_FINDING = {
    "在重看": "waste", "整条轨迹几乎没有": "blind_spot", "处改动之后": "unverified_change",
    "不像调查动作": "plumbing", "不是在验证任何具体怀疑": "drift",
}


def read_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def build_agents() -> dict:
    """One profile per agent, all on the same problem — the cross-agent view."""
    turns = json.loads((RESEARCH / "turns.json").read_text(encoding="utf-8"))
    labels = read_jsonl(RESEARCH / "labels.jsonl")
    truthful = read_jsonl(RESEARCH / "labels_truthful.jsonl")
    qset = load_question_set("sre.v1")

    blind = {(r["agent"], r["turn"]): r["answers"] for r in labels if r["narration"] is False}
    told = {(r["agent"], r["turn"]): r["answers"] for r in labels if r["narration"] is True}
    intent = {(r["agent"], r["turn"]): r["answers"] for r in truthful}

    out = {}
    for agent in sorted({t["agent"] for t in turns}):
        rows = [t for t in turns if t["agent"] == agent]
        rows.sort(key=lambda r: r["turn"])
        model = next((r.get("model") for r in rows if r.get("model")), None)

        paired = [{"turn": r["turn"], "answers": blind[(agent, r["turn"])],
                   "answers_with_narration": told.get((agent, r["turn"]))}
                  for r in rows if (agent, r["turn"]) in blind]

        stated = carried = 0
        per_turn: dict[int, bool] = {}
        for r in rows:
            answers = intent.get((agent, r["turn"]))
            if not answers or answers["states_intent"]["noul"] <= 0.5:
                continue
            stated += 1
            kept = answers["carried_out"]["noul"] > 0.5
            per_turn[r["turn"]] = kept
            carried += kept

        rep = Report(
            agent=agent, model=model, source=f"demo/{agent}",
            turns=[{k: r.get(k, "") for k in ("turn", "actions", "observation", "narration", "reasoning")}
                   for r in rows],
            labels=paired,
            truthfulness={"stated": stated, "carried": carried,
                          "rate": carried / stated if stated else None, "per_turn": per_turn},
            findings=findings(paired, phases=qset.phases, roles=qset.roles),
            labeler="jev", questions="sre.v1", phases=qset.phases, label_failures={},
        )
        out[agent] = rep.to_web_dict()
        print(f"  {agent:12} {out[agent]['n_turns']:>3} steps  "
              f"said-and-did {carried}/{stated}  {len(out[agent]['findings'])} findings")
    return out


def modernise(row: dict) -> dict:
    """An old summary.jsonl row in the current schema."""
    out = dict(row)
    out["n_turns"] = out.pop("turns", 0)
    out["stats"] = {LEGACY_STATS.get(k, k): v for k, v in (out.get("stats") or {}).items()}
    out.setdefault("questions", "sre.v1")
    out.setdefault("phases", ["survey", "localize", "inspect", "probe", "repair", "verify",
                              "report", "other"])
    rebuilt = []
    for finding in out.get("findings") or []:
        kind = finding.get("kind")
        if not kind:
            headline = finding.get("headline", "")
            kind = next((v for k, v in LEGACY_FINDING.items() if k in headline), "waste")
        rebuilt.append({"kind": kind, "severity": finding.get("severity", 0.0),
                        "turns": finding.get("turns", []),
                        "facts": finding.get("facts") or
                        ({"count": finding["n"], "total": out["n_turns"]} if "n" in finding else {})})
    out["findings"] = rebuilt
    out.pop("per_turn", None)
    return out


def build_compare() -> dict:
    """The two rounds that motivate the whole tool: same 21 problems, effort high vs max."""
    sides = {}
    for name, folder in (("before", "watch_high"), ("after", "watch_demo")):
        rows = read_jsonl(RESEARCH / folder / "summary.jsonl")
        sides[name] = {r["problem"]: modernise(r) for r in rows}
        print(f"  {name:7} {folder:12} {len(rows)} problems")
    return sides


def main() -> int:
    if not RESEARCH.exists():
        print(f"research directory not found: {RESEARCH}", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)

    print("agents (cross-agent view):")
    agents = build_agents()
    (OUT / "agents.json").write_text(json.dumps(agents, ensure_ascii=False), encoding="utf-8")

    print("compare (two rounds of the same config):")
    sides = build_compare()
    (OUT / "compare.json").write_text(json.dumps(sides, ensure_ascii=False), encoding="utf-8")

    for name in ("agents.json", "compare.json"):
        print(f"  {name:16} {(OUT / name).stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
