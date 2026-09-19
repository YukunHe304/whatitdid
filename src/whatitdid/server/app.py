"""HTTP API behind the web app.

Profiling a trajectory takes seconds to a minute, so it runs as a background job and the
browser polls. Everything else is a plain read.

Two rules this file exists to enforce:

  - A key is never returned to the browser, not even masked beyond a boolean. It is
    written to the user's config directory with owner-only permissions and read from
    there or from the environment.
  - Demo mode cannot label. It serves pre-computed data and refuses profiling outright,
    so `whatitdid demo` cannot quietly start spending someone's credits.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import pathlib
import shutil
import tempfile
import threading
import time
import uuid
import webbrowser
from typing import Any

from concurrent.futures import ThreadPoolExecutor

from fastapi import Body, FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import i18n
from ..compare import compare as run_compare
from ..core import profile
from ..labeler import KEY_FILES, ChatModel, Jev, LabelerError, load_question_set
from ..noise import load_reference
from ..watch import finished_runs, session_in

PACKAGE = pathlib.Path(__file__).resolve().parent.parent
STATIC = PACKAGE / "static"
DEMO = PACKAGE / "data" / "demo"
CONFIG_DIR = pathlib.Path(os.path.expanduser("~/.config/whatitdid"))
MAX_UPLOAD = 64 * 1024 * 1024


class Jobs:
    """In-memory job table. Deliberately not persisted — this is a local tool, and a
    half-finished job from a previous process is not worth resuming."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}

    def create(self, name: str) -> str:
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {"id": job_id, "name": name, "state": "running",
                                  "done": 0, "total": 0, "started": time.time(),
                                  "error": None, "result": None}
        return job_id

    def update(self, job_id: str, **fields) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(fields)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def listing(self) -> list[dict]:
        with self._lock:
            return [{k: v for k, v in job.items() if k != "result"}
                    for job in self._jobs.values()]


class Watch:
    """One directory being followed while a benchmark writes into it.

    The CLI version writes HTML and a summary file as it goes. This one keeps the reports
    in the same place the rest of the server does, so a task that finishes mid-run is
    something you can click on immediately rather than after the round ends.
    """

    def __init__(self, root: pathlib.Path, questions: str, reports: dict,
                 labeler_kind: str, concurrency: int, poll: int, parallel: int = 2):
        self.root, self.questions, self.reports = root, questions, reports
        self.labeler_kind, self.concurrency, self.poll = labeler_kind, concurrency, poll
        self.parallel = parallel
        self.id = uuid.uuid4().hex[:12]
        self.state = "running"
        self.error: str | None = None
        self.started = time.time()
        self.seen: set[str] = set()
        self.total = 0          # tasks the directory holds, not just the ones started
        self.done: list[dict] = []
        self.failed: list[dict] = []
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def stop(self) -> None:
        self._stop.set()

    def snapshot(self) -> dict:
        with self._lock:
            return {"id": self.id, "root": str(self.root), "state": self.state,
                    "error": self.error, "questions": self.questions,
                    "seconds": round(time.time() - self.started, 1),
                    "found": self.total, "done": list(self.done),
                    "failed": list(self.failed)}

    def run(self) -> None:
        try:
            labeler = Jev() if self.labeler_kind == "jev" else ChatModel(model="deepseek-flash")
        except LabelerError as exc:
            with self._lock:
                self.state, self.error = "error", str(exc)
            return
        def handle(problem: str, run_dir: pathlib.Path) -> None:
            session = session_in(run_dir)
            if session is None:
                with self._lock:
                    self.failed.append({"problem": problem, "why": "no session file found"})
                return
            t0 = time.monotonic()
            try:
                rep = profile(session, labeler=labeler, questions=self.questions,
                              workers=self.concurrency)
                self.reports[problem] = rep.to_web_dict()
                with self._lock:
                    self.done.append({"problem": problem, "n_turns": rep.to_dict()["n_turns"],
                                      "seconds": round(time.monotonic() - t0, 1)})
            except Exception as exc:  # noqa: BLE001  a checkup must not stop the watch
                with self._lock:
                    self.failed.append({"problem": problem,
                                        "why": f"{type(exc).__name__}: {exc}"})

        # Several tasks at a time, as the CLI does. Profiling is network-bound, so waiting
        # for one trajectory before looking at the next wastes the whole point.
        pool = ThreadPoolExecutor(max_workers=self.parallel)
        try:
            while not self._stop.is_set():
                ready = finished_runs(self.root)
                with self._lock:
                    self.total = len(ready)
                for problem, run_dir in ready:
                    if self._stop.is_set() or problem in self.seen:
                        continue
                    self.seen.add(problem)
                    pool.submit(handle, problem, run_dir)
                if self._stop.wait(self.poll):
                    break
        finally:
            pool.shutdown(wait=True)
        with self._lock:
            if self.state == "running":
                self.state = "stopped"


