# Sprint 5 / T5.3 — CandidateEvaluator 结果评估引擎（Completion Report）

> 日期: 2026-08-08 | 状态: 完成
> 目标: 多候选 → 确定性 5 层评分 → Best 选择 + 可解释明细 + 诚实拒绝
> 设计依据: docs/validation/sprint5-t51-execution-strategy-design.md §3/§4 (T5.1 冻结)
> 约束: 禁 LLM 评分 / 禁随机 / 禁人工选择; Core/Runtime/Desktop = 0; 不跑真实 Benchmark

## 完成内容

```
① CandidateEvaluator (exec/evaluator.py 新建)
   List[ExecutionCandidate] → EvaluationResult:
   - selected_candidate_id  选中候选 (验证通过者中 5 层总分最高; 无合格 → None)
   - ranking                选择优先级序 (合格在前 → 总分降序 → 逐层优先 → Run 序;
                            含失败候选 — 诚实全排序, 全失败时首位 = 最不差)
   - score_breakdown        每候选 5 层分数明细 (LayerScore: 分数+理由+证据细节)
                            + verdict 一句话结论 (为什么选它/不选它)
   - rejection_reason       无候选 / 全失败 → 诚实拒绝理由 (逐候选列验证失败原因,
                            不静默); 有选中 → None

② 5 层确定性评分 (纯函数, 禁 LLM/随机/IO; 证据缺省 {} → 该层 0 分中性, 不臆造)
   ① Validation Pass      +100 (硬条件: failure_reason 非空 / passed 非真 /
                            无验证证据 → 直接降级不可选; 支持测试计数推断)
   ② Patch Apply          +50 / -50 (git apply/check 成功/失败; 无证据 0)
   ③ 修改范围 (Scope)     基准 +30, 每多改 1 文件 -5, 每多改 10 行 -1, 下限 -30
   ④ 回归风险 (Risk)      核心文件 -20 / 删码>50 行 -10 / 测试减少 -15 /
                          影响面小 (≤3 符号) +10; 合计钳制 [-30, +10]
   ⑤ 需求覆盖 (Coverage)  验收标准逐条覆盖 +10, 封顶 +40

③ 决策规则 (确定性, 可解释)
   - 硬门槛: 验证未通过 → 不可选 (除非全部失败 → 诚实拒绝, 不选最不差伪装成功)
   - 平局决胜: 层优先级 (Validation→Patch→Scope→Risk→Coverage), 再输入序
     (Run 序 — 先 Run 者胜, 与 T5.2 临时选择语义延续, 旧测试零破坏)

④ select_result 升级正式 Evaluator
   - SequentialRunner.evaluate(): CandidateEvaluator 正式评估 → last_evaluation 可审计
   - select_result(): 选中候选对应执行结果; 全失败 → 最后一个失败结果
     (如实返回, 拒绝理由经 last_evaluation 审计, 不静默伪装成功)
   - 异常 Run 结果占位对齐修复 (候选/结果索引一一对应, 选中结果按索引精确回取)
   - AgentRuntime.last_evaluation: Flag 开 → 评估明细审计; Flag 关 → None (旧流程零变化)

⑤ 证据字段 (ExecutionCandidate 扩展, 向后兼容)
   patch_apply_result / scope_result / regression_risk_result /
   requirement_coverage_result — 缺省 {} (None 归一), to_dict/from_dict round-trip 兼容
```

## 评分示例 (可解释性)

```
候选 CAND-2 胜出明细 (score_breakdown):
  validation:         +100  验证通过 (测试/verifier 全绿) — 硬条件满足
  patch_apply:        +50   patch 可应用 (1 文件)
  scope:               0    无修改范围证据 — 中性 0 分 (不臆造)
  regression_risk:     0    无回归风险证据 — 中性保分 0
  requirement_coverage: 0   无需求覆盖证据 — 中性 0 分
  verdict: 验证通过, 合格 — 总分 +150 [validation:+100 | patch_apply:+50 | ...]
全失败示例 rejection_reason:
  "no qualified candidate: 全部 2 个候选验证未通过 — CAND-F1: 候选已失败
   (failure_reason=empty_output)... (最不差 = CAND-F1)"
```

## 测试

```
Unit 50 (test_exec_evaluator.py): 5 层纯函数逐层覆盖 (含边界: 无证据中性/
  计数推断/下限钳制/封顶) / score_candidate 汇总 (总分=5 层和/层序固定/
  qualified=硬门槛/verdict 可解释) / evaluate 决策 (空列表拒绝/全失败拒绝/
  Best 选择/硬门槛胜出/ranking 合格优先/平局层优先/平局 Run 序/确定性重复/
  breakdown 与 ranking 同序/畸形证据容错/JSON 可序列化/证据 round-trip)
Integration 13 (test_exec_evaluator_integration.py): Runner 级多候选评估全明细/
  证据差异化 Best 选择 (选中结果=选中候选对应结果)/平局 Run 序/全失败诚实拒绝/
  未 run 先 evaluate 拒绝/评估零 Provider 调用 (禁 LLM)/Collector→Evaluator 端到端/
  candidate_from_result 产链/Flag 关零评估/Flag 开评估审计/混合选合格/全失败拒绝/
  重复评估确定性
pytest 全量: 5399 passed (5336 + 63 新增)  — Core/Runtime/Desktop diff = 0
```

## Commits

```
ad08625 T5.3 ① CandidateEvaluator 核心 + 证据字段 (Unit 50)
9ef24d2 T5.3 ② select_result 升级正式 Evaluator + 集成接线 (Integration 13)
bef9bd1 T5.3 ③ Completion Report
```

## 文件变化

```
factory-exec/exec/evaluator.py                  (新建: CandidateEvaluator + 5 层评分)
factory-exec/exec/candidate.py                  (扩展: 4 证据字段 + evaluate/last_evaluation/
                                                  select_result 升级 + 结果占位对齐)
factory-exec/exec/agent_runtime.py              (接入: last_evaluation 审计属性)
tests/exec/test_exec_evaluator.py               (新建, Unit 50)
tests/exec/test_exec_evaluator_integration.py   (新建, Integration 13)
docs/validation/sprint5-t53-result-evaluation-report.md (本报告)
```

## 约束遵守

```
✅ 禁 LLM 评分 (纯规则; evaluate 零 Provider 调用有测试强断言)
✅ 禁随机 (确定性测试: 同输入两次评估逐位一致)
✅ Core/Runtime/Desktop = 0 (git diff 验证)
✅ 不跑真实 Benchmark / 不落数据库 / 不删测试 / basename 唯一
✅ 全失败诚实 rejection (不静默; 拒绝理由逐候选可审计)
```

## 下一步建议 (T5.4)

```
1. Capability Registry: 声明式模型能力 (coding/reasoning/stability/cost 分) —
   数据驱动选择 Provider/模型 + runs 数建议 (T5.1 §5, 真实 Benchmark 数据 T5.5 更新)
2. 产线证据接线: 把真实 git apply --check / 修改范围 / Call Graph 影响面 /
   Task Analysis 验收标准逐条对照 写入候选证据字段 (当前 T5.3 已预留, 产线未接)
3. Benchmark V3: 9 样本 × runs N (Feature Flag 开启) — 恢复 Bug Fix ≥60% + 稳定性
```
