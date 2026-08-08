# S8-002 — UX/UI Designer Agent（Completion Report）

> 日期: 2026-08-09 | 状态: 完成 (待人工审核) | pytest 6145 (6076 + 69)
> 目标: UX/UI Designer Agent executable — Product Artifact → 结构化 UX/UI Artifact (7 节),
> CONTRACTS ux_ui 类型, Workflow ux_ui stage 接入 (role_ref=ui-designer),
> 只扩展不重写 (Core/Runtime/Console/Desktop diff = 0)

## 实现概述

```
S8-002 把 UX/UI Designer 从 planning 角色升级为 executable (真实 LLM 执行路径):
  roles.py    — ui-designer execution_kind planning → executable; _UI_PROMPT 7 节;
                capabilities + workflow_stages(ux_ui) 同步; 别名 ui / UX/UI Designer /
                UX Designer → ui-designer (大小写不敏感)
  uxui.py     — UXUIDesignerAgent (Product → UXUIArtifact, mock provider 可注入,
                生产 DeepSeek v4-pro); 宽容 JSON 解析 (围栏剥离/整体解析/子串回退);
                缺 7 节字段/空节/垃圾输出 → UXUIDesignerError 响亮拒绝;
                wireframe.screens 深度校验 (每屏 Screen = name/ascii/components/
                actions); build_uxui_executor (Workflow executor 适配器, product
                解析链); 产物纯 JSON (ASCII 布局嵌 screens[].ascii, 不生成图片,
                不引入 Figma 等外部系统)
  projects.py — ArtifactType.UX_UI 枚举成员 (宽容解析)
  artifact.py — CONTRACTS ux_ui (7 节必填 + validation_rules: wireframe dict 必含
                screens / screen_specifications list / design_tokens dict 等)
约束: 不 import factory-org (Removal Isolation, 同 tester.py/pm.py); 不实现
Architect/Release Agent (S8-003~004); 零明文密钥; 零 Core 修改。
```

## 新增/修改文件

```
新增:
  factory-exec/exec/uxui.py                       (UXUIDesignerAgent/UXUIArtifact/
                                                  _local_validate/build_uxui_executor)
  tests/s8/test_s8_uxui_agent.py                  (27 测试: happy path 9 + 响亮拒绝 18)
  tests/s8/test_s8_uxui_contract.py               (23 测试: CONTRACTS ux_ui 校验/注册)
  tests/s8/test_s8_uxui_role.py                   (9 测试: executable/别名/org 双体系)
  tests/s8/test_s8_workflow_uxui.py               (10 测试: ux_ui stage Runner 接入/事件/失败)
  docs/sprint8/implementation/S8-002-report.md    (本报告)
修改 (只扩展, 不重写):
  factory-exec/exec/roles.py                      (ui-designer executable + prompt 7 节 +
                                                  UX/UI Designer 别名)
  factory-org/org/projects.py                     (ArtifactType UX_UI 枚举)
  factory-org/org/artifact.py                     (CONTRACTS ux_ui 类型)
  tests/s8/s8_helpers.py                          (uxui_json/product_payload_ok/mock provider)
  tests/exec/test_exec_roles.py / tests/s7/*      (executable_role_ids 断言同步扩展)
验证门: git diff factory-core/ factory-console/ factory-runtime/ desktop/ = 0
```

## Artifact Schema — ux_ui 7 节 (CONTRACTS)

| # | 字段 | 类型 | 校验规则 (org) | 深度校验 (exec 侧, 双体系一致) | 说明 |
|---|---|---|---|---|---|
| 1 | information_architecture | dict | min_keys 1 | 非空 dict | 信息架构 (screens 层级 + navigation) |
| 2 | user_flow | list | min_items 1 | 非空 list, 每项含 step/screen | 用户流程 (旅程 → 流程步骤) |
| 3 | wireframe | dict | min_keys 1 + required_keys [screens] | 非空 dict 含 screens; screens 非空 list, 每屏 Screen = {name, ascii, components, actions} (name/ascii 非空 str, components/actions 为 list) | 线框 (ASCII 布局文本, 机器可读, 不生成图片) |
| 4 | screen_specifications | list | min_items 1 | 非空 list, 每项含 screen/elements/behaviors/acceptance | 屏幕规格 (故事 → 验收) |
| 5 | component_definition | list | min_items 1 | 非空 list, 每项含 name/description/usage | 组件定义 |
| 6 | design_tokens | dict | min_keys 1 | 非空 dict | 设计规范 (colors/typography/spacing) |
| 7 | prototype | str | min_length 1 (strip) | 非空 str | 原型说明 (交互描述文本, 无外部工具依赖) |

