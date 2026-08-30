# S41 Extensibility Audit

> 日期: 2026-08-29 | 纯审计

## 新增能力是否需要修改 Core?
| 新增 | Core 修改? | 路径 | 证据 |
|------|:---:|------|------|
| Agent | NO | Plugin type=agent → register → enable | S31/S32 |
| Skill | NO | Plugin type=skill | S32 test_skill_substitution |
| Tool | NO | Plugin type=tool | S31 |
| Model | NO | Plugin type=model | S31 |
| Provider | NO | Plugin type=provider | S31 test (provider.alt 零 Core) |
| Runtime | NO | Plugin type=runtime | S32 |
| Memory | NO | Plugin type=memory | S35 test_memory_plugin_replacement |
| Retriever | NO | Plugin type=retriever | S35 |
| Workflow | NO | Plugin type=workflow | S31 |
| Intelligence Strategy | NO | Plugin type=strategy/learning/optimization | S36/S37/S40 |
| Business Module | NO | 企业模块 (未来) | 见 enterprise audit |

## 需改 Core 的情况
- 新 Plugin type → PLUGIN_TYPES 元组扩展 (S31) — 轻微 Core 触碰 (白名单)
  → 建议: 未来改为开放注册 (PROPOSED, DEFERRED)

## 结论
核心扩展点全部 Plugin 化;仅 Plugin type 白名单需扩展 (低风险, DEFERRED 改进)。
