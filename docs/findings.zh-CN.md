# 实测结论与研究记录

从 README 迁出的历史、有条件的观察，只描述当时测试的模型、任务和协议，不是普遍定律。README 仅保留摘要与公开 API。

[← 返回 README](../README.zh-CN.md) · [English](findings.md)

## 核心结论（实测，无预设结论）

下列编号结论记录当时测试过的任务、模型和评测协议，其质量排序不是普遍定律。
旧评判将位置分歧记为平局；新的来源约束评测将其保留为无法确定。
名义调用次数相等不能证明 token 或费用相等。

1. **引擎真正赢的地方——能力，不是质量。** 在需要*行动*的任务上（agentic 隐藏
   oracle 基准），小模型用 `agent(tools=[...])` 得 **8/8**，单次调用 **0/8**：它探测
   隐藏函数、推断规则、实现之——单次调用无从知晓任意规则。这是真正的价值类别。

2. **scaffold 不赢的地方——自包含结果质量。** 在历史的 *matched-cost* 比较中，**测试过的
   纯 LLM scaffold 未胜过当时的单次调用对照**：dialectic 模式 vs prompt-matched 强基线在各档模型上
   **0-3-2**（早先 4-1-0 的"赢"是 prompt+长度，不是结构）。**repair** 引擎打败
   *单次*调用，但在通过率上与 *matched-cost best-of-K* **打平**——其真正优势是
   **成本**（best-of-N 可靠性，约 1/3 调用）。

3. **树结构被*压制*，而不仅无用。** 在 **24 点游戏**——ToT *自己*的标志基准
   上——忠实 ToT 得 **14/15，以约 34× 成本输给单次的 15/15**：现代模型一次解出
   2023 论文 GPT-4 失败 96% 的任务。matched-cost 盲评判下 ToT+GAN 模式
   **0-4-1 / 0-2-3 / 0-1-4**（vs 单次 / best-of-N / self-refine）——*从未赢过一
   场*。质量序：**self-refine ≥ best-of-N ≥ 单次 ≥ 树 scaffold**。

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
     以 **3-1-2** 打败 prompt-matched 单次调用——*模式确实在 open-ended 任务上
     提升回答健壮性*（代码轴测不出）。但 **blind-pick 臂**（信号换常数）也以
     **3-1** 打败单次：增益**归因于 roster 异构性，不是 scorer 排序信号**。按 H1
     信号归因条款：**CUT**。
   - **要点：** *无 scorer* 的多模型 best-of-N（采样 N 个异构模型、保留一个）即可
      捕获 ensemble 在 open-ended 上展现的健壮性增益；float scorer 相对 blind-pick
      无可测提升。repair 子判据亦 **CUT**（multi-model-repair@6 vs single@6：6/6 vs
      6/6，**0 次模型切换救援**）。

6. **异构 reflection——诚实的 meta-task 杠杆（2026-07-08）。** `reflection_pattern.py`
   实现 gather → frame → critique → synthesize 结构化 pipeline，各视角分配不同
   模型——无 AB-MCTS、无 LLM scorer。在完整 **5 题 meta 集**上（盲位置交换评判、
   cliproxy roster `openai:qwen3.6-flash` + `openai:glm-5.2`、
   `JUDGE_MODEL_CONFIG=openai:glm-5.2`、`DIALECTICA_DISABLE_THINKING=true`）：
   - **`evals/reflection_ablation.py`——异构 vs 同构 vs 单次：** 异构 reflection
     以 **5-0-0** 打败 prompt-matched 单次，以 **5-0-0** 打败同 pipeline 单模型
     ——增益**归因于 roster 异构性**，不只是多 stage 形状。
   - **`evals/workflow_ablation.py`——同构 vs 单次（对照）：** 同构 reflection pipeline
     以 **4-0-1** 打败单次（NET **+4**）——pipeline 形状在 meta-task 上*确实*有帮助，
     异构性补上剩余边际（含一题同构与单次 tie 但异构赢）。
   - **要点：** open-ended 反思/meta-task 用异构 multi-angle reflection；勿复活
     ensemble float-scorer 排序。复现：`uv run python -m evals.reflection_ablation`
     与 `uv run python -m evals.workflow_ablation`（cliproxy 环境同 #5）。

