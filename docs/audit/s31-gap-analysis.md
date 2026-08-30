# S31 Gap Analysis — Everything-is-a-Plugin Foundation

> 日期: 2026-08-29 | HEAD: a4e8d883 (v1.1.337)

## GAP Audit 表
| 能力 | 现状 | 判定 | 证据 |
|------|------|------|------|
| Plugin Kernel (统一 Contract/Lifecycle/Resolution) | 无 | MISSING | 无 plugin_kernel.py |
| Plugin Registry (register/unregister/enable/disable/health) | 无 | MISSING | 无统一 registry |
| ExternalExecutorRegistry (S4, codex/claude/hermes 适配器) | adapter 级注册 | PARTIAL (非 Plugin Kernel) | external_executor/registry.py:151 |
| Provider 硬编码 | llm_router.py:387 ollama; workflow_runner.py:549 anthropic | PARTIAL | if provider == |
| Agent hard-coded | workforce.py ROLE_CAPABILITIES (7 角色) | PARTIAL | 常量 dict |
| Skill hard-coded | workforce_os.py ROLE_BINDINGS | PARTIAL | 常量 dict |
| Tool/Model/Workflow 硬编码 | 散落各 service | PARTIAL | import table |
| 多 Registry 冲突 | AgentRegistry + ExternalExecutorRegistry + ModelCatalog | 存在 | 需统一为 Plugin Registry 适配 |
| Plugin Lifecycle (DISCOVERED→REGISTERED→ENABLED→DISABLED→RETIRED) | 无 | MISSING | — |
| Plugin Governance (权限/依赖/审计) | S17 governance 可复用 | 复用 | governance_service.py |

## 设计
```
Plugin Kernel (plugin_kernel.py):
- PluginRecord: plugin_id/name/version/type/vendor/capabilities/dependencies/permissions/status/health
- PluginRegistry: register/unregister/get/list/exists/enable/disable/resolve (SSOT)
- PluginResolver: deterministic (capability → eligible → permission → policy; 非 LLM)
- PluginLifecycle: DISCOVERED→REGISTERED→ENABLED→DISABLED→RETIRED (audit)
- 真实 Plugin: 把 llm_router 的 provider 适配抽成 provider plugin (第一个 Production Plugin)
- 反硬编码 Architecture Test: 注册第二个实现不改 Core
```

## 复用
- S17 governance (permission/policy)
- S4 ExternalExecutorRegistry (适配成 provider/executor plugin 的注册源)
- S30 Workforce (AgentProfile 后续引用 plugin_id 兼容层)

## 禁止
- Marketplace/Web Store/远程下载/沙箱/几十种 plugin/大量新 agent/performance ranking
- 第二套 Event/Artifact/Workforce Store;破坏 S0.5 Contract;mock 假 Plugin Execution
