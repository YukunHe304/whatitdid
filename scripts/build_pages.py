"""Build the static demo published to GitHub Pages.

Someone deciding whether this tool is worth installing should be able to see it working
first. Pages cannot run Python, so every endpoint the app reads at startup is baked to a
file here, and the comparison — normally a POST — is pre-computed.

    npm --prefix web run build && python scripts/build_pages.py

Profiling is absent by construction: there is no server to label anything, and the page
says so rather than offering a button that cannot work.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import whatitdid  # noqa: E402
from whatitdid import compare as run_compare  # noqa: E402
from whatitdid import i18n  # noqa: E402
from whatitdid.labeler import load_question_set  # noqa: E402

STATIC = ROOT / "src" / "whatitdid" / "static"
DEMO = ROOT / "src" / "whatitdid" / "data" / "demo"
DOCS = ROOT / "docs"


def write(path: pathlib.Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"  {path.relative_to(DOCS)}  {path.stat().st_size / 1024:.0f} KB")


def main() -> int:
    if not (STATIC / "index.html").exists():
        print("build the web app first: npm --prefix web run build", file=sys.stderr)
        return 1

    # docs/ is rebuilt from scratch every time, so nothing hand-made may live here —
    # the README's images are in media/ at the repo root for exactly that reason.
    if DOCS.exists():
        shutil.rmtree(DOCS)
    shutil.copytree(STATIC, DOCS)
    (DOCS / ".nojekyll").touch()  # keep Pages from eating the assets directory

    print("static endpoints:")
    write(DOCS / "api" / "config", {
        # demo_only hides the upload path: there is no backend here to run it.
        "demo_only": True,
        "has_key": False,
        "lang": "en",
        "langs": list(i18n.LANGS),
        "version": whatitdid.__version__,
        "question_sets": [{"id": q, "phases": load_question_set(q).phases,
                           "roles": load_question_set(q).roles}
                          for q in ("sre.v1", "code.v1")],
    })
    for lang in i18n.LANGS:
        write(DOCS / "api" / "strings" / lang, i18n.strings(lang))

    # Nothing was profiled here and nothing can be; an empty list keeps the startup call
    # from 404ing on every visit.
    write(DOCS / "api" / "reports", [])

    agents = json.loads((DEMO / "agents.json").read_text(encoding="utf-8"))
    write(DOCS / "api" / "demo" / "agents", agents)

    sides = json.loads((DEMO / "compare.json").read_text(encoding="utf-8"))
    write(DOCS / "api" / "compare.json",
          run_compare(sides["before"], sides["after"], rounds=20000))

    total = sum(f.stat().st_size for f in DOCS.rglob("*") if f.is_file())
    print(f"\n{DOCS}  {total / 1024 / 1024:.1f} MB total")
    print("Publish: repository Settings -> Pages -> deploy from branch main, folder /docs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
