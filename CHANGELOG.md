# Changelog

> AI Software Factory — 变更日志 (Keep a Changelog 风格, 中文)。
> 版本语义: `v1.0.0-rc1` 为 v1.0 发布候选 (Release Candidate), 功能冻结, 只做文档与修复。

---

## [v1.1.22] — 2026-08-24

**产品发现引导体验**（S10-101）: 确定性进度/生命周期 + 中间字段智能追问 + 求助建议填入 —
conversation 与 DiscoverySession 两路径同步。

### Added

- **共享引导模块**（新 `session/discovery_guide.py`）— 两路径唯一来源:
  - `lifecycle_line` 生命周期行（发现→确认→创建→PRD→工程→开发, 当前阶段 `[ ]` 标出）+
    `format_progress` 必填进度（"产品定义 X/3: 字段✅/待填", 用 FIELD_LABELS 中文名）—
    纯状态计算, 无 LLM 也显示（确定性）
  - `enhanced_line` DiscoverySession 增强字段可选提示（使用场景/MVP范围/非功能要求, 已填 ✅,
    无待填省略）
  - `HELP_KEYWORDS` 求助关键词确定性硬闸 + `DEFAULT_SUGGESTIONS` 每字段确定性建议
    （无 LLM 兜底 — 诚实降级, 非伪造 LLM）
- **analyzer 契约扩展**（`discovery_intelligence.py`）— `VALID_CATEGORIES` += `help_request`
  （优先级: 控制指令 > 查询 > 求助 > 字段回答 > 产品描述）; 输出契约 += `suggestions`
  {field, items, note}; field_answer 时若还有必填缺失 → `smart_questions` 给出下一个最重要
  缺失字段的追问（带理由）
- **两路径集成**（`conversation.py` + `discovery.py`, 对称）:
  - 每个发现阶段消息前缀 `lifecycle_line` + `format_progress`（批量/编辑/重问等分支统一）;
    READY 3/3 + current=确认
  - 求助流: HELP_KEYWORDS 硬闸（LLM 前）→ LLM `help_request` + suggestions / 默认建议
    → 展示 → 挂起 proposal {field, items} → 用户 y 全填 / 1-3 单选 / 自定义填入 → 进度更新;
    求助输入绝不当字段内容收下
  - 中间字段: field_answer apply 后下一问优先 `analysis.smart_questions[0]`（带理由）,
    空/失败 → 机械模板; system_question 多轮合并（v1.1.19）保持不变

### 测试

- 新 `tests/console/test_discovery_guide.py` 43 用例（计划 §2 契约点 1-9: 进度确定性/推进/
  中间字段智能/求助 LLM+关键词兜底/不当字段/选择自定义/无 LLM 零变化语义/两路径一致 +
  模块单元）
- 两路径新增用例: `test_discovery_llm_intelligence.py`（+4 求助流/中间字段）·
  `test_discovery_session_llm.py`（+4 同）
- 既有测试更新（仅精确消息断言, 逐条记录）:
  - `test_discovery_llm_intelligence.py::test_prompt_contains_priority_and_history` —
    prompt 优先级有意变更（求助 > 字段回答）
  - `test_discovery_session_llm.py::test_field_answer_fills_current_only` —
    消息断言更新为 S10-101 进度前缀格式
- 全量 console 回归: 4826 passed / 1 skipped / 0 新增失败（7 个既有环境类失败为沙箱写
  ~/.factory/端口检测/wheel 构建, 沙箱外全绿）

### Fixed

- **DiscoverySession 首问进度前缀**（S10-101 验收修复）: `_guide_message` 幂等（body 已带
  `流程:` 生命周期行 → 原样返回）+ `_next_question()` 统一装饰 `question` — `start()`
  `questions[0].question` / `actions.discovery_start` 渲染与 conversation 路径同步带进度/
  生命周期前缀; `_last_system_question`/`_llm_question_text` 保持原始问题（LLM
  system_question 上下文干净, 不双重前缀）


**DiscoverySession 同步 LLM 化**（S10-100）: "开始做X/我想做X" 发现路径与 conversation 路径行为对齐 —
LLM 一次产出 + 智能追问 + 理解摘要 + 主动分析, 无 LLM 规则兜底（逐字段零变化）。

### Added

- **DiscoverySession LLM 集成**（`discovery.py`）— 复用 `DiscoveryIntentAnalyzer`（同 conversation 模式）
  - `start("开始做个记账App")` → LLM 提取 7 字段一次填 → 必填齐直达 READY /
    缺则智能追问 1 条（带 "为什么还问" 理由）
  - `process_user_input` LLM 分流: product_description 提取合并（只填缺失不覆盖, v1.1.19 边界）·
    field_answer 并入既有 apply（当前字段）· control(取消类) → cancel ·
    control(非取消)/query → 不当作字段重问当前问题（模型层不逃生）
  - 确认门: 理解摘要首行 + 需求摘要 + 建议名称候选 + 主动建议 + 确认提示（ai_generated 诚实标记）;
    无 LLM → 现有消息逐字节不变
  - 命名 LLM-gated: 临时名 + analyzer 可用 → suggest_names 候选1设名 + 展示候选;
    无 LLM → 临时名保留
  - 持久化: to_dict/from_dict 新增 `_last_system_question/_ai_generated/_understanding/_proactive`
    （旧会话文件缺省兼容, 不崩）
- **analyzer 契约扩展**（`discovery_intelligence.py`）— `EXTRACTION_FIELDS` +=
  `usage_scenarios/mvp_scope/non_functional_requirements`（可选键, 明确提到才填, 否则留空）;
  prompt 输出 schema 同步 + 规则行; 归一化补默认; conversation 路径只读 5 键, 零行为变化

