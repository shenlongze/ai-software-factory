# S32 Gap Analysis — Composable Workforce & Capability

> 日期: 2026-08-29 | HEAD: ff17ae08 (v1.1.338)

## GAP Audit
| 问题 | 现状 | 判定 |
|------|------|------|
| AgentProfile 是否引用 Plugin | 无 plugin_id 字段 | MISSING |
| role 是否 hard-coded | ROLE_CAPABILITIES 常量 dict | PARTIAL |
| capabilities 是否来自 Plugin | S30 独立常量 vs S31 plugin capabilities (两套语义) | GAP |
| skills/tools/model/provider 是否来自 Plugin | ROLE_BINDINGS 常量 | PARTIAL |
| Agent Selection 是否通过 Plugin Resolver | select_agent_deterministic 直接查 ROLE_CAPABILITIES | GAP |
| Workforce 是否由 Plugin 组合 | attach_agent 无 plugin refs | GAP |
| 替换 Model/Provider 不修改 Core | S31 Plugin Kernel 支持 (未接入 AgentProfile) | 待接线 |
| 独立 Registry 与 S31 重复 | AgentRegistry/ExternalExecutorRegistry 存在 | 适配不重建 |

## 设计
```
AgentProfile (扩展):
  agent_plugin_id / skill_plugin_ids[] / tool_plugin_ids[] /
  model_plugin_id / provider_plugin_id / runtime_plugin_id / policies
Composition (workforce_composition.py):
  resolve_agent_profile(root, agent_profile_id) → 确定性解析各 plugin
  (agent→skill→tool→model/provider→runtime→permission→policy→executable)
Capability 统一:
  S30 capabilities 声明 ↔ S31 plugin capabilities 映射 (capability:plugin_id)
替换测试:
  Scenario A: provider A→B (Core 不变) | B: skill A→B | C: runtime A→B | D: disabled 拒绝
Lineage:
  artifact → node_run → task → agent_profile → workforce → plugin version → runtime → model
```

## 复用
S31 Plugin Kernel (Registry/Resolver/Lifecycle) + S30 Workforce + S17 governance

## 禁止
Marketplace/远程下载/UI store/performance ranking/learning/self-healing/大量新 agent/Core 重构
