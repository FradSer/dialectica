# Dialectica ![](https://img.shields.io/badge/A%20FRAD%20PRODUCT-WIP-yellow)

[![PyPI](https://img.shields.io/pypi/v/dialectica.svg)](https://pypi.org/project/dialectica/) [![Twitter Follow](https://img.shields.io/twitter/follow/FradSer?style=social)](https://twitter.com/FradSer) [![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/) [![Framework](https://img.shields.io/badge/Framework-ADK%202.11+-orange.svg)](https://github.com/google/adk-python) [![Evaluation](https://img.shields.io/badge/Evaluation-honesty%20gate-purple.svg)](#评测)

[English](README.md) | **简体中文**

**Dialectica** 是基于 Google ADK 的可审计推理工作流与评测工具箱。它提供可组合执行内核与验证器制导修复，并将研究模式与强单次调用、重复调用对照比较。它要回答的是：*什么时候，额外编排值得其可靠性、质量或成本收益？* 真实调用、失败尝试、未知用量和无法确定的评判都属于证据。

> **历史观察。** 测试过的 ToT/GAN/scorer 编排在自包含任务上没有胜过当时的强单次调用对照。工具访问和客观验证修复带来了能力或成本收益。开放式实验中，异构 reflection（十题池 **10-0-0**）和调好的辩证（三题、单一评判，见结论 #9）出现收益。这些结果的评测覆盖有限，不能推出关于推理计算的普遍定律。新研究模式必须通过独立对照，才考虑进入公开 API。见[评测](#评测)。

受 [karpathy/autoresearch](https://github.com/karpathy/autoresearch)、Sakana AI 的 AB-MCTS / 集体智能系列、以及 Claude Code 可组合工作流启发。

## 公开 API（由数据支撑）

evals 把 ship 出去的接口收敛到数据真正支持的那一点：

| | 靠加入什么赢 | 证据（所测任务/模型） |
|---|---|---|
| **`Workflow` / `agent(tools=...)`** | **能力**——工具让一个 stage act → observe → iterate | ✅ hidden-oracle 任务上的能力增益（8/8 vs 0/8） |
| **`create_repair_engine`** | **ground truth**——验证器在环，通过即短路 | ✅ 在所测通过率下成本更低（best-of-N 可靠性，约 1/3 调用） |

这个项目做过的其余东西——独立的 agentic 引擎类、异构 ensemble + scorer、辩证螺旋、
遗留 ToT+GAN beam search——要么用 `agent(tools=...)` 就够了，要么被测出作为纯 LLM
scaffold 与 prompt-matched 单次调用打平/输掉。它们被保留为可运行的**参考模式**，
不是 ship 出去的 API。开放式 meta-task 的实测配方是异构 reflection
（`examples/patterns/reflection_pattern.py`），组合在内核之上——仍不是第三个
ship 出去的引擎。见[模式](#模式不随包发布仅供参考)。

## 安装

```bash
uv add dialectica      # 或: pip install dialectica
```

```python
import os, asyncio
from dialectica import create_repair_engine

os.environ["GOOGLE_API_KEY"] = "..."  # 环境配置由应用负责


# 验证器对任意客观检查返回 (passed, feedback)——单元测试、JSON schema、
# linter、断言校验的业务逻辑。引擎据反馈反复修复，直到通过或用尽次数。
def verify(answer: str) -> tuple[bool, str]:
    ok = "def solve" in answer  # 你的真实检查写这里
    return ok, "" if ok else "no solve() function defined"


async def main():
    result = await create_repair_engine(
        "Write a solve() function that ...", verifier=verify
    ).run()
    print(result["passed"], result["attempts"], result["final_answer"])


asyncio.run(main())
```

可验证任务优先用 `create_repair_engine`。多步工具任务，构建一个 `Workflow`
脚本并直接调用 `agent(task, tools=[...])`（见下文）。库从 `os.environ` 读配置，
**不**自行加载 `.env`。

## Workflow 内核与 repair

### 🔗 `Workflow` / `agent` / `parallel` / `pipeline`——执行内核
可组合的多 agent 运行时——Claude Code `Workflow` 工具的**程序化**编排面（不含 IDE 宿主 UI）：
`agent()` / `parallel()` / `pipeline()` / `workflow()` / `phase()` / `log()` / `budget()` / `run_id()`。

- **`agent(..., isolation="worktree", agent_type="Explore", sees=[...])`**——`tools` 是能力加成杠杆；`isolation="worktree"` 在独立 git worktree 中运行（无变更则自动清理）；`agent_type` 应用预设角色章程；**`sees`** 是按步骤的访问列表（借鉴 Sakana Fugu-Ultra 的"防编排坍塌"机制）：默认完全隔离（一个 agent 永远看不到另一个 agent 的 transcript），`sees=["gather","critique"]` 只把指定前置步骤的输出注入本次调用的 prompt。未知/未完成的标签会被跳过而非报错，故访问列表能在条件分支下存活。
- **`workflow(script_or_name)`**——子 workflow 内联执行（一层嵌套），共享外层 budget；可用 `register_workflow` 按名称调用。
- **Resume**——`agent()` 调用记入 `.dialectica/workflows/<run_id>/`；`Workflow(..., resume_run_id=...)` 从缓存重放最长不变前缀。
- **护栏**——每 run 最多 1000 次 `agent()`；`parallel`/`pipeline` 每次最多 4096 项。
- **`Workflow(..., meta={...})`**——可选元数据；`phase()` 标题须与 `meta.phases` 一致。
- **诚实适用范围**：无 `tools` 的纯 schema 工作流仍是纯 LLM scaffold；收益需按任务、模型和实际成本验证。

### 与 Claude Workflow 的对应——小模型能从这里得到什么

`Workflow` 内核是 Claude Code `Workflow` 工具的**程序化**编排面（不含 IDE `/workflows` UI）。
同样的 fan-out、分阶段 pipeline、子 workflow、resume、worktree 隔离，都可以用 Python 表达。

| Claude Code Workflow | Dialectica |
|---|---|
| `agent` / `parallel` / `pipeline` / `phase` / `log` / `budget` | ✅ |
| 子 workflow、`run_id`、resume/journal | ✅ |
| `agent(isolation="worktree")` | ✅ |
| `agent_type`（如只读 Explore） | ✅ 仅 Explore 预设 |
| 命名 workflow 注册表 | ✅ `register_workflow` |
| IDE `/workflows` UI、完整 agent 类型库（Plan 等） | ❌ 仅 API |
| 宿主深度集成（终端、文件树） | 自行注入 `tools` |

**这能让小参数模型「更强」吗？** 历史上的收益涉及工具、客观反馈、异构模型或调好的辩证。它们都有模型、任务和预算条件，不能证明收益的必要条件。需要为每个模型设置强单次调用基线，并记录实际成本，再判断编排是否有价值。

| 场景 | 用法 | 小模型收益 |
|---|---|---|
| 必须读代码、跑命令、探测 API | `agent(tools=[...])`，可选 `parallel` | ✅ **能力增益**——hidden-oracle 小模型 + tools **8/8**，单次调用 **0/8** |
| 输出可校验（测试、schema、linter） | `create_repair_engine` + verifier | ✅ **成本收益**——best-of-N 可靠性约 ⅓ 调用；通过率与 matched-cost 打平 |
| 开放式 meta-task（调研、评审、设计） | 异构 reflection：`create_reflection_engine`（或 `create_quality_workflow_engine(..., mode="reflection")`） | ⚠️ **有条件的收益**——异构 reflection 在 meta+default 上对单次 **10-0-0**（结论 #7）；杠杆是 roster 异构性。留出集来源约束任务未证明优于强单次调用（[结果](docs/findings.zh-CN.md#研究更新历史结论有适用条件)） |
| 自包含推理（无工具、无 verifier） | 强单次 prompt 或更大模型 | 历史测试中的同模型 scaffold 未胜过当时的强单次调用对照 |

**小模型实用配方：**

1. **探索 / 调试** — `agent_type="Explore"` + `tools=[...]`，可选 `isolation="worktree"`。
2. **可验证输出** — `create_repair_engine(verifier=...)`；失败时 `models=[小, 小, 中]` 轮换。
3. **调研 / 评审 / 开放式反思** — 可尝试 `create_reflection_engine(problem)`（参考模式；证据有条件，需与强单次调用对比）+ 异构 roster（默认经 cliproxy 的 `qwen` + `glm`）。**不要**默认开 adversarial/dialectic——结论 #7 显示相对异构 reflection 无一致增益。
4. **控成本** — `Workflow(..., budget_unit="tokens")`；fan-out 用小模型，综合或最后一跳 repair 再用大模型。

`parallel` 与并发上限控制调度，并可能降低墙钟时间。额外采样或交互是否提升质量，需要单独比较。Context cache（见[配置](#配置)）在**单次 `agent()` 内的多轮 tool loop** 上省 token——独立 `agent()` 之间不会自动共享，除非自行管理 session。

### 🛠️ 执行制导修复——验证器在环（`create_repair_engine`）
可验证任务：**生成 → 跑注入的验证器 → 据具体失败修复 → 重试**，直到通过或
用尽次数。构建在 `Workflow` 内核之上——内部每次尝试都是循环里的一次
`agent(model=..., label=...)` 调用，不再有自己的一套 agent 构造逻辑。

- **任务无关的验证器**——任意 `Callable[[answer], (passed, feedback)]`：单测、
  schema 校验、linter、断言校验。`solution_format` 钉住验证器解析的输出形态。
- **用满失败历史**——每次失败尝试及其精确失败都回灌，避免在两个错误修复间
  振荡。
- **成本克制**——验证器一通过即短路，以远少于 best-of-N 的调用达到其可靠性。
- **多模型**——传 `models=[...]` 在失败时跨 roster 轮换；`history[i]["model"]`
  记录每次尝试由哪个模型产出。
- **返回** `{final_answer, passed, attempts, history}`。

实测判决（结论 #2）：通过率上打败单次调用、与 matched-cost best-of-K 打平，
但只需约 1/3 的调用。

## 模式（不随包发布，仅供参考）

`examples/patterns/`（与 `evals/` 一样是开发工具，不随 wheel 打包）保留可运行的研究模式：既有历史评测未支持进入稳定 API 的变体，也有仍待验证的新机制。被降级的引擎保留
原本的工厂函数名/签名/返回形态，内部重建在 `Workflow` 内核之上而非
自建 agent。（当初测量它们的 `evals/*.py` 脚本已于 2026-08 清理中移除；实测判决
见下表与 [docs/findings.zh-CN.md](docs/findings.zh-CN.md)。）

| 模式 | 展示什么 | 实测判决 |
|---|---|---|
| `agentic_pattern.py`（`create_agentic_engine`） | `agent(tools=[...], instructions=...)` 作为独立的工具使用 stage | 与内核原语相同的 8/8 vs 0/8 胜绩——保留只是因为它是个带定制系统提示词的可直接复制的范例，不是因为这个能力需要一个类。 |
| `dialectic_pattern.py`（`create_dialectic_engine`） | 正 → 反 → 合螺旋，经 `agent(schema=Verdict)` 打分 | 自包含任务上对 prompt-matched 单次调用打平/输掉（**0-3-2**），但**调好后在开放式 meta-task 上打败单次调用**（调硬 synthesis + `max_rounds=5`：**−0.500 → +0.600 NET**，结论 #9）。 |
| `ensemble_pattern.py`（`create_ensemble_engine`） | 异构 roster 上的 AB-MCTS-lite 自适应搜索（Thompson 采样 bandit） | 被 honesty gate **CUT**——blind-pick roster（scorer 换成常数）打平了真实 scorer 的健壮性增益；信号相对异构性本身无额外贡献。 |
| `reflection_pattern.py`（`create_reflection_engine`） | **规范**开放式配方：异构 gather → frame → critique → synthesize，基于 `Workflow`。可选 `use_access_lists=True` 把 critique/synthesize 的前置上下文经由内核 `sees=` 原语注入（Fugu-Ultra 风格的选择性可见），而非用 `.format()` 内联。 | ⚠️ 有条件的赢——meta 上对单次/同构 **5-0-0**（#6）；经 quality ablation 在 meta+default 上对单次 **10-0-0**（#7）。无 LLM scorer / AB-MCTS。访问列表模式为可选项；上述实测数字用的是内联 prompt。 |
| `quality_workflow_pattern.py`（`create_quality_workflow_engine`） | 同一 roster 上的模式切换：`reflection`（默认，委托 reflection_pattern）/ `adversarial` / `dialectic` | Ablation 夹具——adversarial/dialectic 相对异构 reflection 无一致增益（#7）。除非比模式，否则优先 `create_reflection_engine`。 |
| `tot_gan_pattern.py`（`create_engine`/`create_coordinator`） | beam search + GAN 风格对抗精修，`parallel()` 用于兄弟展开/评估 | **实测被压制**——matched-cost 下从未赢过对单次/best-of-N/self-refine 的任何一场；在 24 点游戏上以约 34× 成本输给单次调用。 |
| `claim_falsification_pattern.py`（`create_claim_falsification_engine`） | 受 CLR 启发：独立断言评估 + 加权候选选择 | **实验性**——重复留出集比较（K=6、K=3）未显示选择收益或确立的质量优势；不升级为稳定 API。 |
| `meta_reasoning_pattern.py`（`create_meta_reasoning_engine`） | 分阶段/直接控制器、选择性上下文、已存储产物的选择 | **实验性**——元推理预算 6 和 12 的留出集上，相对单次的差值区间均包含零。 |
| `self_refine_pattern.py`（`create_self_refine_engine`） | 带可选选择策略与早停收敛的迭代式自我修正（`last`、`plurality`、`convergence`、自定义 `selector`） | **实测**——未受指导的 `last` 仅打平单次调用（2/16 vs 2/16），但无 oracle 的 checker 可找回丢失的中途成功（9/16，100% 覆盖）；`convergence` 早停节省 ~62% 步数。 |

每个模式的 docstring 都写明其确切评测判决。它们按内核自身的组合风格编写
（对 `agent()`/`parallel()` 的纯函数/闭包组合），而非原来基于 Protocol 的插件
系统——保留是为了研究与历史数字的可复现性，不是为了扩展。像 evals 那样导入
它们：

```python
from examples.patterns.agentic_pattern import create_agentic_engine
from examples.patterns.dialectic_pattern import create_dialectic_engine
from examples.patterns.ensemble_pattern import create_ensemble_engine
from examples.patterns.reflection_pattern import create_reflection_engine
from examples.patterns.quality_workflow_pattern import create_quality_workflow_engine
from examples.patterns.tot_gan_pattern import create_engine
from examples.patterns.claim_falsification_pattern import (
    create_claim_falsification_engine,
)
from examples.patterns.meta_reasoning_pattern import create_meta_reasoning_engine
from examples.patterns.self_refine_pattern import create_self_refine_engine
```

## 评测

引擎是否真的打败一次强模型调用？仓库附带评测工具（`evals/`，开发工具——不随
包发布），用数据回答：每题由引擎**和**单次调用基线各解一次；**盲评判**对两答案
各评两次并交换位置（历史流程将不一致记为 tie；新流程保留为无法确定）。新的逐分组
收据包含 token、可观察轮次、失败与原始记录；评测脚本在首次模型调用前保存配置、
任务文本、源码/依赖指纹与分析规则，已使用的实验路径不能复用。

| 脚本 | 用途 |
|---|---|
| `uv run python -m evals.reflection_ablation` | reflection 模式：异构 vs 同构 vs 单次（open-ended） |
| `uv run python -m evals.quality_workflow_ablation` | 多模型模式 vs 单次（meta+default，10 题） |
| `uv run python -m evals.workflow_ablation` | 同构 reflection vs 单次（open-ended） |
| `uv run python -m evals.claim_ablation --help` | 断言证伪 vs 共识/自我修正（客观验证器） |
| `uv run python -m evals.meta_ablation --help` | 元推理控制器 vs 单次（客观验证器） |
| `uv run python -m evals.evidence_ablation --help` | 来源约束决策；生成、校准、评判分别计量 |
| `uv run python -m evals.research_campaign --help` | 冻结的重复留出集实验（不自适应调参、不自动重启） |
| `uv run python -m evals.objective_analysis results.json --output analysis.json` | 分析已完成的客观验证器报告 |
| `uv run python -m evals.evidence_analysis evidence.json --output evidence.analysis.json` | 分析已完成的来源约束报告 |

`objective_analysis` 先在每个任务内对重复试验取平均，再对配对任务重采样；失败的生成
仍留在可靠性分母中，未知用量会阻止完整的上报成本结论，缺失配对、重复试验或
题池不一致会使分析失败。冻结源码/规则漂移默认被拒绝，`--exploratory-reanalysis`
会显式记录漂移。`evidence_analysis` 把每个候选分组与每个声明的单模型基线比较，
未决偏好保持 [-1, +1] 的界限，并报告任务聚类不确定性。区间是探索性的，未做
多重比较校正。

历史评测脚本（ToT+GAN 的 `python -m evals` CLI，以及 `repair_ablation` /
`agentic_eval` / `quality_ablation` / `ensemble_ablation` /
`ensemble_meta_ablation` / `access_list_scale` / `scaffold_boundary` 套件）已于
2026-08 清理中移除；它们支撑的结论作为记录保留。

### 结果一览

完整方法、数字与限制见 [docs/findings.zh-CN.md](docs/findings.zh-CN.md)。以下是
对所测任务、模型和协议的历史观察，不是普遍定律。

| # | 结论 |
|---|---|
| 1 | **工具带来能力：** 小模型 + `agent(tools=...)` 在 hidden-oracle 上 8/8，单次调用 0/8。 |
| 2 | **纯 LLM scaffold 在自包含任务上与强单次调用打平；** repair 胜过单次调用，与 matched-cost best-of-K 打平，调用约 1/3。 |
| 3 | **ToT+GAN 被压制：** 24 点游戏 14/15 vs 单次 15/15，成本约 34×。 |
| 4 | **无提升空间：** 四档模型在最难的 24 点题上单次均 5/5。 |
| 5 | **Ensemble scorer 被 CUT：** 开放式任务上的收益来自 roster 异构性，而非 scorer 排序。 |
| 6 | **异构 reflection** 在 meta 任务上对单次和同构 reflection 均 **5-0-0**。 |
| 7 | **质量模式（10 题）：** 异构 reflection 对单次 10-0-0；adversarial/dialectic 无一致额外增益。 |
| 8 | **访问列表**（`sees=`）作为内核原语发布；reflection 集成仍为可选。 |
| 9 | **调好的辩证** 在 3 个 meta 任务上对单次 NET 从 −0.500 到 +0.600（单一评判）。 |

#### 留出集实验（2026-10-04）

[冻结的七组留出集实验](docs/research/2026-10-04-heldout-protocol.md)筛选了 32 篇
一手来源论文（[论文矩阵](docs/research/2026-10-03-literature.md)），完成 576 次生成
试验：含校准和评判共上报 **3,631,216 token / 3,789 个可观察模型轮次**，保留
**30 次生成失败**。这些是上报成本，不是服务端账单，也不含不可观察的 HTTP 重试。
见[完成审计](docs/research/2026-10-04-completion-audit.md)与
[原始记录完整性审计](docs/research/results/2026-10-04-heldout-v1/final-integrity-audit.json)。

| 留出集比较 | 观察结果 | 采用决定 |
|---|---|---|
| [来源约束决策](docs/research/2026-10-04-heldout-evidence-result.md) | 自我修正相对 Gemini 单次、异构反思相对 Qwen 单次出现探索性正向评判信号；未证明优于 GPT 单次 | 反思保留为参考模式；合成引用核验和评判一致不能证明决策正确或人类偏好对齐 |
| [断言 K=6](docs/research/2026-10-04-heldout-claims-k6-result.md) | 断言 6/24；共识/自我修正 7/24；单次 4/24 | 断言相对单次的差值区间包含零，不新增稳定 API |
| [断言 K=3](docs/research/2026-10-04-heldout-claims-k3-result.md) | 断言/自我修正 7/24；单次/共识 3/24 | 断言相对单次的差值区间包含零，不新增稳定 API |
| [元推理预算 12](docs/research/2026-10-04-heldout-meta-budget12-result.md) | 单次 5/24；共识 3/24；自我修正 8/24；分阶段 2/24；直接 3/24 | 相对单次的差值区间均包含零，控制器保留为研究模式 |
| [元推理预算 6](docs/research/2026-10-04-heldout-meta-budget6-result.md) | 单次 5/24；共识 4/24；自我修正 10/24；分阶段 4/24；直接 0/24 | 差值区间均包含零；自我修正的较好点估计不足以支持采用 |
| 强单次对照：[元推理](docs/research/2026-10-04-heldout-strong-meta-result.md) / [断言](docs/research/2026-10-04-heldout-strong-claim-result.md) | GPT 在两种输出约束下各 24/24 | 仅是本题池的天花板，不能证明普遍成功或新机制在 GPT 上的收益 |

事后[选择诊断](docs/research/2026-10-04-heldout-selection-diagnostics.md)用于指导
未来研究，不用于在冻结题集上调参。区间以小题池为条件、未做多重比较校正，各分组
token 成本不相等。**公开 API 仍只有 Workflow 与验证器制导修复；新的优势声明
需要强 prompt-matched 对照、完整的逐分组成本收据、留出任务、重复试验和可靠评测——
E2E 只证明可执行。**

## 配置

所有配置从 `os.environ` 读取——作为库，Dialectica **不**自行加载 `.env`；环境
配置由消费应用负责。仅测试套件加载 `dialectica/.env`。

```bash
# 所有 agent 的默认模型
export DEFAULT_MODEL_CONFIG="google:gemini-3.5-flash"

# 角色特定覆盖（可选）——每次 wf.agent() 调用都用 Generator 角色
export GENERATOR_MODEL_CONFIG="google:gemini-3.5-flash"
# 供 evals/judge.py 的盲评判使用，与任何 ship 出去的引擎无关
export JUDGE_MODEL_CONFIG="google:gemini-3.1-pro-preview"

# Google AI Studio
export GOOGLE_API_KEY="..."

# 或 Vertex AI
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT="..."
export GOOGLE_CLOUD_LOCATION="..."

# OpenRouter
export OPENROUTER_API_KEY="..."

# OpenAI 兼容（proxy / vLLM / cliproxy）
export OPENAI_API_KEY="..."
export OPENAI_API_BASE="http://localhost:8317/v1"
# 关闭 qwen 族思考链以降评测延迟（可选）
export DIALECTICA_DISABLE_THINKING=true
```

### 运行时变量（均为可选）

| 变量 | 默认值 | 作用 |
|---|---|---|
| `DIALECTICA_CONTEXT_CACHE` | 关 | 经 ADK App 开启 Gemini context cache（设为 `true`） |
| `DIALECTICA_CONTEXT_CACHE_INTERVALS` | `10` | 缓存间隔 |
| `DIALECTICA_CONTEXT_CACHE_TTL_SECONDS` | `1800` | 缓存 TTL |
| `DIALECTICA_CONTEXT_CACHE_MIN_TOKENS` | `4096` | Gemini 硬下限 |
| `DIALECTICA_CONTEXT_CACHE_CREATE_TIMEOUT_MS` | 未设置 | `CachedContent.create()` 超时 |
| `DIALECTICA_ADK_TELEMETRY` | 关 | OpenTelemetry（或改设 `OTEL_EXPORTER_OTLP_*`） |
| `DIALECTICA_TOOL_WORKERS` | 未设置 | 正整数；将阻塞的同步工具移入 ADK 线程池 |
| `DIALECTICA_MAX_LLM_CALLS` | ADK 上限 | 正整数；限制每次 ADK 调用内的模型轮数 |
| `DIALECTICA_WORKFLOW_CONCURRENCY` | `min(16, cpu−2)` | 并发 `agent()` 调用上限；`Workflow(concurrency=...)` 优先 |
| `DIALECTICA_MAX_CONCURRENCY` | 不限 | 并发 `run_agent()` 调用的全局上限 |
| `DIALECTICA_WORKFLOW_JOURNAL_DIR` | `.dialectica/workflows` | resume 日志目录 |

### 运行时行为

运行时以 [ADK 2.11](https://github.com/google/adk-python/releases/tag/v2.11.0) 为基线。
`tools` 与 `schema` 可同时使用：ADK 根据模型声明的能力选择原生结构化输出，
或通过响应工具回退。具体服务端的支持仍有差异；离线测试覆盖两条 ADK 路径，
不代表所有远端模型都已验证。传输失败重试期间复用同一 Runner，每次尝试使用
独立的新 session；整体调用成功、失败或任务取消后统一关闭工具集与插件。
任务取消会直接传播，不会重试。无效请求、认证失败、模型不存在，以及明确的
订阅过期或计费额度错误会立即返回；临时网络和容量错误仍会重试。

日志保存每步上报的用量，包括结构化输出重新询问时成功返回的调用。并行步骤在
模型调用前分配唯一编号，按调用顺序恢复；缓存中的具名输出也会恢复 `sees=` 上下文。
变更后的后缀会替换旧记录；含重复并行编号的历史日志会在恢复时重新计算。
缓存重放不增加本次 token 预算。ADK 模型回调会在事件生成前捕获已上报的 token，
失败尝试纳入重试合计，最终异常通过 `dialectica_usage` 暴露用量。失败步骤会记录，
但不会作为成功结果重放；只追加的 `usage.jsonl` 收据在恢复替换缓存后仍保留用量。
`TokenUsage.unknown_calls` 表示未收到最终用量报告的模型尝试；中断前的部分报告
会保留，收到最终累计报告时则替换中间值，避免重复计算。非零时 token 合计只是
已知部分，不能理解为这些调用免费。

`TokenUsage.model_calls` 记录 ADK 在派发前观察到的模型轮次，包括运行时重试、
工具循环与缓存短路，并写入预算、日志和实验收据。工作流 `spent_calls()` 仍计
agent 步骤；SDK 和供应商内部重试不在这个计数中，不能据此声称准确的 HTTP
请求数或计费次数。缺少该字段的旧日志仍可读取，其默认零表示当时未记录。
`tokens` 预算限制已上报的输出 token（含已上报的思考 token）；输入、总量与
缓存用量分别记录。

显式模型配置格式错误、供应商不支持或缺少 OpenAI/OpenRouter 凭据时，会在派发前
报错，不会静默换成 Google 模型。请使用 `provider:model`（`openrouter:vendor/model`
经 OpenRouter 路由），取消设置 `DEFAULT_MODEL_CONFIG` 才会选择原生默认模型。

依赖调用线程的工具应保持 `DIALECTICA_TOOL_WORKERS` 未设置；Python 无法强制停止
已经在线程中运行的同步工具。`DIALECTICA_TOOL_WORKERS` 与 `DIALECTICA_MAX_LLM_CALLS`
均要求正整数。`DIALECTICA_MAX_LLM_CALLS` 设置后覆盖原生 `ADK_MAX_LLM_CALLS`；
未设置时由 ADK 自行解析上限（两者均未设置时为每次调用 500 轮）。达到上限后直接
失败，不会重启工具循环，并与外层 Workflow 按 `agent()` 步骤或上报 token 计量的预算
分别生效。

使用 `uv sync --locked` 可复现依赖组合。[依赖审计](docs/research/2026-10-04-dependency-audit.md)
区分冻结实验环境与最终安装环境，并说明阻止采用绝对最新版的上游传递依赖约束。

已验证可用的 Gemini 模型为 `gemini-3.5-flash`（默认）和 `gemini-3.1-pro-preview`
（没有稳定的 `gemini-3.1-pro`，见[故障排除](#故障排除)）。provider 串为 `provider:model_name`；
`openai:` provider 显式传 `api_base`（新版 LiteLLM 不再为 `openai/` 前缀读
`OPENAI_API_BASE`）。

### 参数

- **`agent()`**——`tools`、`instructions`、`schema`、`model`（单次覆盖）、`isolation="worktree"`、`agent_type`（如 `"Explore"`）、`sees`（按步骤的访问列表，选择性上下文可见）。
- **`Workflow`**——`budget_total` / `budget_unit`（`"calls"` 或 `"tokens"`）、`resume_run_id`、`meta`、`concurrency`；`budget().usage()` 在后端上报 cache hit 时含 `cached_tokens`。
- **`create_repair_engine`**——`verifier`（必填）、`max_attempts`、`solution_format`、`models`（可选 roster）。
- **模式**——见 `examples/patterns/` 里各模式自己的 docstring/工厂签名；它们保留了被降级引擎原本的参数（例如 ensemble 模式的 `scorer`/`policy`，dialectic 模式的 `criteria`/`rounds`）。

## 使用示例

### Repair（可验证任务）

```python
from dialectica import create_repair_engine


def verify(code: str) -> tuple[bool, str]:
    # 你的真实检查——跑测试、校验 schema 等
    return True, ""


engine = create_repair_engine("Write solve()", verifier=verify, max_attempts=3)
result = await engine.run()
# {"final_answer", "passed", "attempts", "history"}
```

### 工具使用 stage（内核原语）

```python
from dialectica import Workflow, agent


async def script():
    return await agent("Fix the failing test", tools=[read_file, run_tests])


result = await Workflow(script).run()  # 工具负责行动；事后检查结果
```

### 模式（仅供示意——不是 ship 出去的 API）

开放式 meta-task——规范异构 reflection（结论 #6 / #7）：

```python
from examples.patterns.reflection_pattern import create_reflection_engine

engine = create_reflection_engine(
    "Design the pricing tier",
    # 默认 roster：openai:qwen3.6-flash + openai:glm-5.2
    # use_access_lists=True  # 经 sees= 注入前置上下文，而非内联
)
result = await engine.run()
# {"final_answer", "history", "heterogeneous"}
```

Ensemble + float scorer 已被 **CUT**（结论 #5）——仅作历史 ablation；开放式质量
优先用上面的 reflection。

### 查看结果

`create_repair_engine` 和 `examples/patterns/` 里每个模式都返回含
`final_answer` 与轨迹（`history` / `attempts`）的 `dict`。repair 与 ensemble
模式的 `history` 记录每次尝试的产出模型；reflection 的 `history` 记录 stage、
label 与 model。

## 本地开发

```bash
uv sync                                         # 安装依赖
uv run pytest                                   # 模拟，快，无需 API key
uv run pytest -m e2e                            # 真实 repair 与工具/schema/线程池测试（需所选模型凭据）
uv run pytest -m e2e_access                     # 实时访问列表测试（需 OPENAI_API_BASE + OPENAI_API_KEY + DEFAULT_MODEL_CONFIG=openai:...）
uv run pytest -m 'e2e or e2e_access'             # 通过已配置的 OpenAI 兼容服务运行全部真实用例
uv run ruff format && uv run ruff check         # 格式化 / lint
```

使用 cliproxy 时先加载 shell 环境，将 `CLIPROXYAPI_BASE_URL`（含 `/v1`）映射到
`OPENAI_API_BASE`、`CLIPROXYAPI_TOKEN` 映射到 `OPENAI_API_KEY`，再将
`DEFAULT_MODEL_CONFIG` 和 `GENERATOR_MODEL_CONFIG` 设为可用的 `openai:` 模型；
Qwen 可设 `DIALECTICA_DISABLE_THINKING=true`。反思测试通过
`E2E_REFLECTION_FAST_MODEL` 和 `E2E_REFLECTION_STRONG_MODEL` 指定两个不同的
可用模型，历史默认值为 Qwen 3.6 Flash 和 GLM 5.2。工具/schema 测试要求模型
通过工具获取提示中没有的随机值，验证结构化结果、同步工具实际执行线程和
服务端上报的 token 用量。缺少凭据时会跳过；跳过的用例不能视为真实验收通过。

带日期的真实验收快照（通过数、耗时、模型组合）记录在
[docs/findings.zh-CN.md](docs/findings.zh-CN.md#真实验收快照)和
[完成审计](docs/research/2026-10-04-completion-audit.md)中；它们只证明执行链路，不证明质量优势。

库不调用 `logging.basicConfig`——日志配置由消费应用负责。在唯一接缝
`agent_runtime.run_agent()` 处 mock LLM——绝不 patch ADK 内部或各阶段 agent
（`tests/helpers.py` 有 fakes）。`asyncio_mode = auto`；pytest-bdd 步骤为同步，故
用 `asyncio.run()` 包协程。`examples/patterns/` 参考脚本只配一张更轻的回归网
（`tests/test_example_patterns_smoke.py`，每个模式跑一次端到端 mock）——完整的
BDD 场景覆盖只留给 ship 出去的内核 + repair。

## 测试流程（BDD 驱动 TDD）

新行为始于 `tests/features/*.feature` 中的 Gherkin 场景，经 pytest-bdd 执行——步骤
定义在 `tests/test_*_feature.py`（用 `scenarios(...)` 绑定）。然后 RED 测试 → GREEN
代码 → REFACTOR。更新测试时先改对应 `.feature`。CI
（`.github/workflows/test.yml`）在每次 push/PR 跑 `ruff format --check`、
`ruff check`、`pytest`。

## 项目结构

```
dialectica/
  adk_config.py          # ADK 缓存、工具线程池、调用上限与 OpenTelemetry
  agent_factory.py       # 从 ROLE_TEMPLATES 构建 LlmAgent（只剩 Generator）
  agent_runtime.py       # 唯一 LLM 接缝：run_agent() + 重试/退避
  json_repair.py         # 共享的 fence/escape JSON 修复 helper
  llm_config.py          # provider:model 解析（google/openrouter/openai）
  repair.py              # create_repair_engine（成本赢）
  workflow.py            # Workflow + agent/parallel/pipeline/phase/log/budget + sees= 访问列表（内核）
  workflow_journal.py    # 运行日志与 resume（.dialectica/workflows/<run_id>/）
  workflow_registry.py   # register_workflow 命名注册表
  workflow_worktree.py   # agent(isolation="worktree")
examples/patterns/       # 参考实现（不随包发布）
  agentic_pattern.py, dialectic_pattern.py, ensemble_pattern.py, tot_gan_pattern.py  # 被降级的引擎
  reflection_pattern.py       # 规范开放式配方（异构）；可选 use_access_lists
  quality_workflow_pattern.py # 模式 ablation 切换器
  claim_falsification_pattern.py, meta_reasoning_pattern.py  # 实验性研究模式
  self_refine_pattern.py      # 带收敛早停与选择策略的自我修正
  _scoring.py                 # 共享的 Verdict schema
evals/                   # 仅开发的评测工具（不随 wheel 发布）
  baseline.py, harness.py, judge.py, problems.py, meta_problems.py  # 共享原语
  reflection_ablation.py, workflow_ablation.py, quality_workflow_ablation.py  # 开放式 ablation
  claim_ablation.py, meta_ablation.py, research_ablation.py, evidence_ablation.py, research_campaign.py  # 留出集研究
  selection_study.py, selection_rules.py  # 候选轨迹选择研究
  evidence_eval.py, evidence_tasks.py, research_tasks.py  # 题池与来源约束评判
  measurement.py, experiment_protocol.py, objective_analysis.py, evidence_analysis.py  # 收据、冻结、分析
docs/
  findings.zh-CN.md      # 实测结论、研究更新、真实验收快照（英文版 findings.md）
  research/              # 论文矩阵、协议、留出集结果与审计
tests/                   # BDD 特性 + 步骤定义 + helpers
```

## 故障排除

- **`gemini-3.1-pro` 返回 404**——用 `gemini-3.1-pro-preview` 或 `gemini-3.5-flash`。
- **OpenAI 兼容后端 "Connection error"**——新版 LiteLLM 不再为 `openai/` 前缀读
  `OPENAI_API_BASE`；库显式传 `api_base`，故确保设置了 `OPENAI_API_BASE`（而非仅
  `OPENAI_API_KEY`）。
- **模型调用前就 `ValueError`**——显式模型配置会先校验：请使用 `provider:model`、受支持的供应商（`google`、`openrouter`、`openai`）及其凭据。
- **工具循环因 ADK 调用上限而停止**——触达 `DIALECTICA_MAX_LLM_CALLS`（或 `ADK_MAX_LLM_CALLS`）；循环不会重启。请调高上限或收紧任务。
- **E2E 测试显示 skipped**——缺少凭据；跳过的用例不能视为真实验收通过。
- **qwen 族评测慢**——设 `DIALECTICA_DISABLE_THINKING=true` 关闭思考链
  （`chat_template_kwargs.enable_thinking=false`）。
- **Ensemble 模式 roster "collapsed to duplicate effective model"**（`examples/patterns/ensemble_pattern.py`）——这个模式降级后不再自动告警（该检查需要预构建的 agent，降级时被去掉了）；调用 `create_ensemble_engine` 前自己比对一下 `models` 列表有没有重复。
- **ToT+GAN 模式 + 强制 JSON 模式返回空判定**（部分后端，如 gemma-4-26b-a4b）——该模式的 `structured_output` 参数只为签名对齐保留，实际总是走 schema 强制打分；原引擎的绕过办法没有移植过来。

## 从 0.6.x 迁移

`create_agentic_engine`、`create_ensemble_engine`、`create_dialectic_engine`、
`create_engine`/`create_coordinator` 及其配套的 `Protocol`/模型类型**不再是公开
API 的一部分**。它们作为不随包发布的参考实现保留在 `examples/patterns/`
（`pip install dialectica` 不会装它们）：

```python
# 之前 (0.6.x)
from dialectica import create_agentic_engine

# 之后 (0.7.0)——签名/返回形态不变，现在是不随包发布的参考代码
from examples.patterns.agentic_pattern import create_agentic_engine
```

或者，对工具使用场景，直接用内核原语——不需要额外 import：

```python
from dialectica import Workflow, agent

result = await Workflow(lambda: agent(task, tools=[...])).run()
```

`create_repair_engine` 的签名与返回形态不变。`workflow.agent()` 新增了
`instructions=`（任务专属系统提示框架），现在能正确解析 `provider:model` 风格
的 `model=` 覆盖（此前未解析就直接透传），并新增 `sees=`（按步骤的访问列表，
用于选择性上下文可见性——受 Fugu-Ultra "防坍塌"启发；可选，默认行为不变）。
`dialectica.gan_evaluator` 改名为
`dialectica.json_repair`（只有共享的 fence/escape helper 保留下来；GAN 专属的类
迁去了 `examples/patterns/tot_gan_pattern.py`）。

## 贡献

约定式提交。发布 = 推一个版本号与 `pyproject.toml`
**匹配**的 `v*.*.*` tag；CI 跑测试、发 PyPI、建 GitHub release。往公开 API 里加
东西时，连同 ship 会在数据说 CUT 时 CUT 它的 honesty-gate ablation——本仓的传统
是记录负向结果，而非未证实的声明。这次发布本身就是这套 honesty gate 的产物——正
是它把公开 API 收窄到只剩内核和 repair，见[模式](#模式不随包发布仅供参考)。

## 许可证

MIT——见 `LICENSE`。

## 参考资料

- [Tree of Thoughts](https://arxiv.org/abs/2305.10601)——Yao et al., 2023（ToT+GAN
  模式的谱系；现仅供参考）。
- [Sakana AB-MCTS / "Wider or Deeper?"](https://arxiv.org/abs/2503.04412)——ensemble
  模式的谱系（独立性 + ground-truth 信号）。
- [Sakana Fugu](https://sakana.ai/fugu/)——多模型协调器，其按步骤访问列表机制启发了内核 `sees=` 原语（结论 #8）。
- [断言级证伪（CLR）](https://arxiv.org/abs/2608.11994)与[结构化元推理](https://arxiv.org/abs/2609.38147)——`claim_falsification_pattern.py` 与 `meta_reasoning_pattern.py` 的谱系；是作者的结果，不是本地复现。本地筛选见[论文矩阵](docs/research/2026-10-03-literature.md)。
- [karpathy/autoresearch](https://github.com/karpathy/autoresearch)——灵感来源。

## 致谢

基于 Google ADK 构建。honesty-gate 方法得益于 LLM 评测中通用的盲位置交换评判模式。