```
契约校验: validate_artifact 纯函数 → missing/errors 响亮; ArtifactRegistry.validate
  通过 → VALIDATED / 失败 → INVALID (invalid_reason 落库 + org.artifact.failed 事件)
Screen 深度校验: 任务清单规定 Screen = {name, components[], actions[]}; 本实现
  ascii 为 ASCII 布局文本 (机器可读产物, 非图片) — 4 键全必含, 与 org CONTRACTS
  ux_ui (wireframe 必含 screens) 构成双体系: org 保结构, exec 保深度
```

## Prompt-Role 设计

```
roles.py _UI_PROMPT (角色注册表, S7-001 单一事实源):
  - execution_kind: planning → executable (is_executable=True)
  - prompt_template: 职责 = Product Artifact → UX/UI 设计 7 节 (IA/流程/线框/规格/
    组件/规范/原型), "严格 JSON, 仅输出 JSON"
  - workflow_stages: ("ux_ui",) — Workflow stage role_ref 接入点
  - capabilities: ui_design/prototyping (S8-002 新增)
  - 别名: resolve_role("ui") / "UX/UI Designer" / "UX Designer" → ui-designer

uxui.py _UXUI_AGENT_PROMPT (执行 prompt, 生产 provider = DeepSeek v4-pro):
  - Product 摘要前置: UX 消费 5 节 (user_persona/user_journey/feature_list/
    mvp_scope/user_stories) 排序在前, 其余节保留; 8K 字符截断防上下文撑爆
  - 7 节字段全覆盖 (每节带中文说明 + JSON 键名 + wireframe Screen 四键结构)
  - 输出约束: JSON 对象, 7 节字段齐全, 仅输出 JSON 不要多余文字
  - max_tokens 透传 (默认 4096)

executable_role_ids() 现为: [developer, product-manager, tester, ui-designer]
  (按 role_id 排序)
诚实标注: architect/devops 仍为 planning (S8-003~004 未实现, 不假装);
  release 无 exec 角色 (S8-004)
```

## Workflow 接入 (ux_ui stage)

```
定义: WorkflowLifecycle.create_stage(workflow_id, "ui-designer", name="ux_ui")
      — role_id 经 exec 注册表校验 (未注册立即 ValueError); stage_ids 索引 + DAG 拓扑
执行: WorkflowRunner (S7-003 复用, 零修改) + executor = build_uxui_executor(
      UXUIDesignerAgent) — executor 返回 {artifact_type: "ux_ui", ref:
      file:///docs/ux_ui.json, metadata(7 节)} → Runner 自动注册 create→generated
      →validated (CONTRACTS ux_ui 校验)
Product 解析链 (架构 §3): context inputs 的 product artifact metadata (契约载荷) >
  UXUIDesignerAgent 构造绑定 product > UXUIDesignerError (stage FAILED — 诚实,
  不臆造输入; 与 build_pm_executor idea 解析链同模式)
就绪判定: ux_ui stage input_artifacts = [product 产物 id] — product 未 VALIDATED
  → stage BLOCKED (Runner 现有语义零修改; 集成测试 test_blocks_until_product_validated)
事件链: org.workflow.created → started → stage_ready → stage_started →
  stage_completed → completed + org.artifact.created/validated
失败路径: 契约失败 / LLM 垃圾输出 / 无 product → stage FAILED → workflow FAILED
  (org.workflow.failed 带 stage_id; failed_reason 审计)
集成测试 10 个 (test_s8_workflow_uxui.py): 阶段定义 + Runner 执行 (happy path
  VALIDATED / 构造绑定 product 回退 / 事件链 payload / BLOCKED 就绪 / LLM 垃圾输出
  / product→ux_ui 全链动态接线)
```

## 测试结果

