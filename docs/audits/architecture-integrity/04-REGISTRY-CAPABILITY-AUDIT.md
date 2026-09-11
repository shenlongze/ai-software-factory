# 04 — Registry/Capability Audit
- capability_router (S10-116): 需求→资源匹配(agent/skill/mcp) — 存在, 但未管理 tool 注册/授权
- skill_search: 4 技能库 — 远小于实际能力面 (147+ 描述夸大)
- plugin_kernel: 存在 — 核心路径未走 (tool 仍 agent_loop 内联)
- artifact/agent registry: 域内注册 — 健康
- P1 Architectural Bypass: tool universe (schema+handler+授权) 全在 agent_loop;
  新增工具改 3840 行单体; capability_router 与 tool 面脱节
收敛: 工具三分离 (schema 声明 / handler 域逻辑 / 授权 policy), 注册层承接
