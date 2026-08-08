# Sprint 9 — Architecture Design: Productionization

> 日期: 2026-08-09 | 状态: 设计 (ONLY DESIGN, 待审核)
> 目标: MVP Demo → 真实生产使用 (审批 + 已有项目 + 操作台 + 成本日志)

## 1. 目标架构（生产闭环）

```
User (真实项目: MarkPad/ScorePocket/DevToolBox)
  ↓
Project 接入器 (已有代码库 → 选择性沙箱快照)
  ↓
Workflow Run (组织级编排, Sprint 8 引擎)
  ├─ 阶段执行 (Agent 自愈 ≤2)
  ├─ 🛑 人工审批节点 (Workflow BLOCKED → 人确认 → 继续)
  └─ Artifact 流转 (全 VALIDATED 契约)
  ↓
发布产物 + 成本/日志追踪 (持久化)
  ↓
Factory Console (操作台: 建项目/派任务/审批/看状态/看成本)
```

## 2. Human Approval Gate（核心, 用户三挡板落地）

```
设计: Workflow stage 增加 approval_required 属性
  执行到该 stage 完成 → workflow PAUSED (或 stage BLOCKED)
  → 人工确认 (CLI/Console: approve/reject) → 继续/回退

三挡板映射:
  P1 MVP scope 确认   → product stage 后 (PM 产出 → 人确认范围)
  P2 架构变更         → design stage 后 (Architect 产出 → 人确认技术方案)
  P3 发布确认         → release stage 前 (测试通过 → 人确认发布)

实现 (复用):
  WorkflowStatus 已含 PAUSED; stage BLOCKED 语义已有
  新增: ApprovalGate 接线 (stage.completed → if approval_required → PAUSED)
  CLI: workflow approve/reject | Console: 审批按钮
  事件: org.workflow.paused/resumed (枚举 +2)
```

## 3. Existing Project Adoption（已有项目接入）

```
沙箱选择性复制 (已有机制, 默认化):
  项目快照 = 复制必要文件 (MarkPad: lib/ + pubspec.yaml + analysis_options; 
            不复制 build/.dart_tool/2.2G)
  ⚠️ 已实现 (repo_intelligence/沙箱复用) — Sprint 9 验证参数化

项目注册 (Project 接入器):
  register_project(路径, 语言, 构建命令, 测试命令)
  → Project 模型扩展 (repo_path/sandbox_config/build_cmd/test_cmd)
  → 沙箱快照生成 + 基线测试运行 (确认环境可用)

Flutter/Dart 验证 (P0):
  benchmark_s6b 模式: 9 任务 (Dart 小项目, 纯 Dart 逻辑可测)
  dart analyze + dart test (沙箱需 Dart SDK — 本机已有)
  ⚠️ 不跑完整 Flutter (重); 先验证 Dart 逻辑任务 (纯 Dart 包)
```

## 4. Factory Console（操作台, 非只读管理台）

```
现有: Console 7 只读页 (Dashboard/Projects/Lifecycle/Intelligence/Approval/Decisions/Providers)
升级 (增量, 不重写):
  ① Projects 页: 可操作 (注册项目/查看状态) — API 扩展 POST
  ② Approval 页: 审批操作 (approve/reject 按钮, 接审批门) — 已有数据视图, 加操作
  ③ Workflow 页: Run 状态实时 (阶段/负责人/Artifact/成本)
  ④ 成本日志: 每 Project 累计 (calls/tokens/cost/success_rate — 从 events 聚合)

架构: Console API 只读 → 加 POST 端点 (approve/reject/register_project)
  CLI 优先 (org workflow approve), Console 为可视化操作层
```

## 5. 成本/日志追踪

```
数据源: events (179) + ExecutionResult (usage/cost) + Experience
设计: CostLedger (org 扩展):
  per project: {total_calls, total_tokens, total_cost, success_rate, per_stage}
  从 events/execution 聚合 (不重复存储 — 查询时聚合 or 增量维护)
  查询: org cost report --project X / --workflow Y
```

## 6. 多项目管理

```
Project 模型已有 (独立 org 目录/独立沙箱) — 天然隔离
验证: 2 项目并行注册 + 各自 Workflow Run (串行执行, 防并发共享目录 — S8 教训)
```

## 7. 边界

```
✅ 复用: Workflow/Artifact/Agent 自愈/沙箱选择性复制/Approval 核心/Console 页
🆕 新增: Approval 接线 (PAUSED/恢复) + Project 注册器 + Console POST + CostLedger
✅ 保持: Core 冻结 / 仅 DeepSeek / 沙箱铁律 / 用户冻结 (MarkPad 不重构)
❌ 不做: 多行业 / Skill-MCP / 自改进 / 移动端打包 (后续 Sprint)
```

## 8. 风险

```
1. Flutter/Dart 验证: 纯 Dart 可测, 完整 Flutter 重 (2.2G) — 分步 (先 Dart 逻辑)
2. 审批接线: Workflow PAUSED/恢复状态机 — 需严格测试 (禁非法跳转)
3. Console POST: 只读→可写 — 权限/审计 (所有操作记录事件)
4. 多项目: 沙箱磁盘 (MarkPad 2.2G 快照 ~100M 选择性) — 可控
```
