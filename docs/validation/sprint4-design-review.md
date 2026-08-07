# Sprint 4 — Context Intelligence Optimization（设计 Review）

> 日期: 2026-08-07 | 状态: Sprint 设计评审, 待确认 (不编码)
> 目标: 从"大量上下文注入" → "精准上下文选择", 恢复并超过 -1 基线 (55.6%)

## 0. Sprint 背景（数据驱动）

```
Sprint 3 (Context Engine v1, b573614):
  Success 33.3% (↓ from 55.6%) | Bug Fix 20% (↓ from 60%)
  Cost $1.3534 (27×) | Latency 328.4s (3.4×)

真实发现:
  1. Context 越多 ≠ 能力越强
  2. 大 prompt → reasoning 消耗暴涨 → max_tokens 耗尽 (4 空响应)
  3. 成本不可接受 (0.19-0.44/样本)
  4. Context Selection > Context Quantity
  5. operation error 依旧 (symbol 锚点, 上下文量无关)
```

## 1. 核心设计（Task 4.1 Context Ranking Engine）

### 从全量 → Top-K

```
Task → Context Analysis → Context Ranking → Top-K Selection
     → Progressive Loading → Developer Agent

ContextCandidate:
  source: file|symbol|test|experience|arch
  type: code|test|history|experience|architecture
  relevance_score: float
  reason: str (可解释)
  token_cost: int
```

### 评分因素（加权）

```
① task keyword match   (关键词命中: 精确/前缀/包含 — 0.35)
② symbol relevance     (任务符号命中: 目标 symbol + 调用链 — 0.25)
③ dependency distance  (依赖距离: 直接依赖 1.0 / 间接 0.5 / 无关 0.1 — 0.15)
④ test relevance       (测试映射命中 — 0.10)
⑤ historical success   (该文件历史成功率 — 0.08)
⑥ experience feedback  (失败模式权重调整 — 0.07)
```

### Top-K 策略

```
K 按预算: 核心 ≤3 文件 (全量或符号段) + 相关 ≤5 (符号索引) 
输出: 排序列表 + reason (可审计/可调优)
```

## 2. Task 4.2 Progressive Context Loading（三阶段）

```
Stage 1 Repository Overview (必载, 轻量 ~1-2K tokens):
  file tree + module + architecture 摘要
  → 决策: 目标文件识别 (关键词 + symbol 匹配)

Stage 2 Symbol Context (按需, ~3-5K tokens):
  目标文件 symbol 索引 + 相关 symbol (callers/callees)
  → 决策: 修改锚点确定 (symbol 或 line_range)

Stage 3 Code Detail (最小, 只载真需要的):
  锚点附近代码段 (函数体/块) — 非全文件
  测试文件 (test_map 相关)

禁止: 一次注入大量源码 (≤30K chars 总输入, 预算硬顶)
每阶段后: 是否足够执行? (quality score ≥ 阈值) → 不足才进下一阶段
```

## 3. Task 4.3 Context Budget Control

### 任务类型动态预算

```
Bug Fix:   重点 code + test (核心文件符号段 + 相关测试)
Feature:   重点 architecture + 相关模块 (模块图 + 多文件符号)
Greenfield: 重点规范 + 模板 (项目约定 + 结构参考)

记录: before_tokens / after_tokens / context_score (每样本)
硬顶: 总输入 ≤30K chars (~7.5K tokens), 输出 max_tokens 32768
```

## 4. Task 4.4 Experience Feedback Integration

```
失败 (symbol miss / empty / verifier):
  → 记录失败模式
  → 下一次: 相关权重上调 (symbol 易错 → 提前 line_range; 文件大 → 符号段)

成功:
  → 保存最佳 Context 组合 (文件/符号/段选择)
  → 同类任务复用

形成: Experience Driven Context Selection (权重随经验演进)
```

## 5. Task 4.5 Benchmark Validation

```
同一 9 样本 (deepseek-v4-flash):
记录: Success Rate / Bug Fix Rate / Feature Rate / Token Cost / Latency / Failure Type
对比: Sprint 3 (33.3%) vs Sprint 4
目标: 最低 ≥55.6% (-1 基线) | 理想 ≥70%
额外对比: 成本必须显著下降 (目标 <$0.30, 对比 $1.35)
```

## 6. 工程约束

```
✅ Extension 内 (factory-exec/exec/context.py 重构 + benchmark)
✅ Core/Runtime/Desktop 零修改 | ✅ pytest 4926 保持
❌ 禁: Multi Agent / Marketplace / MCP / 商业化 / 新增 Organization 模型
✅ 每 Task: 设计 → 编码 → 测试 → (Benchmark 在 4.5 统一)
```

## 7. 实施计划（每 Task commit）

```
T4.1: Context Ranking Engine (候选/评分/Top-K) + 测试 ≥20
T4.2: Progressive Loading (3 阶段 + 阶段决策) + 测试 ≥15
T4.3: Budget Control (任务类型预算 + 记录) + 测试 ≥10
T4.4: Experience Feedback (权重演进 + 最佳组合) + 测试 ≥10
T4.5: Benchmark 重跑 + sprint-4-context-intelligence-report.md + 对比
```

## 8. 关键成功标准

```
1. 成功率 ≥55.6% (回基线) / 理想 ≥70%
2. 成本 ≤$0.30 (对比 $1.35, -78%)
3. 空响应 (max_tokens) 显著下降 (4 → ≤1)
4. operation error 下降 (2 → ≤1, line_range 兜底)
5. context_score 记录完整
```

## 9. 风险

```
1. Top-K 选错文件 → 成功率反降 → 评分权重需 Benchmark 调优
2. 渐进加载延迟 → 阶段决策阈值调优
3. 经验反馈过拟合 → 权重上限保护 (单因素 ≤0.5)
```

## 10. 结论

```
Sprint 4 设计: Ranking (Top-K) + Progressive (3 阶段) + Budget (任务类型) + Experience (权重)
核心转变: Context Selection > Context Quantity
等待确认后开始 T4.1
```