7. **多模型质量 workflow 模式——扩大题池（2026-07-09）。** `quality_workflow_pattern.py`
   在 **10 题**（5 meta + 5 default；盲评判、cliproxy roster 同 #6）上统一三种异构组合：
   - **vs 单次：** 同构 reflection **4-0-6**（NET +4）；异构 reflection **10-0-0**（NET +10）；
     异构 adversarial **9-0-1**（NET +9）；异构 dialectic **9-0-1**（NET +9）。
   - **vs 异构 reflection（额外 stage 是否有增益）：** adversarial **2-0-8**（NET +2）；
     dialectic **0-1-9**（NET −1）。
   - **要点：** 异构 `reflection` 为默认——扩大题池全胜。额外 adversarial-rival 或一轮
     dialectic 相对异构 reflection 无一致提升（多为 tie；dialectic 还输 1 场 head-to-head）。
     默认用 `create_reflection_engine`；`quality_workflow_pattern` 仅作模式对照。
     复现：`uv run python -m evals.quality_workflow_ablation`。

8. **访问列表——一种上下文可见性杠杆，移植自 Sakana Fugu（2026-07-12）。** 对 Sakana Fugu/Fugu-Ultra 编排器（TRINITY + The Conductor，ICLR 2026）的研究从另一侧印证了上述定律：Fugu 相对每个单 worker 的胜绩来自**模型独立性 + 学习型路由器**，而非 worker 缺少的工具，其机制是带按步骤访问列表的学习型通信拓扑。唯一能移植到无训练内核的机制是**访问列表**——`agent(sees=[...])` 现作为内核原语发布：默认完全隔离，可选注入指定前置步骤的输出。它经 `use_access_lists=True` 接入 reflection 配方（每个 critique 只看自己的 gather 角度；synthesize 只看 tension + critiques，而非全部 transcript），并已对照真实模型（经 OpenAI 兼容端点的 `glm-5.2`）验证。上述实测 reflection 数字用的是内联 prompt，故访问列表模式在 ablation 证明其在相同矩阵上 lift 或 tie 之前保持可选。复现实时校验：`uv run pytest -m e2e_access`。

9. **调好的辩证在开放式 meta-task 上打败 prompt-matched 单次调用（2026-08-05）。** 0-3-2（结论 #2）并不是全部：那个辩证没调到位。两处纯 LLM、同模型的改动——**调硬 `SYNTHESIS_PROMPT`**（做一个绑定决策、给出精确可测触发、说明每边赢的条件、保留具体数字——与 reflection 对 synthesis 的同一标准）和**加深螺旋**（`max_rounds` 3 → 5）——把辩证对 prompt-matched 强单次调用的 NET 从 **−0.500 翻到 +0.600**，经**两次独立运行**确认（+0.100、+0.600）。方法论很关键：这次用的是**连续 0-10 打分**（盲评判对每个答案按 `DEFAULT_CRITERIA` 打分，NET = 平均分差），而非离散胜/负/平——后者的 ±4 逐次摆动让早期测量不可读。被否的方向：再调硬 THESIS prompt（−0.333）和每轮两个对手（`perspectives=2`，−0.567）都回退并弃用。注意：在 3 个 meta 问题上、单一 judge（gpt-5.5）、连续打分设计下测得；同样的调法在完整 5-meta 题池上尚未实测。

## 研究更新：历史结论有适用条件

截至 **2026-10-04**，本次研究升级已筛选 **32 篇一手来源论文**，完成
**7 组真实模型研究、576 次生成试验**。
[论文矩阵](research/2026-10-03-literature.md)保存来源日期、阅读深度和本地实现决定；
筛选不代表全部 32 篇都经过全文审阅或复现。
[完成审计](research/2026-10-04-completion-audit.md)将验收要求与已保存的验证记录对应，
[原始记录完整性审计](research/results/2026-10-04-heldout-v1/final-integrity-audit.json)
核对各组研究的结果和用量。生成试验指实验分组的一次运行，不等于单次模型调用；
校准和评判成本另行记录。

