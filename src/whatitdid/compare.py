"""Two sets of runs, and whether the difference between them is real.

Why this exists: after a change, the pass rate moves a couple of points across twenty-odd
tasks and the interval almost always straddles zero — you cannot say whether the change did
anything. But those same runs contain a few thousand steps, and every step is a measurement.

Two hurdles, both of which a difference has to clear:

1. The paired bootstrap, which compares on the same tasks so task difficulty cancels out.
   It answers: would a different draw of tasks have shown this?
2. The repeat-noise floor from `noise.py`. It answers: would re-running the same config
   have shown this anyway?

The second is the one everybody skips, and it is the one that kills most findings.
"""

from __future__ import annotations

import random
import statistics as st
import unicodedata

from . import noise as noise_mod


def _paired_bootstrap(before: list[float], after: list[float], rounds: int = 20000,
                      seed: int = 0) -> dict:
    deltas = [b - a for a, b in zip(before, after)]
    rng = random.Random(seed)
    means = sorted(st.mean(rng.choices(deltas, k=len(deltas))) for _ in range(rounds))
    low, high = means[int(rounds * 0.025)], means[int(rounds * 0.975)]
    return {"delta": st.mean(deltas), "low": low, "high": high,
            "improved": sum(1 for d in deltas if d > 0), "n": len(deltas),
            "solid": low > 0 or high < 0}


def _question_set(run: dict[str, dict]) -> str | None:
    seen = {row.get("questions") for row in run.values() if row.get("questions")}
    return seen.pop() if len(seen) == 1 else (None if not seen else "|".join(sorted(seen)))


def compare(before: dict[str, dict], after: dict[str, dict], *, rounds: int = 20000,
            seed: int = 0, repeats: list[dict[str, dict]] | None = None) -> dict:
    """Two maps of task id -> ``Report.to_dict()``, paired by task id.

    `repeats` are further runs of the *same* configuration as `before`; when given, the
    repeat-noise floor is measured from them instead of the shipped reference values.
    """
    shared = sorted(set(before) & set(after))
    if len(shared) < 3:
        raise ValueError(f"only {len(shared)} tasks pair up between these two runs — too few")

    # A profile depends entirely on which questions were asked. Comparing across two
    # different sets silently produces a table of meaningless numbers, so refuse.
    left, right = _question_set(before), _question_set(after)
    if left and right and left != right:
        raise ValueError(
            f"these runs used different question sets ({left} vs {right}); their numbers "
            f"are not comparable. Re-profile one side with the other's set.")

    question_set = left or right or "sre.v1"
    floor = noise_mod.resolve(repeats, question_set)
    noise_values = floor.get("metrics", {})

    metrics: list[dict] = []

    def add(metric_id: str, group: str, lefts: list[float], rights: list[float]):
        row = _paired_bootstrap(lefts, rights, rounds, seed)
        level = noise_values.get(metric_id)
        row.update({"id": metric_id, "group": group, "noise": level,
                    "verdict": noise_mod.verdict(row["delta"], row["solid"], level)})
        metrics.append(row)

    phases = [p for p in (before[shared[0]].get("mix") or {})
              if all(p in (after[k].get("mix") or {}) for k in shared)]
    for phase in phases:
        add(phase, "phase", [before[k]["mix"][phase] for k in shared],
            [after[k]["mix"][phase] for k in shared])

    stat_keys = [k for k in (before[shared[0]].get("stats") or {})
                 if all(k in before[s].get("stats", {}) and k in after[s].get("stats", {})
                        for s in shared)]
    for key in stat_keys:
        add(key, "metric", [before[k]["stats"][key] for k in shared],
            [after[k]["stats"][key] for k in shared])

    pairs = [(before[k]["truthfulness"], after[k]["truthfulness"]) for k in shared
             if before[k].get("truthfulness") is not None
             and after[k].get("truthfulness") is not None]
    if len(pairs) >= 3:
        add("truthfulness", "metric", [a for a, _ in pairs], [b for _, b in pairs])

    metrics.sort(key=lambda r: -abs(r["delta"]))
    return {"metrics": metrics, "tasks": {"shared": shared, "n": len(shared)},
            "questions": question_set, "rounds": rounds, "noise": floor}


VERDICT_MARK = {"above_noise": "✓", "within_noise": "·", "unstable": "", "no_baseline": "?"}


def format_compare(result: dict, lang: str = "en") -> str:
    from .i18n import metric_name, phase_name, ui

    n = result["tasks"]["n"]
    lines = [ui("cmp_header", lang, n=n, rounds=result["rounds"])]

    source = result.get("noise", {}).get("source", "none")
    if source == "measured":
        detail = {"en": f"repeat noise measured from {result['noise']['n_runs']} same-config runs",
                  "zh": f"重跑噪声来自 {result['noise']['n_runs']} 次同配置运行"}[lang]
    elif source == "reference":
        detail = {"en": "repeat noise from the shipped reference values (not your runs)",
                  "zh": "重跑噪声用的是随包参考值，不是你自己的运行"}[lang]
    else:
        detail = {"en": "no repeat baseline — re-run the same config to get one",
                  "zh": "没有重跑基准——把同一个配置再跑一遍就能有"}[lang]
    lines.append(f"  {detail}")

    names = {row["id"]: (phase_name(row["id"], lang) if row["group"] == "phase"
                         else metric_name(row["id"], lang)) for row in result["metrics"]}
    # Chinese glyphs are double-width in a terminal, so pad by display width, not len().
    width = max([_width(n) for n in names.values()] + [_width(ui("cmp_metric", lang))])

    lines.append(f"{_pad(ui('cmp_metric', lang), width)}  {ui('cmp_delta', lang):>8}"
                 f"{ui('cmp_interval', lang):>21} {ui('cmp_improved', lang):>10}"
                 f" {ui('cmp_noise', lang):>9}  {ui('cmp_verdict', lang)}")

    for row in result["metrics"]:
        level = f"±{row['noise']:.3f}" if row["noise"] is not None else "—"
        verdict = (ui("noise_unknown", lang) if row["verdict"] == "no_baseline"
                   else ui(f"verdict_{row['verdict']}", lang))
        mark = VERDICT_MARK.get(row["verdict"], " ")
        lines.append(
            f"{_pad(names[row['id']], width)}  {row['delta']:+8.3f}"
            f"  ({row['low']:+.3f}, {row['high']:+.3f})"
            f" {row['improved']:>4}/{row['n']:<4}"
            f" {level:>9}  {mark} {verdict}")
    return "\n".join(lines)


def _width(text: str) -> int:
    """Terminal columns a string occupies. CJK glyphs take two."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def _pad(text: str, width: int) -> str:
    return "  " + text + " " * max(0, width - _width(text))
