"""Does this question set actually fit this trajectory?

Picking the wrong set is the quietest way to get a meaningless profile. Nothing errors:
the labeler still answers every question, the percentages still add to a hundred, the
report still looks like a report. Someone profiling a coding run with the operations set
gets a page full of "probe" and "repair" and no sign that those words do not apply.

There is a signal for it already, and it costs nothing extra. When the options do not fit
the steps, the labeler cannot commit: its top choice gets weaker, the catch-all category
fills up, and more steps come back genuinely undecided.

The thresholds below sit outside the range a *matched* set produces, measured on the seven
CLI agents in the bundled demo — all labelled with sre.v1 on operations trajectories,
which is the case this is supposed to call fine:

    labeler confidence   0.74 – 0.99      (worst: codex 0.74)
    "other" share        0.01 – 0.17      (worst: codex 0.17)
    steps under 0.5      4% – 17%         (worst: codex 17%)

So a warning means the data is clearly outside what a fitting set looks like, not merely
at the weaker end of it. Better to stay quiet than to cry wolf on every codex run.

WHAT THIS ACTUALLY CATCHES, measured rather than assumed. One operations trajectory
(opencode, 14 steps) labelled three times:

    sre.v1      confidence 0.83   other 0.07   undecided  0%   quiet
    code.v1     confidence 0.80   other 0.13   undecided 21%   quiet
    kitchen.v1  confidence 0.78   other 0.74   undecided  0%   WARNS

kitchen.v1 is a set about cooking, applied to kubectl commands — as wrong as a set can
be, and it is caught. code.v1 on operations work is not, because it is not that wrong:
it shares survey, localize, report and other with sre.v1, and those absorb most steps.

Two things follow. This catches a set from the wrong world, not a set that is merely a
poor fit for yours — for that, read the profile and judge. And the useful signal is the
catch-all share: confidence moved 0.83 to 0.78 across all three, which is nearly nothing.
The labeler stays confident while putting everything in the bin marked "other".
"""

from __future__ import annotations

CONFIDENCE_FLOOR = 0.70
OTHER_CEILING = 0.25
UNDECIDED_CEILING = 0.30

# What each shipped set is for, in the words someone would use to describe their own runs.
DOMAINS = {
    "sre.v1": "operations and incident diagnosis",
    "code.v1": "software engineering",
}


def assess(mix: dict[str, float], stats: dict[str, float], per_turn: list[dict]) -> dict:
    """Judge the fit from a finished profile. Returns reasons, never a bare verdict."""
    confidence = stats.get("labeler_confidence", 1.0)
    other = mix.get("other", 0.0)
    scored = [t for t in per_turn if t.get("phase")]
    undecided = (
        sum(1 for t in scored if max(t["phase"].values(), default=1.0) < 0.5) / len(scored)
        if scored else 0.0
    )

    reasons = []
    if confidence < CONFIDENCE_FLOOR:
        reasons.append(("low_confidence", round(confidence, 2)))
    if other > OTHER_CEILING:
        reasons.append(("many_unclassified", round(other, 2)))
    if undecided > UNDECIDED_CEILING:
        reasons.append(("many_undecided", round(undecided, 2)))

    return {
        "confidence": round(confidence, 3),
        "other": round(other, 3),
        "undecided": round(undecided, 3),
        "reasons": reasons,
        "fits": not reasons,
    }


def explain(fit: dict, questions: str, lang: str = "en") -> str | None:
    """One sentence a person can act on, or None when there is nothing to say."""
    if fit["fits"]:
        return None
    alternatives = [q for q in DOMAINS if q != questions]
    alt = alternatives[0] if alternatives else "your own set"
    detail = {
        "low_confidence": {
            "en": f"the labeler's top choice averaged {fit['confidence']:.2f}",
            "zh": f"标注器最高选项只有 {fit['confidence']:.2f}"},
        "many_unclassified": {
            "en": f"{fit['other']:.0%} of steps landed in the catch-all category",
            "zh": f"{fit['other']:.0%} 的步子落进了「归不了类」"},
        "many_undecided": {
            "en": f"{fit['undecided']:.0%} of steps came back undecided",
            "zh": f"{fit['undecided']:.0%} 的步子标注器拿不准"},
    }
    parts = ", ".join(detail[kind][lang] for kind, _ in fit["reasons"])
    return {
        "en": f"The {questions} question set may not fit this run — {parts}. "
              f"Try --questions {alt}, or write a set for your own domain.",
        "zh": f"{questions} 这套问题集可能不适合这次运行——{parts}。"
              f"试试 --questions {alt}，或者给你自己的领域写一套。",
    }[lang]