### 测试

- `tests/console/test_discovery_session_llm.py` 26 用例（一次产出/智能追问带理由/回答并入不覆盖/
  理解摘要+主动分析/无 LLM 零变化/控制查询不当字段/非法输出降级/持久化 round-trip/命名/analyzer 扩展）
- 既有 108 discovery + 35 analyzer + conversation 契约测试 0 破



**LLMIntentParser — 普通对话 LLM 理解意图**（S10-046 §3 Q1 预留扩展点落地）: 每轮对话 LLM 介入。

### Added

- **LLMIntentParser**（`llm_intent.py`）— 自然语言 → LLM 理解 → 注册意图类型 + 参数
  - 只映射注册意图（安全边界, 不生成任意命令）· 低置信(<0.4)/unknown → None
  - 无 key/LLM 失败/非法 JSON → None（规则兜底, 诚实降级）
- **会话装配**（`session.py`）— intent_parser 默认 LLM + `_rule_parser` 规则兜底
  - 真实 LLM 验证: "建个公司叫测试科技"→org_manage · "查一下现在有哪些项目"→list_projects
    "帮我修一下登录的bug"→run_task · "把记账项目挂到财务部"→org_manage
- 纯命令 (/help) 仍走 slash（不该 LLM）

### 测试

- `tests/console/test_llm_intent_parser.py` 8 用例（理解/unknown/安全边界/低置信/无key/失败/非法JSON/code fence）
- 32 相关 passed（无破坏）


**发现阶段多轮字段合并边界修复**（S10-099 遗留改进）: 用户对智能追问的回答被 LLM 当成新产品描述覆盖字段。

### Fixed

- **prompt 注入"系统上一轮问题"**（`discovery_intelligence.py`）— LLM 知道"本轮是对上一问题的回答"→ category=field_answer, 只填对应字段, 不当作新描述
- **conversation 记录追问轮次**（`conversation.py`）— `_last_system_question` 在智能/机械追问时记录, 传入 analyze; 新发现重置
- 验证: "手机上没有顺手又好看的 markdown 编辑器" → 并入 problem, 不再覆盖 name（真实 LLM 实测）

### 测试

- `test_discovery_llm_intelligence.py` +2 用例（system_question 注入 + 回答并入不覆盖）→ 35 passed


**组织管理对话接入**: "建个公司/建部门/把项目挂到部门" → LLM 理解 + 规则兜底 → org CLI（§1.4.5）。

### Added

- **org_manage action**（`actions.py`）— 自然语言组织操作 → 操作序列 → org CLI (create+link)
  - LLM 理解复合句（"成立软件公司建个后端部门" → 多操作序列）
  - 规则兜底（无 LLM/key: 建公司/建部门/挂项目 关键词）
  - 未识别 → 明确请求澄清（不猜测）
- **INTENT_ORG_MANAGE**（`intent.py`）— 建公司/建部门/挂项目 关键词规则
- **路由**（`router.py`）— org_manage → org_manage action

### 测试

- `tests/console/test_org_manage_action.py` 7 用例（意图/路由/规则落盘/未识别）
- 无 LLM 诚实降级（规则兜底, 不伪造理解）


**统一 create 入口**: `factory create <type>` 包装 company/department/project — 便捷铁律落地（§1.4.5）。

### Added

- **`factory create company|department|project`**（`cli_factory.py`）— 一个入口创建任意层
  - company: --name [--template] · department: --company --name · project: --name [--company --departments --goal]
  - project 无 repo 可建（默认数据目录）· 关联公司/部门（可选, Solo 最简）
- 便捷铁律: 前期只建 project 即可用; 组织可选增强; 渐进式挂接（project link）

### 测试

- `tests/console/test_cli_factory_create.py` 6 用例（三类型/Solo/错误路径）
- 与 org 数据模型（v1.1.16）衔接: 项目→公司/部门 关联


### Added

- **产品发现阶段 LLM 深度介入 (S10-099)** — 用户描述 → LLM 意图理解 → 结构化提取
  （替代逐字段追问）→ 智能追问（理解为什么缺）→ 主动分析（平台/竞品/范围）→
  LLM 理解摘要确认（"我理解你要做 X, 给 Y 用, 核心是 A/B/C, 对吗"）；无 LLM/key →
  现有状态机零变化（诚实降级, 不伪造 LLM 理解）。
  - **`session/discovery_intelligence.py`（新）** — `DiscoveryIntentAnalyzer`：
    意图优先级（控制指令 > 查询 > 字段回答 > 产品描述）+ 结构化提取
    {problem, user, core_features, name, platform} + 缺失原因 + 智能追问（≤3,
    优先 1 条）+ 主动分析 + 理解摘要；默认复用 `ReasoningProvider._default_llm_fn()`
    装配（同命名修复 bcc1b14 模式）；JSON 宽容解析链（剥 code fence →
    `json.loads` → `{...}` 子串回退）+ schema 校验；任何失败 →
    `DiscoveryLLMError` → 规则兜底。
  - **`conversation.py` 最小集成** — `start_product_discovery` 初始描述即解析
    （必填齐直入确认 / 缺则智能追问）；`handle_product_answer` 确定性 `_product_control`
    硬闸之后按 LLM category 分流（control→既有控制行为 / query→逃生 /
    product_description→提取合并 / field_answer→既有逐字段）；
    `_enter_product_confirmation` 展示 LLM 理解摘要 + 主动分析（仅 LLM 真产出时,
    `ai_generated` 诚实标注）。
  - **`ConversationResponse` 新增可选字段** `understanding` / `proactive` /
    `ai_generated`（缺省零影响, 前端/日志可区分）。
  - **契约测试** — `tests/console/test_discovery_llm_intelligence.py`（mock LLM
    注入, 不依赖真实 key；覆盖计划 §5 契约点 1-7）。

