"""Measure the repeat-noise floor that ships with the package.

Same agent, same config, same tasks, run twice. Whatever the metrics move by is the floor
a real change has to clear. Without this number every comparison is guesswork dressed up
in a confidence interval.

    python scripts/measure_noise.py --out src/agentvitals/data/noise_reference.json

This is a build script. It needs a Jev key and a local directory of benchmark runs; the
JSON it produces is committed so users get a fallback baseline out of the box.

WHAT COUNTS AS A REPEAT, because getting this wrong is worse than having no baseline.
Both runs must have completed. An aborted run is shorter, and a shorter run has a
different behaviour profile for reasons that have nothing to do with randomness — you
would be measuring truncation and shipping it as noise.

The first attempt at this used `lite21_max_final/superseded/` as the second arm and had
to be thrown away: those runs were superseded precisely because they died early. Step
counts came out 12 vs 74, 116 vs 75, 33 vs 75, 41 vs 80 for the same problem and config,
and several rows had empty success fields. `check_completed` below is what stops that
from happening again silently.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from agentvitals import noise, profile  # noqa: E402
from agentvitals.labeler import Jev  # noqa: E402

ROOT = pathlib.Path(
    "/Users/yukun/Documents/ChatGPT/research/output/sregym-diagnosis-ladder-20260916/oncluster/lite21_max_final")
TRANSCRIPT = "baseline_transcript.jsonl"


def find_pairs(root: pathlib.Path) -> list[tuple[str, pathlib.Path, pathlib.Path]]:
    """Problems that were run twice under the same configuration."""
    pairs = []
    for old_dir in sorted((root / "superseded").glob("*/")):
        problem = old_dir.name
        new_dir = root / "problems" / problem
        old = next(old_dir.rglob(TRANSCRIPT), None)
        new = next(new_dir.rglob(TRANSCRIPT), None) if new_dir.exists() else None
        if old and new:
            pairs.append((problem, old, new))
    return pairs


def check_completed(pairs, tolerance: float = 0.5) -> list[str]:
    """Reject pairs where one arm is obviously a truncated run.

    Two completed runs of the same config wander; they do not differ by 6x in length.
    Anything that far apart is an aborted run, and folding it in would inflate the floor
    with something that is not noise at all.
    """
    complaints = []
    for problem, old, new in pairs:
        a = sum(1 for _ in old.open(encoding="utf-8", errors="ignore"))
        b = sum(1 for _ in new.open(encoding="utf-8", errors="ignore"))
        if min(a, b) == 0 or min(a, b) / max(a, b) < tolerance:
            complaints.append(f"{problem}: {a} vs {b} transcript lines — one arm looks truncated")
    return complaints


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=pathlib.Path, default=ROOT)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--questions", default="sre.v1")
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--allow-uneven", action="store_true",
                    help="profile pairs even when one arm looks truncated (you should not)")
    args = ap.parse_args()

    pairs = find_pairs(args.root)
    if len(pairs) < 3:
        print(f"only {len(pairs)} repeated problems found — need at least 3", file=sys.stderr)
        return 1

    complaints = check_completed(pairs)
    if complaints and not args.allow_uneven:
        print("these pairs are not clean repeats:", file=sys.stderr)
        for line in complaints:
            print(f"  {line}", file=sys.stderr)
        print("\nA truncated arm measures truncation, not run-to-run noise. Point --root at a\n"
              "directory where the same config completed twice, or pass --allow-uneven if you\n"
              "genuinely know better.", file=sys.stderr)
        return 1

    print(f"{len(pairs)} problems were run twice under the same config:")
    for problem, _, _ in pairs:
        print(f"  {problem}")

    labeler = Jev()
    runs: list[dict[str, dict]] = [{}, {}]
    started = time.monotonic()
    for problem, old, new in pairs:
        for index, path in ((0, old), (1, new)):
            t0 = time.monotonic()
            rep = profile(path, labeler=labeler, questions=args.questions,
                          workers=args.concurrency)
            runs[index][problem] = rep.to_dict()
            print(f"  run{index + 1} {problem:48} {rep.to_dict()['n_turns']:>3} steps "
                  f"{time.monotonic() - t0:5.1f}s")

    measured = noise.estimate(runs)
    failures = labeler.failures.to_dict()
    print(f"\n{time.monotonic() - started:.0f}s total, {failures['total']} failed calls")

    payload = {
        args.questions: {
            "metrics": {k: round(v, 4) for k, v in sorted(measured["metrics"].items())},
            "about": (
                f"Repeat-noise floor: the largest mean paired shift seen between two runs of "
                f"the SAME configuration, over {len(pairs)} SREGym-Lite problems "
                f"(baseline agent, deepseek-flash, reasoning effort max). "
                f"A change smaller than this is not a finding. "
                f"Measured {time.strftime('%Y-%m-%d')} from {measured['n_pairs']} run pair(s). "
                f"Only {len(pairs)} problems, so treat it as provisional — if you have your own "
                f"repeated runs, pass them with --repeat and use yours instead."
            ),
            "n_problems": len(pairs),
            "n_pairs": measured["n_pairs"],
            "problems": [p for p, _, _ in pairs],
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
