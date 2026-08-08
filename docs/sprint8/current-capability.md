# Sprint 8 — Current Capability 盘点

> 日期: 2026-08-09 | 基准: ed523b3, pytest 6018, Sprint 7 完成
> 用途: Sprint 8 (AI App Production Team) 设计输入

## 1. Sprint 7 完成后的能力

```
✅ 组织模型: User→Project→Sprint→Workflow→Stage→Task→Artifact
   (S7-001: 角色统一 role_ref + 生命周期模型)
✅ Artifact 系统: Registry/状态机 (CREATED→VALIDATED→CONSUMED)/类型契约
   (prd/design/code/test/release/bug_report) (S7-002)
✅ Workflow 编排: DAG 依赖/Runner 自动推进/事件审计/CLI (S7-003)
✅ Developer 执行: v4-pro 真实闭环 (Sprint 6.5: 27/27, Python 单任务级) (S7-004 前)
✅ Tester 闭环: Dev↔Test Loop ≤2 轮 (确定性测试 + LLM 失败分析 + bug_report) (S7-004)
✅ Full Chain Demo: 5 阶段链集成验证 (S7-005)
   (Product/Arch/Release 用 mock 占位 — 真实角色待 Sprint 8)
```

## 2. 可复用组件（Sprint 8 直接复用）

| 组件 | 复用点 |
|:-----|:-----|
| roles.py (6 角色注册表 + role_ref 映射) | PM/UX-UI/Architect 解锁 executable |
| EmployeeExecutor (统一执行入口) | 所有角色执行 |
| DeveloperAgent (v4-pro + 沙箱 + Operation) | Developer 增强基础 |
| TesterAgent (确定性测试 + 失败分析) | Tester 增强基础 |
| WorkflowLifecycle + Runner | 新角色 stage 编排 |
| ArtifactRegistry + CONTRACTS | 新产物类型 (ux_ui) |
| Context 智能 (Ranking/Progressive/Budget) | 大项目/多文件 |
| Experience 闭环 | 角色经验积累 |
| benchmark_s6b (9 任务分级) | 回归/验收 |

## 3. 当前限制（Sprint 8 要解决）

```
🔴 PM/UX-UI/Architect/Release 角色 = planning (不可执行)
🔴 无 UX/UI 产物类型 (wireframe/screen spec/design token)
🔴 Artifact 链止于 test (release 是 mock 占位)
🔴 Developer 仅验证 Python (多语言/Dart/JS 未验证)
🔴 大项目上下文 (markpad 2.2G) 未默认优化
🔴 无 UI 代码生成 (Developer 写 UI 未验证)
🔴 Tester 仅 unit (无 UI/Integration/Regression 测试类型)
```

## 4. Sprint 8 设计输入

```
目标: "开发一个 App" → Product + UX/UI + Architecture + Code + Test + Release
新增: PM/UX-UI/Architect/Release 4 角色 executable
复用: 全部 Sprint 7 基础设施 (零重写)
核心: PRD → UX/UI Artifact → Design → Code → Test → Release 全链真实
```
