# Sprint 4 / T4.2 — Progressive Loading Engine Design Review

> 日期: 2026-08-07 | 状态: 设计评审, 待确认 (不编码)
> 背景: T4.1 Ranking 完成 (Top-K 选择); T4.2 渐进加载 (避免一次注入大量 Context)
> 目标: Stage 1 Overview → Stage 2 Symbol → Stage 3 Code Detail, 总 ≤30K chars

## 1. 当前 Context Assembly 如何接入 Progressive Loading

### 组件关系

```
Task
 ↓
RankingEngine (T4.1: 候选评分 Top-K)
 ↓
TopKSelector (核心 3 + 相关 5)
 ↓
BudgetController (任务类型预算 + 降级链)
 ↓
【T4.2 新增】ProgressiveLoader
 ↓
ContextLoader (内容加载, 延迟)
 ↓
Developer Agent

关系:
  RankingEngine: 决定"哪些候选" (不加载内容)
  TopKSelector:  决定"取几个" (预算截断)
  BudgetController: 决定"总量上限" (任务类型)
  ProgressiveLoader: 决定"先加载哪部分" (阶段决策) ← T4.2 新增
  ContextLoader: 决定"如何加载" (content_ref → 实际内容, 延迟)
```

### 接入点

```
context.py ranking_assemble() (T4.1) 内部:
  Ranking → TopK → Budget 后, 不再一次性加载全部 Top-K 内容
  → 交给 ProgressiveLoader: 按阶段加载, 每阶段后决策
新类: ProgressiveLoader + StageDecision (纯规则, 无 LLM 扩展)
```

## 2. Progressive Loading Pipeline（3 阶段）

### Stage 1: Overview Context（必载, 轻量）

```
内容: 文件结构 (file tree) + 模块 (ModuleIntelligence) + Architecture Summary
tokens: ~1-2K
进入条件: 总是 (任务起始)
产出: 目标文件候选确认 + 修改点初步定位
```

### Stage 2: Symbol Context（按需）

```
内容: 目标文件 Symbol 索引 + Call Graph (callers/callees) + Test 关系 (test_map)
tokens: ~3-5K
进入条件: Stage 1 已定位候选文件 → 需要精确修改点
产出: 锚点确认 (symbol 或 line_range) + 影响面
```

### Stage 3: Code Detail（最小）

```
内容: 锚点附近代码片段 (函数体/块, 非全文件) + 相关测试代码
tokens: 按预算剩余 (≤30K 总顶)
进入条件: 修改点确定 → 需要精确代码执行修改
产出: 完整可执行上下文
```

### 每阶段进入条件（纯规则）

```
Stage 1 → 2: 候选文件已识别 (Top-K 非空)
Stage 2 → 3: symbol/锚点已确定 (或 line_range 兜底)
Stage 3: 预算允许且锚点确定 → 加载最终代码
不再深入: 预算耗尽 / 锚点无法确定 (转 failure handling) / 任务类型不需要
```

## 3. Context Expansion Decision

### 何时进入下一阶段（依据）

```
① confidence: 当前阶段 confidence < 阈值 (0.6) → 需要更多信息 → 下一阶段
② task type:  Bug Fix 需 Stage 3 (代码); Greenfield 可能只需 Stage 1+3 (规范+骨架)
③ validation feedback: 执行验证失败 → 需补充上下文 (回 Stage 2 重新定位)
④ missing information: symbol miss / 文件未定位 → 扩大范围 1 轮

禁止: LLM 无限扩展
规则: 每阶段至多 1 次回退; 扩展计数 ≤3; 超限 → 标记 low_confidence 执行
```

## 4. Token Budget（每阶段）

```
总顶: ≤30K chars (≈7.5K tokens)
Stage 1: 1-2K chars (固定, 必载)
Stage 2: 3-5K chars (符号索引级)
Stage 3: 预算剩余 (锚点片段 + 测试)

overflow handling:
  - Stage 3 代码片段超限 → 截断至锚点核心 (函数签名 + 关键行)
  - 仍超 → 标记 context_overflow → 执行前警示 + 记录

degrade strategy (复用 T4.1 降级链):
  正文 → 符号索引 → 单行摘要 → 丢弃最低分相关 → overflow 标记
```

