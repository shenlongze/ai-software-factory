# S8-003 — Architect Agent（Completion Report）

> 日期: 2026-08-09 | 状态: 完成 (待人工审核) | pytest 6204 (6145 + 59)
> 目标: Architect Agent executable — Product + UX/UI 双 Artifact → 结构化 Design Artifact (7 节),
> CONTRACTS design 7 节强化, Workflow architecture stage 接入 (role_ref=architect),
> artifact_refs 强引用 (设计产物溯源输入产物 id), 只扩展不重写 (Core/Runtime/Console/Desktop diff = 0)

## 实现概述

```
S8-003 把 Architect 从 planning 角色升级为 executable (真实 LLM 执行路径):
  roles.py    — architect execution_kind planning → executable; _ARCH_PROMPT 7 节
                (system_architecture/technical_stack/database_design/api_design/
                frontend_architecture/backend_architecture/task_breakdown, 每项含
                module/task/api_contract/ui_guidance — Developer 消费);
                capabilities/workflow_stages 同步; executable_role_ids 现为
                [architect, developer, product-manager, tester, ui-designer]
  architect.py — (新建) ArchitectAgent (Product + UX/UI Artifact → DesignArtifact,
                双输入强校验: 构造缺任一输入 → ArchitectError 响亮, 禁止脱离输入
                独立生成 — 架构师不能凭空设计); 宽容 JSON 解析 (围栏剥离/整体解析/
                子串回退); 缺 7 节字段/空节/api_design 缺 endpoints/task_breakdown
                深度结构 (module/task/api_contract/ui_guidance) → ArchitectError
                响亮拒绝 (不伪造技术设计); 本地校验 exec 侧同 CONTRACTS 规则
                (Removal Isolation, 零 import factory-org); build_arch_executor
                (Workflow executor 适配器, context inputs 解析 product + ux_ui
                产物 id → metadata.artifact_refs = [product_id, ux_ui_id] 强引用;
                context 缺任一输入产物 → ArchitectError, stage FAILED)
  artifact.py — CONTRACTS design 由 3 字段 (architecture/api/database) 强化为 7 节
                必填 + validation_rules (task_breakdown list 非空; api_design dict
                必含 endpoints; 其余 str/dict 非空)
  demo.py     — _DEMO_DESIGN_METADATA 同步 7 节 (demo mock 占位, 非 LLM)
约束: 不 import factory-org (Removal Isolation, 同 tester.py/pm.py/uxui.py);
不实现 Release Agent (S8-004); 零明文密钥; 零 Core 修改。
```

## 新增/修改文件

```
新增:
  factory-exec/exec/architect.py                     (ArchitectAgent/DesignArtifact/
                                                     _local_validate/_validate_endpoints/
                                                     _validate_tasks/build_arch_executor/
                                                     _artifact_from_context — 495 行)
  tests/s8/test_s8_arch_agent.py                     (26 测试: 双输入强校验 4 + happy path 7
                                                     + 响亮拒绝 10 + 本地校验 3 + executor 强引用 2)
  tests/s8/test_s8_arch_role.py                      (10 测试: executable/prompt 7 节/JSON/
                                                     Developer 消费/stage 映射/诚实标注)
  tests/s8/test_s8_design_contract.py                (21 测试: CONTRACTS design 声明/校验/
                                                     Registry VALIDATED-INVALID/消费准备)
  docs/sprint8/implementation/S8-003-report.md       (本报告)
修改 (只扩展, 不重写):
  factory-exec/exec/roles.py                         (architect executable + _ARCH_PROMPT 7 节
                                                     + module/task/api_contract/ui_guidance 字面键)
  factory-org/org/artifact.py                        (CONTRACTS design 7 节强化)
  factory-org/org/demo.py                            (_DEMO_DESIGN_METADATA 7 节同步)
  tests/s8/s8_helpers.py                             (design_payload_ok/design_json/
                                                     make_product_artifact/make_uxui_artifact)
  tests/s8/test_s8_pm_role.py / test_s8_uxui_role.py (architect executable 断言同步)
  tests/exec/test_exec_roles.py / tests/s7/*         (executable_role_ids 断言同步扩展;
                                                     design 契约回归: 旧 3 字段断言重构为 7 节
                                                     + 2 净增 — 全量 59 = s8 57 + s7 2)
验证门: git diff factory-core/ factory-console/ factory-runtime/ desktop/ = 0
```

