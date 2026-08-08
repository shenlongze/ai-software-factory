# Sprint 9 — Current Capability 盘点

> 日期: 2026-08-09 | 基准: f090235, pytest 6274, Sprint 8 完成
> 用途: Productionization 设计输入

## 1. Sprint 8 完成后的能力（真实验证）

```
✅ AI App Production Team 成立:
   Idea → PM → UX/UI → Architect → Developer → Tester → Release 全链真实
   记账 Web App 真实产物 (4 文件 + zip 6919B, $0.0126, 275s)
✅ 6 角色全 executable: PM/UX-UI/Architect/Developer/Tester/DevOps
✅ Agent 自愈: 契约失败→反馈重试 ≤2 (4 Agent 通用)
✅ Artifact 链: 7 类型契约 (product/ux_ui/design/code/test/release/bug_report)
✅ Workflow: 组织级编排 (DAG/Runner/事件) + DevTestLoop ≤2
✅ 组织模型: User→Project→Workflow→Stage→Role→Task→Artifact
```

## 2. 生产化缺口（Sprint 9 要解决）

```
🔴 人工审批: Demo 全自动无闸门 — 生产必须有人工确认点
   (MVP scope / 架构变更 / 发布 三挡板 — 用户核心要求)
🔴 已有项目接入: 仅验证 greenfield (空目录) — MarkPad (Flutter 2.2G) 未测
🔴 Flutter/Dart: Developer 仅验证 Python/HTML-JS — Dart 语法/Flutter 结构未验证
🔴 多项目管理: 单 Demo 项目 — 多项目并行/隔离未验证
🔴 成本/日志: Demo 有 totals — 无持久化追踪 (每项目累计成本/成功率)
🔴 工厂操作界面: Console 只读管理台 — 无法操作 (建项目/审批/看状态)
```

## 3. 可复用（Sprint 9 直接复用）

| 组件 | 复用点 |
|:-----|:-----|
| Approval 基础设施 (Core product/models.py ApprovalGate) | 人工闸门核心 (已存在未接线到 Workflow) |
| Workflow BLOCKED 语义 | 审批等待 = stage BLOCKED |
| org CLI / Console 7 页面 | Factory Console 扩展基础 |
| benchmark_s6b (9 任务分级) | Flutter/Dart 验证载体 |
| demo_full_chain.py | 生产驱动模板 (加审批/日志) |
| Experience 闭环 | 成本/成功率追踪数据源 |
| events (179) | 日志追踪完整事件流 |

## 4. 用户项目接入评估（真实约束）

```
MarkPad (~/work/markpad, Flutter):
  2.2G (build 1.4G + .dart_tool 301M) — 沙箱需选择性复制 (只 lib/ + pubspec)
  Dart 语法验证: dart analyze / flutter test (沙箱需 Flutter SDK)
  ⚠️ 用户冻结: MarkPad 架构不重构 (仅 bug/feature 任务可交 AI Factory)

ScorePocket (~/work/ScorePocket, Java+Vue3+uni-app):
  多技术栈混合 — 需模块级任务 (后端 Java / 前端 Vue)

DevToolBox (devcheat.com, 静态站):
  33 工具 — 纯前端小任务适合试水
```

## 5. Sprint 9 设计输入

```
目标: MVP Demo → 真实生产使用
核心: 审批闸门 + 已有项目接入 (Flutter 验证) + 工厂操作台 + 成本日志
```
