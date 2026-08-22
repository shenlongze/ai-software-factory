# S10-087 M2 员工内核 — Completion Report

> 日期: 2026-08-22 | v1.1.9 | 三部门循环: ①Claude②Hermes③Codex④Hermes Review ✅

---

## 交付(A1-A5 + M2-6)

| 节点 | 模块 | 内容 |
|---|---|---|
| A1 | `session/agent_entity.py` (176 行) | AgentEntity: id(agt-前缀)/role/industry/provider/skills/knowledge/workflow/memory/tools/evaluation/profile; roundtrip |
| A2 | `session/agent_registry.py` (173 行) | 工厂层注册表: add/get/list, 行业命名空间 it.*/ops.*, agents.json 持久化 |
| A3 | `session/expert_factory.py` (513 行) | 专家装配器: 校验 skill/workflow/knowledge; 缺 skill → ExpertAssemblyError 明确报错; 无 LLM 确定性兜底 |
| A4 | `session/handoff_bus.py` (371 行) | 交接总线: send/route, parent_artifact 血缘, 冲突→ReviewGate |
| A5 | `actions.product_pipeline` 改造 | 7-prompt 循环 → 真 Agent 链, created_by=agent_id |
| M2-6 | `tests/console/test_m2_agent_core.py` | 契约测试 36 passed |

## Hermes 独立验证(不轻信自报告)

1. ✅ commit 6 个(A1-A5 + 版本)+ 修复 1 个(4b1bd8d), clean
2. ✅ 版本 v1.1.9 (pyproject/install.sh/docs/CHANGELOG/断言全同步)
3. ✅ 装配 7 专家真实成功(agt-it-pm-1 等, workflow=feature-delivery)
4. ✅ 验收断言 2: 让PM分析 → 7 资产链(测试 36 passed 独立确认)
5. ✅ M2+M1 定向 557 passed; console+api+exec 5990 passed
6. ✅ 全量 11981 passed + 1 skipped, 0 failed

## Hermes Review 发现的真实 Bug(已修)

**core_loader._ensure 优先级**:`factory-console/events.py`(单文件模块)与 `factory-core/events/` 包同名。PYTHONPATH 提供的 factory-core 在 path 尾部时,`import events` 命中单文件模块 → `from events.logger` 递归失败 → `_builtin_workflow_ids()` 空集 → **所有专家装配失败**。修复: _ensure 幂等置顶(4b1bd8d)。

**教训**:Codex 测试环境(pytest 装配)与真实运行(sys.path 顺序不同)行为不一致——双重验证必要性的又一例证。

## 版本

v1.1.8 → **v1.1.9** ✅

## Git

```
d9b80e7 A1 AgentEntity → 3e23f81 A2 → bf8f321 A3 → 81c9311 A4 → 6c40290 A5
518822c 版本 v1.1.9 → 4b1bd8d fix core_loader
clean ✅ | push ✅
```

## 下一步(backlog)

1. A6 多 LLM 路由(planner/executor/reviewer)
2. 真 MCP 工具进 Agent 循环
3. 审批→PR 真实链路(E4 GitHub)
4. `expert build` CLI 命令包装