[冻结的七组留出集实验](research/2026-10-04-heldout-protocol.md)已全部完成。
最终依赖更新前，已核验全部 576 次生成试验、报告/协议/分析绑定及逐调用用量之和。
整批上报 **3,631,216 token / 3,789 个可观察模型轮次**，含校准和评判，保留
**30 次生成失败**。本批未知用量为零；先前网关失败中的未知用量仍单独保留。
这些是上报成本，不是服务端账单，也不包含不可观察的底层 HTTP 重试计数。

| 留出集比较 | 观察结果 | 采用决定 |
|---|---|---|
| [来源约束决策](research/2026-10-04-heldout-evidence-result.md) | 自我修正相对 Gemini 单次、异构反思相对 Qwen 单次出现探索性正向评判信号；未证明优于 GPT 单次 | 反思保留为参考模式；合成引用核验和评判一致不能证明决策正确或人类偏好对齐 |
| [断言 K=6](research/2026-10-04-heldout-claims-k6-result.md) | 断言 6/24；共识/自我修正 7/24；单次 4/24 | 断言相对单次的差值区间包含零，不新增稳定 API |
| [断言 K=3](research/2026-10-04-heldout-claims-k3-result.md) | 断言/自我修正 7/24；单次/共识 3/24 | 断言相对单次的差值区间包含零，不新增稳定 API |
| [元推理预算 12](research/2026-10-04-heldout-meta-budget12-result.md) | 单次 5/24；共识 3/24；自我修正 8/24；分阶段 2/24；直接 3/24 | 相对单次的差值区间均包含零，控制器保留为研究模式 |
| [元推理预算 6](research/2026-10-04-heldout-meta-budget6-result.md) | 单次 5/24；共识 4/24；自我修正 10/24；分阶段 4/24；直接 0/24 | 差值区间均包含零；自我修正的较好点估计不足以支持采用 |
| 强单次对照：[元推理](research/2026-10-04-heldout-strong-meta-result.md) / [断言](research/2026-10-04-heldout-strong-claim-result.md) | GPT 在两种输出约束下各 24/24 | 仅是本题池的天花板，不能证明普遍成功或新机制在 GPT 上的收益 |

[候选与选择诊断](research/2026-10-04-heldout-selection-diagnostics.md)显示：
相同候选上的断言加权没有改变最终正确性；元推理控制器的正确候选覆盖较低；
自我修正则会丢失中途正确答案。失败的断言试验覆盖信息不完整，不能填成零。
这些事后描述性诊断用于指导未来研究，不用于在留出题集上调参。
区间条件于小题池，属于未做多重比较校正的探索性结果；实际 token 成本不相等。
公开 API 仍为 Workflow 与验证器制导修复。

上述数字描述当时测试过的模型、任务和流程，不能证明“只有加入外部信息才能赢”的
必要充分定律。小题池、任务饱和、提示要求不对等、仅按调用次数计成本，以及单一
judge，都限制了结论的外推范围。

