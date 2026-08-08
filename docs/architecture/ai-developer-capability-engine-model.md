# AI Developer Capability Engine Model

> 状态: DESIGN ONLY (蓝图, 未实现或部分实现 — 见 ../audit/architecture-reality-audit.md)

> 日期: 2026-08-07 | 状态: 架构评审 (Phase A++++++-2, 不编码)
> 背景: Stage 1 真实 Benchmark 22.2% → 55.6% (Bug Fix 20% → 60%) — 方向正确, 需能力升级
> 目标: Developer Agent 从"代码修改工具" → "Software Engineer AI Employee"
> 约束: Core/Runtime 冻结; 不引入行业模型; 不扩展商业化

## 0. 核心命题

```
Stage 1 证明工程链路正确 (Execution/Sandbox/Operation/Validation)
Stage 2 升级认知能力: Repository Intelligence + Context Engine + Self Review + Experience 驱动
→ 为未来 AI Software Department 打基础
```

---

## 1. Repository Intelligence（AI 如何理解陌生项目）

### 分层理解模型

```
L1 File Structure   文件树/路径/语言/大小 (已有 indexer)
L2 Module           目录 → 模块 → 职责 (模块级语义)
L3 Dependency       import/依赖关系 (模块间依赖图)
L4 Symbol          函数/类/方法 + 行号 + 块范围 (已有 symbol_scan)
L5 Call Relationship 调用链 (谁调用谁 — 影响面分析)
L6 Test Mapping     测试 ↔ 被测代码 (修改后跑哪些测试)
L7 Architecture Context 分层/模式/约定 (入口/核心/外围)
```

### 实现分层（按价值）

```
Stage 2 MVP (本次):
  L5 Call Graph: 符号级调用关系 (正则+启发式, 多语言)
  L6 Test Map:   测试文件 ↔ 源文件 (命名约定 + 引用扫描)
  L7 Architecture: 入口识别 (main/run/app) + 目录职责摘要 (package/__init__/结构)

Stage 3 (后续): 完整依赖图 (静态分析工具按语言)
不实现: 语义理解 (LLM 自身承担)
```

### Repository Intelligence 的用途

```
Context 组装: 只选相关文件 (调用链涉及 + 测试相关)
影响面分析: 修改 A → 影响 B/C (Self Review 依据)
验证选择: 改哪个文件 → 跑哪个测试
```

---

## 2. Context Assembly Engine（用户只说目标）

### 自动上下文构建

```
Task (自然语言目标)
  → Requirement Context   (任务目标 + 验收标准 — 样本自带)
  → Code Context          (相关源文件: 调用链文件 + 行号 + symbol — Stage 1 已有)
  → Architecture Context  (模块结构 + 入口 + 目录职责 — Repository Intelligence)
  → History Context       (目标文件修改历史 git log)
  → Experience Context    (同类任务历史经验 — ExperienceStore 10A-4)
  → Test Context          (相关测试: test_map 选择)
  → AI Native Context     (组装为结构化 prompt, token 预算分配)
```

### 组装策略

```
Token 预算分级:
  核心文件 (直接修改目标): 全量 ≤3000 行
  相关文件 (调用链/引用): symbol 索引 + 关键段
  架构/历史/经验: 摘要 (压缩)
预算分配: 核心 60% / 相关 30% / 上下文 10%
```

### 目标

```
用户只描述目标 ("修这个 bug"/"加个功能") — 系统自动构建完整上下文
不需要: Prompt Engineering / 文件路径指定 / 提示词技巧
```

---

## 3. Self Review Capability（禁止一次生成结束）

### 流程

```
Developer Agent 产出 (Operation + Patch)
  → Reviewer Agent (独立自审角色 — 同一 LLM 的第二轮 prompt, 非独立进程)
  → Validation (语法/相关测试)
  → Correction (发现问题 → 修复指令 → 重执行)
  → 最终 Report

Reviewer 检查项:
  - 需求覆盖 (验收标准逐条对照)
  - 修改正确性 (逻辑/边界)
  - 影响面 (调用链是否有遗漏破坏)
  - 代码质量 (规范/最小性)
  - 测试完整性 (是否补了测试)
```

### 多 Agent 边界

