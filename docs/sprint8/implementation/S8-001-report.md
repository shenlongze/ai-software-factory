# S8-001 — PM Agent（Completion Report）

> 日期: 2026-08-09 | 状态: 完成 (待人工审核) | pytest 6076 (6018 + 58)
> 目标: Product Manager Agent executable — Idea → 结构化 Product Artifact (7 节),
> CONTRACTS product/idea 类型, Workflow product stage 接入 (role_ref=product-manager),
> 只扩展不重写 (Core/Runtime/Desktop diff = 0)

## 实现概述

```
S8-001 把 Product Manager 从 planning 角色升级为 executable (真实 LLM 执行路径):
  roles.py    — product-manager execution_kind planning → executable; _PM_PROMPT 7 节;
                capabilities + workflow_stages(product) 同步; 别名 pm → product-manager
  pm.py       — PMAgent (Idea → ProductArtifact, mock provider 可注入, 生产 DeepSeek
                v4-pro); 结构化 JSON 解析 (围栏剥离/子串回退); 垃圾输出响亮拒绝;
                build_pm_executor (Workflow executor 适配器, idea 解析链)
  projects.py — ArtifactType.PRODUCT / IDEA 枚举成员 (宽容解析)
  artifact.py — CONTRACTS product (7 节必填 + validation_rules) + idea (自然语言);
                str 非空校验按 strip 判定 (与 exec 侧 _local_validate 同规则)
约束: 不 import factory-org (Removal Isolation, 同 tester.py); 不实现
UX/UI/Architect/Release Agent (S8-002~004); 零明文密钥; 零 Core 修改。
```

## 新增/修改文件

```
新增:
  factory-exec/exec/pm.py                       (PMAgent/ProductArtifact/build_pm_executor)
  tests/s8/                                     (58 测试: conftest/s8_helpers/
                                                test_s8_pm_role / test_s8_pm_agent /
                                                test_s8_product_contract /
                                                test_s8_workflow_product)
  docs/sprint8/implementation/S8-001-report.md  (本报告)
修改 (只扩展, 不重写):
  factory-exec/exec/roles.py                    (PM executable + prompt 7 节 + 别名)
  factory-org/org/projects.py                   (ArtifactType PRODUCT/IDEA 枚举)
  factory-org/org/artifact.py                   (CONTRACTS product/idea + str strip 判空)
  tests/exec/test_exec_roles.py / tests/s7/*    (executable_role_ids 断言同步扩展)
验证门: git diff factory-core/ factory-console/ factory-runtime/ desktop/ = 0
```

## Artifact Schema — product 7 节 (CONTRACTS)

| # | 字段 | 类型 | 校验规则 | 说明 |
|---|---|---|---|---|
| 1 | market_analysis | str | min_length 1 (strip) | 市场分析 (目标市场/竞争/机会) |
| 2 | user_persona | str | min_length 1 (strip) | 用户画像 (目标用户/特征/痛点) |
| 3 | user_journey | str | min_length 1 (strip) | 用户旅程 (关键场景/步骤/触点) |
| 4 | problem_statement | str | min_length 1 (strip) | 问题定义 (核心问题/影响) |
| 5 | feature_list | list | min_items 1 | 功能清单 (每项一个功能) |
| 6 | mvp_scope | dict | min_keys 1 + required_keys [in, out] | MVP 范围 (范围内/范围外边界) |
| 7 | user_stories | list | min_items 1 | 用户故事 (as-a/i-want/so-that) |

```
idea 类型 (PM 阶段输入): required_fields (idea,), 规则 {type: str, min_length 1}
契约校验: validate_artifact 纯函数 → missing/errors 响亮; ArtifactRegistry.validate
  通过 → VALIDATED / 失败 → INVALID (invalid_reason 落库 + org.artifact.failed 事件)
str 非空语义: min_length 按 strip 后长度判定 — 纯空白视为空串, 与 exec 侧
  _local_validate 同规则 (双体系一致; 本次修复的 1 个实现 bug)
```

## Prompt-Role 设计

```
roles.py _PM_PROMPT (角色注册表, S7-001 单一事实源):
  - execution_kind: planning → executable (is_executable=True)
  - prompt_template: 职责 = 想法 → 产品分析, 7 节字段全覆盖, "严格 JSON, 仅输出 JSON"
  - workflow_stages: ("product",)  — Workflow stage role_ref 接入点
  - capabilities: requirement/planning + product_analysis (S8-001 新增)
  - 别名: resolve_role("pm") → product-manager (大小写不敏感)

pm.py _PM_AGENT_PROMPT (执行 prompt, 生产 provider = DeepSeek v4-pro):
  - 想法 → 7 节产品分析 (每节带中文说明 + JSON 键名)
  - 输出约束: JSON 对象, 7 节字段齐全, 仅输出 JSON 不要多余文字
  - max_tokens 透传 (默认 4096)

executable_role_ids() 现为: [developer, product-manager, tester] (按 role_id 排序)
诚实标注: ui-designer/architect/devops 仍为 planning (S8-002~004 未实现, 不假装)
```

## Workflow 接入 (product stage)

