## 变更概述 (Summary)

<!-- 一句话: 做了什么、为什么 -->

## 变更内容 (Changes)

- [ ] 功能 / 修复:
- [ ] 测试:
- [ ] 文档:
- [ ] 其他:

## 测试证据 (Testing)

<!-- 必须填写, 缺省视为未完成 -->

- pytest: `N 个用例通过` (全量 4111 基线, 用例数只增不减) — 贴最后一行输出
- Vitest: `N 个用例通过` (全量 92 基线, `cd factory-console/web/frontend && npx vitest run`)
- Removal Isolation: 相关断言 (`test_product_removal.py` 等) 通过 / 不涉及

```text
<pytest 最后一行输出>
```

## 设计决策 (ADR)

- [ ] 涉及设计决策 → 已写 ADR (docs/adr/, 编号递增, 格式参照 ADR-0001–0035): ADR-00XX
- [ ] 不涉及 (纯修复 / 纯文档 / 纯测试)

## 范围声明 — Core 零修改确认 (Scope)

<!-- 铁律: Core 冻结, 新能力一律走 Extension 声明式注册 (docs/core-boundary.md §4) -->

- [ ] **本 PR 未修改 Core 模块行为** (events/tasks/workflows/agents/assignment/execution/runtime/recovery/orchestration/validation/metrics/dashboard/project/workspace/runtimes 及 cli 组合根)
- [ ] 新能力以声明式载体接入 (SKILL.md / catalog.json / workflow YAML / Provider 声明), 仅延迟 import
- [ ] 依赖单向向下, 无反向依赖 / 循环 import

## 检查清单 (Checklist)

- [ ] Commit 信息符合规范: `Phase <N>: <摘要> + <测试数>`
- [ ] 分支命名: `feature/<phase>-<描述>`
- [ ] 相关文档 (docs/) 已更新

---
*模板见 .github/PULL_REQUEST_TEMPLATE.md · 完整流程见 CONTRIBUTING.md*
