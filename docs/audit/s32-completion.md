# S32 Composable Workforce & Capability — Completion Report

> 日期: 2026-08-29 | HEAD: (S32 commit) | v1.1.339

## 1. GAP Audit
S30 AgentProfile 无 plugin 引用;capabilities 两套语义 (S30 常量 vs S31 plugin)。

## 2. Architecture
Workforce = Composition, 非 Implementation;AgentProfile = Plugin references + policy。

## 3. AgentProfile Composition — REAL
agent_plugin_id/skill_plugin_ids/tool_plugin_ids/model_plugin_id/provider_plugin_id/runtime_plugin_id/policies。

## 4. Capability 统一 — REAL
S30 capabilities ↔ S31 plugin capabilities 映射 (CAPABILITY_PLUGIN_MAP);unified_capability_list 16 项。

## 5. Composition Resolution — REAL (deterministic)
agent→skill→tool→model/provider→runtime→permission→policy;6 plugins 全 ENABLED 才 OK;非 LLM。

## 6. Scenario A — provider 替换 (Core 不变) — REAL
deepseek → provider.alt (v2.0);执行成功 (测试证明)。

## 7. Scenario B — skill 替换 (Core 不变) — REAL
skill.coding → skill.advanced;执行成功 + 新 capability (optimize)。

## 8. Scenario D — disabled 拒绝 — REAL
provider DISABLED → resolve FAIL ("plugin 未启用")。

## 9. 两 Workforce 不同 Plugin — REAL
dev (agent.dev) vs qa (agent.qa);capabilities 不同;Core 不变。

## 10. Lineage — REAL
agent_profile → plugins (version) → runtime → model → provider 全可追溯。

## 11. CLI/API — REAL
factory composition bind/resolve/capabilities/lineage + 4 API 端点 (openapi 247)。

## 12. Tests — 9
bind-resolve/unified-capability/provider-substitution/skill-substitution/disabled-rejected/two-workforces/lineage/CLI/API。

## 13. Regression
```
S32: 9/9 | 全量: 936 passed + 6 skipped (零失败) | Zero-Stub: PASS | 前端 tsc: PASS
```

## 14. 核心问题回答 (全部 YES + Evidence)
```
1. Agent 是否 Plugin Composition?      YES — agent.dev plugin (resolve 验证)
2. Skill 是否 Plugin Composition?      YES — skill.coding/advanced (替换测试)
3. Tool 是否 Plugin Composition?       YES — tool.codex (resolve 6 plugins)
4. Model 是否 Plugin Composition?      YES — model.default (lineage 验证)
5. Provider 是否 Plugin Composition?   YES — provider.deepseek→alt (替换测试)
6. Runtime 是否 Plugin Composition?    YES — runtime.llm (lineage 验证)
7. 替换 Plugin 不修改 Core?            YES — Scenario A/B 测试证明
8. Disabled 后 Workforce 拒绝?         YES — test_disabled_rejected
9. Artifact 追溯到 Plugin/Version?     YES — composition_lineage (plugin_versions)
```

## 15. Commits
feat: S32 Composable Workforce & Capability + chore(版本): bump v1.1.339 + tag

## 16. Final Verdict
**S32 = PASS** — AgentProfile 由 Plugin references 组合 (非实现);Capability 单一语义;provider/skill 替换不修改 Core (Architecture Test);disabled 拒绝;lineage 全可追溯。**Workforce = Composition 已落地。** 按指令停止,不进入 S33。
