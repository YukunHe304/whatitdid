"""Native agent session files -> one normalised trajectory.

Vendored from SREGym (MIT, see NOTICE-SREGym.txt at the repo root), which in turn vendors
the ATIF schema. Seven agents are recognised by content, so callers hand over a file and
do not have to know which CLI produced it.
"""

from .converter import SUPPORTED_AGENTS, convert, detect_agent  # noqa: F401
