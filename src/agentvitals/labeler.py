"""Ask a labeller the same typed questions about every step.

Two backends. Jev (TypeSafe) answers up to 16 typed questions in one parallel pass and
returns probability distributions; an OpenAI-compatible chat model is the fallback and the
control arm. They are not interchangeable: measured on the same 153 turns, the chat model's
labels move 28% of the time when the agent's own narration is included, against 9% for Jev,
and the bias tracks how much the agent talks. Anything comparing different agents should
prefer Jev, or at least report both.
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import re
import threading
import time
import urllib.error
import urllib.request

JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
JEV_REQUEST_LIMIT = 65_536
RETRY_STATUSES = {429, 500, 502, 503, 529}

# Where a key is looked for when none is passed. The first entry is ours; the second is
# kept so an existing SREGym checkout keeps working.
KEY_FILES = ("~/.config/agentvitals/typesafe.env", "~/.config/sregym/typesafe.env")
CHAT_KEY_FILES = ("~/.config/agentvitals/chat.env", "~/.config/sregym/deepseek-agent.env")


class LabelerError(RuntimeError):
    pass


class FailureLog:
    """Why calls failed, counted by cause.

    A dropped step used to vanish silently, so a run that lost a third of its steps to an
    expired key looked exactly like a clean one. The counts travel with the report.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counts: dict[str, int] = {}
        self.samples: dict[str, str] = {}

    def record(self, cause: str, detail: str = "") -> None:
        with self._lock:
            self.counts[cause] = self.counts.get(cause, 0) + 1
            if detail and cause not in self.samples:
                self.samples[cause] = str(detail)[:200]

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def to_dict(self) -> dict:
        with self._lock:
            return {"total": self.total, "by_cause": dict(self.counts), "samples": dict(self.samples)}


def read_secret(path: str, name: str) -> str:
    try:
        for line in open(os.path.expanduser(path)):
            if line.startswith(name):
                return line.split("=", 1)[1].strip()
    except OSError as exc:
        raise LabelerError(f"cannot read {path}: {exc}") from exc
    raise LabelerError(f"{name} not found in {path}")


def first_secret(paths: tuple[str, ...], name: str) -> str:
    """First of `paths` that yields `name`. Reports every path tried, not just the last."""
    for path in paths:
        try:
            return read_secret(path, name)
        except LabelerError:
            continue
    raise LabelerError(f"{name} not set. Put it in {paths[0]} or export {name}.")


@dataclasses.dataclass(frozen=True)
class QuestionSet:
    """A frozen set of questions plus what the rest of the package needs to know about it.

    `roles` is what keeps `findings.py` free of domain vocabulary: it says which phase
    options count as verifying and which count as changing, so the same rules apply to an
    SRE set and a coding set.
    """

    id: str
    questions: dict
    phase_question: str
    phases: list[str]
    roles: dict[str, list[str]]

    def portable_metrics(self) -> list[str]:
        """Question ids that are not the domain-specific one — comparable across sets."""
        return [q for q in self.questions if q != self.phase_question]


def _resolve(name_or_path: str) -> pathlib.Path:
    path = pathlib.Path(name_or_path)
    if path.exists():
        return path
    packaged = pathlib.Path(__file__).parent / "questions" / f"{name_or_path}.json"
    if packaged.exists():
        return packaged
    raise LabelerError(f"question set not found: {name_or_path}")


