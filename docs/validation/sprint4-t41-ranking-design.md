# Sprint 4 / T4.1 — Context Ranking Engine Design Review

> 日期: 2026-08-07 | 状态: 设计评审, 待确认 (不编码)
> 背景: Sprint 3 Context Engine v1 真实 Benchmark 33.3% (成本 27×) — 上下文过量/无优先级
> 目标: Ranking (Top-K) + Progressive Loading 替代全量注入

## 1. 当前 Context 架构分析

### 现有组件连接

```
Task → context.py (Sprint 3):
  Selector: 关键词 → symbol 匹配 → 文件选择 → 测试 → 经验
  Budget:   核心 ≤3000 行全量 + 相关符号索引 + 经验
  Quality:  completeness 评分 (四维)
  → developer.py 6 节 prompt

依赖:
  repo_index.py (文件树/语言/symbol/importance)
  repo_intelligence.py (Module/Dependency/CallGraph/TestMap/Architecture)
  experience.py (ExperienceRecord)
```

### 保持不变（复用）

```
✅ repo_index / repo_intelligence (候选生成的数据源)
✅ experience.py (ExperienceRecord 查询)
✅ developer.py 输出协议 (<operations>/<patch>)
✅ agent_runtime 失败安全接入模式
```

### 新增（T4.1）

```
🆕 ContextCandidate 模型 + RankingEngine + TopKSelector
🆕 Task Analyzer (结构化任务解析)
🆕 Feature Extractor (评分特征)
🆕 context.py Selector 重构 → 走 Ranking Pipeline (替换全量选择)
```

## 2. ContextCandidate 数据模型

```python
class ContextCandidate(Pydantic):
    id: str                    # 唯一 (file:symbol / test:xxx / exp:xxx)
    type: str                  # code|test|history|experience|architecture
    source: str                # 来源路径/引用
    content_ref: str           # 内容引用 (文件路径 + 段/行范围) — 不预载全文
    token_cost: int            # 预估 token
    relevance_score: float     # 0-1 评分
    reason: str                # 可解释理由 (评分明细)
    confidence: float          # 置信度 (特征完整性)

可审计保证:
  - 每候选带 reason (各因素得分明细, 可复算)
  - 评分纯规则 (无 LLM 自评, 无黑盒)
  - content_ref 延迟加载 (候选列表先于内容, 审计只列引用)
  - 全流程事件记录 (context.candidate_scored → org 事件)
```

## 3. Ranking Pipeline

```
Task Input (自然语言)
  ↓
① Task Analyzer: 结构化任务 (目标/类型/关键词/符号候选/验收) — 规则解析 (camelCase/snake 拆分, 已有基础)
  ↓
② Candidate Generator: 从数据源生成候选:
     symbol 命中文件 (repo_index.symbols_by_name)
     依赖影响面 (repo_intelligence.dependents)
     同模块文件 (ModuleIntelligence.related_files)
     测试映射 (TestMapper)
     历史经验 (ExperienceStore 查询)
     架构摘要 (ArchitectureSummarizer)
  ↓
③ Feature Extractor: 每候选提取 6 维特征 (§4)
  ↓
④ Ranking Score: 加权求和 → relevance_score + reason
  ↓
⑤ Top-K Selector: 按预算取 Top-K (核心/相关分级)
  ↓
⑥ Context Assembly: 延迟加载 content_ref → 组装 prompt (3 阶段渐进 — T4.2)
```

**每步职责**: ① 理解任务 / ② 收集可能相关 / ③ 量化特征 / ④ 评分排序 / ⑤ 预算截断 / ⑥ 组装交付

## 4. Ranking Algorithm v1（规则模型, 禁 ML/LLM 自评）

```
score = 0.35·keyword_match + 0.25·symbol_relation + 0.15·dependency_distance
      + 0.10·test_relation + 0.08·history_success + 0.07·experience_match
```

### 计算方式

