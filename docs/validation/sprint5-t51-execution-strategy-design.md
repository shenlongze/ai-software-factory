# Sprint 5 / T5.1 — Execution Strategy Design Review

> 日期: 2026-08-07 | 状态: 设计评审, 待确认 (不编码)
> 背景: Sprint 4 结论 — Context 工程有效 (成本 -67%), 瓶颈是 LLM Executor Reliability (55.6→33.3→11.1 波动)
> 目标: 从"一次 LLM 调用决定结果" → "多策略执行 + 验证 + 选择" (不提高 Prompt 复杂度)

## 1. 当前 Developer Agent 执行流程分析

### 当前流程

```
Task → Context (Ranking/Progressive/Budget) → LLM (单次调用)
  → Patch → Validation → Result
```

### 问题定位（真实数据驱动）

```
① 单次执行波动大: 同模型同任务 55.6%→33.3%→11.1% (randomness 主导)
② finish_reason=length (7/9): reasoning 模型单次生成耗尽 → 空响应
   → 重试 1 次仍可能耗尽 → 任务失败
③ operation error: 文件/symbol 定位失败 → 单次路径无替代
④ 无候选比较: 一次失败 = 整个任务失败 (无 second opinion)

结论: 问题不在"如何问" (Context 已精准), 在"一次就中" 的假设
```

## 2. Multi Run Execution

### 设计

```
Task
 ↓
Run A ──┐
Run B ──┼→ Candidate Results → Evaluator → Best Result
Run C ──┘

不复制 Agent: 同一 Agent/Context, 多次执行 (不同随机种子/温度/重试语义)
```

### 执行参数

```
Runs: N 次独立执行 (默认 3, 可配)
每次 Run: 同一 Task + Context (可微变: 重试提示/温度), 独立 Provider 调用
产出: N 个 ExecutionCandidate
Evaluator: 选 Best (T5.3)
```

### 价值

```
- 抗随机性: 单次失败不再致命 (3 次至少 1 次成功概率大幅提升)
- 空响应自愈: 某次 reasoning 耗尽 → 其他次成功
- 质量比较: 多个 patch 选最优 (验证通过 + 质量分最高)
- 成本可控: N=3 成本 ×3, 但成功率提升的边际收益 >> 成本 (对比空响应浪费)
```

## 3. Candidate Result 数据模型

```python
class ExecutionCandidate(Pydantic):
    run_id: str                # 第几次执行
    patch: str                 # 生成 patch
    provider: str              # openai|anthropic
    model: str                 # deepseek-v4-flash 等
    context_trace: dict        # ranking/progressive/budget trace (Sprint 4)
    token_usage: dict          # prompt/completion/cost
    validation_result: dict    # 语法/测试/verifier 结果
    quality_score: float       # 0-100 (pq 启发式 + 人工)
    failure_reason: str | None # 空响应/operation error/验证失败
    timestamp: str
```

```
可审计: 每候选完整记录 (来源/上下文/成本/结果)
用于: Evaluator 评分 + Experience 入库
```

## 4. Result Ranking 设计

### 评价规则（优先级）

```
① Validation Pass (测试通过 — 硬条件, 最高优先)
② Patch Apply Success (patch 可应用)
③ 修改范围 (最小性: 只改必要文件)
④ 回归风险 (影响面小优先 — Call Graph 影响范围)
⑤ 用户目标覆盖 (验收标准逐条对照)

评分: 优先级加权 (通过测试者直接胜出; 同通过 → 质量分 + 范围 + 风险)
```

### 输出

```
BestCandidate: 最优候选 + 评分明细 (为什么选它, 可审计)
```

## 5. Model Capability Profile

### 声明式能力记录

```yaml
provider/model:
  deepseek-v4-flash:
    coding_score: 0.6      # 代码修改能力
    reasoning_score: 0.8   # 推理能力 (高但耗 token)
    stability_score: 0.3   # 长任务稳定性 (reasoning 耗尽风险)
    cost_score: 0.9        # 成本 (便宜)
    max_output_tokens: 32768
  deepseek-v4-pro:
    coding_score: 0.7
    reasoning_score: 0.9
    stability_score: 0.5
    cost_score: 0.7
    max_output_tokens: 32768
  (future: claude/gpt4o/local)
```

```
用途:
  未来自动选择 Provider (任务类型 × 能力匹配)
  当前: 诊断 (解释为什么 7/9 空响应 — stability 低)
  数据来源: 真实 Benchmark 累积 (T5.5 更新)
```

## 6. Failure Experience Integration

```
每次 Run 结果 (成功/失败) → ExperienceRecord (T4.4 已有):
  失败: failure_reason (reasoning_exhausted/operation_error/verifier_failed)
        + context_trace + token/cost
  成功: 最佳 patch + 有效 context 组合

影响下一次任务:
  - 候选数量建议 (该任务类型失败率高 → runs 提升)
  - Provider/模型选择 (Capability Profile 数据驱动)
  - max_tokens 建议 (reasoning 耗尽历史 → 提升/换模型)

失败必须入库 — 不可静默
```

## 7. 工程约束

```
✅ Extension 内 (factory-exec) | ✅ Core/Runtime/Desktop = 0
✅ 旧流程兼容 (Multi Run 默认关闭, Feature Flag 控制)
❌ 禁 Multi Agent / Department / Marketplace / Domain Expert
❌ 禁大范围重构 / 不必要依赖
✅ 每 Task: Design → 确认 → 实现 → 测试 → commit → push → report
```

## 8. 测试计划（T5.2-T5.5 汇总）

```
T5.2 Unit+Integration: ExecutionCandidate/Run/Collector (默认关, 旧流程不变)
T5.3 Unit: CandidateEvaluator 优先级规则/Best 选择
T5.4 Unit: Capability Registry 声明式加载/查询
T5.5 Benchmark V3: 9 样本 × runs N — 恢复 Bug Fix ≥60% + 连续运行稳定性
```

## 9. 结论

```
T5.1 设计冻结: Multi Run (N 次独立) + Candidate 模型 + Evaluator 优先级
  + Model Capability Profile + Failure Experience
核心转变: 单次执行 → 多策略执行 + 选择 (抗随机性, 不依赖单次运气)
等待确认后进入 T5.2
```
