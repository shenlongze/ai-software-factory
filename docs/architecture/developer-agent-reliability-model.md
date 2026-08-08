# Developer Agent Reliability Model

> 状态: IMPLEMENTED (已实现 — 见 ../audit/architecture-reality-audit.md)

> 日期: 2026-08-07 | 状态: 架构评审 (Phase A++++++, 不编码)
> 背景: 真实 Benchmark 22.2% (2/9) — 瓶颈是 Agent Engineering 非 LLM 智能
> 目标: Developer Agent 从"生成 patch"→"可靠完成工程任务" (Bug Fix ≥70% → ≥90%, Feature ≥50% → ≥80%)
> 约束: Core/Runtime 冻结; 不进入 Phase B; 不做行业能力; 先做可靠产品

## 0. 核心命题

```
失败不是 LLM 不够聪明, 而是 Agent Engineering 不足:
  Repository Understanding / Context Assembly / Code Modification Reliability / Validation Loop
本次只强化 Developer Agent 可靠性, 不新增宏观架构
```

---

## 1. 当前失败根因分析（责任边界）

### 失败数据（真实, 9 样本）

```
空内容 ×4:      reasoning 模型 max_tokens 8192 耗尽 → 无输出
diff 不可应用 ×2: hunk context 与真实文件不匹配 (rc 128)
功能未实现 ×1:   patch 可应用但验收未达
```

### LLM Capability vs Agent Engineering 责任边界

```
LLM Capability (模型责任):
  - 理解任务语义 / 推理修复方案 / 生成代码逻辑
  - 已证明: 小任务/单文件修改表现良好

Agent Engineering (我们责任):
  - 给模型足够的 max_tokens (8192 → 16384): 空内容修复
  - 喂精确的文件内容 + 行号 (hunk 匹配): diff 可应用修复
  - 迭代验证循环 (修→测→修): 功能完整性修复
  - 上下文组装 (不靠用户写完整 prompt)

结论: 4/7 失败 (空内容) 是 Engineering 问题可直修; 2/7 (diff) 是上下文精确性问题;
     1/7 (功能) 需要验证循环。LLM 智能不是当前瓶颈。
```

---

## 2. Code Modification Architecture

### 当前流程问题

```
LLM → Patch (git diff 文本) → git apply
问题: diff 依赖模型精确回忆文件内容/行号 — 一次生成即最终, 无中间校验
```

### 未来流程

```
LLM → Intent (结构化意图) → Structured Code Operation → Validation → Patch → Approval

Intent: {target_file, operation: insert|replace|delete|create, anchor, new_content}
Structured Operation: 基于 AST/Symbol 定位的精确修改 (非文本猜测)
Validation: 语法检查 + 锚点存在性 + 应用试跑
Patch: 由 Operation 生成 (确定性, 非模型手写 diff)
```

### 是否需要 AST/Symbol/File API?

```
阶段 1 (本次): File Operation API — 逐文件意图修改 (锚点 + 内容), 生成可靠 patch
              (AST 太重, 多语言成本高; 先解决 80% 的 diff 不匹配问题)
阶段 2 (后续): Symbol Graph 定位 (函数/类级别锚点) — 复杂重构需要
阶段 3 (远期): AST 级修改 (多语言) — 高难度重构

本次实现: File Operation API (Intent → 锚点替换 → patch 生成 → 应用校验)
```

---

## 3. Repository Intelligence Model

### AI 如何理解陌生项目（分层）

```
Repository Index (文件清单 + 大小 + 语言)
Module Graph (目录 → 模块 → 文件)
Dependency Graph (import/依赖关系)
Symbol Graph (函数/类/变量 定义与引用)
Function/Class Relationship (调用链/继承)
Test Relationship (测试 ↔ 被测代码)

MVP 实现 (本次):
  indexer: 文件树 + 语言识别 + 大小排序 (轻量)
  symbol_scan: 函数/类定义位置 (正则级, 多语言)
  test_map: test 文件 ↔ 源文件 (命名约定)
  不实现: 完整依赖图 (后续阶段)
```

### 用途

```
Context 组装只选相关文件 (非全库)
锚点定位用 symbol 位置 (非行号猜测)
测试关联 → 验证选择
```

---

## 4. Context Assembly Engine

### 输入 Task → 自动构建 AI Native Context

```
Requirement Context: 任务目标 + 验收标准 (样本自带)
Code Context:       source_files 内联 + 行号 + symbol 位置 (已有基础, 强化)
Architecture Context: 相关模块图 (indexer 提供)
History Context:    相关文件修改历史 (git log, 简单版)
Experience Context: 同类任务历史经验 (ExperienceStore 查询 — 10A-4)
Test Context:       相关测试 (test_map)

组装: 按预算 token 分配 (相关文件全量 ≤ 3000 行/文件, 截断策略已有)
```

### 原则

```
AI Native Context: 系统自动组装, 用户只需自然语言任务
不依赖: 用户提供完整提示词/文件路径
```

---

## 5. Developer Agent Workflow（重新定义）