def load_question_set(name_or_path: str) -> QuestionSet:
    path = _resolve(name_or_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    meta = raw.pop("_meta", {}) or {}

    shared = meta.get("shares")
    if shared:  # a domain set pulls the five portable questions in by reference
        base = json.loads(_resolve(shared).read_text(encoding="utf-8"))
        base.pop("_meta", None)
        raw = {**raw, **base}

    phase_question = meta.get("phase_question", "phase")
    spec = raw.get(phase_question) or {}
    phases = list((spec.get("criteria") or {}).keys())
    return QuestionSet(
        id=meta.get("id", pathlib.Path(name_or_path).stem),
        questions=raw,
        phase_question=phase_question,
        phases=phases,
        roles=meta.get("roles", {}) or {},
    )


def load_questions(name_or_path: str) -> dict:
    """Just the questions, ready to send. Kept for callers that only need that."""
    return load_question_set(name_or_path).questions


class Jev:
    """TypeSafe's System One model. No text out, so a label cannot be talked into anything
    the option set does not already contain."""

    name = "jev"

    def __init__(self, model: str = "jev-latest", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ.get("TYPESAFE_API_KEY") or first_secret(
            KEY_FILES, "TYPESAFE_API_KEY")
        self.failures = FailureLog()

    def __call__(self, state: dict, questions: dict) -> dict | None:
        body = {"state": state, "model": self.model, "questions": questions}
        payload = json.dumps(body, ensure_ascii=False).encode()
        if len(payload) > JEV_REQUEST_LIMIT:
            state = _shrink(state)
            payload = json.dumps({"state": state, "model": self.model, "questions": questions},
                                 ensure_ascii=False).encode()
            if len(payload) > JEV_REQUEST_LIMIT:
                self.failures.record("too_large", f"{len(payload)} bytes after shrinking")
                return None
        for attempt in range(3):
            # A fresh Request per attempt; urllib mutates the one it is given.
            request = urllib.request.Request(
                JEV_ENDPOINT, data=payload,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"})
            try:
                with urllib.request.urlopen(request, timeout=40) as response:
                    return json.loads(response.read())["answers"]
            except urllib.error.HTTPError as exc:
                if exc.code in RETRY_STATUSES and attempt < 2:
                    time.sleep(3 * (attempt + 1))
                    continue
                self.failures.record(f"http_{exc.code}", exc.reason)
                return None
            except Exception as exc:  # noqa: BLE001
                self.failures.record(type(exc).__name__, str(exc))
                return None
        return None


class ChatModel:
    """Any OpenAI-compatible endpoint. Slower, and its labels are swayed by what the agent
    says about itself — kept as the control arm, and for people without a Jev key."""

    name = "chat"

    def __init__(self, model: str, base_url: str | None = None, api_key: str | None = None,
                 thinking: bool = False):
        self.model = model
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL") or first_secret(
            CHAT_KEY_FILES, "AGENT_API_BASE")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or first_secret(
            CHAT_KEY_FILES, "AGENT_API_KEY")
        self.thinking = thinking
        self.failures = FailureLog()

    def __call__(self, state: dict, questions: dict) -> dict | None:
        lines = ["QUESTIONS:"]
        for name, q in questions.items():
            lines.append(f"- {name}: {q['instructions']}")
            if q["type"] == "choice":
                lines += [f"    {k}: {v}" for k, v in q["criteria"].items()]
            elif q["type"] == "score":
                lines += [f"    {i}: {c}" for i, c in enumerate(q["criteria"])]
        shape = {n: ("{<option>: <probability>, ...} covering every option and summing to 1"
                     if q["type"] == "choice" else
                     f"<number 0..{len(q['criteria']) - 1}>" if q["type"] == "score" else "<number 0..1>")
                 for n, q in questions.items()}
        body = {
            "model": self.model, "max_tokens": 1024,
            "thinking": {"type": "enabled" if self.thinking else "disabled"},
            "messages": [
                {"role": "system", "content":
                 "You label one step of an agent's run. Answer only with JSON, no other text.\n"
                 f"Return exactly this shape: {json.dumps(shape, ensure_ascii=False)}"},
                {"role": "user", "content": "\n".join(lines) + "\n\nSTEP:\n"
                 + json.dumps(state, ensure_ascii=False)}]}
        request = urllib.request.Request(
            self.base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    payload = json.loads(response.read())
                break
            except urllib.error.HTTPError as exc:
                if exc.code in RETRY_STATUSES and attempt < 2:
                    time.sleep(6 * (attempt + 1))
                    continue
                self.failures.record(f"http_{exc.code}", exc.reason)
                return None
            except Exception as exc:  # noqa: BLE001
                self.failures.record(type(exc).__name__, str(exc))
                return None
        else:
            self.failures.record("retries_exhausted", "")
            return None
        message = payload["choices"][0]["message"]
        text = (message.get("content") or "") or (message.get("reasoning_content") or "")
        answers = _parse_chat(text, questions)
        if answers is None:
            self.failures.record("unparsable", text[:200])
        return answers


def _shrink(state: dict) -> dict:
    out = dict(state)
    if isinstance(out.get("result"), str):
        out["result"] = out["result"][:1500]
    if isinstance(out.get("prior_actions"), list):
        out["prior_actions"] = out["prior_actions"][-5:]
    for key in ("agent_reasoning", "agent_said"):
        if isinstance(out.get(key), str):
            out[key] = out[key][:800]
    return out


def _parse_chat(text: str, questions: dict) -> dict | None:
    """Rebuild Jev's answer shape from free text, or give up. A chat model has no contract,
    so a malformed reply is dropped rather than guessed at."""
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        raw = json.loads(match.group(0))
    except ValueError:
        return None
    out: dict = {}
    for name, q in questions.items():
        value = raw.get(name)
        if q["type"] == "choice":
            if not isinstance(value, dict):
                return None
            dist = {k: float(value.get(k, 0) or 0) for k in q["criteria"]}
            total = sum(dist.values())
            if total <= 0:
                return None
            dist = {k: v / total for k, v in dist.items()}
            out[name] = {"type": "choice", "choice": max(dist, key=dist.get),
                         "probabilities": dist, "confidence": max(dist.values())}
        elif q["type"] == "score":
            top = len(q["criteria"]) - 1
            if not isinstance(value, (int, float)) or not 0 <= value <= top:
                return None
            out[name] = {"type": "score", "score": float(value)}
        else:
            if not isinstance(value, (int, float)) or not 0 <= value <= 1:
                return None
            out[name] = {"type": "noul", "noul": float(value)}
    return out
