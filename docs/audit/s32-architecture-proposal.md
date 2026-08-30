# S32 Architecture Proposal — Composable Workforce & Capability

> 日期: 2026-08-29 | 状态: PROPOSAL (Contract Freeze 前)

## 1. AgentProfile Composition (冻结)
```
agent_profile_id / role / agent_plugin_id / skill_plugin_ids[] / tool_plugin_ids[] /
model_plugin_id / provider_plugin_id / runtime_plugin_id / capabilities[] / policies[]
= Plugin references + policy/configuration (非实现)
```

## 2. Capability 统一 (冻结)
```
S30 capabilities (implement/verify) ↔ S31 plugin capabilities (llm.complete/execute.code)
映射表: capability → 满足该 capability 的 plugin (capability:plugin_id)
AgentProfile.capabilities = agent_plugin.capabilities ∪ skill_plugins.capabilities ∪ tool_plugins...
单一语义: capability 是 Plugin 声明, 经 Registry/Resolver 到 Workforce
```

## 3. Composition Resolution (冻结, deterministic)
```
resolve_agent_profile(profile_id):
  resolve agent_plugin → skill_plugins → tool_plugins → model/provider → runtime
  → permission 检查 → policy → executable config
  非 LLM; 复用 S31 resolve_plugin
```

## 4. 替换测试 (冻结)
```
A: provider A→B (Core 不变) → 执行成功
B: skill A→B → 执行成功
C: runtime A→B → 执行成功
D: plugin DISABLED → Workforce 执行拒绝 (Governance)
```

## 5. Lineage (冻结)
```
artifact → node_run → task → agent_profile → workforce →
plugin composition (plugin_id + version) → runtime → model/provider
```

## 6. CLI/API
```
factory workforce agent inspect <agent_profile_id>
GET /api/agent-profiles/{id}/composition | /api/workforces/{id}/composition
```