### Fixed

- **产品发现"太模板化"根因** — 用户初始自然描述只存 `raw` 从不解析 → 逐字段机械
  追问。修复: LLM 可用时初始描述即理解提取, 一次产出结构化定义（"我想做个
  markdown 编辑器..." 一次直达确认）; "整理一下" 类模糊控制不再被当字段（LLM
  分类 control → 整理不创建）; 无 LLM/key → 规则状态机逐字节不变（诚实降级）。

---

## [v1.1.16] — 2026-08-24

**组织×工作正交数据模型**: Project 关联公司/部门（渐进式, 多对多可选）— 从"单层项目工具"迈向"公司 OS"（§1.4.5）。

### Added

- **Project.company_id + department_ids**（`org/projects.py`）— 归属公司 + 关联部门（多对多可选, 默认值向后兼容）
- **register 支持 --company/--departments**（`org/cli.py`）— 注册项目即可关联组织（可选, Solo 最简）
- **company department create**（`org/cli.py`）— Department 模型补 CLI（渐进式建部门）
- **project link**（`org/cli.py`）— 项目挂接/解绑部门（渐进式: 先项目后组织, 无损升级）
- **_dispatch 嵌套子命令**（`org/cli.py`）— company department create 展平分发

### 测试

- `tests/org/test_org_project_org_link.py` 5 用例（字段默认/注册关联/link/unlink/错误路径）
- org 全量 861 passed · 向后兼容（旧项目零破坏）


### Fixed

- **产品命名 LLM 未接线（S10-081 设计缺口）** — `conversation.py` 调用
  `suggest_names` 时硬编码 `llm_fn=None`，导致 LLM 命名 prompt 从未生效，
  产品名永远走 deterministic 规则提取（"markdown编辑器需"式模板化根因）。
  修复: 接上 `ReasoningProvider._default_llm_fn()`，无 provider/key → 诚实回退
  deterministic（不伪造 LLM 结论）。40 相关测试通过。

**M3e 调度器接管真实执行 + 动态分配 (S10-097)**: M3 收尾 — M3a-d 计划层产物
正式驱动真实执行 (不再走旧 TaskTree 顺序路径)。

### Added

- **`orchestrator.execute_project(mode="m3")` 全链分支** — DecomposeEngine
  (复合→原子) → CriticalPathEngine (关键路径, 落盘 plan.json/dependencies.json)
  → TaskScheduler (依赖就绪轮次 + 同文件冲突 ConflictResolver 串行) → 每轮
  AgentMatcher 实时动态分配 → ExecutionLoop 执行 (复用 `_execute_with_retry` +
  Validator) → 每任务 EvidenceBundle 落盘 evidence/ (M1a 复用) → 审计 → 下一轮。
  默认 `mode="solo"` 旧路径零变化; 输出同既有结果结构 + `state.m3 = {rounds,
  assignments, evidence}`。
- **动态分配 M3-4** — 每轮就绪叶子 `AgentMatcher.match` 实时匹配 (skill × 历史
  成功率, 复用 agents.py 不修改); 分配落盘 `state.m3.assignments`
  [{round, task, agent_id}]; 空注册表 → 无匹配诚实报告 (不伪造分配)。
- **审计 5 事件** — `EXECUTION_ROUND_STARTED` / `EXECUTION_TASK_ASSIGNED` /
  `EXECUTION_TASK_COMPLETED` / `EXECUTION_ROUND_COMPLETED` /
  `EXECUTION_M3_DEGRADED` (注册表 + 真实发射)。
- **失败安全** — 单任务失败不中断整链 (标记 failed, 后续轮次继续); M3 链任何
  异常 → 降级 solo 顺序执行 (`EXECUTION_M3_DEGRADED` + `state.m3.degraded=True`
  诚实标注, 不伪造 M3 执行)。
- **契约测试** — `tests/console/test_m3e_full_chain.py`: 全链真实执行 (复合任务
  → M3 链 → 真实执行 → 项目目录产物) / 动态分配断言 / 旧路径零变化 / 单任务
  失败不中断 / 冲突串行 (同文件不同轮) / 失败回退 solo。

### 边界 (S10-097 §8, 未做)

- ❌ 轮内并行线程化 (轮内仍依序, 线程后置)
- ❌ 原子沙箱改造 / M3f / M3g (后续)


**M3d 拆解质量评估 + LLM 深度拆解 (S10-095)**: M3 三部曲之后补上**质量门控** —
拆解完先验质量（六维确定性评分），不合格诚实降级，不伪造 LLM 质量；同时
LLM 深度拆解升级为结构化产出并接入门控。

### Added

- **DecompositionEvaluator** (`session/decomposition_evaluator.py`) —
  `evaluate(decomposition, task, context)` → `{score, dims{完整性25/粒度20/
  依赖20/可行性15/可测性10/风险10}, decision, reasons}`; 六维确定性规则
  （完整性=core_features 覆盖 / 粒度=原子四条件通过率 / 依赖=cycle_detect+
  关键路径合理性 / 可行性=agent∈capabilities / 可测性=verify_cmd 覆盖率 /
  风险=risks 标注存在），score=Σ(维×权重)。
- **四档行动** — ≥0.9 `adopt`; 0.7-0.9 `adjust`（`adjust()` 自动修正: 补缺失
  feature / 补默认 verify_cmd / 修剪依赖环 → 修正后采用，标注 adjusted）;
  <0.7 `reject`（回退确定性技术层模板, 诚实降级）; <0.5 `ask_user`（返回
  questions, REPL 层处理后重评）。