```
tests/s8: 127 passed, 0 failed (新增 69: uxui_agent 27 + uxui_contract 23 +
  uxui_role 9 + workflow_uxui 10)
修复的 30 个失败 (2 类):
  1. _UXUI_AGENT_PROMPT 字面花括号 {name, ascii, components[], actions[]} 被
     str.format(product=...) 误解析为占位符 → KeyError (29 测试连锁失败) →
     转义为 {{...}} (prompt 渲染输出不变) — 修实现
  2. resolve_role("UX/UI Designer") 未解析 (ROLE_ALIASES 缺 UX 别名) → 补
     "ux/ui designer" / "ux designer" → ui-designer — 修实现
测试分布:
  test_s8_uxui_agent.py      27  (happy path 9: 7 节全字段/围栏/散文包裹/覆盖绑定/
                                  5 节摘要/max_tokens/无图片; 响亮拒绝 18)
  test_s8_uxui_contract.py   23  (CONTRACTS ux_ui 校验/注册/INVALID 落库)
  test_s8_uxui_role.py       9   (executable/prompt/别名/org 双体系)
  test_s8_workflow_uxui.py   10  (ux_ui stage Runner 接入/事件/失败/全链)
pytest 全量: 6145 passed, 0 failed (6076 基线 + 69 新增)
执行: mock provider 注入 LLM 输出 (零真实 LLM 调用; 能力证明 = S8-005 真实 v4-pro);
Core/Console/Runtime/Desktop diff = 0
```

## S8-003 接入说明 (Architect 消费 product + ux_ui)

```
S8-003 前置依赖 (backlog: dep: S8-002): Architect Agent
  输入 = product Artifact (S8-001) + ux_ui Artifact (本任务输出) 双 VALIDATED
  → 输出 = design Artifact (架构 3 节: architecture/api/database, 既有 CONTRACTS)

接入方式 (架构 §3/§4, S7-003 复用, 与 S8-002 同模式):
  1. Workflow 阶段链: product → ux_ui → architecture → development → testing →
     release (AppLifecycleWorkflow; depends_on 链 + input/output artifacts + role_ref)
  2. architecture stage: role_id = architect (S8-003 升级 executable),
     input_artifacts = [product 产物 id, ux_ui 产物 id] — 就绪判定要求
     product AND ux_ui 均 VALIDATED (任一未验证 → stage BLOCKED, Runner 现有
     语义零修改; S8-002 已证明 ux_ui 产物经 CONTRACTS 校验落 VALIDATED)
  3. ux_ui 7 节中 Architect 消费重点: information_architecture (模块/边界 →
     架构分层) / screen_specifications (界面契约 → API 数据形状) /
     component_definition (复用组件 → 架构组件边界) / design_tokens (视觉规范 →
     UI 层实现约束)
  4. 执行: build_arch_executor 适配器 (模式同 build_uxui_executor / build_pm_executor)
     → Runner 自动注册 design 产物 → CONTRACTS design 校验 → VALIDATED
     (契约失败 → stage FAILED)
  5. 事件: org.workflow.stage_* 复用 (无新事件类型 — 只扩展枚举: CONTRACTS
     design 已存在 (S7 既有), 无需新增契约; ArtifactType.DESIGN 已存在)
  6. Release (S8-004) 输入 = 全链产物 (design/code/test), 与 Architect 无关
```

## 当前限制 (诚实标注)

```
1. Architect / Release Agent 未实现 (S8-003~004): 对应角色 execution_kind=planning
   (不假装可执行); architect/devops 场景已由 test 断言标注 (test_architect_devops_
   still_planning)
2. UXUIDesignerAgent 生产 provider 为 DeepSeek v4-pro, 但本任务测试全部注入 mock
   (零真实 LLM 调用) — 真实 v4-pro 能力证明留待 S8-005 全链 Demo
3. wireframe Screen 深度校验在 exec 侧 (org CONTRACTS 只保 wireframe 含 screens 键)
   — 双体系一致 (同 S8-001 str strip 判空策略), 有意为之: org 契约保持结构级,
   exec 深度校验防垃圾产物入库
4. ROLE_OUTPUT_TYPES 默认 (ui-designer → design) 保持向后兼容 S7-005 demo;
   build_uxui_executor 显式声明 artifact_type="ux_ui" (不覆盖默认)
5. ux_ui 产物纯 JSON 结构化文本 (ASCII 布局嵌 screens[].ascii) — 无图片生成、
   无 Figma 集成 (任务约束, 非缺失)
```

## 验证门

```
pytest 全量:   6145 passed, 0 failed (180s)
tests/s8:      127 passed, 0 failed
Core diff:     factory-core/ = 0      (events 枚举未动 — ADR-0001 扩展路径)
Runtime diff:  factory-runtime/ = 0
Console diff:  factory-console/ = 0
Desktop diff:  desktop/ = 0
scripts_diag_empty.py: 未触碰
```
