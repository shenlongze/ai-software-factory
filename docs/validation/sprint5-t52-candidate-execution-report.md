# Sprint 5 / T5.2 — Candidate Execution Engine（Completion Report）

> 日期: 2026-08-08 | 状态: 完成
> 目标: 单次 LLM 执行 → 多 Candidate 流程 (抗随机性, 不复制 Agent)

## 完成内容

```
① ExecutionCandidate (16 字段): id/task_id/run_id/provider/model/context_trace/
   budget_trace/generated_output/patch/token_usage/latency/validation_result/
   quality_score/failure_reason/created_at
   - 可序列化 (to_dict↔from_dict) + to_experience_signals (成功 candidate_success /
     失败映射 experience_ctx 五类: empty_output→token_overflow, token_limit, operation_error, validation_failed, other)
② ExecutionRun 状态机: pending→running→success|failed (非法迁移拒绝, 8 条非法路径全测)
③ CandidateCollector: 多 Run 收集; 失败候选 failure_reason 必填 (禁静默丢弃)
④ SequentialRunner: N=3 默认, 单线程顺序 (禁并发); 每 Run 独立 Provider 调用 + 独立沙箱;
   异常→失败候选 (不中断收集)
⑤ Feature Flag: execution_strategy_enabled=False 默认 — 旧流程逐位不变
   (execute 派发 _execute_legacy); 开 → 策略路径 (异常失败安全回退旧流程)
⑥ Experience Integration: 每 Candidate → Experience Signal (成功/五类失败)
```

## 测试

```
Unit 63: 模型/序列化/状态机全非法迁移/Collector/信号映射/失败归类/Runner
Integration 13: 关=单次单事件零候选强断言 / 开=N=3 独立调用 / 失败必存混合收集
  / 全失败如实返回 / 单线程 / 每 Run 事件链与落库 / 回退零破坏
pytest 全量: 5336 passed (5260 + 76)
```

## Commits

```
b037297 T5.2 ① Candidate Execution Engine 核心 (Unit 63)
4e8edd1 T5.2 ②③ Feature Flag 接入 + Integration 13
```

## 文件变化

```
factory-exec/exec/candidate.py          (新建: Candidate/Run/Collector/SequentialRunner)
factory-exec/exec/agent_runtime.py      (接入: execution_strategy_enabled 开关 + 策略/旧流程派发)
tests/exec/test_exec_candidate.py       (新建, Unit)
tests/exec/test_exec_candidate_strategy.py (新建, Integration)
```

## 下一步建议 (T5.3)

```
1. CandidateEvaluator: Validation Pass > Patch Apply > 范围 > 风险 > 目标 (T5.1 §4)
2. select_result() 临时选择 → 正式 Evaluator
3. Benchmark V3: 9 样本 × runs N (Feature Flag 开启) — 恢复 Bug Fix ≥60% + 稳定性
```