- **decomposer 最小集成** — `decompose()` 后置评估（`evaluator` 可注入,
  `evaluate_after` 默认开）; `llm_fn` 产出结构化 `{tasks:[{id,name,
  requirement,depends_on,verify_cmd,est,risks}], summary}` → 质量门控;
  无 LLM → 确定性 leaves 照常评估（不跳过）; reject/ask_user → 确定性兜底。
- **落盘 + 审计** — `evaluation{score,dims,decision,reasons}` 进
  `decomposition.json` state + evidence 证据包（`EvidenceBundle.evaluation`）;
  审计事件 2 个: `EVAL_COMPLETED` / `EVAL_REJECTED_FALLBACK`（EVENT_TYPES
  52→54）。
- **契约测试** `tests/console/test_m3d_evaluator.py` — 17 例: 六维手算对照 /
  好拆解 adopt / 差拆解 reject 回退 / ask_user questions / adjust 自动修正 /
  无 LLM 照常评估 / evidence+审计落盘 / 向后兼容（评估器可选、M3a 零变化）。


**M3c 并行调度执行 (M3-3, S10-090)**: 原子任务不再简单顺序跑 — 消费
plan.json (M3b 依赖边) + execution_state → 依赖就绪队列 + 同文件冲突串行化 +
并发上限分桶 → 调度轮次 (rounds) 落盘 schedule.json (可审计可回放)。

### Added

- **TaskScheduler** (`session/scheduler.py`) — `schedule(plan, state,
  max_concurrency=1, agent_matcher=None, conflict_resolver=None)` →
  `{rounds, order, conflicts, state}`; `ready_tasks(completed)` 入度=0 就绪;
  并发分桶 (`_concurrency_bucket`, max_c=1 → 每轮单任务 = 旧顺序零变化)。
- **冲突串行化复用** — 同 `target_file` 冲突检测 → `ConflictResolver.resolve`
  (S10-057, 不修改核心) → 冲突任务不同轮 + `conflicts[]` 记录
  `{task, reason, resolution}`。
- **失败安全** — 环 / 无 plan → 降级顺序执行 (`schedule.json` + 执行状态
  `degraded=True` 诚实标注, 不伪造并行)。
- **落盘** — `projects/<slug>/schedule.json` `{rounds, order, conflicts,
  max_concurrency, created_at}` (可审计)。
- **orchestrator parallel 模式** — `execute_project(mode="parallel",
  max_concurrency=N)`: 消费 plan.json → rounds 依序执行 (同轮内按现有执行链
  跑); 默认 solo 完全不变 (零新增落盘字段, state.schedule 仅 parallel 非空)。
- **契约测试** `tests/console/test_m3c_scheduler.py` — 6 种手算对照 (无依赖
  并行 / 单链 4 轮串行 / 汇聚先并行后串行 / 同文件冲突串行 / 并发上限分桶 /
  max_c=1 向后兼容) + 落盘 + 环降级 + orchestrator parallel 集成。

---

## [v1.1.12] — 2026-08-23

**M3b 关键路径标注 (M3-2, S10-090)**: M3a 原子叶子（树关系）补上横向依赖边
(DAG) + 关键路径（最长链 CRITICAL 标注）+ merge 汇聚点 + 整链预估 —
"拆到不能拆" 之后告诉执行层哪些任务在最长链上、哪些是汇聚点（计划层标注,
不调度）。

### Added

- **CriticalPathEngine** (`session/critical_path.py`) — 依赖边推断 + 关键路径
  算法 + merge 标注 + 落盘 `projects/<slug>/plan.json` + `dependencies.json`。
- **依赖边推断 4 来源** (设计 §1) — ① 技术层确定性链（同 feature:
  db→api→frontend→test, 硬编码模板兜底）② 跨 feature 共享（共享 target_file /
  共享模块目录, 确定性检测）③ LLM 注入点 `llm_fn(leaves, edges)`（失败 → 跳过,
  不伪造）④ 落盘 dependencies.json 复用（`load_dependencies` 回注）。
- **关键路径算法** (设计 §2) — 复用 `dependencies.py` `add_dependency`（成环
  逐条拒绝 + 审计）→ `topological_order` → `dist[task]=max(dist[dep])+est`
  → 最长链回溯 → `estimated_duration`。
- **merge point** (设计 §4) — 入度 ≥ 2 节点 → `merges[]`（只标注, 不调度）。
- **CRITICAL 落盘** — `plan.json.tasks[]` 每任务 `critical: bool`（关键路径上
  = True）+ `summary_text` CLI 展示。
- **失败安全铁律** — 环 → 拒绝 + `PLAN_KEYPATH_COMPUTED(status=cycle_rejected)`
  审计, 不产出关键路径（诚实不伪造）; LLM 失败 → 确定性技术层链; 异常 →
  部分结果 + error; 落盘故障 → None。
- **审计事件 2 个** — PLAN_KEYPATH_COMPUTED / PLAN_MERGE_MARKED
  (`audit/audit_event.py` EVENT_TYPES 50→52)。
- **actions.execute_project 接线** — 拆解后前置标注（`FACTORY_CRITICAL_PATH=0`
  关闭, 默认开; 失败安全不中断执行; data 附 critical_path 摘要 + message 附
  summary_text）。
- **契约测试** `tests/console/test_m3b_critical_path.py` — 16 用例: 5 种 DAG
  （单链/分叉/汇聚/环/无依赖）手算对照 + 技术层链 + 共享/LLM 推断 + 落盘 +
  审计事件 + M3a 无依赖边向后兼容。