## Architect Artifact Schema — design 7 节 (CONTRACTS)

| # | 字段 | 类型 | 校验规则 (org) | 深度校验 (exec 侧, 双体系一致) | 说明 |
|---|---|---|---|---|---|
| 1 | system_architecture | str | min_length 1 (strip) | 非空 str | 系统架构 (分层/模块边界/数据流) |
| 2 | technical_stack | dict | min_keys 1 | 非空 dict | 技术选型 (语言/框架/存储等) |
| 3 | database_design | dict | min_keys 1 | 非空 dict | 数据库设计 (模型/表结构) |
| 4 | api_design | dict | min_keys 1 + required_keys [endpoints] | 非空 dict 含 endpoints; endpoints 非空 list, 每项 endpoint = {method, path, contract} (method/path 非空 str) | API 设计 (endpoints = API 约定, 供 S8-005 Developer 消费) |
| 5 | frontend_architecture | str | min_length 1 (strip) | 非空 str | 前端架构 (目录/组件边界, 依据 UX/UI 产物) |
| 6 | backend_architecture | str | min_length 1 (strip) | 非空 str | 后端架构 (服务/模块) |
| 7 | task_breakdown | list | min_items 1 | 非空 list, 每项 task = {module, task, api_contract, ui_guidance} (全非空 str) | 任务拆分 (模块/技术任务/API 约定/UI 实现指导 — Developer 直接消费) |

```
契约校验: validate_artifact 纯函数 → missing/errors 响亮; ArtifactRegistry.validate
  通过 → VALIDATED / 失败 → INVALID (invalid_reason 落库 + org.artifact.failed 事件)
深度校验策略 (同 S8-001/002): org 契约保结构 (api_design 必含 endpoints 键 /
  task_breakdown 非空 list), exec 侧 _local_validate 保深度 (endpoints 每项
  method/path/contract; task_breakdown 每项 module/task/api_contract/ui_guidance)
  — 双体系一致, 防垃圾产物入库, 为 S8-005 Developer 消费准备
S8-002 接入说明预言的 3 字段 design (architecture/api/database) 已按 sprint8
  architecture 升级为 7 节 — demo.py mock 载荷同步迁移
```

## Agent 设计 (ArchitectAgent: 双输入 + artifact_refs 强引用)

```
roles.py _ARCH_PROMPT (角色注册表, S7-001 单一事实源):
  - execution_kind: planning → executable (is_executable=True)
  - prompt_template: 职责 = Product + UX/UI → 技术设计 7 节 (每节带 JSON 键名;
    task_breakdown 字面键 module/task/api_contract/ui_guidance — Developer 消费)
  - workflow_stages: ("architecture",) — Workflow stage role_ref 接入点
  - capabilities: architecture/design (S8-003 新增)

architect.py (执行, 生产 provider = DeepSeek v4-pro, 测试注入 mock):
  双输入强校验 (本任务硬性要求 — 架构师不能凭空设计):
    - 构造: product + ux_ui 必须同时存在 (任一缺失/空 dict/非 dict →
      ArchitectError 响亮, "禁止脱离 product + ux_ui 独立生成")
    - set_product/set_ux_ui 同样拒绝空输入 (不变量全入口生效)
    - design(product=None, ux_ui=None) 解析链: 方法显式参数 > 构造绑定
      (先解析再校验 — 参数缺省回退绑定值)
    - build_arch_executor: context inputs 缺任一输入产物 → ArchitectError
      (即使 agent 构造已绑定 payload, executor 仍要求 context 输入 id 强引用)
  artifact_refs 强引用 (本任务硬性要求 — 审计/溯源):
    - executor 从 context inputs 解析 product/ux_ui 产物 id →
      metadata["artifact_refs"] = [product_id, ux_ui_id] (设计产物显式引用
      输入产物; 附加键不破坏 CONTRACTS 契约, test_design_artifact_refs_passthrough)
  LLM 输出消费 (同 pm/uxui 模式):
    - 宽容解析: markdown 围栏剥离 → 整体解析 → 子串回退 ({})
    - 响亮拒绝: 非 JSON / 非对象 / 缺 7 节字段 / 空节 / api_design 缺 endpoints /
      endpoints 深度 / task_breakdown 深度 → ArchitectError (不假装生成成功)
    - 双输入消费证明: prompt 含 product (功能/MVP/故事) + ux_ui (信息架构/屏幕/
      组件/设计规范) 内容; 各自 8K 字符截断防上下文撑爆
    - max_tokens 透传 (默认 4096); provider 缺失/调用失败 → ArchitectError

executable_role_ids() 现为: [architect, developer, product-manager, tester,
  ui-designer] (按 role_id 排序)
诚实标注: devops 仍为 planning (S8-004 Release 未实现, 不假装); S7-005 Demo
  的 architect 阶段仍注入 mock 占位 (Demo 零 LLM, mock 与注册表 execution_kind 分离)
```

