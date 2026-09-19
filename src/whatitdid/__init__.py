"""Read any CLI agent's session file and report what the run actually did.

    from whatitdid import profile
    rep = profile("session.jsonl")
    rep.to_html("report.html")
    rep.to_dict()          # for programs; this is what a self-improvement loop reads

The default labeler is Jev (TypeSafe's System One model): it answers several typed
questions in one parallel pass and returns probability distributions rather than hard
labels, and it has no text output channel at all. Any OpenAI-compatible model works as a
fallback, but its labels are swayed by what the agent says about itself — measured on the
same 153 turns, 28% of its labels move when the narration is included, against 9% for Jev,
and the bias tracks how much each agent talks. That makes it the wrong tool for comparing
agents to each other.
"""

from . import i18n, noise  # noqa: F401
from .compare import compare, format_compare  # noqa: F401
from .core import DEFAULT_TASK, Report, profile, read_turns  # noqa: F401
from .labeler import ChatModel, Jev, QuestionSet, load_question_set, load_questions  # noqa: F401
from .serialize import to_summary_row, to_web_dict  # noqa: F401

__version__ = "0.1.0"
__all__ = [
    "profile", "compare", "format_compare", "Report", "Jev", "ChatModel",
    "QuestionSet", "load_questions", "load_question_set", "read_turns",
    "to_web_dict", "to_summary_row", "DEFAULT_TASK", "i18n", "noise",
]
