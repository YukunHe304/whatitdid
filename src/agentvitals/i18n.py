"""Every user-facing string, in both languages, keyed by a stable id.

Nothing else in the package may hold a display string. The rule that makes this work:
data structures carry ids, never words. A profile computed under one language must be
byte-identical to the same profile computed under the other, so that two runs labelled
on different machines stay comparable.
"""

from __future__ import annotations

LANGS = ("en", "zh")
DEFAULT_LANG = "en"

# The one domain-specific question. Its option ids come from the question set; these are
# the display names for the shipped sets. An unknown id falls back to the id itself.
PHASES: dict[str, dict[str, str]] = {
    "survey": {"en": "survey", "zh": "大范围扫"},
    "localize": {"en": "localize", "zh": "缩小范围"},
    "inspect": {"en": "inspect", "zh": "细看一个对象"},
    "probe": {"en": "probe", "zh": "主动试系统"},
    "repair": {"en": "repair", "zh": "改动"},
    "verify": {"en": "verify", "zh": "验证改动"},
    "report": {"en": "report", "zh": "写结论"},
    "other": {"en": "unclassified", "zh": "归不了类"},
    # code.v1
    "read": {"en": "read code", "zh": "读代码"},
    "reproduce": {"en": "reproduce", "zh": "复现"},
    "edit": {"en": "edit", "zh": "改代码"},
    "test": {"en": "run tests", "zh": "跑测试"},
    "revert": {"en": "revert", "zh": "回退"},
}

# The five portable questions plus the two derived numbers. These ids are the contract:
# they appear in to_dict(), in summary.jsonl, in the compare output and in the web API.
METRICS: dict[str, dict[str, str]] = {
    "hypothesis_driven": {"en": "testing a suspicion", "zh": "验具体怀疑"},
    "new_information": {"en": "brought new information", "zh": "带来新信息"},
    "revisits": {"en": "re-examining", "zh": "在重看"},
    "changes_system": {"en": "changed the system", "zh": "改动系统"},
    "targeting": {"en": "how narrowly aimed", "zh": "瞄得多准"},
    "labeler_confidence": {"en": "labeler confidence", "zh": "标注器把握"},
    "truthfulness": {"en": "said-and-did rate", "zh": "自述兑现率"},
}

METRIC_HELP: dict[str, dict[str, str]] = {
    "hypothesis_driven": {
        "en": "Testing one specific suspicion, rather than a routine action it would take whatever the fault was.",
        "zh": "在验一个具体怀疑，而不是不管故障是什么都会做的例行动作。"},
    "new_information": {
        "en": "The result revealed something earlier steps had not already established.",
        "zh": "这一步的结果揭示了前面还没确立的东西。"},
    "revisits": {
        "en": "Re-examines something an earlier step already examined.",
        "zh": "又看了一遍前面已经看过的东西。"},
    "changes_system": {
        "en": "Modifies the system rather than only reading from it.",
        "zh": "改动了系统，而不是只读。"},
    "targeting": {
        "en": "0 = the whole system, 4 = one property of one object.",
        "zh": "0＝整个系统，4＝某个对象的某个属性。"},
    "labeler_confidence": {
        "en": "Median top-1 probability. Low means the steps did not fit the categories.",
        "zh": "最高标签概率的中位数。低说明这些步子不太落在这组分类里。"},
    "truthfulness": {
        "en": "It said what it would do next; did the following three steps do it?",
        "zh": "它说了下一步要做什么，后面三步真做了吗。"},
}

# Findings carry numbers, not sentences. The sentence is assembled here.
FINDINGS: dict[str, dict[str, str]] = {
    "waste": {
        "en": "{count}/{total} steps re-examine something already seen without turning up anything new",
        "zh": "{count}/{total} 步在重看已经看过的东西，而且没带来新信息"},
    "blind_spot": {
        "en": "Almost absent from the whole run: {phases}",
        "zh": "整条轨迹几乎没有这些行为：{phases}"},
    "unverified_change": {
        "en": "{count} changes with no verifying action in the five steps that follow",
        "zh": "{count} 处改动之后的五步内没有任何验证动作"},
    "plumbing": {
        "en": "{count}/{total} steps do not look like investigation — most likely the harness's own plumbing leaking into the trajectory",
        "zh": "{count}/{total} 步不像调查动作，多半是 harness 自己的管道进了轨迹"},
    "drift": {
        "en": "{count}/{total} steps test no particular suspicion — routine looking-around",
        "zh": "{count}/{total} 步不是在验证任何具体怀疑，是例行翻看"},
}