### 边界（不做）

- M3-3 并行调度执行 / M3-4 动态 Agent 分配 / 质量评估 — 后续 Sprint。
- `dependencies.py` 核心零修改（只读复用）。
- 向后兼容: M3a decompose 无依赖边输入 → 默认技术层链（不崩溃）。

---

## [v1.1.11] — 2026-08-23

**M3a 递归原子拆解引擎 (Sprint, S10-090)**: 复合任务 → 原子叶子（单 Agent /
单文件单工具 / 可验证 / ≤10min）— "拆到不能拆" 直接提高执行成功率（"一步一个坑"
根因 = 任务粒度太粗）。

### Added

- **DecomposeEngine** (`session/decomposer.py`) — 递归拆解: `decompose(task,
  product, capabilities, llm_fn)` → {leaves, tree, state} + 落盘
  `projects/<slug>/decomposition.json`。
- **原子判定四条件** (§3.7.3) — 确定性优先 + LLM 注入点: ① 单 Agent（能力表
  候选=1）② 单文件（target_file 提取）③ 可验证（语言→验证命令映射）④ ≤10min
  （关键词启发）。
- **拆分单向推进** `_split_mode: root→features→technical→final` — 防同层反复
  拆死循环; final 层仍不原子 → `atomic(unverified)` 诚实标注（能力边界, 不伪造）。
- **递归防护** — `_max_depth=5` + `_max_tasks=64` + 祖先链环检测 →
  `DECOMPOSE_CYCLE_REJECTED` 审计事件。
- **失败安全铁律** — LLM 失败/无 LLM → 确定性拆分非空; 异常 → 部分结果 + error。
- **审计事件 5 个** — DECOMPOSE_STARTED / ATOMIC / SPLIT / CYCLE_REJECTED /
  COMPLETED (`audit/audit_event.py` EVENT_TYPES 45→50)。
- **actions.execute_project 接线** — 执行前拆解（`FACTORY_DECOMPOSE=0` 关闭,
  默认开; 失败安全不中断执行; data 附 decomposition 摘要）。
- **契约测试** `tests/console/test_m3a_decomposer.py` — 11 用例: 四条件断言 /
  深度收敛 / 成环拒绝 / 无 LLM 降级 / 深度上限诚实 / 状态落盘 / 旧流程兼容。

### 边界（不做）

- M3-2 关键路径 / M3-3 并行调度 / M3-4 动态分配 / 质量评估 — 后续 Sprint。
- 非叶子节点编排 Loop 仅接口/事件占位（M3b+）。
- 向后兼容: 旧 TaskTree/FeatureTaskGenerator 流程不破坏。


