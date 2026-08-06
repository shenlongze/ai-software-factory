---
name: Feature request
about: 提议一个新能力 / 新 Extension, 帮助 Factory 持续生长
title: "[feature] 简述需求"
labels: enhancement
assignees: ''
---

<!-- 提交前: 请确认已阅读 CONTRIBUTING.md — 新能力优先走 Extension 声明式注册, 不修改 Core -->

## 场景 (Scenario)

<!-- 在什么场景下、谁、遇到了什么问题/想做但做不到的事 -->

## 需求 (Requirement)

<!-- 希望系统具备什么能力; 若涉及新模型, 建议先补设计文档再写代码 -->

## 候选方案 (Proposed approach)

<!-- 可选: 你的实现思路 — 声明式载体 (SKILL.md / catalog.json / workflow YAML / Provider 声明) 是什么、注册到哪里 -->

## 验收标准 (Acceptance criteria)

- [ ] 场景可跑通: ...
- [ ] 附带测试: pytest / Vitest 用例数只增不减
- [ ] Removal Isolation: 新能力删除后 Core 照常运行 (延迟 import 断言通过)
- [ ] 文档: 设计文档 (docs/) + ADR (如属设计决策)

## 范围声明 (Scope)

- [ ] 承诺 **Core 零修改** (领域能力一律走 Extension)
- [ ] 涉及 Core 原语 (需先与维护者讨论 core-boundary 判定)

## 附加说明 (Additional context)

<!-- 是否已有相关 ADR / Issue / 设计文档可引用 -->
