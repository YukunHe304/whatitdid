# whatitdid

**Read any CLI agent's session file and report what the run actually did — step by step, with error bars.**

[**Live demo**](https://yukunhe304.github.io/whatitdid/) · [中文](https://github.com/YukunHe304/whatitdid/blob/main/README.zh.md) ·
[![ci](https://github.com/YukunHe304/whatitdid/actions/workflows/ci.yml/badge.svg)](https://github.com/YukunHe304/whatitdid/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/YukunHe304/whatitdid/blob/main/LICENSE)

```bash
uvx whatitdid demo        # opens the browser on real bundled data. No API key needed.
```

![Seven CLI agents on the same fault, each run drawn as a trace of labelled steps](https://raw.githubusercontent.com/YukunHe304/whatitdid/main/media/agents.png)

---

A benchmark hands you two things: a score, and tens of thousands of lines of log. Nothing
in between. You know Claude Code got 66.7% and Codex got 61.9%; you have no idea what
either of them actually *did*.

whatitdid labels every step of a run — what kind of move it was, whether it turned up
anything new, whether it changed something and then checked — and then compares two rounds
against the noise a re-run produces anyway.

```bash
whatitdid run session.jsonl --out report.html   # one run
whatitdid watch ./runs --out reports/           # profile each task as the benchmark finishes it
whatitdid compare ./before ./after              # what did the change actually change
whatitdid serve                                 # the web app
```

## What it tells you that a score does not

Seven CLI agents, same Kubernetes fault, 153 steps, labelled:

| agent | probe | inspect | report | re-examining | said-and-did |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 0.10 | **0.42** | 0.12 | **0.70** | 85% |
| claudecode | **0.00** | 0.18 | 0.25 | 0.56 | 62% |
| codex | 0.09 | 0.15 | 0.12 | 0.47 | 73% |
| copilot | **0.00** | 0.22 | **0.26** | 0.36 | 67% |
| gemini | 0.08 | 0.30 | 0.11 | 0.47 | **53%** |
| opencode | 0.08 | 0.20 | 0.18 | 0.54 | 67% |
| stratus | **0.00** | 0.24 | 0.18 | 0.63 | 74% |

`probe` is 0.00 for claudecode, copilot and stratus: across those runs, **none of them
ever exercises the system to see how it behaves.** They read state and decide. If your
environment punishes an untested fix, that matters more than five points of pass rate.

`said-and-did` is how often the agent did the thing it had just said it would do, checked
over the next three steps. It ranges from 53% to 85%.

> **Read this table as a demonstration, not a verdict on these products.** It is one run
> each on one problem — enough to show the instrument works and that the agents differ,
> nowhere near enough to rank them. Every number here comes from the data bundled in this
> repository, so you can reproduce it (`uvx whatitdid demo`) or disagree with it. Drawing
> a real conclusion about any of these agents means many problems and repeated runs, and
> then holding the differences up against the repeat-noise floor below — which is the
> whole point of the next section.

## Why compare is the point

You change something — a prompt, a model, a reasoning effort — and re-run the benchmark.
The score moves a couple of points across twenty-odd tasks and the interval straddles
zero. You have learned nothing, four hours later.

Real example, same agent and same 21 problems, reasoning effort raised:

```
diagnosis pass rate   +0.190  (−0.000, +0.429)   crosses zero — says nothing

report                −0.084  (−0.138, −0.038)    5/21 up
said-and-did rate     −0.061  (−0.093, −0.032)    2/21 up   ← 19 of 21 tasks got worse
probe                 +0.056  (+0.020, +0.091)   15/21 up
re-examining          +0.045  (+0.011, +0.083)   15/21 up
```

The score is 21 binary outcomes. The behaviour is two thousand steps, six questions each —
two orders of magnitude more observations from the same compute.

### The second hurdle, which everyone skips

A paired bootstrap tells you whether a *different draw of tasks* would have shown the same
thing. It says nothing about whether *re-running the same config* would have. Agents are
not deterministic, and that second wobble is often the larger one.

So whatitdid asks for a repeat-noise floor and refuses to rule without one:

```
metric              change        95% interval  tasks up  repeat noise  verdict
report              -0.084  (-0.138, -0.038)      5/21             —    ? no repeat baseline
said-and-did rate   -0.061  (-0.093, -0.032)      2/21             —    ? no repeat baseline
probe               +0.056  (+0.020, +0.091)     15/21             —    ? no repeat baseline
survey              +0.023  (-0.009, +0.053)     14/21             —      interval crosses zero
```

That is the real output for this comparison, because those two rounds have no third run to
measure against. **The tool says so rather than passing the bootstrap off as a verdict.**

Give it repeated runs of the same configuration and the last two columns fill in: each
change is then judged against how far that metric drifts when nothing changed, and anything
smaller is marked `within noise` however tight its interval looks.

```bash
whatitdid compare ./before ./after --repeat ./before-again
```

No shipped default. A floor measured on someone else's agent, on someone else's tasks, is
not your floor — and a wrong floor is worse than none, because it makes noise look like a
finding.

## Formats

Session files are identified by their **contents, not their filename**, so you point at
whatever the agent wrote and it works:

`claudecode` · `codex` · `copilot` · `gemini` · `opencode` · `stratus` · `baseline`

No SDK, no instrumentation, no changes to the agent or the benchmark.

## The questions

Six per step, answered in one call. One names the kind of move and changes with the
domain; the other five are identical across domains, so a coding agent and an ops agent
stay comparable on those.

| | |
| --- | --- |
| **what kind of move** | domain-specific — `sre.v1`: survey / localize / inspect / probe / repair / verify / report. `code.v1`: survey / localize / read / reproduce / edit / test / revert / report |
| testing a suspicion | or a routine action it would take whatever the fault was |
| brought new information | or only confirmed what was already visible |
| re-examining | something an earlier step already looked at |
| changed the system | rather than only reading from it |
| how narrowly aimed | 0 = the whole system, 4 = one property of one object |

The set is a file, not a constant — `--questions path/to/your.json`. It is recorded in
every report, and `compare` **refuses** to compare two runs labelled with different sets.

## The labeler

Default is [Jev](https://docs.typesafe.ai), TypeSafe's System One model: several typed
questions answered in one parallel pass, probability distributions rather than hard
labels, and no text output channel at all.

|  | Jev | a chat model |
| --- | --- | --- |
| one 28-step trajectory | **6s / $0.008** | 3.7 min / $0.028 |
| 21-problem benchmark | **2.4 min / $0.36** | 2.8 h / $1.27 |
| labels that flip when the agent's narration is included | **9%** | 28% |
| median top-1 probability | 0.88 | 0.70 |

That last row is why this is affordable at all, and the third row is why it is trustworthy
across agents. Agents differ 4.5x in how much they narrate; a labeler that reads the
narration will score the talkative one as more methodical. **whatitdid never shows the
agent's own words to the pass that produces the comparable labels** — narration is used
only for a separate said-and-did check.

Without a Jev key, `--labeler chat` uses any OpenAI-compatible endpoint. It is slower,
costlier, and biased in the way above; use it for a single run, not for comparing agents.

## Keys

Read from `TYPESAFE_API_KEY`, or `~/.config/whatitdid/typesafe.env` (mode 600). The web
app can write one there for you. Nothing is ever committed, logged, or sent anywhere but
the labeling API you chose. Trajectories stay on your machine.

## Install

```bash
pip install whatitdid
```

Python 3.11+. From source:

```bash
git clone https://github.com/YukunHe304/whatitdid && cd whatitdid
pip install -e ".[dev]"
npm --prefix web install && npm --prefix web run build   # only if you change the web app
pytest
```

## Python

```python
from whatitdid import profile, compare

rep = profile("session.jsonl")
rep.to_html("report.html")
rep.to_dict()        # ids only, no display strings — safe to compare across machines
rep.to_web_dict()    # the above plus step text, for a UI

print(compare(before, after, repeats=[before_again]))
```

## What it is not

It does not run agents or benchmarks — point it at what you already have.
[`vercel-labs/agent-eval`](https://github.com/vercel-labs/agent-eval) runs them; this
reads what they leave behind.

It does not tell you whether an answer was right. That is your benchmark's job. This tells
you how the agent got there.

## Licence

Apache-2.0. The trajectory converter derives from
[Harbor](https://github.com/harbor-framework/harbor) (Apache-2.0) and
[SREGym](https://github.com/SREGym/SREGym) (MIT); see [NOTICE](https://github.com/YukunHe304/whatitdid/blob/main/NOTICE).
