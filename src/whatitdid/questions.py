"""Write a question set for a domain we do not ship, and check whether it is any good.

A model will happily produce six questions that read like a methodology section and
measure nothing. The generating is the easy half; the half that matters is refusing to
use the result until it has been tried on real steps.

Only the domain question is generated. The five portable questions are fixed, which keeps
the ask small — name the kinds of move this work is made of — and keeps every generated
set comparable to every other one on those five.

Four checks, each with a threshold taken from what the shipped set does on data it fits
(seven CLI agents, 153 steps, `sre.v1` on operations trajectories):

  answerable     the labeler commits to a top choice        matched: 0.74 - 0.99
  useful         no option is dead, none swallows the run   matched: max share 0.42
  grounded       the label follows the action, not the      matched: 9% of labels move
                 agent's own account of it                  when narration is included
  distinct       two questions are not the same question    matched: |r| below 0.9

A set that fails is reported with the failures, not quietly used. Cheap to run: a sample
of steps, two passes, a few seconds.
"""

from __future__ import annotations

import concurrent.futures as futures
import json
import statistics as st
import urllib.request

from .labeler import ChatModel, QuestionSet, load_question_set

SAMPLE = 40

# "This option is never used" is only meaningful once the sample could plausibly have
# shown it. Below this the check abstains rather than reporting a defect that is really a
# short sample: a run's first dozen steps are all investigation, so repair and verify are
# absent from the window, not from the set.
def _enough_for_dead(n_steps: int, n_options: int) -> bool:
    return n_steps >= max(25, 3 * n_options)


CONFIDENCE_FLOOR = 0.65
DEAD_OPTION = 0.01
DOMINANT_OPTION = 0.60
FLIP_CEILING = 0.25
REDUNDANT = 0.90

PROMPT = """You are naming the kinds of move an AI agent makes while doing a particular \
kind of work. Below are real steps from one such run: the command taken and what came back.

Write the option list for a single multiple-choice question: "What is this step doing?"

Rules:
- Between 6 and 9 options, plus "other" as the last one.
- Every option is a kind of MOVE, not a topic or a quality judgement. "reads a log file"
  is a move; "careful" and "database work" are not.
- The options must be mutually exclusive: a step should fall into exactly one.
- Each option gets one sentence a labeller can apply without knowing this domain.
- Include an option for changing something and an option for checking whether a change
  worked, if this kind of work has them.
- Use the vocabulary of the work itself, not of this prompt.

Return exactly this JSON and nothing else:
{"instructions": "<the question, one sentence>",
 "criteria": {"<option_id>": "<one sentence>", ..., "other": "None of the above."},
 "roles": {"verify": ["<option ids that mean checking a change>"],
           "change": ["<option ids that mean changing something>"]}}

option_id is lowercase, one word, no spaces."""


def spread(turns: list[dict], sample: int) -> list[dict]:
    """Take `sample` steps evenly across the run, keeping order.

    Not the first N: a run opens with investigation and only changes things later, so a
    prefix makes every set look as though it has no repair and no verification.
    """
    if len(turns) <= sample:
        return list(turns)
    step = len(turns) / sample
    return [turns[int(i * step)] for i in range(sample)]