近期反证促成了上述受控实验：[关键主张验证](https://arxiv.org/abs/2608.11994) 和
[结构化元推理](https://arxiv.org/abs/2609.38147) 报告了重新分配推理计算的增益，
同时也有预算与模型限制。这些是作者的结果，尚非本项目复现。当前研究升级的假设、
来源和验收条件记录在[升级契约](research/2026-10-03-upgrade.md) 与
[论文矩阵](research/2026-10-03-literature.md)。新的优势声明必须有强提示匹配基线、
按实验分组的完整成本收据、保留题集、重复试验和可靠评判；E2E 只能证明执行链路。

新增的[关键断言证伪研究模式](../examples/patterns/claim_falsification_pattern.py)
实现独立断言评估和加权候选选择。[比较脚本](../evals/claim_ablation.py) 保存评估调用成本、
原始候选、正确答案覆盖率，以及相同候选上的无权重选择结果。首轮真实模型开发实验
在十四项目题上出现零覆盖率，详见[试跑诊断](research/2026-10-04-pilot-diagnostics.md)。
重复留出集比较已完成，未建立选择收益或明确质量优势，因此暂不进入公开 API。

[元推理研究模式](../examples/patterns/meta_reasoning_pattern.py) 已实现分阶段控制器与
直接控制器对照、选择性上下文和已有产物选择；尚未测出质量优势。
[来源约束决策评测](../evals/evidence_ablation.py) 分别记录生成、校准与评判成本，
并将位置偏差、不同评判的分歧及校准失败保留为无法确定。首轮真实调用中，
引用核对通过但评判发生位置分歧，因此没有胜负结论。调用预算计的是工作流
agent 步骤；底层重试可能产生更多请求，不能据此声称请求、token 或费用相等。

新的比较脚本会在首次模型调用前保存配置、题目、源码与依赖指纹以及分析规则，
包括评判校准调用；已有实验路径不可复用。完整的客观验证报告可以这样分析：

```bash
uv run python -m evals.objective_analysis results.json --output analysis.json
```

分析先在题目内平均重复试验，再按题目进行配对重采样。生成失败保留在可靠性分母中，
未知用量阻止完整的已上报成本声明；缺失配对、重复试验或模型组使用不同题池都会报错。
默认拒绝冻结源码或规则发生变化的分析；历史诊断可显式使用
`--exploratory-reanalysis` 并保存差异。区间属于探索性分析，未进行多重比较校正。
全对或全错时出现的退化区间，不能证明确定性或普遍优势。

完成的来源约束决策报告使用独立分析入口：

```bash
uv run python -m evals.evidence_analysis evidence.json --output evidence.analysis.json
```

它将各候选模式分别与每个已声明的单模型基线比较，无法确定的偏好保留为 [-1, +1]
边界，而非平局。结果包含按题目重采样的不确定性，以及生成、校准、评判的分项成本。
仅对有效判决计算的偏好只是筛选后证据的诊断，不能证明人类认可；题目、重复试验或
基线比较不完整时，分析会拒绝。

## 早期 advice 矩阵（2026-06-10/11）——已被取代

首轮矩阵将 ToT+GAN 模式与*较弱*的单次基线（无 prompt 匹配对照）和"Innovation"
判别准则（偏向过度复杂的答案）比较。已被上方 #2–#7 取代。记录于此：V1（Innovation
准则）技术上 7-1-1 赢、组织上 0-4-2 输；V2（Feasibility
准则）合计 20-8-2 vs V1 的 7-5-3——证明判别准则引导答案*内容*而非仅选择，但都未
打败 prompt-matched 强基线。

## 真实验收快照

ADK 2.11 真实验收（2026-10-03）：经 cliproxy **9 项通过、0 项跳过，耗时 145.37 秒**。
默认、generator 和 fast 模型为 `openai:qwen3.8-flash`，反思的第二个模型为
`openai:gemini-3.5-flash-lite`。覆盖访问列表、默认隔离、异构反思全部 10 次调用、
repair、关闭/开启同步工具线程池时的 tools + schema，以及并行恢复时的
缓存上下文、真实用量和零调用重放，以及真实模型响应在事件生成前报错时的
用量保留（重试后成功和最终失败均核对上报 token 的精确合计）。最终缓存事件
计量修复后，重新运行这两项真实失败场景：**2 项通过，耗时 21.17 秒**。
结果适用于 OpenAI 兼容路由；Gemini 直连凭据已失效，当前 GLM 路由受套餐/路由问题阻断。

最终实验后环境验收（2026-10-04）：**212 项离线测试通过；9 项真实模型 E2E
通过、零跳过，耗时 114.77 秒**。异构反思使用 Gemini Flash Lite 与 GPT-5.5。
lint、格式、打包和依赖检查见[完成审计](research/2026-10-04-completion-audit.md)。
首轮最终真实验收的 8 项通过和 1 项历史模型路由失败均保留；配置可用异构模型后，
全部断言原样通过。仍有一条上游 Pydantic `ReadOnly` 提示；通过的运行未观察到未处理
的异步任务失败。这证明执行链路及事件返回前失败的用量保留，不证明质量优势。
