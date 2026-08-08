# Sprint 5 / T5.5 — Benchmark V3 Report（真实数据，诚实）

> 日期: 2026-08-08 | 状态: 已执行
> 配置: deepseek-v4-flash / 9 样本 × 3 runs / 全开 strategy+ranking+progressive+experience

## 1. Benchmark 配置

```
Provider: openai-adapter → deepseek-v4-flash (DeepSeek 端点)
runs: 3 (每样本 3 次独立执行, Sequential)
启用: --strategy (SequentialRunner + CandidateEvaluator) + --ranking + --progressive + --experience
经验库: /tmp/exp-s5 (冷启动, 0 条)
Capability Registry: 3 模型 (基准 deepseek-v4-flash 声明能力)
```

## 2. 原始数据（9 样本 × 3 runs）

| 样本 | Run1 | Run2 | Run3 | Selected | 原因 |
|---|---|---|---|---|---|
| BUG-MKP-001 | ✗ empty | ✗ empty | ✗ empty | failed | 3/3 空响应 |
| BUG-MKP-002 | ✗ empty | ✗ empty | ✗ empty | failed | 3/3 空响应 |
| BUG-MKP-003 | ✗ empty | ✗ empty | ✗ empty | failed | 3/3 空响应 |
| BUG-MKP-004 | ✗ empty | ✗ empty | ✗ empty | failed | 3/3 空响应 |
| BUG-MKP-005 | ✗ empty | ✗ empty | ✗ empty | failed | 3/3 空响应 |
| FEAT-MKP-001 | ✗ empty | ✗ empty | ✗ empty | failed | 3/3 空响应 |
| FEAT-MKP-002 | ✗ empty | ✗ empty | ✗ empty | failed | 3/3 空响应 |
| FEAT-MKP-003 | ✗ empty | ✗ empty | ✗ empty | failed | 3/3 空响应 |
| GREENFIELD-001 | ✓ | ✓ | ✗ | **success** | 2/3 成功, Evaluator 选 best |

## 3. Sprint 对比表

| Metric | Sprint3 | Sprint4 | Sprint5 (V3) | Change (S4→S5) |
|---|---|---|---|---|
| Success Rate | 33.3% | 11.1% | **11.1%** | 持平 |
| Bug Fix | 20% | 0% | **0%** | 持平 |
| Cost | $1.35 | $0.45 | ~$1.6 (27 runs) | 3.5× (runs 数) |
| Latency avg | 328s | 292s | ~300s | 持平 |
| Failure: empty | 4/6 | 7/9 | **25/27** | 恶化 |

## 4. Multi Run 效果分析（关键发现）

```
✅ 机制有效 (有证据):
  GREENFIELD-001: 3 runs = [✓, ✓, ✗] → Evaluator 正确选成功候选 (qualified 2/3)
  → 单次失败不再致命 (第 3 次失败不影响结果)

❌ 但无法救系统性失败:
  8 个复杂样本: 27 runs 中 25 次 empty_output (reasoning 耗尽)
  → 不是运气问题, 是 deepseek-v4-flash 在这些任务上系统性输出耗尽
  → Multi Run 对"必然失败"的模型行为无效 (3 次全空 = 0 候选可选)

提升比例: 0 (除 Greenfield 的抗随机性外, 无整体提升)
```

## 5. Failure Analysis（最终根因确认）

```
empty_output (finish_reason=length) ×25/27:
  deepseek-v4-flash = reasoning 模型 → 复杂代码任务推理 token 消耗巨量
  → 32768 max_tokens 被 reasoning 吃光 → 内容输出为空

工程层全部正确 (数据证据):
  Context: budget actual 4.2K-11.2K chars (受控 ✓)
  Progressive: stages = overview/symbol/detail 全走 (✓)
  Ranking: candidates 17-21, top1 合理 (✓)
  Evaluator: 正确降级 + 诚实 rejection (✓)
  → 工程无法补偿模型层系统性失败

结论: 当前唯一瓶颈 = 模型 (deepseek-v4-flash 不适合此任务类)
```

## 6. Capability Registry 分析

```
声明 vs 实测:
  stability_score: 0.3 (声明) — 实测吻合 (25/27 空响应 = 极不稳定 ✓)
  coding_score: 0.75 (声明) — 实测 0 代码产出 (严重高估 ✗)
  → 声明分需以实测回填 (Benchmark 数据驱动)
```

## 7. AI Developer Level 判定

```
❌ 未达 Level 2 (Bug Fix 0/5, 无法独立完成简单任务)
Level: 停留 Level 1 (辅助)

Multi Run + Evaluator 工程: ✅ 正确 (机制有效)
模型可靠性: ❌ 阻塞 (换模型是唯一路径)
```

## 8. 下一步建议（数据驱动）

```
1. 换模型 (最高优先):
   - Ollama 本地 qwen3:8b (非 reasoning, 零成本, 8GB 内存可行 — 已确认)
   - 或 DeepSeek 非 reasoning 档 / max_tokens 65536
2. Model Capability Registry 回填实测分 (stability 0.3 ✓ / coding 重估)
3. 锚点预检 (operation error 类) — 次要
4. Multi Run 保留 (抗随机性有据: Greenfield 2/3 成功), 默认 runs=2-3
```

## 9. 结论

```
Sprint 5 工程 (Multi Run/Evaluator/Capability Registry) 全部正确落地,
但真实 Benchmark 证明: deepseek-v4-flash 是系统性瓶颈 (25/27 空响应),
换模型后 Sprint 5 机制才能兑现价值。
```