def propose(turns: list[dict], *, model: str = "deepseek-flash", set_id: str = "custom.v1",
            sample: int = 12) -> dict:
    """Draft a question set from real steps. The result is a draft until `check` passes."""
    chat = ChatModel(model=model)
    steps = []
    # Spread, for the same reason check does: drafting from a run's opening produces a
    # vocabulary of nothing but investigation, because that is all the opening contains.
    for row in spread(turns, sample):
        steps.append({
            "actions": [{"tool": a.get("tool"), "args": a.get("args")} for a in (row.get("actions") or [])],
            "result": (row.get("observation") or "")[:400],
        })

    body = {"model": chat.model, "max_tokens": 1600, "thinking": {"type": "disabled"},
            "messages": [{"role": "system", "content": PROMPT},
                         {"role": "user", "content": json.dumps(steps, ensure_ascii=False)}]}
    request = urllib.request.Request(
        chat.base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {chat.api_key}"})
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = json.loads(response.read())
    message = payload["choices"][0]["message"]
    text = (message.get("content") or message.get("reasoning_content") or "")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError(f"the model did not return a question set: {text[:200]}")
    draft = json.loads(text[start:end + 1])

    criteria = draft.get("criteria") or {}
    if len(criteria) < 4:
        raise ValueError(f"only {len(criteria)} options came back; too few to be a vocabulary")
    criteria.setdefault("other", "None of the above.")

    return {
        "_meta": {
            "id": set_id,
            "shares": "_shared",
            "phase_question": "phase",
            "roles": draft.get("roles") or {},
            "note": f"Drafted by {model} from {sample} real steps, then checked with "
                    f"whatitdid questions check. Not frozen until you freeze it.",
        },
        "phase": {"type": "choice",
                  "instructions": draft.get("instructions") or "What is this step doing?",
                  "criteria": criteria},
    }


def _label(labeler, qset: QuestionSet, rows: list[dict], workers: int) -> list[dict]:
    def one(item):
        index, row = item
        base = {"task": "An autonomous agent is working on a task.", "turn": row["turn"],
                "actions": row["actions"], "result": row["observation"],
                "prior_actions": [{"turn": p["turn"], "actions": p["actions"]}
                                  for p in rows[max(0, index - 6): index]]}
        blind = labeler(base, qset.questions)
        if not blind:
            return None
        told = labeler({**base, "agent_said": row["narration"],
                        "agent_reasoning": row["reasoning"]}, qset.questions)
        return {"blind": blind, "told": told}

    with futures.ThreadPoolExecutor(max_workers=workers) as pool:
        return [r for r in pool.map(one, enumerate(rows)) if r]


def check(set_name: str, turns: list[dict], *, labeler=None, sample: int = SAMPLE,
          workers: int = 8) -> dict:
    """Try a set on real steps and say whether it holds up. Four checks, all measured."""
    from .labeler import Jev

    qset = load_question_set(set_name)
    labeler = labeler or Jev()
    rows = spread(turns, sample)
    labelled = _label(labeler, qset, rows, workers)
    if not labelled:
        raise RuntimeError("the labeler answered none of the sampled steps")

    tops = [max(r["blind"]["phase"]["probabilities"].values()) for r in labelled]
    confidence = st.median(tops)

    share: dict[str, float] = {o: 0.0 for o in qset.phases}
    for r in labelled:
        for option, value in r["blind"]["phase"]["probabilities"].items():
            if option in share:
                share[option] += value / len(labelled)

    paired = [r for r in labelled if r["told"]]
    flips = sum(1 for r in paired
                if r["told"]["phase"]["choice"] != r["blind"]["phase"]["choice"])
    flip_rate = flips / len(paired) if paired else 0.0

    nouls = [q for q, spec in qset.questions.items() if spec["type"] == "noul"]
    series = {q: [r["blind"][q]["noul"] for r in labelled] for q in nouls}
    redundant = []
    for i, a in enumerate(nouls):
        for b in nouls[i + 1:]:
            try:
                r = st.correlation(series[a], series[b])
            except st.StatisticsError:
                continue
            if abs(r) >= REDUNDANT:
                redundant.append((a, b, round(r, 2)))

    judged_dead = _enough_for_dead(len(labelled), len(qset.phases))
    dead = [o for o, v in share.items() if v < DEAD_OPTION] if judged_dead else []
    dominant = [o for o, v in share.items() if v > DOMINANT_OPTION]

    problems = []
    if confidence < CONFIDENCE_FLOOR:
        problems.append(("not_answerable",
                         f"top choice median {confidence:.2f}, below {CONFIDENCE_FLOOR}"))
    if dead:
        problems.append(("dead_options", f"never used: {', '.join(dead)}"))
    if dominant:
        problems.append(("dominant_option",
                         f"{dominant[0]} takes {share[dominant[0]]:.0%} of the run"))
    if flip_rate > FLIP_CEILING:
        problems.append(("narration_driven",
                         f"{flip_rate:.0%} of labels move when the agent's own words are shown"))
    if redundant:
        a, b, r = redundant[0]
        problems.append(("redundant", f"{a} and {b} correlate at {r}"))

    return {
        "set": qset.id, "n_steps": len(labelled), "judged_dead_options": judged_dead,
        "confidence": round(confidence, 3),
        "share": {o: round(v, 3) for o, v in sorted(share.items(), key=lambda kv: -kv[1])},
        "flip_rate": round(flip_rate, 3),
        "redundant": redundant,
        "problems": problems,
        "usable": not problems,
    }


def format_check(result: dict, lang: str = "en") -> str:
    head = {"en": f"{result['set']} on {result['n_steps']} real steps",
            "zh": f"{result['set']}，在 {result['n_steps']} 个真实步子上"}[lang]
    labels = {
        "answerable": {"en": "answerable", "zh": "答得出来"},
        "useful": {"en": "every option used", "zh": "选项都用得上"},
        "grounded": {"en": "follows the action", "zh": "跟着动作走"},
        "distinct": {"en": "questions are distinct", "zh": "问题不重复"},
    }
    kinds = {kind for kind, _ in result["problems"]}
    rows = [
        ("answerable", "not_answerable" not in kinds, f"top choice median {result['confidence']:.2f}"),
        ("useful", not ({"dead_options", "dominant_option"} & kinds),
         f"largest option {max(result['share'].values(), default=0):.0%}"
         + ("" if result.get("judged_dead_options", True)
            else {"en": ", too few steps to judge unused options",
                  "zh": "，步数太少，判断不了有没有用不上的选项"}[lang])),
        ("grounded", "narration_driven" not in kinds, f"{result['flip_rate']:.0%} move with narration"),
        ("distinct", "redundant" not in kinds,
         f"{len(result['redundant'])} correlated pairs"),
    ]
    lines = [head]
    for key, ok, detail in rows:
        lines.append(f"  {'ok  ' if ok else 'FAIL'} {labels[key][lang]:<22} {detail}")
    if result["problems"]:
        lines.append({"en": "  not usable yet:", "zh": "  还不能用："}[lang])
        for _, why in result["problems"]:
            lines.append(f"    - {why}")
    return "\n".join(lines)