```
定义: WorkflowLifecycle.create_stage(workflow_id, "product-manager", name="product")
      — role_id 经 exec 注册表校验 (未注册立即 ValueError); stage_ids 索引 + DAG 拓扑
执行: WorkflowRunner (S7-003 复用, 零修改) + executor = build_pm_executor(PMAgent)
      — executor 返回 {artifact_type: "product", ref, metadata(7 节)} → Runner 自动
      注册 create→generated→validated (CONTRACTS product 校验)
Idea 解析链 (架构 §2): context inputs 的 idea artifact metadata.idea >
  PMAgent 构造绑定 idea > ProductManagerError (stage FAILED — 诚实, 不臆造输入)
事件链: org.workflow.created → started → stage_ready → stage_started →
  stage_completed → completed + org.artifact.created/validated
失败路径: 契约失败 / LLM 垃圾输出 / 无 idea → stage FAILED → workflow FAILED
  (org.workflow.failed 带 stage_id; failed_reason 审计)
集成测试 8 个 (test_s8_workflow_product.py): 阶段定义 ×2 + Runner 执行 ×6
  (happy path VALIDATED / idea 输入解析链 / 事件链 payload / 契约失败 / 无 idea /
  LLM 垃圾输出)
```

## 测试结果

```
tests/s8: 58 passed, 0 failed (原 50 + 新增 Workflow 集成 8)
修复的 5 个失败 (test_s8_product_contract.py):
  1. _seed_stage 导入错误: ProjectLifecycle 位于 org.projects (非 org.lifecycle) → 修测试
  2. str 非空语义: "   " (纯空白) 应判空 → 修实现 (org 校验 strip 后判 min_length,
     与 exec 侧 _local_validate 同规则; 其余 4 个 Registry 失败同因导入错误)
测试分布:
  test_s8_pm_role.py            9   (executable/prompt 7 节/JSON 约束/别名/org 双体系)
  test_s8_pm_agent.py           19  (Idea→Product 解析/结构化/垃圾拒绝/契约)
  test_s8_product_contract.py   22  (CONTRACTS product/idea 校验/注册)
  test_s8_workflow_product.py   8   (product stage Runner 接入/事件/失败路径)
pytest 全量: 6076 passed, 0 failed (6018 基线 + 58 新增)
执行: mock provider 注入 LLM 输出 (零真实 LLM 调用; 能力证明 = S8-005 真实 v4-pro);
Core/Console/Runtime/Desktop diff = 0
```

## S8-002 接入说明 (UX/UI Designer 消费 product)

```
S8-002 前置依赖 (backlog: dep: S8-001): UX/UI Designer Agent executable
  输入 = product Artifact (本任务输出) → 输出 = ux_ui Artifact (7 节:
  information_architecture / user_flow / wireframe / screen_specification /
  ui_component_definition / design_token / prototype_description)

接入方式 (架构 §3/§4, S7-003 复用):
  1. Workflow 阶段链: product → ux_ui → architecture → development → testing → release
     (AppLifecycleWorkflow; depends_on 链 + input/output artifacts + role_ref)
  2. ux_ui stage: role_id = ui-designer (executable, roles.py S8-002 升级),
     input_artifacts = [product artifact id] — 就绪判定要求 product VALIDATED
     (未验证 → BLOCKED, Runner 现有语义零修改)
  3. Product 7 节中 UX 消费重点: user_persona (画像驱动界面决策) /
     user_journey (流程 → user_flow) / feature_list (功能 → IA 与 screen) /
     mvp_scope (优先级 → 线框范围) / user_stories (场景 → screen_spec 验收)
  4. 执行: build_uxui_executor 适配器 (模式同 build_pm_executor) → Runner 自动注册
     ux_ui 产物 → CONTRACTS ux_ui 校验 → VALIDATED (契约失败 → stage FAILED)
  5. 事件: org.workflow.stage_* 复用 (无新事件类型 — 只扩展枚举: ux_ui ArtifactType +
     CONTRACTS ux_ui 条目, 单点扩展路径)
  6. Architect (S8-003) 输入 = product + ux_ui 双 VALIDATED 产物 (id 引用)
```

## 当前限制 (诚实标注)

```
1. UX/UI Designer / Architect / Release Agent 未实现 (S8-002~004): 对应角色
   execution_kind=planning (不假装可执行); UI Designer 场景已由 test 断言标注
2. PMAgent 生产 provider 为 DeepSeek v4-pro, 但本任务测试全部注入 mock
   (零真实 LLM 调用) — 真实 v4-pro 能力证明留待 S8-005 全链 Demo
3. ROLE_OUTPUT_TYPES 默认 (product-manager → prd) 保持向后兼容 S7-005 demo;
   build_pm_executor 显式声明 artifact_type="product" (不覆盖默认)
```

## 验证门

```
pytest 全量:   6076 passed, 0 failed (150s)
tests/s8:      58 passed, 0 failed
Core diff:     factory-core/ = 0      (events 枚举未动 — ADR-0001 扩展路径)
Runtime diff:  factory-runtime/ = 0
Console diff:  factory-console/ = 0
Desktop diff:  desktop/ = 0
scripts_diag_empty.py: 未触碰
```
