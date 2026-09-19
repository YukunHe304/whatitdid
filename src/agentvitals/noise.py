"""How much a number moves when nothing changed.

The reason this file exists: a paired bootstrap over N tasks measures how much the mean
would wobble if you drew a different set of tasks. It says nothing about how much it
wobbles when you re-run *the same* config on *the same* tasks — and agents are not
deterministic, so that second wobble is real and is often the larger of the two. A change
smaller than it is not a finding, however tight its confidence interval looks.

Two sources, in this order:

1. The user's own repeats. If they ran the same config more than once, that is the right
   baseline — it is their agent, their tasks, their temperature.
2. Values shipped with the package, measured on SREGym-Lite. A fallback, and labelled as
   one: someone else's agent on someone else's tasks is a weak guide to yours.

Never invented. If neither source has a number, the verdict is "no baseline", not "fine".
"""

from __future__ import annotations

import itertools
import json
import pathlib
import statistics as st

REFERENCE_FILE = pathlib.Path(__file__).parent / "data" / "noise_reference.json"


def _paired_mean_delta(a: dict[str, dict], b: dict[str, dict], getter) -> float | None:
    """Mean of (b - a) over the tasks both runs share, or None if too few."""
    shared = sorted(set(a) & set(b))
    pairs = []
    for key in shared:
        left, right = getter(a[key]), getter(b[key])
        if left is None or right is None:
            continue
        pairs.append(right - left)
    return st.mean(pairs) if len(pairs) >= 3 else None


def _getters(run: dict[str, dict]) -> dict[str, object]:
    """Metric id -> a function pulling that metric out of one task's report row."""
    sample = next(iter(run.values()), {})
    out: dict[str, object] = {}
    for phase in (sample.get("mix") or {}):
        out[phase] = (lambda p: lambda row: (row.get("mix") or {}).get(p))(phase)
    for metric in (sample.get("stats") or {}):
        out[metric] = (lambda m: lambda row: (row.get("stats") or {}).get(m))(metric)
    out["truthfulness"] = lambda row: row.get("truthfulness")
    return out


def estimate(runs: list[dict[str, dict]]) -> dict:
    """Repeat noise from two or more runs of the *same* configuration.

    For each metric we compute the same statistic `compare` reports — the mean paired
    delta across tasks — for every pair of same-config runs. Whatever that statistic
    reaches when nothing changed is the floor a real change has to clear.

    With only two or three repeats there is no meaningful percentile, so this takes the
    largest observed value. That is deliberately conservative: it is better to withhold a
    finding than to publish one that a re-run would have produced anyway.
    """
    runs = [r for r in runs if r]
    if len(runs) < 2:
        return {"source": "none", "n_runs": len(runs), "n_pairs": 0, "metrics": {}}

    getters = _getters(runs[0])
    metrics: dict[str, float] = {}
    pairs = list(itertools.combinations(range(len(runs)), 2))
    for metric, getter in getters.items():
        observed = []
        for i, j in pairs:
            delta = _paired_mean_delta(runs[i], runs[j], getter)
            if delta is not None:
                observed.append(abs(delta))
        if observed:
            metrics[metric] = max(observed)
    return {"source": "measured", "n_runs": len(runs), "n_pairs": len(pairs), "metrics": metrics}


def load_reference(question_set: str = "sre.v1") -> dict:
    """Values shipped with the package. Absent until we have measured them."""
    try:
        blob = json.loads(REFERENCE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"source": "none", "metrics": {}}
    entry = blob.get(question_set)
    if not entry:
        return {"source": "none", "metrics": {}}
    return {"source": "reference", "question_set": question_set,
            "metrics": entry.get("metrics", {}), "about": entry.get("about", "")}


def resolve(runs: list[dict[str, dict]] | None = None, question_set: str = "sre.v1") -> dict:
    """The user's own repeats if they have them, otherwise the shipped values."""
    if runs and len(runs) >= 2:
        measured = estimate(runs)
        if measured["metrics"]:
            return measured
    return load_reference(question_set)


def verdict(delta: float, solid: bool, noise: float | None) -> str:
    """What to tell someone about one row of the comparison.

    `solid` is the bootstrap's own answer — does the interval clear zero. That question and
    "is it bigger than a re-run" are different, and both have to pass.
    """
    if not solid:
        return "unstable"
    if noise is None:
        return "no_baseline"
    return "above_noise" if abs(delta) > noise else "within_noise"
