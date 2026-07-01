# Dialectica ![](https://img.shields.io/badge/A%20FRAD%20PRODUCT-WIP-yellow)

[![PyPI](https://img.shields.io/pypi/v/dialectica.svg)](https://pypi.org/project/dialectica/) [![Twitter Follow](https://img.shields.io/twitter/follow/FradSer?style=social)](https://twitter.com/FradSer) [![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/) [![Framework](https://img.shields.io/badge/Framework-ADK%202.0+-orange.svg)]() [![Evaluation](https://img.shields.io/badge/Evaluation-honesty%20gate-purple.svg)]()

[English](README.md) | **简体中文**

**Dialectica** 是基于 Google ADK 的推理引擎工具箱，按硬方式构建与度量：每个引擎都跑过 matched-cost 基线和盲评判，只有数据支持的赢才保留，其余作为负向结果记录在案。全部目的就是用数字（而非感觉）回答一个问题——*scaffold 是否能打败一次精心提示的单次调用？*

> **一句话结论。** 在自包含任务上，*没有任何*纯 LLM scaffold（ToT、GAN、辩证、异构 ensemble）能在结果质量上打败 prompt-matched 单次调用——它们只是重排模型自己的思考，不增加信息。引擎只有在做到单次前向传播做不到的事时才赢：**作用于世界**（agentic）、**运行 ground-truth 验证**（repair），或——经实测、部分地——**采样独立模型**（ensemble 健壮性，但起作用的是异构性，不是 scorer）。见[评测](#评测)。

受 [karpathy/autoresearch](https://github.com/karpathy/autoresearch)、Sakana AI 的 AB-MCTS / 集体智能系列、以及 Claude Code 可组合工作流启发。

## 引擎层级（由数据支撑）

按"单次调用缺什么"来选：

| 引擎 | 靠加入什么赢 | 判决 |
|---|---|---|
| **Agentic**（`create_agentic_engine`） | **能力**——工具让模型 act → observe → iterate | ✅ 真赢（hidden-oracle 上 8/8 vs 0/8） |
| **Repair**（`create_repair_engine`） | **ground truth**——验证器在环，通过即短路 | ✅ 成本赢（best-of-N 可靠性，约 1/3 调用） |
| **Ensemble**（`create_ensemble_engine`） | **独立性**——异构 roster | ⚠️ 待定 / CUT（健壮性增益来自异构性，不是 scorer） |
| **Dialectic**（`create_dialectic_engine`） | ——纯 LLM scaffold | ❌ 与单次打平（0-3-2）；仅可审计轨迹 |
| **ToT + GAN**（`create_engine`） | ——纯 LLM scaffold | ❌ 被压制（0-4-1 / 0-2-3 / 0-1-4）；仅作基线 |

## 安装

```bash
uv add dialectica      # 或: pip install dialectica
```

```python
import os, asyncio
from dialectica import create_repair_engine

os.environ["GOOGLE_API_KEY"] = "..."          # 环境配置由应用负责

# 验证器对任意客观检查返回 (passed, feedback)——单元测试、JSON schema、
# linter、断言校验的业务逻辑。引擎据反馈反复修复，直到通过或用尽次数。
def verify(answer: str) -> tuple[bool, str]:
    ok = "def solve" in answer                 # 你的真实检查写这里
    return ok, "" if ok else "no solve() function defined"

async def main():
    result = await create_repair_engine(
        "Write a solve() function that ...", verifier=verify
    ).run()
    print(result["passed"], result["attempts"], result["final_answer"])

asyncio.run(main())
```

可验证任务优先用 `create_repair_engine`（核心引擎）。多步工具任务用
`create_agentic_engine`。库从 `os.environ` 读配置，**不**自行加载 `.env`。

## 引擎与原语

### 🤖 Agentic 引擎——增加能力（`create_agentic_engine`）
唯一让模型做到单次前向传播*做不到*之事的引擎：工具使用循环。注入你的工具
（读文件、跑测试、查服务），agent 规划、调用工具、读结果、迭代直到任务客观
完成——ADK 驱动循环。

- **靠能力赢，不靠质量**——小模型在需通过工具采集信息的任务上测得 **8/8 vs
  单次 0/8**（`evals/agentic_eval.py`）。这是真正的价值类别；自包含 prompt
  上的推理 scaffold 与单次打平。
- **任务无关**——工具是注入的可调用对象，ADK 自动推导 schema。
- **返回** `{final_answer}`；副作用通过你的工具发生，调用方事后检查客观结果。

### 🛠️ 执行制导修复——验证器在环（`create_repair_engine`）
可验证任务：**生成 → 跑注入的验证器 → 据具体失败修复 → 重试**，直到通过或
用尽次数。

- **任务无关的验证器**——任意 `Callable[[answer], (passed, feedback)]`：单测、
  schema 校验、linter、断言校验。`solution_format` 钉住验证器解析的输出形态。
- **用满失败历史**——每次失败尝试及其精确失败都回灌，避免在两个错误修复间
  振荡。
- **成本克制**——验证器一通过即短路，以远少于 best-of-N 的调用达到其可靠性。
- **多模型**——传 `models=[...]` 在失败时跨 roster 轮换；`history[i]["model"]`
  记录每次尝试由哪个模型产出。
- **返回** `{final_answer, passed, attempts, history}`。

用 `uv run python -m evals.repair_ablation` 对比 pass@1 与 matched-cost best-of-K。

### 🌐 集成搜索引擎（`create_ensemble_engine`）—— *待定*
AB-MCTS-lite 自适应搜索（wider = 采样新模型，deeper = 修优当前最佳），由
**必填的注入式 float scorer** 排序。设计为第四个诚实赢的杠杆——*独立性*
（不同训练分布）由 ground-truth 级信号排序。

**honesty gate 判 CUT**（评测结论 #5）：open-ended meta 任务上 ensemble 在盲
评判下*确实*打败单次调用（**3-1-2**），但 **blind-pick** 臂（信号换成常数）
与之持平（**3-1**）——增益来自 **roster 异构性，不是 scorer 信号**。可验证
代码上两臂都饱和（6/6）。保留以供研究；no-scorer 多模型 best-of-N 更诚实地
捕获实测的健壮性增益。

- **必填 scorer**（`Callable[[str], float]` 或 async）——不传则构造失败，纯
  scaffold 误用不可表示。布尔验证器包一层：`lambda a: 1.0 if v(a)[0] else 0.0`。
- **可注入 policy**——默认 Thompson 采样 bandit；测试注入脚本化确定性 policy。
- **FR6 roster 去重**——两个成员解析到同一有效模型或静默回退默认时告警。
- **返回** `{final_answer, passed, attempts, history, best_score}`。

### 🔗 Workflow 原语——可组合的多 agent 运行时（`Workflow`）
Claude Code `Workflow` 编排面的 Python 复刻：`agent()` / `parallel()` /
`pipeline()` / `phase()` / `log()` / `budget()`。用于 *meta-task* 编排（研究、
评审、规划、设计）——生成 → 对抗评审 → 综合 真正有用的场景。它是**编排层**，
不是自包含质量引擎：上述负向结论仍然成立，在这些原语上组合工作流不会推翻它们。

### 🧩 辩证引擎（`create_dialectic_engine`）
*正 → 反 → 合*：自包含螺旋，产出**可审计**的推理轨迹，由 `criteria` 引导。纯
LLM scaffold——对透明度和内容引导有用，但（实测）**不**在结果质量上胜过单次
调用。其价值是可审计轨迹与 criteria 引导，不是更好的答案。

### 🌳 思维树 + GAN 引擎（`create_engine`）
上一代可插拔管线（beam search + GAN 风格对抗精修，每个阶段是可替换 `Protocol`）。
**实测被压制**（输给单次、best-of-N、平铺 self-refine）；保留以供研究与向后
兼容，不推荐用于质量。

## 评测

引擎是否真的打败一次强模型调用？仓库附带评测工具（`evals/`，开发工具——不随
包发布），用数据回答：每题由引擎**和**单次调用基线各解一次；**盲评判**对两答案
各评两次并交换位置（不一致记 tie）；LLM 调用通过测试 mock 的同一 `run_agent`
接缝计数。

```bash
uv run python -m evals                          # 全部基准题
uv run python -m evals.repair_ablation          # repair vs best-of-K
uv run python -m evals.agentic_eval             # agentic vs 单次（隐藏 oracle）
uv run python -m evals.quality_ablation         # ToT+GAN vs 单次/best-of-N/self-refine
uv run python -m evals.ensemble_ablation        # ensemble 三臂 honesty gate（代码）
uv run python -m evals.ensemble_meta_ablation   # ensemble honesty gate（open-ended，LLM 评判）
```

### 核心结论（实测，无预设结论）

1. **引擎真正赢的地方——能力，不是质量。** 在需要*行动*的任务上（agentic 隐藏
   oracle 基准），小模型用 **agentic 引擎**得 **8/8**，单次调用 **0/8**：它探测
   隐藏函数、推断规则、实现之——单次调用无从知晓任意规则。这是真正的价值类别。
   复现：`uv run python -m evals.agentic_eval`。

2. **scaffold 不赢的地方——自包含结果质量。** 与 *matched-cost* 基线相比，**无
   纯 LLM scaffold 打败单次调用**：辩证 vs prompt-matched 强基线在各档模型上
   **0-3-2**（早先 4-1-0 的"赢"是 prompt+长度，不是结构）。**repair** 引擎打败
   *单次*调用，但在通过率上与 *matched-cost best-of-K* **打平**——其真正优势是
   **成本**（best-of-N 可靠性，约 1/3 调用）。复现：`uv run python -m evals.repair_ablation`。

3. **树结构被*压制*，而不仅无用。** 在 **24 点游戏**——ToT *自己*的标志基准
   上——忠实 ToT 得 **14/15，以约 34× 成本输给单次的 15/15**：现代模型一次解出
   2023 论文 GPT-4 失败 96% 的任务。matched-cost 盲评判下 ToT+GAN 引擎
   **0-4-1 / 0-2-3 / 0-1-4**（vs 单次 / best-of-N / self-refine）——*从未赢过一
   场*。质量序：**self-refine ≥ best-of-N ≥ 单次 ≥ 树 scaffold**。复现：
   `uv run python -m evals.game24` 与 `uv run python -m evals.quality_ablation`。

4. **价值窗口在可达模型范围上已关闭。** ToT 只在基模型单独失败但搜索能恢复的
   "失败但可修"区间有用。对最难的 24 点题在四个模型档位（最弱的可达云模型）上
   探测，单次调用**每个模型、每题都是 5/5**。没有可达的弱模型会失败这些任务，
   所以没有搜索可恢复的空隙——边界已越过此任务。

5. **异构 ensemble——scorer 的信号并非起作用者（2026-06-26）。** ensemble 设计
   为第四个诚实赢的杠杆——*独立性*由 ground-truth 级信号排序。两轴 honesty gate
   证伪了信号这一半的论题，同时浮现一个真实的更窄结果：
   - **代码（ground-truth 验证器，6 题，budget 6）：** ensemble+信号 **6/6**、
     best-single best-of-6 **6/6**、blind-pick **6/6**——**CUT**：两模型均一击解
     出，异构性与信号都无空间。饱和，同 #4。
   - **Open-ended meta（盲 LLM 评判，5 题，budget 6，位置交换）：** ensemble+信号
     以 **3-1-2** 打败 prompt-matched 单次调用——*引擎确实在 open-ended 任务上
     提升回答健壮性*（代码轴测不出）。但 **blind-pick 臂**（信号换常数）也以
     **3-1** 打败单次：增益**归因于 roster 异构性，不是 scorer 排序信号**。按 H1
     信号归因条款：**CUT**。
   - **要点：** *无 scorer* 的多模型 best-of-N（采样 N 个异构模型、保留一个）即可
     捕获 ensemble 在 open-ended 上展现的健壮性增益；float scorer 相对 blind-pick
     无可测提升。repair 子判据亦 **CUT**（multi-model-repair@6 vs single@6：6/6 vs
     6/6，**0 次模型切换救援**）。复现：`uv run python -m evals.ensemble_ablation`
     与 `uv run python -m evals.ensemble_meta_ablation`（需经 `OPENAI_API_BASE`/
     `OPENAI_API_KEY` 的多 provider roster，如暴露 qwen+glm 的 cliproxy；
     `DIALECTICA_DISABLE_THINKING=true` 以降 qwen 族延迟）。

### 这些结论共同指向的定律

scaffold 打败一次前向传播，**当且仅当**它加入了单次传播无法获得的信息——**工具**
（agentic）、**ground-truth 验证**（repair），或**独立样本**（ensemble 健壮性，
但只经异构性，非学习到的排序）。对一个模型在单上下文上的纯重排（ToT、GAN、辩证、
对同族候选的 LLM-judge scorer）与单次打平。Sakana AI 的研究合集从另一侧收敛到同
一定律：那里每个真正的赢也都由模型外部的 ground-truth oracle 支撑。

### 早期 advice 矩阵（2026-06-10/11）——已被取代

首轮矩阵将 ToT+GAN 引擎与*较弱*的单次基线（无 prompt 匹配对照）和"Innovation"
判别准则（偏向过度复杂的答案）比较。已被上方 #2–#5 取代。保留在 `evals/results/`
以供复现：V1（Innovation 准则）技术上 7-1-1 赢、组织上 0-4-2 输；V2（Feasibility
准则）合计 20-8-2 vs V1 的 7-5-3——证明判别准则引导答案*内容*而非仅选择，但都未
打败 prompt-matched 强基线。

## 配置

所有配置从 `os.environ` 读取——作为库，Dialectica **不**自行加载 `.env`；环境
配置由消费应用负责。仅测试套件加载 `dialectica/.env`。

```bash
# 所有 agent 的默认模型
export DEFAULT_MODEL_CONFIG="google:gemini-3.5-flash"

# 角色特定覆盖（可选）
export GENERATOR_MODEL_CONFIG="google:gemini-3.5-flash"
export DISCRIMINATOR_MODEL_CONFIG="google:gemini-3.1-pro-preview"
export SYNTESIZER_MODEL_CONFIG="google:gemini-3.5-flash"
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

只用 `gemini-3.5-flash`（默认）或 `gemini-3.1-pro-preview`——没有稳定的
`gemini-3.1-pro`（generateContent 返回 404）。provider 串为 `provider:model_name`；
`openai:` provider 显式传 `api_base`（新版 LiteLLM 不再为 `openai/` 前缀读
`OPENAI_API_BASE`）。

### 引擎参数

- **Agentic**——`tools`（注入的可调用对象）、`instructions`（任务指引）。
- **Repair**——`verifier`（必填）、`max_attempts`、`solution_format`、`models`（可选 roster）。
- **Ensemble**——`scorer`（必填）、`models`（roster）、`max_calls`、`solved_score`、`policy`（默认 Thompson bandit）。
- **Dialectic**——`criteria`（引导综合内容）、`rounds`。
- **Workflow**——`budget_total`、`concurrency`（或 `DIALECTICA_WORKFLOW_CONCURRENCY`）。

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

### Agentic（工具任务）

```python
from dialectica import create_agentic_engine

engine = create_agentic_engine("Fix the failing test", tools=[read_file, run_tests])
result = await engine.run()   # 工具负责行动；事后检查结果
```

### Ensemble（异构 roster）

```python
from dialectica import create_ensemble_engine

def scorer(answer: str) -> float: ...      # 你的 ground-truth 级排序

engine = create_ensemble_engine(
    "Design the pricing tier",
    scorer=scorer,
    models=["google:gemini-3.5-flash", "openrouter:qwen3.6-32b"],
    max_calls=8,
)
result = await engine.run()
# {"final_answer", "passed", "attempts", "history", "best_score"}
```

### 查看结果

所有引擎返回含 `final_answer`、`passed`（或隐含）、`attempts`、`history` 的
`dict`。ensemble 与 repair 的 `history` 条目记录每次尝试的产出模型，便于将赢归因
到具体臂或模型切换。

## ToT + GAN 引擎（遗留，深入）

可插拔管线，每个阶段是 `protocols.py` 中的 `typing.Protocol`：`Generator.expand`
→ `Evaluator.evaluate` → `Selector.select` → `Synthesizer.synthesize`。
`coordinator.py` 跑三阶段（Initialize → Explore → Synthesize），兄弟展开/评估经
`asyncio.gather` 并发。旋钮：`score_threshold`（beam 准入）vs
`gan_score_threshold`（停止精修门槛），`criteria`（判别 rubric——引导答案内容，
非仅选择）。

默认：`LlmGenerator`、`AdversarialEvaluator`（GAN 精修循环）/`SinglePassEvaluator`、
`BeamSearch`/`GreedySearch`、`LlmSynthesizer`。不可解析的判定最多重试 3 次；重试后
连续 3 次失败触发断路器中止运行。所有公开阶段方法为 `async`。

此引擎**实测被压制**（结论 #3）——保留以供研究与向后兼容，不用于质量。

## 本地开发

```bash
uv sync                                         # 安装依赖
uv run pytest                                   # 模拟，快，无需 API key
uv run pytest -m e2e                            # 实时 E2E（需 GOOGLE_API_KEY）
uv run ruff format && uv run ruff check         # 格式化 / lint
```

库不调用 `logging.basicConfig`——日志配置由消费应用负责。在唯一接缝
`agent_runtime.run_agent()` 处 mock LLM——绝不 patch ADK 内部或各阶段 agent
（`tests/helpers.py` 有 fakes）。`asyncio_mode = auto`；pytest-bdd 步骤为同步，故
用 `asyncio.run()` 包协程。

## 测试流程（BDD 驱动 TDD）

新行为始于 `tests/features/*.feature` 中的 Gherkin 场景，经 pytest-bdd 执行——步骤
定义在 `tests/test_*_feature.py`（用 `scenarios(...)` 绑定）。然后 RED 测试 → GREEN
代码 → REFACTOR。更新测试时先改对应 `.feature`。CI
（`.github/workflows/test.yml`）在每次 push/PR 跑 `ruff format --check`、
`ruff check`、`pytest`。

## 项目结构

```
dialectica/
  agent.py            # 遗留 ToT+GAN 组合根（create_engine）
  agent_factory.py    # 从 ROLE_TEMPLATES 构建 LlmAgent
  agent_runtime.py    # 唯一 LLM 接缝：run_agent() + 重试/退避
  agentic.py          # create_agentic_engine（真正赢的引擎）
  coordinator.py      # 遗留 ToT Explore/Synthesize 循环
  dialectic.py        # create_dialectic_engine（可审计轨迹，无质量赢）
  ensemble.py         # create_ensemble_engine（待定 / CUT）
  gan_evaluator.py    # AdversarialEvaluator + 判定解析/修复
  llm_config.py       # provider:model 解析（google/openrouter/openai）
  models.py           # ThoughtData / EvaluationResult / DiscriminatorVerdict
  protocols.py        # Generator/Evaluator/Selector/Synthesizer Protocol
  repair.py           # create_repair_engine（成本赢）
  workflow.py         # Workflow + agent/parallel/pipeline/phase/log/budget
evals/                # 仅开发的评测工具（不随 wheel 发布）
tests/                # BDD 特性 + 步骤定义 + helpers
docs/plans/           # 设计与计划文件夹（brainstorming/writing-plans）
```

## 故障排除

- **`gemini-3.1-pro` 返回 404**——用 `gemini-3.1-pro-preview` 或 `gemini-3.5-flash`。
- **OpenAI 兼容后端 "Connection error"**——新版 LiteLLM 不再为 `openai/` 前缀读
  `OPENAI_API_BASE`；库显式传 `api_base`，故确保设置了 `OPENAI_API_BASE`（而非仅
  `OPENAI_API_KEY`）。
- **qwen 族评测慢**——设 `DIALECTICA_DISABLE_THINKING=true` 关闭思考链
  （`chat_template_kwargs.enable_thinking=false`）。
- **Ensemble roster "collapsed to duplicate effective model"**——两成员解析到同一
  模型（常因某 provider key 未设，双双静默回退默认）。设该 provider 的 API key 或
  用不同模型。
- **强制 JSON 模式返回空判定**（部分后端，如 gemma-4-26b-a4b）——用
  `structured_output=False` / `--no-structured-output`。

## 贡献

约定式提交（用 `/git:commit` skill）。发布 = 推一个版本号与 `pyproject.toml`
**匹配**的 `v*.*.*` tag；CI 跑测试、发 PyPI、建 GitHub release。新增引擎时，连同
ship 会在数据说 CUT 时 CUT 它的 honesty-gate ablation——本仓的传统是记录负向结果，
而非未证实的声明。

## 许可证

MIT——见 `LICENSE`。

## 参考资料

- [Tree of Thoughts](https://arxiv.org/abs/2305.10601)——Yao et al., 2023（ToT 引擎
  的谱系；现作基线）。
- [Sakana AB-MCTS / "Wider or Deeper?"](https://arxiv.org/abs/2503.04412)——ensemble
  引擎的谱系（独立性 + ground-truth 信号）。
- [karpathy/autoresearch](https://github.com/karpathy/autoresearch)——灵感来源。

## 致谢

基于 Google ADK 构建。honesty-gate 方法得益于 LLM 评测中通用的盲位置交换评判模式。