**专家真干活 (Sprint, S10-088)**: 生产路径接真实 LLM + 专家交接消费上一产出 +
PRD 消费专家资产 + 专家团队落盘 — M2→M1 消费链打通 (Claude M2 评估: "骨架诚实、
产出未兑现" 的下一刀)。

### Added

- **product_pipeline 生产路径接 LLM** (T1) — `actions.product_pipeline` 装配
  `ReasoningProvider._default_llm_fn()` (有 providers.json + key → 真调 7 专家);
  无 LLM → 确定性兜底非空 (诚实, 不静默)。`llm_fn` 注入点保留 (测试/生产同路径)。
- **HandoffBus 交接消费上一产出正文** (T2) — `route` 每步经
  `ArtifactRegistry.read` 读上一资产 content, 作为 produce 第 4 参传入;
  `ProductPipeline._produce` prompt 嵌 `上一资产内容: <前 2000 字>` (而非仅 id);
  血缘双字段 (parent_artifact + parent_event_id) 保留。
- **prepare_project 消费专家 prd 资产** (T3) — 项目存在 HandoffBus 产出的
  `prd` 资产 (created_by=agt-*) → 用专家产出生成 PRD.md (M2→M1 打通);
  无专家资产 → 规则兜底 (向后兼容)。
- **build_team 落盘专家注册表** (T4) — `ExpertFactory.build_team` 装配后
  `registry.add` 落盘 agents.json (persist=True 默认, 项目内 agents.json 含 7 个
  agt-*); `persist=False` 保留不自动落盘选项。
- **真实产出断言** (T5) — 注入 fake llm_fn → market/全 7 资产含 LLM 真实内容
  (非 "待补充/规则占位" 段落)。

### Validation

- `我要做CRM` → `让PM分析` → 7 专家 LLM 产出 + 互引 → `准备开发` → PRD.md 含专家内容
- 全量回归 0 failed (runtime flaky 除外); 版本断言 v1.1.10 同步
  (pyproject/install.sh/docs/CHANGELOG/test_s10_074_deployment.py)



**M2 员工内核 (Sprint)**: "我要做CRM" → 7 个真实 Agent 实体交接产出 —
用 AgentEntity/ExpertFactory/HandoffBus 替换"7 个 prompt 换提示词"的单模型循环。

### Added

- **`session/agent_entity.py`** (A1) — AgentEntity 专家身份模型
  (id/role/industry/provider{id,model}/system_prompt/skills/knowledge_ref/
  workflow_ref/memory_ref/tools/evaluation_ref/profile): `agt-` 前缀 id
  (agt-<industry>-<role>-<n>), to_dict/from_dict roundtrip, 缺必填字段明确报错;
  provider 可空 (无 LLM → 确定性兜底可用)。
- **`session/agent_registry.py`** (A2) — 工厂层专家注册表
  (add/get/list/remove/next_id): 行业命名空间 it.* / ops.* 隔离, 同 role 多
  provider 并存 (id 唯一), agents.json 键值持久化。
- **`session/expert_factory.py`** (A3) — 专家装配器: assemble(role, industry,
  skills, knowledge_ref, workflow_ref, provider) → AgentEntity; 校验 skill 存在
  / workflow 可执行 / knowledge 可挂载, 缺 skill 明确报错 (不静默); build_team
  装配 7 软件行业专家; 无 LLM → deterministic_content 确定性兜底非空。
- **`session/handoff_bus.py`** (A4) — 交接总线: send/route (PM→Market→
  Competitive→UX→Architect→QA→SeniorPM); 消息 {from, to, artifacts[],
  decisions[], constraints[]}; 血缘双字段 metadata.parent_artifact +
  parent_event_id; 冲突 → ConflictResolver → ReviewGate 挂起等审批
  (status=pending_review); 消息落盘 m2_handoffs.json。
- **product_pipeline 接线** (A5) — "让PM分析" 走真 Agent 链:
  ExpertFactory.assemble + HandoffBus 替换 7-prompt 循环; 每资产
  created_by=agent_id (agt- 前缀); M1 资产类型/版本递增/审计血缘零回归。
- **`tests/console/test_m2_agent_core.py`** (M2-6) — A1-A5 契约测试套件
  (schema/接口/血缘/错误码, 36 passed)。

### Validation

- `让PM分析` → 7 资产互引 (parent_artifact 链), 每资产 created_by 以 agt- 开头;
- 引用不存在 skill → ExpertAssemblyError 明确报错; 无 LLM 环境 → 各角色确定性
  兜底非空; 冲突交接 → ReviewGate 挂起等审批;
- M1 链路 (repo/evidence/approval/backlog) 零回归。

---
## [v1.1.8] — 2026-08-21

**M1 闭环补全 (Sprint)**: 从证据到签字到落地最后一公里 — approve 后不再死路。
采纳 Claude 审查 P0/P1: approval apply 接入主 CLI + demo 全 dependency + 解析
失败模板提示 + evidence/approval 交叉引用。

### Added

- **`factory approval apply <id> [--project <dir>]`** (T1, P0) — 薄代理
  `ApprovalGate.apply` (主 CLI 经 exec CLI 同源 `cmd_exec_approval_apply`):
  仅 **APPROVED** 可应用 patch 到目标项目; 未批准/已拒绝 → 硬拒绝 (不绕过
  门禁); 已应用 → 拒绝重复应用 (幂等); 非 git 目标 → 响亮错误 (应用前须
  可审计)。
- **decide approve 后提示下一步** (T1, P0) — 审批通过后打印
  「已批准。下一步: factory approval apply <id> --project <repo> 可应用」,
  演示闭环不再死路。
- **demo/repo issues.json 默认全 dependency** (T2, P0) — 3 个 dependency issue
  (缺少 requests / 缺少 httpx / 升级 flask 到 3.0.0), 无 LLM 也 3/3 确定性
  修完; 演示完整闭环: 3/3 修完 + approve + apply 落地。
- **无 LLM skipped 文案优化** (T2) — bug/feature 未配置 LLM 时明确提示
  「需要 LLM(未配置)。配置后可用 factory init 解锁 bug/feature 修复」。
- **dependency 标题解析失败模板提示** (T3, P1) — 无法解析时报告提示
  「标题无法解析, 建议改成 `缺少 X 依赖` 或 `升级 X 到 V`」。
- **evidence/approval 交叉引用** (T4, Minor) — `approval list` 每行附证据包
  id; `evidence show` 附关联审批状态 (请求 input.evidence_bundle_id 锚点);
  修复 EvidenceStore.list() 排序 (文件名 uuid 字典序 ≠ 创建序 → 按
  created_at), 保证证据包↔审批一一对应不串包。

### Validation

- 实测 demo 完整闭环: `factory workload backlog --project demo/repo` →
  3/3 fixed (各自独立证据包 + pending 审批) → `factory approval list` (每行
  附证据包) → `factory approval decide <id> approve` (提示下一步) →
  `factory approval apply <id> --project demo/repo` (patch 真实落地) →
  `factory evidence show` (附审批状态); 重复 apply 硬拒绝。
- 新增测试: tests/console/test_approval_apply.py (10) + test_workload_backlog
  新增 5 (3/3 fixed / demo 默认全 dependency / 无 LLM 文案 / 解析失败模板 /
  交叉引用); 全量回归 0 failed (runtime 沙箱 flaky 除外)。

---

## [v1.1.7] — 2026-08-20

**M1b 积压清道夫 (E3 第一个可售卖工作负载)**: 分诊 → 执行 → 证据包 → 审批 → 报告
+ M1a Review 3 个 Minor 修复。

### Added

- **`factory workload backlog --project <dir>`** — BacklogSweeper 积压清道夫
  (`session/workloads/backlog_sweeper.py`): 读取项目 `issues.json`
  ([{id,title,type}]) → 分诊 (bug/feature/dependency → 修复策略) → 对每个
  issue 执行 (复用 RepoModeRunner Execution Kernel → Sandbox patch + pytest)
  → 组装 EvidenceBundle (diff+测试+日志+决策+变更文件, 落盘
  `projects/<slug>/evidence/`) → 自动请求审批 (复用 ApprovalGate) → 运行报告
  (`projects/<slug>/sweeps/sweep-*.json`)。
- **确定性依赖修复** — `DependencyPatchGenerator`: 真实分析 requirements.txt /
  pyproject.toml, 生成可应用 unified diff (无 LLM 也能「干完一件看得见的活」);
  bug/feature 走 LLM patch (无 LLM → 诚实 skipped, 不伪造)。
- **`factory workload status --project <dir>`** — 最近一次清道夫运行报告 (只读)。
- **`factory approval list [--project X]` / `factory approval decide <id> approve|reject`**
  (T2, Minor #2) — 待审批列表 + 审批决策, 复用 exec ApprovalGate (终态落库 +
  org.execution.approved 审计), 与 `factory-exec approval` 同源。
- **EvidenceBundle 接入普通执行** (T3, Minor #3) — `execute_project`/`resume`
  完成后自动组装证据包 (`EvidenceBuilder.from_execution_result`, 复用
  from_repo_result 模式), `factory evidence list` 可见。
- **logs 字段填充** (T4, Minor #1) — 组装证据包时填充执行日志 (执行事件摘要:
  理解/计划/patch/测试; 任务队列/验证/终态), 失败安全。
- **demo/repo** — BacklogSweeper 演示仓库 (main.py + 测试 + requirements.txt +
  issues.json: dependency 可确定性修复, feature/bug 需 LLM)。

### Validation

- 实测: `factory workload backlog --project demo/repo` → ISS-001 dependency 真实
  修复 (requirements.txt 变更 + 测试✅) + 证据包可见 + pending 审批; approval
  list/decide 全链路可用。
- 新增 31 测试 (test_workload_backlog 20 / test_evidence_attach 7 /
  test_approval_decide 9 含注册); 全量回归 0 failed。

---

## [v1.1.7] — 2026-08-21

**产品方案书 v3.0（终极版）合并**: 完整产品方案书更新为终极版（2656 行，12 章：
复杂任务拆解/多Agent编排/审计可观测/治理合规/学习进化/RAG/工具生态/行业工厂/
全部交互场景/演进路线/术语表），旧版独有章节（战略愿景/领域智能架构/生态对比/
附录）保留为 §十三 不丢失。
另: M1b 依赖修复收尾（中文升级句式 + 版本满足幂等, backlog_sweeper.py）。

---

**M1 内核切片（AI Company OS 第一块地基）**: 存量仓库模式 + 工具发现 + 真 MCP 客户端。

### Added

- **`factory repo <path> <目标> [--patch]`** — 存量仓库模式: 理解(core/understanding) →
  计划(LLM 或确定性) → patch 应用(Sandbox 副本, 原仓库零影响) → pytest 验证。
- **`factory tools list`** — 发现本机 AI CLI (codex/hermes/openclaw/claude) +
  MCP server 配置 (~/.codex/config.toml / ~/.claude.json / .mcp.json)。
- **StdioMCPClient** — 真 MCP stdio 客户端 (JSON-RPC 2024-11-05, 不绑第三方 SDK);
  工具是增强层, 任何任务不依赖外部 CLI 完成。
- **core_loader** — 延迟加载 factory-core/factory-exec (对齐 actions 模式)。

### Validation

- 实测: 临时 git 仓库 + patch → 变更文件 + pytest 通过; tools 发现 3 CLI + 2 MCP。
- 新增 21 测试; tests/console+exec 5791 passed; 全仓库 11805 passed。

---

**S10-084 Product Intelligence Pipeline (P0)**: 从 Idea 到 PRD 的多角色资产链。

### Added

- **ArtifactRegistry** (`session/artifact_registry.py`): 版本化资产注册表
  (`projects/<slug>/artifacts/<type>/v<n>/artifact.md + artifact.json`, v+1 递增,
  旧版本保留 — 渐进明细/变更前提)。
- **ProductPipeline** (`session/pipeline_runner.py`): 7 角色资产链
  (PM→product / Market→market_analysis / Competitive→competitive_analysis /
  UX→ux_flow / Architect→architecture / QA→test_plan / SeniorPM→prd),
  LLM 可用 → 角色 prompt; 失败/无 LLM → deterministic 兜底 (复用既有引擎)。
- **审计血缘**: 每资产 `ARTIFACT_CREATED` 事件 (artifact_reference + parent_event_id 链)。
- **discovery.md 落盘**: "先帮我整理需求，不要创建项目" → 需求快照落盘为
  discovery 资产 (draft), 不创建项目。
- **入口**: 意图 `让PM分析/产品管线` + action `product_pipeline` + 路由。

### Validation

- 新增 8 测试 (registry 3 + pipeline 3 + action/intent 2 + discovery 1)。
- `tests/console` 全量通过 (4488, 含既有回归); 全仓库 11760+ passed。

### Notes

- 需求变更与渐进明细闭环 (ChangeProposal → 影响分析 → 审批 → 资产 v+1 →
  ReplanningEngine) 为 P1, 见 docs/sprint10/S10-084-plan.md §4。

---

**Discovery 沟通修复 (S10-082 遗留问题 #1 落地)**: 产品发现流程不再把一切输入当字段答案,
控制指令/查询/编辑与字段回答分层处理。

### Added

- **控制短语 (非答案)**: 发现/确认阶段识别 `取消` / `整理需求不创建` / `项目列表` / `创建项目`
  等指令, 不再被吞成字段答案 (问题/用户/核心功能)。
- **批量问题模式**: `问题有点多` → 一次性列出剩余必填问题; 支持 `问题:...; 用户:...; 功能:...`
  一次填充多个字段 (自动去标签前缀)。
- **修改已有信息**: `把目标用户改成创业公司` / `修改一下，功能改成X` 更新已填字段
  (发现阶段与确认阶段均支持, 确认阶段普通文本仍是改名)。
- **创建引导**: 信息不足时 `现在创建项目` → 列出还缺字段并询问是否补充 (不再创建空名项目)。

### Fixed

- 发现阶段输入其它意图 (`我现在有哪些项目` 等) 时, 产品流程让位, 原输入走普通意图链。

### Validation

- 新增边界测试覆盖: 正常发现/多段填充不重问、用户打断→项目查询、创建引导、
  任意阶段取消、修改已有信息 (含反例不误判)。
- `tests/console` 全量通过 (4470+ 用例, 含既有回归)。

---
## [v1.0.0-rc1] — 2026-08-07

首个发布候选: **AI Software Factory v1.0 全能力落地**。Core + Extension + Intelligence
+ Human Console 四层齐备, 真实项目 (MarkPad) 走通完整生命周期, 4111 后端测试 +
92 前端测试全绿。

### Architecture

- **Core 冻结 (8 项通用原语)**: 状态管理 · 生命周期 · 调度 · 执行抽象 · 事件审计 ·
  恢复 · 观测基础 · 组织 — `events/ tasks/ workflows/ agents/ assignment/ execution/
  runtime/ runtimes/ recovery/ orchestration/ validation/ metrics/ dashboard/ project/
  workspace/ cli/`。冻结后不修改 Core 行为, 新能力一律走 Extension 声明式注册。
  冻结审查: [docs/architecture-freeze-2026-08.md](./docs/architecture-freeze-2026-08.md)。
- **Extension 系统 (声明式注册, 零 Core 破坏)**: `understanding/ product/ providers/
  git/ change/ changeflow/` — 依赖面仅 `events` + 区内, 删除任一 Extension 不影响
  Core 运行 (有测试断言, 如 `test_product_removal.py`)。
- **Intelligence 层 (只读复用, 决策/推荐/经验)**: `intelligence/` — Decision
  (决策链 + Evidence 六来源强制 + Risk R1–R5 + Approval 绑定)、Recommendation
  (四因素可解释评分 0.35/0.30/0.20/0.15)、Experience (五域 + 30 天半衰期衰减)。
- **Human Console (人在环上)**: `factory-console/` — React 7 页面 + FastAPI
  8 只读 GET 路由, Simple/Expert 双模式, 零写 API (人工审批走 CLI 决策动词)。

### Capabilities

- **Idea → Development 生命周期**: 12 阶段模型 (docs/lifecycle-model.md) 中 6–9
  完整实现, 1–5 由 Product Intelligence 承接, 10–11 部分支撑。software_project
  8 阶段链: `idea → research → prd → [approval] → ui → [approval] → architecture
  → task`。`factory demo markpad` 一键走通 (docs/demo-guide.md)。
- **Decision Intelligence (Phase 9c / 10A-2)**: 决策链 (Product → Architecture →
  Task Plan)、Evidence 六来源强制、Approval 状态机 (5 态终态可逆, 高风险自动绑定
  人工审批)、三类挡板 (产品冲突/架构变更/Scope 扩展)。
- **Provider Intelligence (Phase 8A–8B3)**: LLM Provider 抽象 (统一 I/O + Adapter +
  Registry)、四因素可解释推荐 (Capability/Cost/Performance/Experience)、Cost/Usage/
  Performance 聚合, 换 Provider = 改配置。
- **Experience Loop (Phase 10A-4)**: 成功/失败/审批经验五域沉淀, 30 天半衰期新鲜度
  衰减, 推荐回馈 "影响但不支配" (冷启动中性分, 不惩罚新候选)。
- **可观测与恢复**: 事件是唯一事实源 (append-only SQLite), Dashboard 20 视图,
  六域指标, checkpoint + 事件回放断点续跑。
- **CLI**: 23 命令组 / 77 叶子命令。

### Validation

- **MarkPad 真实项目验证 (Phase 12B)**: 表格编辑器增强需求走通
  `Idea→Research→PRD→[审批]→UI→[审批]→Architecture→Task→Experience` 完整闭环 —
  **34 事件 / 6 Artifacts / 2 经验 / 2 次人工审批 / Core 零修改**。
  详见 [docs/real-world-validation.md](./docs/real-world-validation.md)。
- **测试**: **4111 pytest 全绿** (24 个域, 基线只增不减) + **92 Vitest** (Web UI
  12 文件)。分域明细见 [docs/quality-report.md](./docs/quality-report.md)。
- **架构冻结审计 (2026-08-06)**: 四层依赖单向向下、无循环 import、Extension 隔离
  复核通过 (docs/system-architecture-review.md)。
- **流程**: Phase 0 → 14B, **48 次提交**, 每阶段独立可交付、可回退;
  ADR-0001–0035 (docs/adr/), 设计文档 30+ 篇。

### Known limitations (v1.0.0-rc1 边界)

本版本为**单机、单人、开源核心**里程碑, 以下能力明确不在 v1.0 范围:

- **无 SaaS / 多租户托管**: 无云端托管服务, 无租户隔离、无账号体系; 部署与运维由使用者自理。
- **无身份认证/授权**: CLI 与 Human Console 均为本机信任模型, 无登录、无 RBAC;
  请勿直接暴露到公网。
- **无支付/计费**: 不包含用量计费、账单、订阅; Provider 成本仅用于推荐评分与观测。
- **无市场 (Marketplace)**: 无 Skill/Agent/Workflow 的在线分发市场; 共享靠 git 分发
  + Extension 声明式注册。
- **反馈闭环为设计稿**: docs/feedback-model.md 定义接口契约, 采集/分类后台留待未来
  Feedback 阶段实现 (本阶段不落库、不建服务)。

---

## 版本记录约定

- 自 v1.0.0-rc1 起维护本文件; 每阶段交付追加一节 (Keep a Changelog:
  Added / Changed / Fixed / Removed)。
- 测试基线随阶段只增不减 (pytest 全量绿 + Vitest 全量绿为合入门槛)。
