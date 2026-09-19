"""Turn per-step labels into things a person can act on.

A profile is only a table until it points at specific turns. Everything here names the
turns it is talking about, so the reader can go look.

Findings carry numbers, never sentences — `i18n.finding_headline` assembles the wording.
Nothing here hardcodes the phase vocabulary either: which options exist, and which of them
count as "verifying" or "changing", come from the question set, so a set written for coding
agents works without touching this file.
"""

from __future__ import annotations

import statistics as st

# Thresholds. These are judgement calls, not measurements — they are gathered here so they
# can be argued with in one place rather than hunted through the code.
REVISIT_HIGH = 0.6
NEW_INFO_LOW = 0.45
BLIND_SPOT_MAX = 0.03
CHANGE_YES = 0.5
VERIFY_WINDOW = 5
VERIFY_TAIL = 3          # a change in the last few turns has nothing after it to check
VERIFY_PROB = 0.4
OTHER_HIGH = 0.25
UNSURE_TOP1 = 0.45
DRIFT_LOW = 0.35
DRIFT_SHARE = 0.25


def phase_ids(labels: list[dict]) -> list[str]:
    """The option ids actually present in these labels, in the labeler's own order."""
    for r in labels:
        probs = r["answers"]["phase"]["probabilities"]
        return list(probs)
    return []


def mix(labels: list[dict], phases: list[str] | None = None) -> dict[str, float]:
    phases = phases or phase_ids(labels)
    total = {p: 0.0 for p in phases}
    for r in labels:
        for p, v in r["answers"]["phase"]["probabilities"].items():
            if p in total:
                total[p] += v
    return {p: total[p] / len(labels) for p in phases} if labels else total


def findings(labels: list[dict], *, phases: list[str] | None = None,
             roles: dict[str, list[str]] | None = None) -> dict:
    """Per-step labels in, an actionable summary out.

    `roles` maps a semantic role to the phase ids that fill it, e.g.
    ``{"verify": ["verify"], "change": ["repair"]}`` for SRE work or
    ``{"verify": ["test"], "change": ["edit"]}`` for coding work.
    """
    labels = sorted(labels, key=lambda r: r["turn"])
    n = len(labels)
    phases = phases or phase_ids(labels)
    roles = roles or {}
    verify_ids = set(roles.get("verify") or [])
    m = mix(labels, phases)
    out: dict = {"n_turns": n, "mix": m, "findings": []}

    def noul(r, q):
        return r["answers"][q]["noul"]

    def top1(r):
        return max(r["answers"]["phase"]["probabilities"].values())

    def add(kind: str, severity: float, turns: list[int], **facts):
        out["findings"].append({"kind": kind, "severity": severity, "turns": turns, "facts": facts})

    # 1. Steps that went nowhere: re-examining, and nothing new came back.
    waste = [r for r in labels if noul(r, "revisits") > REVISIT_HIGH
             and noul(r, "new_information") < NEW_INFO_LOW]
    if waste:
        add("waste", len(waste) / n, [r["turn"] for r in waste], count=len(waste), total=n)

    # 2. Blind spots: behaviour almost absent from the whole run.
    blind = [p for p in phases if p != "other" and m.get(p, 0.0) < BLIND_SPOT_MAX]
    if blind:
        add("blind_spot", len(blind) / max(1, len(phases) - 1), [], phases=blind)

    # 3. Changed the system, then never checked.
    if verify_ids:
        unverified = []
        for i, r in enumerate(labels):
            if noul(r, "changes_system") < CHANGE_YES:
                continue
            later = labels[i + 1: i + 1 + VERIFY_WINDOW]
            if len(later) < VERIFY_TAIL:
                continue
            checked = any(
                x["answers"]["phase"]["choice"] in verify_ids
                or max((x["answers"]["phase"]["probabilities"].get(v, 0.0) for v in verify_ids), default=0.0)
                > VERIFY_PROB
                for x in later)
            if not checked:
                unverified.append(r["turn"])
        if unverified:
            add("unverified_change", min(1.0, len(unverified) / max(1, n / 5)), unverified,
                count=len(unverified))

    # 4. Steps that are not investigation at all — usually the harness's own plumbing.
    plumbing = [r for r in labels
                if r["answers"]["phase"]["probabilities"].get("other", 0.0) > OTHER_HIGH
                or top1(r) < UNSURE_TOP1]
    if plumbing:
        add("plumbing", len(plumbing) / n, [r["turn"] for r in plumbing],
            count=len(plumbing), total=n)

    # 5. Drifting: not testing any particular suspicion.
    drift = [r for r in labels if noul(r, "hypothesis_driven") < DRIFT_LOW]
    if len(drift) > n * DRIFT_SHARE:
        add("drift", len(drift) / n, [r["turn"] for r in drift], count=len(drift), total=n)

    out["stats"] = {
        "hypothesis_driven": st.mean(noul(r, "hypothesis_driven") for r in labels),
        "new_information": st.mean(noul(r, "new_information") for r in labels),
        "revisits": st.mean(noul(r, "revisits") for r in labels),
        "changes_system": st.mean(noul(r, "changes_system") for r in labels),
        "targeting": st.mean(r["answers"]["targeting"]["score"] for r in labels),
        "labeler_confidence": st.median(top1(r) for r in labels),
    }
    out["findings"].sort(key=lambda f: -f["severity"])
    return out