## Workflow 接入 (architecture stage)

```
定义: WorkflowLifecycle.create_stage(workflow_id, "architect", name="architecture")
      — role_id 经 exec 注册表校验 (未注册立即 ValueError); ROLE_OUTPUT_TYPES
      architect→design 默认保持 (向后兼容 S7-005 demo), build_arch_executor 显式
      声明 artifact_type="design"
执行: WorkflowRunner (S7-003 复用, 零修改) + executor = build_arch_executor(
      ArchitectAgent) — executor 返回 {artifact_type: "design", ref:
      file:///docs/design.json, metadata(7 节 + artifact_refs)} → Runner 自动注册
      create→generated→validated (CONTRACTS design 7 节校验)
双输入就绪判定 (S8-002 接入说明 §1/§2): architecture stage input_artifacts =
      [product 产物 id, ux_ui 产物 id] — product AND ux_ui 均须 VALIDATED,
      任一未验证 → stage BLOCKED (Runner 现有就绪语义零修改; S8-002 已证明
      product/ux_ui 产物经 CONTRACTS 校验落 VALIDATED)
输入解析链 (架构 §3): context inputs 的 product/ux_ui 产物 metadata (契约载荷) →
      agent.design(product, ux_ui); 缺任一输入产物 → ArchitectError (stage FAILED
      — 诚实, 禁止脱离输入独立生成, 即使 agent 构造已绑定 payload)
事件链: org.workflow.created → started → stage_ready → stage_started →
      stage_completed → completed + org.artifact.created/validated
失败路径: 契约失败 / LLM 垃圾输出 / 缺双输入 → stage FAILED → workflow FAILED
      (org.workflow.failed 带 stage_id; failed_reason 审计)
无新事件类型 (org.workflow.stage_* 复用); 无新 ArtifactType (ArtifactType.DESIGN
      S7 既有) — 只扩展 CONTRACTS design 契约 (7 节), 不新增枚举
```

## 测试结果

```
tests/s8: 184 passed, 0 failed (127 基线 + 57 新增)
新增 57: test_s8_arch_agent 26 + test_s8_arch_role 10 + test_s8_design_contract 21
修复的 21 个失败 (4 类):
  1. architect.py design() 解析链死代码 (16 测试连锁失败): 原实现
     _require_input("product", product) or self._product — 方法参数缺省为 None
     时 _require_input 直接抛 ArchitectError, or 回退 (构造绑定) 永不生效 →
     改为"先解析再校验" (参数 if not None else 构造绑定) — 修实现
  2. _ARCH_PROMPT 缺字面键 api_contract/ui_guidance (1 失败): task_breakdown
     描述只有中文"模块/API 约定/UI 实现指导" → 补字面键 (与 design 契约键同源,
     Developer 消费断言) — 修实现
  3. test_s8_design_contract TestRegistryDesign 未预建项目 (3 失败): 用
     project_id fixture (conftest 预建 P-8) — 修测试
  4. 旧断言 architect 仍 planning (1 失败): test_s8_pm_role
     test_architect_devops_still_planning → 拆分为 architect executable +
     devops planning — 旧断言更新
  另: test_missing_required_fields 经 design_json(**payload) 无法表达"删除字段"
     (override 只增改) → 直接 json.dumps 序列化缺字段载荷 — 修测试表达
全量断言同步 (同 S8-002 惯例): tests/exec/test_exec_roles.py
  test_four_roles_executable → test_five_roles_executable (architect 入 executable
  集); tests/s7/test_s7_full_chain_demo.py test_planning_roles_are_mocked
  (architect executable, Demo 仍 mock, devops planning);
  tests/s7/test_s7_artifact_contract.py: 旧 3 字段 design 断言
  (test_design_missing_database) 重构为 7 节 (test_design_missing_task_breakdown)
  + 2 个 design 规则回归 (net +2); test_s8_uxui_role/test_s8_pm_role 同步
pytest 全量: 6204 passed, 0 failed (6145 基线 + 59 新增 = s8 57 + s7 2)
执行: mock provider 注入 LLM 输出 (零真实 LLM 调用; 能力证明 = S8-005 真实 v4-pro);
Core/Console/Runtime/Desktop diff = 0
```

