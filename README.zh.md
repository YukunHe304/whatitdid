# whatitdid

**读任何一个 CLI agent 的会话文件，告诉你这次运行实际做了什么——逐步，带误差。**

[**在线演示**](https://yukunhe304.github.io/whatitdid/) · [English](https://github.com/YukunHe304/whatitdid/blob/main/README.md) ·
[![ci](https://github.com/YukunHe304/whatitdid/actions/workflows/ci.yml/badge.svg)](https://github.com/YukunHe304/whatitdid/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/YukunHe304/whatitdid/blob/main/LICENSE)

```bash
uvx whatitdid demo        # 用随包的真实数据打开浏览器，不需要 API key
```

![七个 CLI agent 跑同一个故障，每次运行画成一条按步打过标签的轨迹](https://raw.githubusercontent.com/YukunHe304/whatitdid/main/media/agents.png)

---

一轮 benchmark 跑完，你手上只有两样东西：一个分数，和几万行日志。中间是空的。
你知道 Claude Code 66.7%、Codex 61.9%，但完全不知道它们各自**干了什么**。

whatitdid 给每一步打标签——这一步是哪类动作、有没有带来新信息、有没有改动系统之后去验证——
然后把两轮运行放在一起比，并且扣掉重跑本来就会有的波动。

```bash
whatitdid run session.jsonl --out report.html   # 体检一条轨迹
whatitdid watch ./runs --out reports/           # benchmark 每跑完一题就体检一题
whatitdid compare ./before ./after              # 这次改动到底改了什么
whatitdid serve                                 # 网页版
```

## 分数给不了的东西

七个 CLI agent，同一个 Kubernetes 故障，153 步，全部打过标签：

| agent | 主动试 | 细看一个对象 | 写结论 | 在重看 | 自述兑现 |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 0.10 | **0.42** | 0.12 | **0.70** | 85% |
| claudecode | **0.00** | 0.18 | 0.25 | 0.56 | 62% |
| codex | 0.09 | 0.15 | 0.12 | 0.47 | 73% |
| copilot | **0.00** | 0.22 | **0.26** | 0.36 | 67% |
| gemini | 0.08 | 0.30 | 0.11 | 0.47 | **53%** |
| opencode | 0.08 | 0.20 | 0.18 | 0.54 | 67% |
| stratus | **0.00** | 0.24 | 0.18 | 0.63 | 74% |

claudecode、copilot、stratus 的「主动试」是 **0.00**：在这几次运行里，
**它们从来没有主动去试一下系统的反应**，只读状态然后下判断。
如果你的环境里「改完没验证」是要付代价的，这比五个点的通过率重要得多。

「自述兑现」是指它刚说完下一步要做什么，之后三步里真的做了的比例。七家从 53% 到 85%。

> **这张表是演示，不是对这些产品的判决。** 它是每家一次运行、一道题——足以说明这把尺子能用、
> 也足以说明这几家确实不一样，但远不足以给它们排名。表里每个数字都来自本仓库随附的数据，
> 你可以自己复现（`uvx whatitdid demo`），也可以不同意。
> 要对其中任何一家下真结论，得多题、多次重跑，再把差异拿去和下一节的重跑噪声底比——
> 那正是下一节存在的理由。

## 为什么重点是 compare

你改了一个东西——提示词、模型、推理档位——重跑 benchmark。
通过率在二十来道题上动了几个点，区间跨零。四个小时过去，你什么也没学到。

真实例子，同一个 agent、同样 21 道题，只把推理档位调高：

```
诊断通过率        +0.190  (−0.000, +0.429)   跨零，说明不了任何事

写结论            −0.084  (−0.138, −0.038)    5/21 变大
自述兑现率        −0.061  (−0.093, −0.032)    2/21 变大   ← 21 题里 19 题变差
主动试系统        +0.056  (+0.020, +0.091)   15/21 变大
在重看            +0.045  (+0.011, +0.083)   15/21 变大
```

分数是 21 个二值结果。行为是两千多步、每步六个问题——同样的算力，观测数多两个数量级。

### 第二道坎，几乎所有人都跳过了

配对自助法回答的是「换一批题还会不会看到同样的结果」。
它完全没有回答「**同一个配置再跑一遍**会不会也这样」。
agent 不是确定性的，而后面这个波动往往更大。

所以 whatitdid 会要一条重跑噪声底，没有它就拒绝下判定：

```
指标            差值              95% 区间       变大   重跑噪声   判定
写结论          -0.084  (-0.138, -0.038)      5/21        —     ? 没有重跑基准
自述兑现率      -0.061  (-0.093, -0.032)      2/21        —     ? 没有重跑基准
主动试系统      +0.056  (+0.020, +0.091)     15/21        —     ? 没有重跑基准
大范围扫        +0.023  (-0.009, +0.053)     14/21        —       区间跨零
```

这就是这组对照的真实输出——因为那两轮没有第三次运行可以拿来量噪声。
**工具会直说，而不是把自助法的结论冒充成判定。**

给它同一配置的重复运行，最后两列就会填上：每个变化会跟「什么都没改时这个指标能漂多远」比，
比它小的一律标成「噪声内」，区间再窄也一样。

```bash
whatitdid compare ./before ./after --repeat ./before-again
```

不随包发默认值。别人的 agent 在别人的题目上测出来的底不是你的底，
而**错的底比没有底更糟**——它会把噪声装扮成发现。

## 支持的格式

会话文件按**内容**识别，不看文件名，所以直接把 agent 留下的东西丢给它就行：

`claudecode` · `codex` · `copilot` · `gemini` · `opencode` · `stratus` · `baseline`

不需要 SDK、不需要插桩、不用改 agent 也不用改 benchmark。

## 问的是哪六个问题

每步六个，一次调用并行返回。第一个问「这是哪类动作」，跟领域走；
后五个跨领域完全相同，所以写代码的 agent 和运维的 agent 在这五项上仍然可比。

| | |
| --- | --- |
| **这一步在干什么** | 跟领域走——`sre.v1`：大范围扫 / 缩小范围 / 细看一个对象 / 主动试 / 改动 / 验证 / 写结论。`code.v1`：大范围扫 / 定位 / 读代码 / 复现 / 改代码 / 跑测试 / 回退 / 写结论 |
| 是不是在验一个具体怀疑 | 还是不管故障是什么都会做的例行动作 |
| 有没有带来新信息 | 还是只确认了之前已经看到的 |
| 是不是在重看 | 前面已经看过的东西又看一遍 |
| 有没有改动系统 | 还是只读 |
| 瞄得有多准 | 0＝整个系统，4＝某个对象的某个属性 |

问题集是一个文件，不是代码里的常量——`--questions 你的问题集.json`。
它会记进每一份报告，`compare` 也会读它：两边用同一套就全比，用了不同的套就只比它们共有的问题，
并且丢掉「这一步在干什么」那一题——它的选项在两边根本不同名。输出里会写明是哪种情况。

## 打标签的模型

默认是 [Jev](https://docs.typesafe.ai)，TypeSafe 的 System One 模型：
一次并行回答多个类型化问题、返回概率分布而不是硬标签、并且根本没有文字输出通道。

|  | Jev | 聊天模型 |
| --- | --- | --- |
| 一条 28 步的轨迹 | **6 秒 / $0.008** | 3.7 分钟 / $0.028 |
| 21 题的 benchmark | **2.4 分钟 / $0.36** | 2.8 小时 / $1.27 |
| 带上 agent 自述后标签翻转 | **9%** | 28% |
| top-1 概率中位数 | 0.88 | 0.70 |

前两行解释了为什么这件事现在做得起，第三行解释了为什么跨 agent 比较时它才靠得住：
不同 agent 的自述量差 4.5 倍，而会读自述的标注器，会把话多的那个读成更有章法。
**whatitdid 在产出可比标签的那一遍里，从不把 agent 自己的话给标注器看**，
自述只用于单独的兑现率核对。

没有 Jev key 的话，`--labeler chat` 可以用任何 OpenAI 兼容的接口。
但它更慢、更贵、并且有上面那个偏倚——用来看单条轨迹可以，用来比不同 agent 不行。

## key 放哪

从 `TYPESAFE_API_KEY` 或 `~/.config/whatitdid/typesafe.env`（600）读。
网页版可以帮你写进去。不会提交、不会打日志、除了你自己选的标注接口之外不发去任何地方。
轨迹始终留在你自己的机器上。

## 安装

```bash
pip install whatitdid
```

需要 Python 3.11+。从源码装：

```bash
git clone https://github.com/YukunHe304/whatitdid && cd whatitdid
pip install -e ".[dev]"
npm --prefix web install && npm --prefix web run build   # 只有改了网页版才需要
pytest
```

## Python 接口

```python
from whatitdid import profile, compare

rep = profile("session.jsonl")
rep.to_html("report.html")
rep.to_dict()        # 只有 id，没有显示字符串——跨机器可比
rep.to_web_dict()    # 上面那些再加逐步文本，给界面用

print(compare(before, after, repeats=[before_again]))
```

## 它不做什么

它不负责跑 agent 和 benchmark，你把已经有的东西指给它就行。
跑是 [`vercel-labs/agent-eval`](https://github.com/vercel-labs/agent-eval) 的事，
这个工具读它们留下来的东西。

它也不判断答案对不对，那是你的 benchmark 的事。它告诉你的是 agent 怎么走到那一步的。

## 许可证

Apache-2.0。轨迹转换器衍生自
[Harbor](https://github.com/harbor-framework/harbor)（Apache-2.0）与
[SREGym](https://github.com/SREGym/SREGym)（MIT），见 [NOTICE](https://github.com/YukunHe304/whatitdid/blob/main/NOTICE)。
