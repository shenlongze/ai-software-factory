# Sprint 8 — Architecture Design: AI App Production Team

> 日期: 2026-08-09 | 状态: 设计 (ONLY DESIGN, 待审核)
> 目标: AI Software Organization → AI App Production Team ("开发一个 App" 全链产物)

## 1. 目标架构

```
Idea ("开发一个 App")
  ↓
① PM Agent → Product Artifact (market/persona/journey/PRD/MVP/user story)
  ↓
② UX/UI Designer Agent → UX/UI Artifact (IA/user flow/wireframe/screen spec/
                                    UI component/design token/prototype)
  ↓
③ Architect Agent → Design Artifact (tech arch/db/api/frontend/backend/task breakdown)
  ↓
④ Developer Agent (增强) → Code Artifact (多语言/大项目/UI 代码)
  ↓
⑤ Tester Agent (增强) → Test Artifact (unit/integration/UI/regression) ↔ Loop
  ↓
⑥ Release Agent → Release Artifact (build/version/package/release note/deployment)

Artifact 链: Product → UX/UI → Design → Code → Test → Release
每阶段: 输入必须 VALIDATED; 输出自动注册 (Sprint 7 机制复用)
```

## 2. Agent 架构

### ① PM Agent (executable)
```
输入: Idea (自然语言)
输出: Product Artifact (6 节):
  market_analysis / user_persona / user_journey / prd (需求+验收) / mvp_scope / user_stories
实现: roles.py PM executable + pm.py (PMAgent: 结构化 prompt → Product Artifact)
验证: CONTRACTS product 类型 (required fields + 规则)
接入: Workflow stage "product" (role_ref=pm)
```

### ② UX/UI Designer Agent (新增角色 executable)
```
输入: Product Artifact
输出: UX/UI Artifact (7 节):
  information_architecture / user_flow / wireframe (ASCII/描述) / screen_specification
  / ui_component_definition / design_token / prototype_description
实现: roles.py UX/UI Designer executable + uxui.py (UXUIDesignerAgent)
验证: CONTRACTS ux_ui 类型
连接: PRD → UI Artifact → Architect (输入含 PRD + UI) → Developer (UI 代码生成参考)
接入: Workflow stage "ux_ui" (role_ref=ui-designer)
```

### ③ Architect Agent (executable)
```
输入: Product + UX/UI Artifact
输出: Design Artifact (6 节):
  technical_architecture / database_design / api_design / frontend_structure
  / backend_structure / task_breakdown
实现: roles.py Architect executable + architect.py (ArchitectAgent)
验证: CONTRACTS design 类型
接入: Workflow stage "architecture" (role_ref=architect)
```

### ④ Developer Agent (增强, 已有)
```
增强点 (非重写):
  - 多语言: prompt 模板按语言 (python/dart/js 已验证, 新增: html/css/js UI 栈)
  - 大项目: Context 智能默认化 (Progressive/Ranking 已建)
  - UI 代码生成: 消费 UX/UI Artifact (wireframe/spec → HTML/JS 代码)
  - ProjectLayout 助手: 前端/后端目录结构生成
接入: Workflow stage "development" (已有, 输入增强: Design + UX/UI)
```

### ⑤ Tester Agent (增强, 已有)
```
增强点:
  - Test 类型: unit/integration/ui/regression (Tester prompt + 策略)
  - UI Test: 静态检查 (HTML 结构/可访问性基础) + 命令 (如 playwright 可选)
  - Regression: 全量测试复用
接入: Workflow stage "testing" (已有) + Loop ≤2 保持
```

### ⑥ Release Agent (executable)
```
输入: Test Artifact (通过)
输出: Release Artifact (5 节):
  build / version / package (文件清单) / release_note / deployment (步骤)
实现: roles.py DevOps executable + release.py (ReleaseAgent: 沙箱 build 命令 + 文档)
验证: CONTRACTS release 类型 (强化)
接入: Workflow stage "release" (role_ref=devops)
```

## 3. Artifact 流转（完整链）

```
Product (pm) → ux_ui (ui-designer) → design (architect) → code (developer)
→ test (tester, bug_report loop) → release (devops)

规则 (Sprint 7 复用):
  输入 Artifact 必须 VALIDATED (未验证 → stage BLOCKED)
  输出 Artifact 自动注册 (继承上下文)
  每阶段产物 = 下一阶段输入 (id 引用)
  新增类型: ux_ui (CONTRACTS 扩展)
```

## 4. Workflow 接入方式

```
① 标准 App Workflow 定义 (AppLifecycleWorkflow):
   product → ux_ui → architecture → development → testing → release
   (depends_on 链 + input/output artifacts + role_ref)
② Runner: 复用 S7-003 (自动推进 + 事件 + BLOCKED/FAILED 语义)
③ Dev↔Test Loop: 复用 S7-004 (≤2 轮)
④ 人工闸门: MVP scope 确认 (Product 后) + 发布确认 (Release 前) — 三挡板保持
⑤ 事件: 复用 org.workflow.* (无需新增或少量)
```

## 5. 架构边界

```
✅ 复用: Organization/Artifact/Workflow/Role Executor/Tester Loop/Context/Experience
🆕 新增: pm.py / uxui.py / architect.py / release.py (角色 Agent, 同 Developer 模式)
        CONTRACTS ux_ui 类型 + 各角色 prompt
✅ 保持: Core 冻结 / 沙箱铁律 / 审批闸门 / 仅 DeepSeek v4-pro
❌ 不做: 多行业 / Skill-MCP / 自改进 / 移动端打包 (web app 为验证载体)
```

## 6. 风险

```
1. UX/UI Agent 输出质量: wireframe/spec 是结构化文本 — 需严格契约 (ASCII 布局 + JSON spec)
2. UI 代码生成: Developer 消费 UI Artifact → HTML/JS — 需验证 (S8-005 Demo 实测)
3. 角色串联质量: PM→UI→Arch 逐链 — 每环节质量影响下游 (小步验证 + 人工闸门)
4. 多语言: 验证载体选 Web App (HTML/CSS/JS + 少量 Python 后端) — 避免一上来全栈复杂
```

## 7. Demo 验证载体（S8-005 建议）

```
目标 App: 简单 Web App (如 "记账 Web App" — 呼应用户之前例子)
栈: 纯前端 HTML/CSS/JS (无后端依赖) → 降低发布复杂度, 全链可测
产出: product + ux_ui + design + code (HTML/JS) + test (静态+单元) + release (zip+notes)
```
