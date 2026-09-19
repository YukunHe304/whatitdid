"""Offline tests. Nothing here touches the network.

The labeler is faked deterministically, which is the point: everything except the model
call is our code, and it is the part that silently goes wrong.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from agentvitals import compare, i18n, noise, profile, read_turns
from agentvitals.compare import _paired_bootstrap
from agentvitals.findings import findings
from agentvitals.formats import SUPPORTED_AGENTS, detect_agent
from agentvitals.labeler import load_question_set
from agentvitals.serialize import command_of, to_summary_row

FIX = pathlib.Path(__file__).parent / "fixtures"

# One directory per agent, holding that agent's own session file untouched. `baseline` has
# no upstream fixture, so it is exercised by the adapter only, not here.
FIXTURES = {
    "claudecode": "claudecode_run/sessions/projects/-logs/74bfdd52-f1bd-477d-98c8-306bde810080.jsonl",
    "codex": "codex_run/sessions/2026/06/29/rollout-2026-06-29T16-58-06-019f1451-1903-7092-b4ca-73a57d9bdd9d.jsonl",
    "copilot": "copilot_run_real/copilot-cli.jsonl",
    "gemini": "gemini_run/sessions/2026/07/04/session-fdaf509c.jsonl",
    "opencode": "opencode_run/sessions/2026/06/30/session-ses_0e8fabe63ffe91KaErs7Mh9g5O.json",
    "stratus": "stratus_run/0704_1458_service_port_conflict_hotel_reservation_stratus_agent_trajectory.jsonl",
}


class FakeLabeler:
    """Deterministic answers derived from the turn number.

    It builds its reply from the question set it is handed rather than from a hardcoded
    list, so a question set that does not round-trip shows up here as a KeyError instead of
    as a quietly wrong profile.
    """

    name = "fake"

    def __init__(self, seed: int = 0):
        self.seed = seed
        self.calls = 0

    def __call__(self, state: dict, questions: dict) -> dict:
        self.calls += 1
        turn = state.get("turn", self.calls)
        out = {}
        for name, spec in questions.items():
            if spec["type"] == "choice":
                options = list(spec["criteria"])
                pick = options[(turn + self.seed) % len(options)]
                rest = (1.0 - 0.6) / max(1, len(options) - 1)
                probs = {o: (0.6 if o == pick else rest) for o in options}
                out[name] = {"type": "choice", "choice": pick, "probabilities": probs,
                             "confidence": 0.6}
            elif spec["type"] == "score":
                out[name] = {"type": "score", "score": (turn + self.seed) % len(spec["criteria"])}
            else:
                out[name] = {"type": "noul", "noul": ((turn * 7 + self.seed) % 10) / 10}
        return out


# --- formats -----------------------------------------------------------------

def test_seven_adapters_are_registered():
    assert len(SUPPORTED_AGENTS) == 7


@pytest.mark.parametrize("agent,relpath", sorted(FIXTURES.items()))
def test_detects_each_agent_from_content_alone(agent, relpath):
    assert detect_agent(FIX / relpath) == agent


@pytest.mark.parametrize("agent,relpath", sorted(FIXTURES.items()))
def test_reads_turns_and_keeps_narration_separate_from_actions(agent, relpath):
    rows, detected, _model = read_turns(FIX / relpath)
    assert detected == agent
    assert rows, f"{agent} produced no turns"
    assert set(rows[0]) == {"turn", "actions", "observation", "narration", "reasoning"}
    assert [r["turn"] for r in rows] == list(range(1, len(rows) + 1))


# --- question sets -----------------------------------------------------------

def test_both_shipped_sets_share_the_same_portable_questions():
    sre, code = load_question_set("sre.v1"), load_question_set("code.v1")
    assert sre.portable_metrics() == code.portable_metrics()
    assert sre.phases != code.phases          # the domain question differs
    assert sre.roles["verify"] == ["verify"]
    assert code.roles["verify"] == ["test"]


def test_a_set_declares_which_options_count_as_verifying():
    """findings() must not know the word 'verify' — the set tells it."""
    labels = []
    for turn in range(1, 11):
        probs = {"survey": 0.1, "repair": 0.8, "verify": 0.1}
        labels.append({"turn": turn,
                       "answers": {"phase": {"choice": "repair", "probabilities": probs},
                                   "hypothesis_driven": {"noul": 0.5},
                                   "new_information": {"noul": 0.5},
                                   "revisits": {"noul": 0.1},
                                   "changes_system": {"noul": 0.9},
                                   "targeting": {"score": 2.0}}})
    got = findings(labels, phases=["survey", "repair", "verify"], roles={"verify": ["verify"]})
    kinds = {f["kind"] for f in got["findings"]}
    assert "unverified_change" in kinds, "ten changes and no verify step should be flagged"

    # With no role declared there is nothing to check against, so no claim is made.
    quiet = findings(labels, phases=["survey", "repair", "verify"], roles={})
    assert "unverified_change" not in {f["kind"] for f in quiet["findings"]}


# --- profile -----------------------------------------------------------------

def test_profile_emits_stable_ids_only():
    rep = profile(FIX / FIXTURES["codex"], labeler=FakeLabeler(), workers=4)
    d = rep.to_dict()

    assert d["n_turns"] > 0
    assert d["questions"] == "sre.v1"
    assert set(d["stats"]) == {"hypothesis_driven", "new_information", "revisits",
                               "changes_system", "targeting", "labeler_confidence"}
    assert set(d["mix"]) == set(load_question_set("sre.v1").phases)

    # No display string may reach the data. Non-ASCII here means a label leaked through.
    blob = json.dumps({k: v for k, v in d.items() if k != "source"}, ensure_ascii=True)
    assert "\\u" not in blob, "a display string leaked into to_dict()"

    for finding in d["findings"]:
        assert set(finding) == {"kind", "severity", "turns", "facts"}
        assert i18n.finding_headline(finding, "en") != finding["kind"]
        assert i18n.finding_headline(finding, "zh") != finding["kind"]


def test_profile_with_the_coding_question_set():
    rep = profile(FIX / FIXTURES["codex"], labeler=FakeLabeler(), workers=4, questions="code.v1")
    d = rep.to_dict()
    assert d["questions"] == "code.v1"
    assert "reproduce" in d["mix"] and "probe" not in d["mix"]
    assert set(d["stats"]) == set(
        profile(FIX / FIXTURES["codex"], labeler=FakeLabeler(), workers=4).to_dict()["stats"]
    ), "the five portable metrics must survive a change of domain"


def test_web_dict_carries_the_step_text_that_to_dict_drops():
    rep = profile(FIX / FIXTURES["codex"], labeler=FakeLabeler(), workers=4)
    plain, web = rep.to_dict(), rep.to_web_dict()
    assert "command" not in plain["per_turn"][0]
    assert "command" in web["per_turn"][0]
    assert {"top", "top_p", "marks", "observation", "narration"} <= set(web["per_turn"][0])


def test_summary_row_drops_per_turn():
    rep = profile(FIX / FIXTURES["codex"], labeler=FakeLabeler(), workers=4)
    row = to_summary_row(rep, problem="p1", report="p1.html", seconds=1.0)
    assert "per_turn" not in row
    assert row["problem"] == "p1" and row["n_turns"] > 0


def test_command_of_finds_the_command_under_whatever_key():
    assert command_of([{"tool": "bash", "args": {"command": "kubectl get pods"}}]) == "kubectl get pods"
    assert command_of([{"tool": "x", "args": {"cmd": "ls"}}]) == "ls"
    assert command_of([]) == ""
    assert command_of([{"tool": "wait", "args": {}}]) == "wait"


def test_html_renders_in_both_languages(tmp_path):
    rep = profile(FIX / FIXTURES["codex"], labeler=FakeLabeler(), workers=4)
    for lang in ("en", "zh"):
        out = rep.to_html(tmp_path / f"r_{lang}.html", lang=lang)
        text = out.read_text(encoding="utf-8")
        assert text.startswith("<!DOCTYPE html>") and f'lang="{lang}"' in text
        assert "<script" not in text, "reports must stay script-free and self-contained"
        # URLs inside the trajectory text are fine — those are the commands the agent ran.
        # What must not appear is the page fetching anything of its own.
        assert "<link" not in text, "no external stylesheets"
        assert 'src="http' not in text and "@import" not in text, "no external assets"


# --- i18n --------------------------------------------------------------------

def test_every_string_exists_in_every_language():
    missing = []
    for table_name in ("PHASES", "METRICS", "METRIC_HELP", "FINDINGS", "UI"):
        table = getattr(i18n, table_name)
        for key, entry in table.items():
            for lang in i18n.LANGS:
                if not entry.get(lang):
                    missing.append(f"{table_name}.{key}.{lang}")
    assert not missing, f"missing translations: {missing}"


def test_strings_bundle_covers_both_languages():
    for lang in i18n.LANGS:
        bundle = i18n.strings(lang)
        assert bundle["lang"] == lang
        assert bundle["metrics"]["truthfulness"]
        assert bundle["ui"]["where_steps_went"]


# --- compare -----------------------------------------------------------------

def _run(offset: float, n: int = 12, questions: str = "sre.v1", alternate: float = 0.0) -> dict:
    out = {}
    for i in range(n):
        wobble = alternate * (1 if i % 2 else -1)
        out[f"task{i}"] = {
            "questions": questions,
            "mix": {"survey": 0.2, "localize": 0.1, "inspect": 0.2, "probe": 0.1 + offset,
                    "repair": 0.1, "verify": 0.1, "report": 0.1, "other": 0.1},
            "stats": {"hypothesis_driven": 0.5 + wobble, "new_information": 0.5,
                      "revisits": 0.5, "changes_system": 0.2, "targeting": 2.0,
                      "labeler_confidence": 0.8},
            "truthfulness": 0.7,
        }
    return out


def test_compare_separates_a_real_shift_from_an_alternating_one():
    result = compare(_run(0.0), _run(0.10, alternate=0.02), rounds=2000)
    by_id = {r["id"]: r for r in result["metrics"]}
    assert by_id["probe"]["solid"] is True
    assert by_id["probe"]["delta"] == pytest.approx(0.10, abs=1e-9)
    assert by_id["hypothesis_driven"]["solid"] is False


def test_compare_refuses_two_different_question_sets():
    with pytest.raises(ValueError, match="different question sets"):
        compare(_run(0.0, questions="sre.v1"), _run(0.1, questions="code.v1"), rounds=200)


def test_compare_survives_a_metric_missing_on_one_side():
    before, after = _run(0.0), _run(0.1)
    for row in after.values():
        row["stats"].pop("targeting")
    result = compare(before, after, rounds=200)
    assert "targeting" not in {r["id"] for r in result["metrics"]}
    assert "hypothesis_driven" in {r["id"] for r in result["metrics"]}


def test_compare_needs_at_least_three_paired_tasks():
    with pytest.raises(ValueError, match="too few"):
        compare(_run(0.0, n=2), _run(0.1, n=2), rounds=200)


# --- noise -------------------------------------------------------------------

def test_noise_floor_demotes_a_change_smaller_than_a_rerun():
    before, after = _run(0.0), _run(0.10)
    # Two "repeats" of the before config that differ by more than the change under test.
    repeats = [_run(0.0), _run(0.15)]
    result = compare(before, after, rounds=2000, repeats=repeats)
    probe = next(r for r in result["metrics"] if r["id"] == "probe")
    assert result["noise"]["source"] == "measured"
    assert probe["solid"] is True, "the bootstrap alone still calls it solid"
    assert probe["verdict"] == "within_noise", "but a re-run moves it further, so it is not a finding"


def test_noise_floor_promotes_a_change_larger_than_a_rerun():
    result = compare(_run(0.0), _run(0.10), rounds=2000, repeats=[_run(0.0), _run(0.01)])
    probe = next(r for r in result["metrics"] if r["id"] == "probe")
    assert probe["verdict"] == "above_noise"


def test_without_a_baseline_the_verdict_says_so_rather_than_guessing():
    result = compare(_run(0.0), _run(0.10), rounds=2000)
    probe = next(r for r in result["metrics"] if r["id"] == "probe")
    assert result["noise"]["source"] in {"none", "reference"}
    if result["noise"]["source"] == "none":
        assert probe["verdict"] == "no_baseline"


def test_a_single_run_cannot_estimate_repeat_noise():
    assert noise.estimate([_run(0.0)])["metrics"] == {}
    assert noise.verdict(0.5, solid=True, noise=None) == "no_baseline"
    assert noise.verdict(0.5, solid=False, noise=0.01) == "unstable"


def test_paired_bootstrap_is_reproducible():
    a, b = [0.1] * 10, [0.2] * 10
    assert _paired_bootstrap(a, b, 500, seed=1) == _paired_bootstrap(a, b, 500, seed=1)