```
Receive Task
  → Analyze (理解需求 + 计划)
  → Explore Repository (indexer/symbol 定位相关文件)
  → Create Plan (修改方案: 文件 + 操作列表)
  → Modify (Intent → Structured Operation → 应用)
  → Run Validation (语法 + 相关测试)
  → Self Review (对照验收标准检查)
  → Generate Report (改了啥/为什么/验证结果)
  → Human Approval

对比当前: 一次性 prompt→patch→apply
改进: 分步 + 中间校验 + 自审循环 (修→测→修 ≤2 轮)
```

---

## 6. Multi Agent 是否提前引入

### 分析

```
单 Agent + Tool: 够处理 80% 当前失败 (工程问题, 非协作问题)
Multi Agent (Developer+Reviewer+Tester): 协作开销大, 当前收益低
  (Reviewer 纠错依赖 Developer 的产出质量; Tester 验证可用 Tool 替代)

阶段建议:
  阶段 1: 单 Agent + Tool (Self Review 内建 + 验证工具)
  阶段 2: 独立 Reviewer (代码质量把关) — 在单 Agent 稳定后
  阶段 3: Tester Agent — 复杂系统验证
先单 Agent 打磨可靠性, 再引多 Agent (执行权 != 审核权 保持)
```

---

## 7. Experience Learning

### 一次失败如何变成经验

```
失败记录 (ExecutionRecord → ExperienceRecord):
  Cause: 结构化根因 (max_tokens 不足 / hunk 不匹配 / 功能缺失 / verifier 失败)
  Solution: 修复动作 (扩 token / 加行号 / 验证循环)
  Future Recommendation: 下次任务参数建议 (max_tokens 升级 / 文件选择策略)

影响下一次 Task Matching:
  - 同能力成功率高 → 任务加权 (10A-4 已有)
  - 失败模式 → 预调参数 (如该类型任务自动用更高 max_tokens)
  - 同类任务历史 → 推荐最可靠 Provider/配置
```

### 本次实现

```
ExperienceRecord 扩展: failure_reason 结构化 (已有基础) + recommendation 字段
复盘循环: Benchmark 失败 → 归类 → 参数/策略调整 → 重测
```

---

## 8. Benchmark V2

### 场景扩展

```
Bug Fix (5) / Feature (3) / Refactor (新增 2: 重命名/提取) / Greenfield (1)
```

### 指标

```
Success Rate (verifier 通过)
Human Intervention (次数)
Cost ($/任务)
Latency (s)
Code Quality (patch 最小性/规范 — 已有 pq 启发式)
Regression (修复不破坏其他测试 — 新增)
```

### 门槛

```
阶段目标: Bug Fix ≥70% → ≥90%, Feature ≥50% → ≥80%
每轮 Benchmark 驱动: 失败 → 归因 → 修复 → 重测
```

---

## 9. 与 AI Enterprise OS 架构关系

```
Developer Agent = AI Employee 的第一个行业实例 (软件行业)
归属: Extension / Domain Capability (factory-exec + benchmark + org 集成)
不污染: Core (冻结) / Runtime (冻结)
复用: org (Employee) / exec (执行链) / intelligence (Experience/推荐)
架构关系: 与 ai-employee-execution-runtime-model.md 一致 (Employee→Agent→Provider)
```

---

## 10. 实现路线（3 阶段）

### Phase A++++++-1: 快速修复 (低风险高收益)
```
目标: 空内容修复 + diff 可靠性
范围:
  - max_tokens 8192 → 16384 (推理模型余量)
  - File Operation API MVP (锚点替换生成 patch, 非模型手写 diff)
  - 行号 + symbol 位置进内联上下文
  - 验证循环 ≤2 轮 (验证失败 → 反馈 → 重试)
验收: 9 样本重跑 — 空内容 0/9, Bug Fix ≥50% (首个里程碑)
```

### Phase A++++++-2: Repository Intelligence + Context Engine
```
目标: 陌生项目理解 + 自动上下文
范围:
  - indexer (文件树/语言/大小) + symbol_scan (函数/类定位)
  - Context Assembly Engine (6 类上下文自动组装)
  - test_map (相关测试选择)
验收: Bug Fix ≥70%, Feature ≥50% (阶段门槛)
```

### Phase A++++++-3: 可靠性闭环
```
目标: 经验驱动 + 自审 + Benchmark V2
范围:
  - Experience 失败复盘循环 (失败→参数/策略调整)
  - Self Review 内建 (对照验收自检)
  - Benchmark V2 (4 场景 + 6 指标)
  - 独立 Reviewer (多 Agent 阶段 2)
验收: Bug Fix ≥90%, Feature ≥80% (目标门槛) → Phase B 评估
```

---

## 11. 边界

```
✅ Core/Runtime/Desktop 零修改 | ✅ 4695 tests 保持
✅ 无重复模型 (复用 exec/org/intelligence) | ✅ 不做行业能力
✅ 不做 Marketplace | ✅ 单 Agent 优先 (多 Agent 阶段化)
```

## 12. 结论

```
Developer Agent 可靠性升级路线冻结:
  失败 4/7 是 Engineering 可修 → 3 阶段 (快速修复 → 仓库智能 → 可靠性闭环)
  目标: Bug Fix 70%→90%, Feature 50%→80%
等待确认后进入 Phase A++++++-1 实现
```