def write_key(name: str, value: str) -> pathlib.Path:
    """Store a key where only this user can read it."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = CONFIG_DIR / ("typesafe.env" if name == "TYPESAFE_API_KEY" else "chat.env")
    lines = []
    if path.exists():
        lines = [l for l in path.read_text(encoding="utf-8").splitlines()
                 if not l.startswith(name)]
    lines.append(f"{name}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)
    CONFIG_DIR.chmod(0o700)
    return path


def key_present() -> bool:
    if os.environ.get("TYPESAFE_API_KEY"):
        return True
    return any(pathlib.Path(os.path.expanduser(p)).exists() for p in KEY_FILES)


def load_demo(name: str) -> Any:
    path = DEMO / f"{name}.json"
    if not path.exists():
        raise HTTPException(404, f"no bundled demo data for {name!r}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_summary_dir(path: pathlib.Path) -> dict[str, dict]:
    if path.is_dir():
        path = path / "summary.jsonl"
    if not path.exists():
        raise HTTPException(400, f"no summary.jsonl at {path}")
    out = {}
    for line in path.open(encoding="utf-8"):
        if not line.strip():
            continue
        row = json.loads(line)
        key = row.get("problem") or row.get("task") or pathlib.Path(row.get("source", "")).stem
        out[key] = row
    return out


def build_app(*, lang: str = "en", reports_dir: pathlib.Path | None = None,
              demo_only: bool = False) -> FastAPI:
    app = FastAPI(title="whatitdid", docs_url=None, redoc_url=None)
    jobs = Jobs()
    watches: dict[str, Watch] = {}
    reports: dict[str, dict] = {}
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="whatitdid-"))

    if reports_dir and reports_dir.exists():
        for path in sorted(reports_dir.glob("*.json")):
            with contextlib.suppress(ValueError, OSError):
                reports[path.stem] = json.loads(path.read_text(encoding="utf-8"))

    @app.get("/api/config")
    def get_config():
        return {
            "demo_only": demo_only,
            "has_key": key_present(),
            "lang": lang,
            "langs": list(i18n.LANGS),
            "version": __import__("whatitdid").__version__,
            "question_sets": [
                {"id": q, **{k: v for k, v in
                             (("phases", load_question_set(q).phases),
                              ("roles", load_question_set(q).roles))}}
                for q in ("sre.v1", "code.v1")],
        }

    @app.get("/api/strings/{language}")
    def get_strings(language: str):
        if language not in i18n.LANGS:
            raise HTTPException(404, f"unknown language {language!r}")
        return i18n.strings(language)

    @app.post("/api/config/key")
    def set_key(payload: dict = Body(...)):
        if demo_only:
            raise HTTPException(403, "demo mode does not take a key")
        value = (payload.get("key") or "").strip()
        if not value:
            raise HTTPException(400, "empty key")
        name = payload.get("name", "TYPESAFE_API_KEY")
        if name not in {"TYPESAFE_API_KEY", "AGENT_API_KEY"}:
            raise HTTPException(400, f"unexpected key name {name!r}")
        path = write_key(name, value)
        # Never echo the value back, not even truncated.
        return {"stored": True, "path": str(path), "has_key": key_present()}

    @app.get("/api/noise")
    def get_noise(questions: str = "sre.v1"):
        return load_reference(questions)

    @app.get("/api/demo/{name}")
    def get_demo(name: str):
        if name not in {"agents", "compare"}:
            raise HTTPException(404, f"unknown demo dataset {name!r}")
        return load_demo(name)

    @app.get("/api/reports")
    def list_reports():
        return [{"id": rid, "agent": r.get("agent"), "model": r.get("model"),
                 "n_turns": r.get("n_turns"), "questions": r.get("questions"),
                 "truthfulness": r.get("truthfulness")}
                for rid, r in reports.items()]

    @app.get("/api/reports/{report_id}")
    def get_report(report_id: str):
        if report_id not in reports:
            raise HTTPException(404, f"no report {report_id!r}")
        return reports[report_id]

    def _profile_job(job_id: str, path: pathlib.Path, name: str, questions: str,
                     labeler_kind: str, concurrency: int, check_narration: bool):
        try:
            labeler = Jev() if labeler_kind == "jev" else ChatModel(model="deepseek-flash")
        except LabelerError as exc:
            jobs.update(job_id, state="error", error=str(exc))
            return
        try:
            rep = profile(path, labeler=labeler, questions=questions, workers=concurrency,
                          check_narration=check_narration,
                          progress=lambda d, t: jobs.update(job_id, done=d, total=t))
            payload = rep.to_web_dict()
            reports[name] = payload
            jobs.update(job_id, state="done", result=name)
        except Exception as exc:  # noqa: BLE001
            jobs.update(job_id, state="error", error=f"{type(exc).__name__}: {exc}")

    @app.post("/api/profile")
    async def start_profile(file: UploadFile | None = None, path: str | None = None,
                            questions: str = "sre.v1", labeler: str = "jev",
                            concurrency: int = 8, check_narration: bool = True):
        if demo_only:
            raise HTTPException(
                403, "this is the bundled demo; run `whatitdid serve` to profile your own runs")
        if file is None and not path:
            raise HTTPException(400, "send a file or a path")

        if file is not None:
            target = scratch / f"{uuid.uuid4().hex[:8]}-{pathlib.Path(file.filename or 'session').name}"
            size = 0
            with target.open("wb") as fh:
                while chunk := await file.read(1 << 20):
                    size += len(chunk)
                    if size > MAX_UPLOAD:
                        target.unlink(missing_ok=True)
                        raise HTTPException(413, "file larger than 64 MB")
                    fh.write(chunk)
            name = pathlib.Path(file.filename or target.name).stem
        else:
            target = pathlib.Path(path).expanduser()
            if not target.exists():
                raise HTTPException(400, f"no such file: {target}")
            name = target.stem

        job_id = jobs.create(name)
        asyncio.get_running_loop().run_in_executor(
            None, _profile_job, job_id, target, name, questions, labeler, concurrency,
            check_narration)
        return {"job": job_id, "name": name}

    @app.post("/api/watch")
    def start_watch(payload: dict = Body(...)):
        if demo_only:
            raise HTTPException(403, "this is the bundled demo; run `whatitdid serve` to watch a run")
        root = pathlib.Path(payload.get("root", "")).expanduser()
        if not root.is_dir():
            raise HTTPException(400, f"not a directory: {root}")
        watch = Watch(root, payload.get("questions", "sre.v1"), reports,
                      payload.get("labeler", "jev"), int(payload.get("concurrency", 8)),
                      int(payload.get("poll", 15)), int(payload.get("parallel", 2)))
        watches[watch.id] = watch
        threading.Thread(target=watch.run, daemon=True).start()
        return watch.snapshot()

    @app.get("/api/watch")
    def list_watches():
        return [w.snapshot() for w in watches.values()]

    @app.get("/api/watch/{watch_id}")
    def get_watch(watch_id: str):
        watch = watches.get(watch_id)
        if not watch:
            raise HTTPException(404, f"no watch {watch_id!r}")
        return watch.snapshot()

    @app.post("/api/watch/{watch_id}/stop")
    def stop_watch(watch_id: str):
        watch = watches.get(watch_id)
        if not watch:
            raise HTTPException(404, f"no watch {watch_id!r}")
        watch.stop()
        return watch.snapshot()

    @app.get("/api/jobs")
    def list_jobs():
        return jobs.listing()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(404, f"no job {job_id!r}")
        return job

    @app.post("/api/compare")
    def post_compare(payload: dict = Body(...)):
        if payload.get("demo"):
            sides = load_demo("compare")
            before, after = sides["before"], sides["after"]
            repeats = None
        else:
            before = read_summary_dir(pathlib.Path(payload["before"]).expanduser())
            after = read_summary_dir(pathlib.Path(payload["after"]).expanduser())
            repeats = [read_summary_dir(pathlib.Path(p).expanduser())
                       for p in payload.get("repeats", [])] or None
        try:
            return run_compare(before, after, rounds=int(payload.get("rounds", 20000)),
                               seed=int(payload.get("seed", 0)), repeats=repeats)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.on_event("shutdown")
    def _cleanup():
        for watch in watches.values():
            watch.stop()
        shutil.rmtree(scratch, ignore_errors=True)

    if STATIC.exists():
        app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    else:
        @app.get("/")
        def _missing():
            return JSONResponse(
                {"error": "the web UI was not built into this install",
                 "fix": "run `npm --prefix web install && npm --prefix web run build`"},
                status_code=503)

    return app


def serve(*, host: str = "127.0.0.1", port: int = 8321, lang: str = "en",
          open_browser: bool = True, reports_dir: pathlib.Path | None = None,
          demo_only: bool = False) -> int:
    import uvicorn

    app = build_app(lang=lang, reports_dir=reports_dir, demo_only=demo_only)
    url = f"http://{host}:{port}/"
    if demo_only:
        print(f"whatitdid demo — bundled sample data, no API key needed\n{url}")
    else:
        print(f"whatitdid — {url}")
        if not key_present():
            print("  no TYPESAFE_API_KEY yet; the app will ask for one before it labels anything")
    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0
