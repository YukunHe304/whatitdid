"""The local web app.

Local-first on purpose. Profiling needs an API key, and a hosted service would mean
either holding other people's keys or paying for their labelling — so this runs on the
user's machine, reads their key from their own config, and never sends a trajectory
anywhere except to the labeling API they chose.
"""

from .app import build_app, serve  # noqa: F401

__all__ = ["build_app", "serve"]
