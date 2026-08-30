# S31 Architecture Proposal — Everything-is-a-Plugin Foundation

> 日期: 2026-08-29 | 状态: PROPOSAL (Contract Freeze 前)

## 1. Plugin Contract (冻结)
```
plugin_id / name / version / type / vendor / description /
capabilities[] / dependencies[] / permissions[] / configuration_schema /
lifecycle(DISCOVERED|REGISTERED|ENABLED|DISABLED|RETIRED) / health / entrypoint / metadata
```

## 2. Plugin Types (冻结)
```
agent | skill | tool | mcp | provider | model | runtime | executor | workflow | artifact_type | domain
S31 纳入: provider (第一个真实 Plugin) + executor (适配 S4) + agent/skill (元数据)
S31 不纳入: mcp/model/runtime/workflow/artifact_type/domain (架构理由: 现有模型未耦合, 后续 Sprint 按需)

## 3. Plugin Registry (冻结, SSOT)
```
register / unregister / get / list / exists / enable / disable / resolve / health
唯一 Registry (适配 AgentRegistry/ExternalExecutorRegistry/ModelCatalog, 不重复建)
```

## 4. Plugin Resolver (冻结, deterministic)
```
required capability → eligible plugins → permission 检查 → policy → 首个 ENABLED
非 LLM (测试断言)
```

## 5. Plugin Lifecycle (冻结)
```
DISCOVERED → REGISTERED → ENABLED → DISABLED → RETIRED
≠ Workforce lifecycle (独立); audit + append-only
```

## 6. 反硬编码 Architecture Test (冻结)
```
Core 不修改即可注册第二个 provider 实现 (FAIL = 未真正 Plugin)
禁用 Plugin 后执行被拒绝
```

## 7. 真实 Plugin
```
第一个 Production Plugin: llm provider (deepseek/ollama/anthropic 抽成 provider plugins)
经 Registry → Resolution → Permission → Execution → Audit
```

## 8. CLI/API
```
factory plugin list/inspect/enable/disable/status/health
GET /api/plugins | /api/plugins/{id} | POST /api/plugins/{id}/enable | /disable | /status | /health
```
