# EXEC MODULE FORENSICS — STEP 2 (2026-09-02)

## factory-exec 事实

- 独立 Python 包 (52 py), console 经延迟导入使用 (service.py:412/422/445/539/671/818,
  Removal Isolation 设计 service.py:376)
- 独立 CLI: factory-exec/exec/cli.py (610 行)

## Agent 执行器清单 (docstring 证据)

| 模块 | 行数 | 职责 |
|------|------|------|
| developer.py | 756 | Developer Agent (第一个 AI Employee) |
| pm.py | 435 | PM Agent |
| architect.py | 605 | Architect Agent |
| tester.py | 446 | Tester Agent |
| release.py | 586 | Release Agent |
| uxui.py | 517 | UX/UI Designer Agent |
| agent_runtime.py | 704 | AgentRuntime (执行权: Provider/沙箱/产补丁) |
| agent_executor.py | 170 | AgentExecutor (编排层) |
| execution_loop.py | 878 | Agent Execution Loop |
| sandbox.py | 249 | Sandbox (临时项目副本+git+patch) |
| approval.py | 242 | ApprovalGate (Human 门禁) |
| tool.py | 397 | Tool Runtime |
| skill.py | 420 | Skill System |
| mcp.py | 615 | MCP Adapter |
| runtime_session.py | 480 | Runtime Session (console 集成: service.py:412) |
| employee_executor.py | 264 | Employee-Execution 连接 |
| operations.py | 437 | File Operation API (diff) |
| patch_filter.py | 100 | Artifact Boundary |
| store.py | 260 | 独立数据空间 |
| provider.py | 259 | Provider 接口+注册表 |

## 与 console 执行系统关系 (事实, 不判断)

- console service.py 经 `from exec import` 懒装配 runtime_session/agent_executor/
  AgentRuntime/tool/skill/mcp
- console external_executor (gateway.py) 是另一条外部执行路径 (适配器注册表)
- console production_run.py (M3) 是第三条
- 三者是否同一能力多实现 / 分工: UNKNOWN (需逐调用链验证)
