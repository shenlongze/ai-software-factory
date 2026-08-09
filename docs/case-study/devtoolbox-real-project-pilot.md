# AI Factory Real Project Pilot Case Study

## DevToolBox Production Bug Fix

> 日期: 2026-08-09 | 来源: Sprint 9 S9-005 真实执行数据
> 文档性质: 能力证明 (非 Sprint 报告) — 面向外部展示

---

## 1. Executive Summary

AI Software Factory 首次完成**真实生产项目接管**：从已有代码仓库出发，经
自动分析 → AI 修复 → 自动测试 → 发布产物 → 人工审批，全链自动执行。

```
项目名称:   DevToolBox (devcheat.com 生产工具站)
技术栈:     JavaScript / 纯前端静态站 (33 个在线工具)
任务类型:   真实 Bug 修复 (DOM id 引用错误)
AI 模型:    DeepSeek v4-pro
执行时间:   79.4 秒 (2 次 LLM 调用)
成本:       $0.0038
修改规模:   4 行代码 (单文件)
```

核心结论：这不是"生成一段代码"，而是完成了一个**软件生产生命周期闭环**
（Brownfield 项目 → 任务 → 代码变更 → 测试通过 → 发布包 → 人工放行）。

---

## 2. Project Background

DevToolBox 是一个**已有生产项目**（非新建），部署于 Cloudflare Pages，
每日面向开发者提供在线工具。AI Factory 面临的是真实 **Brownfield 场景**：

```
项目类型:   javascript / static web (多文件: index.html + js/tools/*.js 33 个工具)
接入方式:   通过 S9-004 Existing Project Adoption 注册现有仓库
项目注册:   ProjectAdoption.register(repo_path=..., language=javascript,
            build_command=..., test_command=...) → 自动创建 Project 记录
环境分析:   Repository Analyzer 生成 project_analysis artifact
            (语言/框架/结构/依赖) + Context Snapshot (目录树/重要文件/架构摘要)
```

注册成功后，系统自动完成分析、基线验证与上下文快照，后续 Agent 无需
人工解释项目结构即可理解代码库。

---

## 3. Task Definition

用户任务：修复 `js/tools/base64.js` 的 DOM id 引用错误。

```
输入任务:  "修复 base64.js clear()/example() 引用不存在的 DOM id"
问题描述:  clear() 引用 'base-input'/'base-output'/'base-mode'，
           但页面实际元素 id 为 'b64-input'/'b64-output'/'b64-mode'
           → 工具的 Clear 按钮与示例填充功能真实损坏
约束条件:
  - 不直接修改生产源码 (真实项目零接触)
  - 在隔离 Sandbox 副本中执行
  - 自动测试验证
  - 生成 Release Artifact (zip + version + notes)
```

---

## 4. AI Factory Execution Pipeline

```
Existing Project (DevToolBox)
  ↓
① Project Registration  注册真实仓库, 建立项目记录
  ↓
② Repository Analysis   自动分析语言/框架/结构/依赖 → project_analysis artifact
  ↓
③ Baseline Validation   基线构建/测试/分析 → baseline artifact
  ↓
④ Developer Agent       理解任务 + 上下文快照 + 生成最小代码变更
  ↓
⑤ Patch Generation      Operation/Patch 输出 (不直接写生产)
  ↓
⑥ Tester Agent          确定性测试执行 (语法 + 功能断言)
  ↓
⑦ Release Agent         打包 → version/notes → 发布产物
  ↓
⑧ Approval Gate         人工审批放行 → Workflow 完成
```

每个阶段以 Artifact 契约衔接（输入必须 VALIDATED 才能进入下一阶段），
全程事件审计（org.workflow.* / org.artifact.* / org.approval.*）。

---

## 5. Developer Agent Execution

```
使用模型:  DeepSeek v4-pro (max_tokens 16384)
修改方式:  上下文快照 + 目标源文件行号内联 → LLM 生成结构化操作 → Sandbox 内应用
修改文件:  js/tools/base64.js (单文件)
修改规模:  4 行 DOM id 修复 (base-* → b64-*)
Patch 输出: sandbox_patches/s9-005-base64-fix.patch
```

**重点**：AI 没有直接修改生产项目。所有变更先落地到隔离沙箱副本，
生成可审查的 unified diff，生产源码保持零修改。

---

## 6. Testing and Validation

Tester Agent 在沙箱内执行确定性验证（非 LLM 猜测）：

```
测试方式:  tests/tool_checks.py (node 语法检查 + DOM id 引用断言 + 功能检查)
测试结果:  passed=True, bugs=0
Regression: 沙箱修复后全量检查 (无残留 base-* 引用 / b64-* 引用齐全 /
            example() 键正确 / 语法通过)
```

---

## 7. Release Generation

Release Agent 在测试通过后自动产出发布包：

```
版本:        1.0.1
产物:        devtoolbox-1.0.1.zip (234,981 bytes)
Release Notes: 自动生成 (版本 + 变更摘要)
部署信息:     deployment 描述 (Cloudflare Pages 重新部署即可生效)
```

---

## 8. Human Approval Workflow

Approval Gate（S9-001）保证"AI 自动执行 + 人工控制"的生产模式：

```
Stage COMPLETED
  ↓ (release 阶段 approval_required=True)
PENDING  ← 审批门创建, Workflow PAUSED
  ↓ 人工在 Console/CLI 批准 (approve + comment, source=console 审计)
APPROVED → Workflow 恢复 → COMPLETED
```

发布前必须人工放行；拒绝则 Workflow 终止并记录原因。执行权始终在人工一侧。

---

## 9. Final Result

| Capability | Result |
|---|---|
| Existing Project Adoption | PASS |
| Bug Analysis | PASS |
| Code Modification | PASS |
| Automated Testing | PASS |
| Release Generation | PASS |
| Human Approval | PASS |

---

## 10. Metrics

| Metric | Value |
|---|---|
| AI Calls | 2 |
| Cost | $0.0038 |
| Duration | 79.4s |
| Code Change | 4 lines (1 file) |
| Release Size | 234KB |
| Source Project Modified | FALSE |

---

## 11. Significance

这个案例证明 AI Factory 已从 **AI Coding Assistant** 升级为
**AI Software Production System**：

```
之前 (Assistant 范式):  用户给提示词 → AI 生成代码片段 → 用户自己集成/测试/发布
现在 (Production 范式): 用户给真实项目任务 → 系统自动完成
                        分析 → 修改 → 测试 → 打包 → 审批 → 交付
```

强调：不是"生成代码"，而是完成**软件生命周期闭环**——每个环节都有
Artifact 证据、自动测试保障、人工审批控制、成本可计量。

---

## 12. Technical Evidence

```
Commits:
  01a52ea  S9-005: Real Project Pilot (全链执行 + 验收)
  e68206d  fix: pilot 运行时目录 gitignore

Test Suite:
  pytest 6456 passed, 0 failed

Artifact (Patch):
  factory-exec/benchmark_s9_pilot/sandbox_patches/s9-005-base64-fix.patch

Release:
  factory-exec/benchmark_s9_pilot/dist/devtoolbox-1.0.1.zip (234KB)

完整报告:
  docs/sprint9/implementation/S9-005-report.md
```

---

### 生产模式声明

本案例展示的是 **"AI 执行 + Artifact 证据 + 自动测试 + 人工审批"** 的生产模式，
而非"完全无人化"。真实源码变更需人工批准后应用（patch 已保存，可审查、可回滚）。
