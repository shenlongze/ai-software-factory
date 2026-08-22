# S10-087 M2 Sprint 规格（Hermes CTO → Codex 实现）

> 日期: 2026-08-22 | 目标版本 v1.1.9 | 三部门循环第②步产物
> 验收锚点: "我要做CRM" → 7 个真实 Agent 实体交接产出(parent_artifact 互引)

---

## 0. 架构决策:先收尾还是先地基?

**决策:地基优先(A1-A4 → A5 接线),收尾并入 A5 后。**

理由:
1. A5("让PM分析"走真 Agent 链)是 M2 验收核心;没有 AgentEntity/HandoffBus 地基,收尾(PR/记忆)无处附着
2. 记忆回流最小切片已由 `artifact_registry.metadata` + `parent_event_id` 承载血缘——A5 实现时自然带上,不必单独排期
3. 审批→PR 链路依赖真实 issue 源(E4,GitHub)——依赖 MCP 真连(后置项),M2 不做,防漂移
4. 风险:地基 4 模块全新建,若返工代价大 → 每节点独立提交 + 定向回归(Pre-flight 契约已核验,返工概率已压到最低)

## 1. 任务拆解(Codex 执行清单)

### M2-1 → A1: `session/agent_entity.py`(新建, ~150 行)
- **做什么**: AgentEntity pydantic 模型(id/role/industry/provider{id,model}/system_prompt/skills/knowledge_ref/workflow_ref/memory_ref/tools/evaluation_ref/profile)
- **改文件**: 新建 `factory-console/session/agent_entity.py`
- **依赖**: `core/agents/models.py` Agent(身份字段口径)
- **契约**: `agt-` 前缀 id(如 `agt-it-pm-1`);to_dict/from_dict roundtrip;职责边界注释(entity=身份, DeveloperAgent=执行)
- **验收断言**: `AgentEntity(id="agt-it-pm-1", ...)` → to_dict → from_dict → 相等;缺字段报错明确

### M2-2 → A2: `session/agent_registry.py`(新建, 薄包装)
- **做什么**: 工厂层注册表(add/get/list, industry 命名空间 it.*, agents.json 持久化)
- **改文件**: 新建 `factory-console/session/agent_registry.py`
- **依赖**: `session/agents.py` AgentRegistry.load 模式;`core/agents/registry.py`
- **契约**: 同 role 多 provider 并存(agent id 唯一);行业隔离(it.* / ops.*)
- **验收断言**: register→get→list;同 role 两个 agent 并存;跨行业互不可见

### M2-3 → A3: `session/expert_factory.py`(核心, "造专家")
- **做什么**: ExpertFactory.assemble(role, industry, skills, knowledge_ref, workflow_ref, provider) → AgentEntity;校验 skill 存在/workflow 可执行/knowledge 可挂载
- **改文件**: 新建 `factory-console/session/expert_factory.py`;可能需要 skills 注册表只读查询
- **依赖**: skills 注册表(capabilities 相关);provider 路由(ReasoningProvider)
- **契约**: 缺 skill → 明确报错(不静默);无 LLM → 确定性兜底可用
- **验收断言**: assemble 7 个软件行业专家(pm/market/competitive/ux/architect/backend/qa);缺 skill 抛明确错误

### M2-4 → A4: `session/handoff_bus.py`(多 Agent 协作)
- **做什么**: HandoffBus.route(role_graph) + send;消息 {from, to, artifacts[], decisions[], constraints[]};资产 parent_artifact 互引;冲突 → ReviewGate
- **改文件**: 新建 `factory-console/session/handoff_bus.py`
- **依赖**: `session/artifact_registry.py` ArtifactRegistry.write(created_by=agent_id, parent_event_id);`session/conflicts.py` ConflictResolver.resolve(S10-057);`session/review_gate.py`
- **契约**: 血缘用 `ArtifactRegistry.write(..., created_by=agent_id, parent_event_id=<上一资产 id>, metadata={"parent_artifact": <上一资产 id>})`;冲突挂起等审批
- **验收断言**: PM→Market→Competitive→UX→Architect→QA→SeniorPM 依次消费上一产出;每资产 metadata.parent_artifact 指向上一资产

### M2-5 → A5: 改造 `actions.product_pipeline`(接线)
- **做什么**: 用 ExpertFactory.assemble + HandoffBus 替换 7-prompt 循环;created_by=agent_id(非 role 字符串)
- **改文件**: `factory-console/session/actions.py`(product_pipeline)+ 可能 `session/pipeline.py`
- **依赖**: A1-A4;`session/product_intelligence.py` 作为各角色确定性兜底(LLM 失败非空)
- **契约**: 每资产 created_by == agent_id;资产互引;M1 链路(证据/审批/backlog)零回归
- **验收断言**: `让PM分析` → 7 专家真实产出;每资产 created_by 以 agt- 开头;无 LLM 环境兜底非空

### M2-6 → 契约测试套件
- **做什么**: 新模块契约测试(schema/接口/返回值/错误码/血缘)
- **改文件**: 新建 `tests/console/test_m2_agent_core.py`(A1-A5 全覆盖)
- **验收断言**: 每新模块过套件;定向 + 全量回归

## 2. 契约要求(统一)

```
1. 所有新模块 agent id 用 agt- 前缀 (agt-<industry>-<role>-<n>)
2. Action 层统一 ActionResult 壳 (ok/message/data) — 沿用现有
3. created_by 一律 agent_id (非 role 字符串)
4. 血缘: metadata.parent_artifact + parent_event_id 双字段
5. 无 LLM → 确定性兜底非空 (沿用 product_intelligence 模式)
6. 失败明确报错 (禁静默降级)
```

## 3. 验收标准(可断言)

| # | 断言 |
|---|---|
| 1 | `expert build --role PM --industry it` → AgentEntity 落盘 agents.json |
| 2 | `让PM分析` → 7 资产, 每资产 created_by 以 agt- 开头 + parent_artifact 指向上一产出 |
| 3 | 引用不存在 skill → 明确报错(非静默) |
| 4 | 无 LLM 环境 → 各角色确定性兜底非空 |
| 5 | M1 链路(repo/evidence/approval/backlog)零回归;全量 0 failed(runtime flaky 除外) |
| 6 | 版本 v1.1.9(pyproject/install.sh/docs/CHANGELOG/版本断言测试同步) |

## 4. 明确不做(防漂移)

- ❌ A6 多 LLM 路由(planner/executor/reviewer 分档)— backlog
- ❌ 真 MCP 工具进 Agent 循环 — 增强层 T,后置
- ❌ 审批→PR 真实链路(E4 GitHub 集成)— 依赖 MCP 真连,后置
- ❌ 第二行业 / 知识图谱 / 消息平台 — M5-M7
- ❌ 不推倒现有代码,只新增智能层(≈3-4K 行)

## 5. 版本

v1.1.8 → **v1.1.9**(patch+1;同步 pyproject.toml / scripts/install.sh / docs/DEPLOYMENT.md / docs/USER_GUIDE.md / CHANGELOG.md / tests/console/test_s10_074_deployment.py 版本断言)

## 6. 完成标准

1. A1-A5 + M2-6 全部落地,每节点独立提交
2. `让PM分析` 走真 Agent 链(7 资产互引)真实可演示
3. Hermes 独立验证:定向 + 全量回归,不靠 Codex 自述
4. git clean + push + Completion Report
