"""Guess which question set a trajectory wants, and show the evidence for the guess.

The domain question is the one thing that has to match the work. Choosing it silently is
the failure this module exists to avoid: a coding run labelled with the operations set
produces a page of "probe" and "repair" that reads perfectly and means nothing.

So this never decides alone. It reports what it saw — the actual commands it matched — and
the caller shows that to the person before anything is labelled. A guess with its evidence
attached is something you can disagree with; a silent default is not.

Deliberately dumb: substring counts over the commands, no model call, no network, runs in
milliseconds on a trajectory already in memory. A cleverer detector would be harder to
argue with, which is the wrong direction for something whose whole job is to be checkable.
"""

from __future__ import annotations

import collections
import re

# Words that only show up when someone is doing that kind of work. Kept narrow on purpose:
# a marker that fires on both domains tells us nothing, so `git` is absent (people run it
# everywhere) while `pytest` and `kubectl` are not.
MARKERS: dict[str, list[str]] = {
    "sre.v1": [
        "kubectl", "helm", "istioctl", "journalctl", "systemctl", "docker ", "crictl",
        "namespace", "kube-system", "deployment/", "statefulset", "configmap",
        "get pods", "describe pod", "rollout", "prometheus", "grafana",
    ],
    "code.v1": [
        "pytest", "npm test", "npm run", "cargo ", "go test", "tox", "jest", "mocha",
        "make test", "unittest", "git diff", "git apply", "patch -p", "pip install -e",
        "def ", "import ", "class ", "traceback", "assertionerror", "lint", "mypy", "ruff",
    ],
}

MINIMUM_HITS = 3        # one stray word is not a domain
MARGIN = 1.6            # the winner must be clearly ahead, not ahead by a nose


def sniff(turns: list[dict], *, sample: int = 200) -> dict:
    """Which set the commands look like, with the matches that led there.

    Returns `pick` of None when the evidence does not separate the candidates, which is a
    real answer: better to ask than to choose badly.
    """
    haystack = []
    for row in turns[:sample]:
        for action in row.get("actions") or []:
            haystack.append(str(action.get("tool", "")).lower())
            haystack.extend(str(v).lower() for v in (action.get("args") or {}).values())
    text = "\n".join(haystack)

    evidence: dict[str, dict[str, int]] = {}
    for name, markers in MARKERS.items():
        hits = {m: text.count(m) for m in markers}
        evidence[name] = {m: n for m, n in sorted(hits.items(), key=lambda kv: -kv[1]) if n}

    totals = {name: sum(hits.values()) for name, hits in evidence.items()}
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])
    best, best_n = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0

    decided = best_n >= MINIMUM_HITS and best_n >= max(1, runner_up) * MARGIN
    return {
        "pick": best if decided else None,
        "scores": totals,
        "evidence": {name: dict(list(hits.items())[:5]) for name, hits in evidence.items()},
        "n_steps_read": min(len(turns), sample),
    }


def describe(result: dict, lang: str = "en") -> str:
    """The guess and why, in one line, for a person about to accept or override it."""
    pick = result["pick"]
    if not pick:
        return {
            "en": "Could not tell which question set this run wants from its commands; "
                  "using the default. Pass --questions to choose.",
            "zh": "从命令看不出这次运行该用哪套问题集，先用默认的。可以用 --questions 指定。",
        }[lang]
    found = result["evidence"].get(pick, {})
    shown = ", ".join(f"{m} x{n}" for m, n in list(found.items())[:3])
    return {
        "en": f"Looks like {pick} ({shown})",
        "zh": f"看起来是 {pick}（{shown}）",
    }[lang]


def tool_profile(turns: list[dict], top: int = 8) -> list[tuple[str, int]]:
    """Which tools this run leaned on. Shown beside the guess so it can be judged."""
    counter: collections.Counter[str] = collections.Counter()
    for row in turns:
        for action in row.get("actions") or []:
            name = str(action.get("tool") or "").strip()
            if name:
                counter[re.sub(r"\s+", " ", name)[:40]] += 1
    return counter.most_common(top)