UI: dict[str, dict[str, str]] = {
    "report_title": {"en": "{agent} trajectory checkup", "zh": "{agent} 轨迹体检"},
    "index_title": {"en": "Trajectory checkup summary", "zh": "轨迹体检汇总"},
    "steps": {"en": "steps", "zh": "步"},
    "questions": {"en": "question set", "zh": "问题集"},
    "where_steps_went": {"en": "Where the steps went", "zh": "步数花在哪"},
    "worth_acting_on": {"en": "Worth acting on", "zh": "该动手的地方"},
    "step_by_step": {"en": "Step by step", "zh": "逐步"},
    "nothing_found": {"en": "Nothing obviously wrong.", "zh": "没有发现明显问题。"},
    "trust_high": {"en": "It generally does what it says", "zh": "说话基本算数"},
    "trust_mid": {"en": "It mostly does what it says", "zh": "说话大致算数"},
    "trust_low": {"en": "What it says and what it does do not line up", "zh": "说的和做的对不太上"},
    "trust_line": {"en": "Stated an intention on {stated} steps, carried it out on {carried} — {rate:.0%}.",
                   "zh": "{stated} 步说了打算做什么，其中 {carried} 步真做了——{rate:.0%}。"},
    "trust_none": {"en": "This run states almost no intentions, so there is nothing to check them against.",
                   "zh": "这次运行几乎没有说过打算做什么，无从核对。"},
    "flag_waste": {"en": "wasted", "zh": "白跑"},
    "flag_changed": {"en": "changed the system", "zh": "改了系统"},
    "flag_other": {"en": "unclassified", "zh": "归不了类"},
    "flag_narration": {"en": "narration flipped the label", "zh": "自述改变了标签"},
    "kept_word": {"en": "kept its word", "zh": "说到做到"},
    "broke_word": {"en": "did not", "zh": "说了没做"},
    "problem": {"en": "problem", "zh": "题目"},
    "main_issues": {"en": "main issues", "zh": "主要问题"},
    "elapsed_min": {"en": "minutes elapsed", "zh": "已跑分钟"},
    "problems": {"en": "problems", "zh": "题数"},
    "total_steps": {"en": "total steps", "zh": "总步数"},
    "avg_truthfulness": {"en": "mean said-and-did", "zh": "平均自述兑现"},
    "total_findings": {"en": "findings", "zh": "发现"},
    # compare
    "cmp_header": {"en": "Paired bootstrap over {n} tasks, {rounds} resamples",
                   "zh": "配对自助法，{n} 个任务配对，重采样 {rounds} 次"},
    "cmp_metric": {"en": "metric", "zh": "指标"},
    "cmp_delta": {"en": "change", "zh": "差值"},
    "cmp_interval": {"en": "95% interval", "zh": "95% 区间"},
    "cmp_improved": {"en": "tasks up", "zh": "变大的任务"},
    "cmp_noise": {"en": "repeat noise", "zh": "重跑噪声"},
    "cmp_verdict": {"en": "verdict", "zh": "判定"},
    "verdict_above_noise": {"en": "above noise", "zh": "超出噪声"},
    "verdict_within_noise": {"en": "within noise", "zh": "噪声内"},
    "verdict_unstable": {"en": "interval crosses zero", "zh": "区间跨零"},
    "noise_unknown": {"en": "no repeat baseline", "zh": "没有重跑基准"},
    "foot": {
        "en": "Every step was labelled from its action and result alone; the agent's own words were "
              "used only for the said-and-did check. Labels are probabilities, not hard categories.",
        "zh": "每一步只根据它的动作和结果打标签；agent 自己的话只用来做自述兑现核对。"
              "标签是概率，不是硬分类。"},
}


def _pick(table: dict[str, dict[str, str]], key: str, lang: str) -> str:
    entry = table.get(key)
    if entry is None:
        return key
    return entry.get(lang) or entry.get(DEFAULT_LANG) or key


def phase_name(phase_id: str, lang: str = DEFAULT_LANG) -> str:
    return _pick(PHASES, phase_id, lang)


def metric_name(metric_id: str, lang: str = DEFAULT_LANG) -> str:
    return _pick(METRICS, metric_id, lang)


def metric_help(metric_id: str, lang: str = DEFAULT_LANG) -> str:
    return _pick(METRIC_HELP, metric_id, lang)


def ui(key: str, lang: str = DEFAULT_LANG, **fmt) -> str:
    text = _pick(UI, key, lang)
    return text.format(**fmt) if fmt else text


def finding_headline(finding: dict, lang: str = DEFAULT_LANG) -> str:
    """Render a structured finding. `finding` carries numbers; the sentence lives here."""
    template = _pick(FINDINGS, finding["kind"], lang)
    fmt = dict(finding.get("facts") or {})
    if "phases" in fmt:
        joiner = ", " if lang == "en" else "、"
        fmt["phases"] = joiner.join(phase_name(p, lang) for p in fmt["phases"])
    try:
        return template.format(**fmt)
    except (KeyError, IndexError):
        return template


def strings(lang: str = DEFAULT_LANG) -> dict:
    """The whole table flattened for one language — what the web UI fetches once."""
    return {
        "lang": lang,
        "phases": {k: _pick(PHASES, k, lang) for k in PHASES},
        "metrics": {k: _pick(METRICS, k, lang) for k in METRICS},
        "metric_help": {k: _pick(METRIC_HELP, k, lang) for k in METRIC_HELP},
        "findings": {k: _pick(FINDINGS, k, lang) for k in FINDINGS},
        "ui": {k: _pick(UI, k, lang) for k in UI},
    }