```
keyword_match:  任务关键词命中 (精确 1.0 / 前缀 0.8 / 包含 0.6 / 无 0) — 文件路径+符号名+内容头
symbol_relation: 候选含任务 symbol (定义 1.0 / 调用 0.7 / 被调 0.5 / 无关 0)
dependency_distance: 直接依赖 1.0 / 间接 0.5 / 无关 0.1 (repo_intelligence 图)
test_relation:   候选是目标测试 1.0 / 相关测试 0.6 / 无 0 (TestMap)
history_success: 文件历史任务成功率 (经验库聚合, 冷启动 0.5 中性)
experience_match: 历史失败模式匹配 (symbol miss 相关文件 +0.2 — 经验反馈, 首轮 0)
```

### 测试方式

```
纯函数可测: 输入特征向量 → 断言分数精确
边界: 全零 → 0; 全满分 → 1.0; 权重超限保护 (≤上限)
Gold 集: 3 个已知样本的期望 Top-K (人工标注) → 回归
```

## 5. Token Budget Strategy（按任务类型）

```
Bug Fix:   最大 20K chars; 优先 code+test (核心符号段 + 相关测试)
Feature:   最大 25K chars; 优先 architecture+相关模块 (模块图 + 多文件符号)
Greenfield: 最大 15K chars; 优先规范+模板 (项目约定 + 结构参考)

降级策略 (超限):
  1. 相关文件符号索引 → 移除正文段
  2. 经验 → 摘要化
  3. 架构 → 单行摘要
  4. 仍超 → 标记 context_overflow + context_score 降级 (执行前警示)

硬顶: 总输入 ≤30K chars (≈7.5K tokens); max_tokens 32768 (输出)
```

## 6. Failure Handling

```
symbol 未找到: → line_range 兜底 (自动降级行号, operation error 修复)
              → 记录 failure_reason=symbol_miss + 权重上调 (下次提前 line_range)
context 不足:  → quality score < 阈值 → 扩大候选 1 轮 (同模块+影响面提升)
              → 仍不足 → 标记 low_confidence 执行 (警示) + 记录
context 过多:  → 降级链 (§5) → 仍超 → context_overflow 标记 + 记录
token 超限:    → finish_reason=length 检测 → 重试 1 次 (提示精简输出)
              → 仍超 → 记录 max_tokens_exhausted (经验: 该任务类型预算上调)

全部失败 → ExperienceRecord (失败模式 + 建议) — 不可静默
```

## 7. Experience Integration

```
已有 ExperienceRecord 影响 Ranking:
  第一阶段: 只影响 score (history_success + experience_match 两维)
  禁止: 自动修改核心逻辑/权重结构

实现:
  experience_advice(task_type) → {file_success_rates, failure_patterns}
  → 候选评分加权 (±0.2 上限)
  → symbol_miss 历史 → 该文件候选提权 + 提前 line_range 提示
```

## 8. Testing Plan

```
Unit (≥20):
  - Candidate 模型/校验/审计 (reason 可复算)
  - 各因素评分纯函数 (边界/权重)
  - Top-K 选择 (预算截断/排序)
  - Task Analyzer (关键词/类型解析)

Integration (≥15):
  - Pipeline 全链 (Task → 候选 → 评分 → Top-K → 组装)
  - 降级链 (超限各层)
  - 失败处理 (symbol miss → line_range; 空 → 重试)
  - 经验权重影响

Benchmark (T4.5 统一):
  9 样本回归, 指标:
    Success Rate / Bug Fix Rate / Feature Rate / Cost / Latency / Context Efficiency
  Context Efficiency = 输入 tokens / 成功率 (目标: 显著优于 Sprint 3)
```

## 工程约束

```
✅ Core/Runtime/Desktop 修改 = 0 (Extension: factory-exec/exec/context.py 重构)
❌ 禁 Multi Agent / MCP / Skill Marketplace / 商业功能
✅ 每 Task: 设计 → 编码 → 测试 → commit
```

## 验收（T4.1 单独）

```
1. RankingEngine 纯函数全绿 (Unit ≥20)
2. context.py Selector 接入 Ranking (全量选择 → Top-K) — 旧路径兼容
3. 测试 ≥35 新增, pytest 4926+ 全绿
4. Core/Runtime/Desktop diff = 0
```

## 结论

```
T4.1 设计冻结: ContextCandidate + Ranking Pipeline + 规则评分 + Top-K + 预算分级 + 失败兜底
替换全量注入 → 精准选择; 保留审计 (reason 可复算)
等待确认后编码
```
