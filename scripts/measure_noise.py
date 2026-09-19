"""Measure the repeat-noise floor that ships with the package.

Same agent, same config, same tasks, run more than once. Whatever the metrics move by is
the floor a real change has to clear. Without this number every comparison is guesswork
dressed up in a confidence interval.

    python scripts/measure_noise.py --out src/whatitdid/data/noise_reference.json \
        --run <dir-of-run-1> --run <dir-of-run-2> --label "deepseek-flash effort=max"

Each --run is a directory that will be walked for per-task session files. Tasks are paired
across runs by the directory name they sit under.

WHAT COUNTS AS A REPEAT, because getting this wrong is worse than having no baseline.
Every arm must have completed. An aborted run is shorter, and a shorter run has a
different behaviour profile for reasons that have nothing to do with randomness — you
would be measuring truncation and shipping it as noise.

Two ways this has already gone wrong on real data, both now guarded:

  1. A `superseded/` directory as the second arm. Those runs were superseded precisely
     because they died early — step counts of 12 vs 74 for the same problem. That measures
     truncation. `check_even` catches it.

  2. A directory that looked like a second run but was the first one with four problems
     re-run: 17 of 21 transcripts byte-identical. Comparing a file against itself gives a
     delta of exactly zero, so the floor came out at +-0.000 and every subsequent change
     would have looked significant. `check_distinct` catches it, and it runs first because
     it is the cheapest and the most dangerous to miss.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from whatitdid import noise, profile  # noqa: E402
from whatitdid.labeler import Jev  # noqa: E402
from whatitdid.watch import finished_runs, session_in  # noqa: E402


def collect(root: pathlib.Path) -> dict[str, pathlib.Path]:
    """Task id -> its session file, for every finished task under `root`."""
    out = {}
    for problem, run_dir in finished_runs(root):
        session = session_in(run_dir)
        if session is not None:
            out[problem] = session
    return out


def check_distinct(runs: list[dict[str, pathlib.Path]], names: list[str]) -> dict[str, str]:
    """Reject tasks whose arms are the same file.

    A "second run" is often a directory assembled from the first one with a few problems
    re-run. Comparing a transcript against itself gives a delta of exactly zero, so the
    floor comes out near zero and every later change looks significant — the most
    dangerous possible failure, because the numbers look clean.

    This is the first thing to check and it costs one hash per file.
    """
    shared = sorted(set.intersection(*[set(r) for r in runs]))
    complaints = {}
    for task in shared:
        digests = {hashlib.md5(r[task].read_bytes()).hexdigest() for r in runs}
        if len(digests) < len(runs):
            complaints[task] = "the arms are the same file, byte for byte"
    return complaints


def check_even(runs: list[dict[str, pathlib.Path]], names: list[str],
               tolerance: float = 0.5) -> dict[str, str]:
    """Reject tasks where one arm is obviously a truncated run.

    Two completed runs of the same config wander; they do not differ several-fold in
    length. Anything that far apart is an aborted run, and folding it in would inflate the
    floor with something that is not noise at all.
    """
    shared = sorted(set.intersection(*[set(r) for r in runs]))
    complaints = {}
    for task in shared:
        sizes = [sum(1 for _ in r[task].open(encoding="utf-8", errors="ignore")) for r in runs]
        if min(sizes) == 0 or min(sizes) / max(sizes) < tolerance:
            pairs = ", ".join(f"{n}={s}" for n, s in zip(names, sizes))
            complaints[task] = f"{pairs} transcript lines — one arm looks truncated"
    return complaints


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=pathlib.Path, action="append", required=True,
                    help="a directory of runs under one configuration; pass it twice or more")
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--label", default="", help="what configuration these runs share")
    ap.add_argument("--questions", default="sre.v1")
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--drop-uneven", action="store_true",
                    help="exclude tasks where one arm looks truncated and measure on the rest")
    ap.add_argument("--allow-uneven", action="store_true",
                    help="keep tasks where one arm looks truncated (you should not)")
    args = ap.parse_args()

    if len(args.run) < 2:
        print("need at least two --run directories", file=sys.stderr)
        return 1

    found = [collect(root) for root in args.run]
    names = [root.name for root in args.run]
    for name, tasks in zip(names, found):
        print(f"{name}: {len(tasks)} finished tasks")

    shared = sorted(set.intersection(*[set(f) for f in found]))
    if len(shared) < 3:
        print(f"only {len(shared)} tasks appear in every run — need at least 3", file=sys.stderr)
        return 1

    complaints = {**check_distinct(found, names), **check_even(found, names)}
    dropped: list[str] = []
    if complaints and not args.allow_uneven:
        print(f"\n{len(complaints)} of {len(shared)} shared tasks are not clean repeats:")
        for task, why in list(complaints.items())[:10]:
            print(f"  {task}: {why}")
        if not args.drop_uneven:
            print("\nA truncated arm measures truncation, not run-to-run noise. Re-run with\n"
                  "--drop-uneven to exclude these and measure on the rest, or --allow-uneven if\n"
                  "you genuinely know better.", file=sys.stderr)
            return 1
        dropped = sorted(complaints)
        shared = [t for t in shared if t not in complaints]
        print(f"  dropping them; measuring on the remaining {len(shared)}")
        if len(shared) < 3:
            print("too few clean tasks left", file=sys.stderr)
            return 1

    print(f"\n{len(shared)} tasks run {len(found)}x under the same config")
    labeler = Jev()
    runs: list[dict[str, dict]] = [{} for _ in found]
    started = time.monotonic()
    for task in shared:
        line = f"  {task:50}"
        for index, tasks in enumerate(found):
            rep = profile(tasks[task], labeler=labeler, questions=args.questions,
                          workers=args.concurrency)
            runs[index][task] = rep.to_dict()
            line += f"  {rep.to_dict()['n_turns']:>4}"
        print(line, flush=True)

    measured = noise.estimate(runs)
    failures = labeler.failures.to_dict()
    print(f"\n{time.monotonic() - started:.0f}s, {failures['total']} failed calls")
    if failures["total"]:
        print(f"  {failures['by_cause']}")

    payload = {
        args.questions: {
            "metrics": {k: round(v, 4) for k, v in sorted(measured["metrics"].items())},
            "about": (
                f"Repeat-noise floor: the largest mean paired shift between two runs of the "
                f"SAME configuration ({args.label or 'unspecified'}) over {len(shared)} "
                f"SREGym-Lite problems"
                + (f" ({len(dropped)} more excluded: one arm was truncated)" if dropped else "")
                + f". A change smaller than this is not a finding. "
                f"Measured {time.strftime('%Y-%m-%d')} from {measured['n_pairs']} run pair(s). "
                f"These are one agent on one benchmark — if you have your own repeated runs, "
                f"pass them with --repeat and use yours instead."
            ),
            "label": args.label,
            "n_problems": len(shared),
            "dropped_problems": dropped,
            "n_runs": len(found),
            "n_pairs": measured["n_pairs"],
            "runs": names,
            "problems": shared,
            "measured_on": time.strftime("%Y-%m-%d"),
        }
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if args.out.exists():
        existing = json.loads(args.out.read_text(encoding="utf-8"))
    existing.update(payload)
    args.out.write_text(json.dumps(existing, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nrepeat-noise floor ({args.questions}):")
    for key, value in sorted(measured["metrics"].items(), key=lambda kv: -kv[1]):
        print(f"  {key:22} ±{value:.3f}")
    print(f"\nwritten to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