```
Stage 2: Self Review = 同一 LLM 的第二轮评审 prompt (轻量, 无进程开销)
Stage 3: 独立 Reviewer Agent (执行权 != 审核权 强化 — 未来)
本阶段不引入独立 Reviewer 进程 (Stage 1 裁决保持)
```

### Correction 循环

```
Review 发现问题 → Correction 指令 → 重新执行 ≤2 轮 (与 Validation Loop 复用)
禁止无限循环
```

---

## 4. Experience Driven Improvement

### Execution Experience → 决策影响

```
ExperienceRecord (结构化失败原因):
  provider_error / max_tokens / symbol_miss / verifier_failed / operation_error

→ Provider 选择: 同类任务成功率高的 Provider 优先 (10A-3 已有)
→ Prompt 策略: 失败模式预调 (超长文件 → 分块; symbol 易错 → 行号优先)
→ Context 加载: 相关文件命中率学习 (哪些文件常被需要)
→ Validation 流程: 历史失败验证类型优先跑
```

### 实施

```
ExperienceStore 查询 → Task 匹配 (task_type + capability) → 返回:
  - 历史成功率
  - 常见失败模式 + 建议参数
  - 相关经验样本 (供 context 注入)

复盘循环 (已有): Benchmark 失败 → 归类 → 参数/策略调整 → 重测
```

---

## 5. Capability Measurement（AI Developer Level）

### Level 定义

```
Level 1 辅助开发 (Assist):
  人主导, AI 辅助 (生成片段/解释/搜索)
  特征: 需要人工全程指导, 产出入需大改

Level 2 独立完成简单任务 (Independent):
  常见任务无人工干预 (小 bug/小功能)
  特征: Benchmark 达标 (Bug Fix 通过), 人工介入 <30%

Level 3 生产级软件工程师 (Production):
  复杂任务可靠交付 (多文件/重构/跨模块)
  特征: Bug Fix ≥90%, Feature ≥80%, 回归保护, 成本可控
```

### 测量体系

```
客观: Benchmark V2 (Success/Intervention/Cost/Latency/Quality/Regression)
主观: 人工评分 (产出质量/报告质量)
追踪: 每 Benchmark 运行 → Level 判定 → 演进记录
```

### 当前状态（诚实）

```
Developer Agent = Level 1 → Level 2 过渡 (Bug Fix 60%, 简单任务接近独立)
Stage 2 目标: 稳定 Level 2 (Benchmark 达标)
Stage 3 目标: 冲击 Level 3
```

---

## 6. 数据模型提案（新增, 不重复）

```python
class CallGraphNode(Pydantic):     # L5 (symbol/文件/被谁调用/调用谁)
class TestMapEntry(Pydantic):      # L6 (test_file ↔ source_file)
class ArchitectureSummary(Pydantic): # L7 (entry/modules/duties)
class ReviewResult(Pydantic):      # §3 (checks/passed/failed/comments)
class ExperienceAdvice(Pydantic):  # §4 (task_type/success_rate/failure_patterns/params)
```

## 7. 边界

```
✅ Core/Runtime/Desktop 零修改 | ✅ 4784 tests 保持
✅ 无重复模型 (复用 exec/operations/repo_index/Experience)
✅ 不引入行业模型 | ✅ 不扩展商业化 | ✅ 单 Agent + Self Review (无独立进程)
```

## 8. 实现路线（Phase A++++++-2 内部）

```
-2a: Call Graph + Test Map + Architecture Summary (Repository Intelligence 增强) + 测试
-2b: Context Assembly Engine (6 类上下文自动组装 + token 预算) + 测试
-2c: Self Review 循环 (Reviewer prompt + Correction ≤2) + Experience 决策接入
-2d: Benchmark V2 重跑 (真实数据) — 门槛: Bug Fix ≥70%
```

## 9. 结论

```
Stage 2 将 Developer Agent 从"代码修改工具"升级为"Software Engineer AI Employee":
  Repository Intelligence (理解项目) + Context Engine (自动上下文)
  + Self Review (质量闭环) + Experience 驱动 (越用越准)
Level 目标: 稳定 Level 2 (独立完成简单任务) → 为 AI Software Department 打基础
等待确认后进入 Phase A++++++-2a 实现
```
