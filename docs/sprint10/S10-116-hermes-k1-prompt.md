# S10-116 · K-1 能力路由 + 员工管理 — Hermes 提示词（2026-08-25）

> 战役: K-1（docs/战役规划-统一路线.md §2 K-1）· 目标版本 v1.1.85
> 交付后: 待办清单 K-1 ✅ · 战役规划状态追踪 K-1 ✅ · 能力缺口 B-1~B-4 ✅ · 员工管理 A-2/A-3 ✅ · F-4 ✅

---

请作为 Hermes 派发 Sprint 任务给 Codex，遵守既有纪律（pre-flight → plan → dispatch → verify → acceptance → report）。

【任务】S10-116 · K-1 能力路由 + 员工管理（战役规划第一战役）
版本目标：v1.1.85（从实际 HEAD +1；若并发消耗则顺延，不回退版本）

【背景（K-1 是什么）】
战役规划 K 系列统一路线（docs/战役规划-统一路线.md）第一战役。解决 Founder 核心问题：
"拥有同样技能的多个 skill / agent / mcp 如何分配调用关系？" + "内置/外置资产如何管理（CLI/API/界面）？"
合并项：B-1 skill 路由 · B-2 agent 能力路由 · B-3 mcp 路由 · B-4 统一能力路由层 · A-2 board 员工 tab · A-3 MCP 管理命令+API · F-4 提示词版本管理

【现状（实事求是，pre-flight 必须核对，不限于此）】
1. Skill: factory skill list|add|remove CLI + skills.json 注册 + ExpertFactory.assemble 装配校验 + 执行时全部 skills 注入 prompt（v1.1.82 真调用；A-1 已补齐 7 角色所需 skill）
2. Agent: factory agent list|add|remove CLI + AgentRegistry（~/.factory/agents/factory_agents.json）+ workspace agents.json + select_agent 只按 2 关键词（前端→flutter-dev，其余→backend-1，actions.py select_agent）
3. MCP: API 已有（GET/POST /api/mcp/connections, GET /api/mcp/tools — api/mcp_api.py）+ exec.mcp domain（MCPRegistry/MockMCPClient/MCPToolAdapter）+ Service 层 + factory tools list|doctor（只有发现，无 mcp 管理命令）
4. Board: 导航 _board_nav 已有 tab 列表；无 "员工" tab
5. 提示词版本：无版本管理（改 prompt 不可追溯）

【设计与实现要求（先出设计文档 docs/sprint10/S10-116-k1-capability-router-plan.md，批准后再实现）】
1. B-4 统一能力路由层（底座）:
   - CapabilityResource{id, type(agent|skill|mcp), capabilities[], status(ready|degraded|disabled), load, priority, version}
     （load 先落字段；负载均衡是 K-3 M4-5 的事，本战役不做实现）
   - CapabilityRequest{task/objective → capabilities[]} + 确定性匹配（capabilities 交集 → 按 priority/version/load 排序）
     → 返回 {resource_id, reason}（可解释，reason 必须能说清"为什么选它"）
   - 三个资源域（agent/skill/mcp）都实现"有注册 + 可路由"
2. B-1 skill 路由: 同技能多 skill → 按优先级/版本/匹配度确定性选择；执行注入从"全部 skills"改为"路由选中的 skill"
   （向后兼容：无匹配时全注入或明确兜底默认，测试断言）
3. B-2 agent 路由: select_agent 升级为 capability-aware（按 agent.capabilities 匹配任务需求），
   保留向后兼容（旧关键词行为不破坏：前端→flutter-dev 等；测试断言旧行为）
4. B-3 mcp 路由: 任务需工具 → 按 capabilities 选 MCP server/tool；factory mcp list|connect|remove CLI + 复用已有 MCP API
5. A-2 board 员工 tab: 导航加 "👥 员工"（与 📋 AI主线 并列）；只读展示 Agent 列表
   （id/role/skills/装配状态 ✅可装配 / ⚠️缺skill: x）、Skill 列表（id/name/category/version）、
   角色定义（7 角色 × skills × 现状 真引擎/规则/占位）、skill 缺失提示；
   数据源 agents.json + skills.json + ExpertFactory.assemble 校验；管理动作走 CLI/API，面板不写
6. A-3 MCP 管理: factory mcp list|connect|remove（发现/连接注册/移除）+ API 复用已有
7. F-4 提示词版本管理: 7 角色 prompt 版本化（版本号 + changed_at + 变更摘要；改 prompt 可追溯）—
   最小实现：prompt 资产带版本元数据，board 员工 tab 可见
8. 注册表门禁（P0-10/11 强制）: 新增 CLI 命令/意图/action/事件/API 必须同步注册表（测试自动红）

【硬边界】
- 只做路由/管理/展示，不做 K-2 执行质量分/优选（路由层预留 status/load 挂点即可）、
  不做 K-3 学习闭环/负载均衡/画像分配
- 纯规则确定性路由，不调 LLM
- 只读 board 展示；写操作走 CLI/API
- 不碰工作区他人未提交文件；不扩展无关模块
- 不动 S10-115 lifecycle_store 语义（可读其 canonical，不改其写入口）

【验收标准（独立可验证，非 Codex 自报告）】
1. 统一路由: 同技能多资源场景（构造 fixture: 2 skill / 2 agent / 2 mcp 含同一 capability）→ 确定性选择 + reason 可解释
2. skill 路由: 执行注入改为路由选中（fixture 断言注入内容，不再全量）
3. agent 路由: 旧关键词行为不破坏（前端→flutter-dev）+ 新 capability 匹配生效
4. mcp: factory mcp list|connect|remove 可用 + 路由可选 MCP tool（真实/ Mock 皆可，诚实标注）
5. board 员工 tab: 7 Agent + N Skill + 装配状态 + 缺失提示可见（只读，渲染后 mtime 不变）
6. F-4: prompt 版本化可追溯（版本号/变更摘要）
7. 契约测试 ≥10（路由确定性/可解释/向后兼容/管理命令/API/board 渲染/只读/注册表）
8. 全量回归 0 新增失败（环境性失败如实标注，与 HEAD 基线对照）
9. 版本 v1.1.85（pyproject + CHANGELOG + FEATURES + 版本断言 + 待办清单 K-1 ✅ + 能力缺口 B-1~B-4 ✅ + 员工管理 A-2/A-3 ✅ + F-4 ✅ 同步）
10. 设计文档落盘 docs/sprint10/S10-116-k1-capability-router-plan.md

【诚实记录】任何无法判定的存量资产如实标注；改动波及面超预期 → 列出并征询，不擅自扩大