## 5. Audit Trace

```
每次加载记录 (ProgressiveTrace):
  stage: 1|2|3
  loaded_items: [content_ref...]
  reason: 进入该阶段的依据
  token_cost: 本阶段消耗
  decision: continue|stop|fallback
  final_usage: 总消耗 (before/after)

用途:
  - Experience Learning: 成功任务的阶段路径保存 (最佳组合复用)
  - 失败任务: 哪阶段缺信息 (经验权重调整)
  - 审计: 全程可追溯 (加载了什么/为什么/花多少)
```

## 6. Failure Handling

```
Stage 1 无法定位: 候选文件为空 → 扩大关键词 1 轮 → 仍空 → 标记 unable_to_locate (经验记录, 建议人工)
symbol miss:     → line_range 兜底 (已有) + 记录 symbol_miss (权重上调)
code too large:  → 符号索引 + 锚点片段 (不全文) + 记录 large_file
token exceeded:  → 降级链 + context_overflow 标记 + 重试 1 次 (精简指令)
全部失败 → ExperienceRecord (失败模式 + 建议) — 不可静默
```

## 7. Agent 通用化（Context Loading 不绑定 Developer）

```
ProgressiveLoader 设计为通用:
  输入: TaskProfile + 候选列表 + 预算 (与 Agent 类型无关)
  阶段: Overview/Symbol/Detail 语义化 (不依赖代码语言)

未来:
  Product Agent:  Stage 1 市场/需求概览 → Stage 2 竞品 Symbol → Stage 3 文档细节
  Finance Agent:  Stage 1 报表概览 → Stage 2 指标 → Stage 3 明细
  Medical Agent:  Stage 1 病历概览 → Stage 2 检查项 → Stage 3 明细
  Skill/MCP:      加载策略声明 (stage 配置), 引擎不变

实现: 阶段定义 = 配置 (声明式), 引擎 = 通用循环
```

## 8. Testing Plan

```
Unit (≥15):
  - Stage 决策纯函数 (进入条件/回退计数)
  - 预算分配 (每阶段上限/overflow)
  - ProgressiveTrace 记录 (审计字段)
  - Failure handling 各分支

Integration (≥12):
  - Pipeline 全链 (Ranking→TopK→Progressive 3 阶段)
  - 阶段决策 (confidence 触发下一阶段)
  - 回退 (Stage 3 验证失败 → Stage 2)
  - 通用化 (非代码任务配置)

Benchmark (T4.5 统一, 9 样本):
  指标:
    Context Efficiency = 输入 tokens / 成功率 (对比 Sprint 3)
    Waste Rate = 未使用 tokens / 总输入 (目标下降)
    Success Rate (目标 ≥55.6%, 理想 ≥70%)
```

## 工程约束

```
✅ Core/Runtime/Desktop = 0 修改 (factory-exec Extension)
❌ 禁 Multi Agent / MCP / Skill Marketplace / 商业功能
✅ 旧路径兼容 (ranking_assemble 逐位不动, Progressive 为新阶段开关)
```

## 验收（T4.2 单独）

```
1. ProgressiveLoader + StageDecision 全绿 (Unit ≥15 + Integration ≥12)
2. ranking_assemble 接入 Progressive (开关控制, 默认开启渐进但旧路径可回退)
3. pytest 5070+ 全绿 | Core/Runtime/Desktop diff = 0
4. 审计 Trace 完整 (加载/理由/成本/决策)
```

## 结论

```
T4.2 设计冻结: 3 阶段渐进 + 决策规则 + 预算分级 + 审计 Trace + 失败兜底 + Agent 通用化
避免一次注入大量 Context (Sprint 3 教训)
等待确认后编码
```