## S8-004 Release 接入说明

```
前置 (backlog: dep: S8-003): Release Agent (devops 角色升级 executable)
  输入 = 全链产物: product (S8-001) + ux_ui (S8-002) + design (本任务) + code/test
  (S8-005) — 与 Architect 无直接依赖 (Release 消费设计产物, 不消费 Architect 双输入)

接入方式 (架构 §3/§4, S7-003 复用, 与 S8-003 同模式):
  1. Workflow 阶段链: product → ux_ui → architecture → development → testing →
     release (AppLifecycleWorkflow; depends_on 链 + input/output artifacts +
     role_ref; architecture stage 已由本任务接入)
  2. release stage: role_id = devops (S8-004 升级 executable),
     input_artifacts = [design 产物 id, code 产物 id, test 产物 id] — 就绪判定
     要求全链产物 VALIDATED (任一未验证 → stage BLOCKED, Runner 现有语义零修改;
     本任务已证明 design 产物经 CONTRACTS 7 节校验落 VALIDATED)
  3. design 7 节中 Release 消费重点: system_architecture/backend_architecture/
     task_breakdown (部署单元/构建顺序/模块清单) — 无需新契约字段
  4. 执行: build_release_executor 适配器 (模式同 build_arch_executor) → Runner
     自动注册 release 产物 → CONTRACTS release 校验 → VALIDATED (契约失败 →
     stage FAILED)
  5. 事件: org.workflow.stage_* 复用 (无新事件类型); 产物类型: code/test/release
     CONTRACTS 均 S7 既有, 无需新增契约; ArtifactType 枚举已含
  6. 诚实边界: S8-004 完成前 devops execution_kind=planning (不假装), release
     stage 无 executor → 运行即 FAILED (响亮, 与未知角色同语义)

本任务不实现 Release Agent (S8-004 范围外) — 只保证 design 7 节契约与
  artifact_refs 溯源为该链路就绪
```

## 当前限制 (诚实标注)

```
1. Release Agent 未实现 (S8-004): devops execution_kind=planning (不假装可执行);
   architect/devops 场景已由 test 断言标注 (test_architect_executable_devops_
   still_planning / test_planning_roles_are_mocked)
2. ArchitectAgent 生产 provider 为 DeepSeek v4-pro, 但本任务测试全部注入 mock
   (零真实 LLM 调用) — 真实 v4-pro 能力证明留待 S8-005 全链 Demo
3. endpoints/task_breakdown 深度校验在 exec 侧 (org CONTRACTS 只保结构:
   api_design 含 endpoints 键 / task_breakdown 非空 list) — 双体系一致
   (同 S8-001/002 策略), 有意为之: org 契约保持结构级, exec 深度校验防垃圾产物
4. ROLE_OUTPUT_TYPES 默认 (architect→design) 保持向后兼容 S7-005 demo;
   build_arch_executor 显式声明 artifact_type="design" (不覆盖默认)
5. S7-005 Demo 的 architect 阶段仍为 mock 占位 (Demo 零 LLM, 不随注册表升级) —
   mock 与角色 execution_kind 分离, 诚实标注
```

## 验证门

```
pytest 全量:   6204 passed, 0 failed (150s)
tests/s8:      184 passed, 0 failed
Core diff:     factory-core/ = 0
Runtime diff:  factory-runtime/ = 0
Console diff:  factory-console/ = 0
Desktop diff:  desktop/ = 0
scripts_diag_empty.py: 未触碰
```
