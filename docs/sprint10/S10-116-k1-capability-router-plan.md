# S10-116 — K-1 能力路由 + 员工管理：设计文档 + 实现计划（CTO 架构设计 + Codex 指令）

> 日期: 2026-08-25 | 前置: v1.1.84 · 战役规划 K 系列第一战役
> 用途: 三部门循环第 ②→③ 步 — Hermes(CTO) 设计 → Codex(工程) 实现
> 规格来源: docs/sprint10/S10-116 提示词（K-1: B-1~B-4 + A-2/A-3 + F-4 合并）

---

## 0. 现状审计（CTO 独立复核）

| 资产 | 现状 | 缺口 |
|---|---|---|
| Skill | factory skill list/add CLI + skills.json + ExpertFactory.assemble; 执行时 developer.py:229 **全量注入** skills | B-1: 无路由 (全注入不选) |
| Agent | factory agent CLI + AgentRegistry + select_agent (actions.py:916) 只按 2 关键词 (前端→flutter-dev / 其余→backend-1) | B-2: 不看 capabilities/负载/画像 |
| MCP | api/mcp_api.py (GET/POST connections, GET tools) + exec/mcp.py (MCPRegistry/MockMCPClient) + Service (service.py:785-866) | B-3: 无"任务需要工具→选哪个 MCP"; A-3: factory mcp 命令缺 |
| Board | _board_nav (board.py:1603 视图表: mainline/graph/...) | A-2: 无 员工 tab |
| Prompt | ROLE_DEFINITIONS (expert_factory.py): 7 角色 system_prompt, skill 条目已有 version 字段 (L45-73) | F-4: 角色 prompt 无版本元数据 |
| 注册表门禁 | P0-10/11 (S10-112) 常驻 | 新增命令/意图/action/事件/API 必须同步 |

版本: 1.1.84 → 目标 1.1.85 (HEAD+1, 顺延不回退)。

## 1. 架构决策

### 1.1 B-4 统一能力路由层（底座, 新模块 `factory-console/session/capability_router.py`）

```python
@dataclass
class CapabilityResource:
    id: str; type: str                    # agent | skill | mcp
    capabilities: list[str]               # 能力标签 (如 "frontend_ui", "database", "code_generation")
    status: str = "ready"                 # ready | degraded | disabled (挂点, K-2 用)
    load: float = 0.0                     # 字段落位 (负载均衡 K-3 不做实现)
    priority: int = 0                     # 高=优先 (确定性排序)
    version: str = "1.0.0"
    def __post_init__(self): ...          # id/type 校验

@dataclass
class CapabilityRequest:
    objective: str; capabilities: list[str]  # 任务需求 (capabilities 交集匹配)

@dataclass
class RouteDecision:
    resource_id: str; reason: str        # reason 必须能说清"为什么选它" (可解释)

class CapabilityRouter:
    def __init__(self, resources: list[CapabilityResource]): ...
    def route(self, request: CapabilityRequest) -> Optional[RouteDecision]:
        # 确定性: capabilities 交集 → 按 (priority desc, version desc, load asc, id) 排序
        # → 首个 status=ready 的; 无交集/全 disabled → None
        # reason 示例: "skill 'flutter-dev' 命中 capabilities {frontend_ui} (priority 5, 唯一匹配)"
```

### 1.2 B-1 skill 路由（注入改造, 向后兼容）

- 资源域: skills.json 外部注册 + 内置 skill 表 → CapabilityResource(skill)
- 任务 → skills 候选: 按 objective 关键词推导能力需求 (确定性规则表) → CapabilityRouter.route
- **执行注入改造** (developer.py:229): "全部 skills" → "路由选中的 skill" (注入 "You have skill X (selected by router: reason)")
- **向后兼容**: 无匹配 → 明确兜底默认 (全注入? 或注入 DEFAULT_FALLBACK_SKILL) — **设计: 无匹配 → 全注入 (现状)**;
  测试断言: 有匹配 → 只注入选中; 无匹配 → 全注入 (零变化)
- ExpertFactory.assemble 不动 (装配校验与路由分离)

### 1.3 B-2 agent 路由（select_agent 升级, 向后兼容）

- 资源域: AgentRegistry (factory_agents.json + workspace agents.json) → CapabilityResource(agent, capabilities=agent.skills+supported_tasks 推导)
- select_agent 升级: ① params.agent_id 优先 (现状) ② 旧关键词规则优先 (前端/flutter/ui/界面→flutter-dev; 其余→backend-1 — **逐字节保留**) ③ 关键词未命中且有多 agent → capability 匹配 (objective 能力需求 → router)
- 测试: 旧行为断言 (前端→flutter-dev) 不破坏 + 新 capability 匹配生效

### 1.4 B-3 + A-3 MCP 路由 + 管理命令

- 资源域: MCPRegistry (exec/mcp.py) → CapabilityResource(mcp, capabilities=tools 名/域)
- 路由: 任务需工具 (objective 含工具关键词) → MCP tool 选择
- A-3: `factory mcp list|connect|remove` CLI — 复用 service.mcp_connections/create_mcp_connection + registry; 新命令必须同步 CLI 注册表 (P0-10 门禁)
- 诚实标注: MockMCPClient 可用于路由验证 (真实 MCP 连接可选)

### 1.5 A-2 board 员工 tab

- _board_nav 视图表加 ("employees", "/api/board?view=employees", "👥 员工")
- 渲染: 只读 — Agent 列表 (id/role/skills/装配状态 ✅/⚠️缺skill:x) + Skill 列表 (id/name/category/version) + 角色定义 (7 角色 × skills × 现状 真引擎/规则/占位) + 缺失提示
- 数据源: agents.json + skills.json + ExpertFactory.assemble (失败安全)
- **只读铁律**: 渲染后 mtime 不变 (验收 5); 管理动作走 CLI/API

### 1.6 F-4 提示词版本管理

- ROLE_DEFINITIONS 7 角色 prompt 条目 += `prompt_version: "1.0.0"` + `changed_at` + `change_summary` (改 prompt 可追溯)
- 最小实现: 版本元数据 + board 员工 tab 可见; 不改 prompt 内容语义

### 1.7 注册表门禁（P0-10/11）

- 新增: factory mcp CLI 命令 / intent (如有) / action / API 路由 → 必须同步:
  CLI 注册表 (build_parser) · intent→DEFAULT_ROUTES · action registry · 写路由白名单
- 契约测试包含门禁断言 (新增项在注册表可见)

## 2. 契约测试（tests/console/test_s10_116_capability_router.py, ≥10）

1. **统一路由确定性**: 2 skill/2 agent/2 mcp 含同一 capability fixture → 同输入同输出 (排序 priority>version>load)
2. **reason 可解释**: 含命中 capabilities + 排序依据
3. **skill 路由注入**: 有匹配 → 注入只含选中 skill; 无匹配 → 全注入 (向后兼容断言)
4. **agent 路由旧行为**: 前端/flutter/ui → flutter-dev; 其余 → backend-1 (逐字节)
5. **agent 新 capability 匹配**: 多 agent 场景 objective 能力需求 → 正确 agent
6. **MCP 路由**: objective 需工具 → 选 MCP tool; factory mcp list|connect|remove 可用 (Mock 诚实标注)
7. **board 员工 tab**: 渲染含 7 Agent + Skill + 装配状态 + 缺失提示; 渲染后 mtime 不变 (只读)
8. **F-4 版本元数据**: 7 角色 prompt 含 prompt_version/changed_at/change_summary
9. **注册表门禁**: 新 CLI 命令 (mcp) 在 build_parser 注册表可见 + intent/action 同步
10. **全量回归**: 0 新增失败

## 3. 版本与发布

- pyproject `1.1.84` → `1.1.85`; CHANGELOG v1.1.85; 版本断言同步; docs/FEATURES.md;
  docs/sprint10/待办清单-已发现未落地.md: K-1 (L13) ✅ + B-1~B-4 (L126-129) ✅ + A-2/A-3 (L114-115) ✅ + F-4 (L187) ✅

## 4. Codex 实施范围

**Allowed/Files**:
- NEW `factory-console/session/capability_router.py` (CapabilityResource/CapabilityRequest/RouteDecision/CapabilityRouter)
- MOD `factory-exec/exec/developer.py` (skill 注入: 路由选中替代全量, 无匹配全量兜底)
- MOD `factory-console/session/actions.py` (select_agent 升级: 旧关键词优先 + capability 匹配)
- MOD `factory-console/session/agents.py` (AgentRegistry → capability 资源化, 只读)
- MOD `factory-console/session/board.py` (员工 tab 渲染, 只读)
- MOD `factory-console/cli_factory.py` (factory mcp list|connect|remove — 注册表同步)
- MOD `factory-console/session/expert_factory.py` (F-4: ROLE_DEFINITIONS prompt 版本元数据)
- MOD `factory-console/service.py` (MCP 管理复用, 如需)
- NEW `tests/console/test_s10_116_capability_router.py`
- MOD pyproject.toml / CHANGELOG.md / 版本断言 / docs/FEATURES.md / docs/sprint10/待办清单-已发现未落地.md

**Forbidden（硬边界）**:
- 不做 K-2 执行质量分/优选 (status/load 只挂字段); 不做 K-3 学习闭环/负载均衡/画像分配
- 纯规则确定性路由, 不调 LLM
- board 只读; 写操作走 CLI/API
- 不动 S10-115 lifecycle_store 语义 (可读 canonical, 不改写入口)
- 不改 skill 内容/装配校验语义 (ExpertFactory.assemble 不动); 禁 git add -A
- 不碰工作区他人未提交文件 (当前仅 untracked demo/、unused/)

**Validation**:
- `pytest tests/console/test_s10_116_capability_router.py -q` 全绿
- env -u 聚焦 (agents/actions/board/cli/expert_factory + 既有 agent/skill/mcp/board 测试) 全绿
- env -u 全量 console+api 0 新增失败
- 实测: 路由确定性 + reason; 注入改造; mcp CLI; board 员工 tab 只读
- commit: `feat(S10-116): K-1 能力路由+员工管理 — B-1~B-4统一路由层 + A-2员工tab + A-3 mcp管理 + F-4提示词版本化, v1.1.85`

## 5. 验收标准（Hermes 独立验证）

- [ ] 1. 统一路由 fixture 确定性 + reason 可解释
- [ ] 2. skill 注入改为路由选中 (fixture 断言)
- [ ] 3. agent 旧关键词不破坏 + 新 capability 生效
- [ ] 4. factory mcp list|connect|remove + 路由选 MCP tool
- [ ] 5. board 员工 tab: 7 Agent + N Skill + 装配状态 + 缺失提示, 渲染后 mtime 不变
- [ ] 6. F-4 prompt 版本化可追溯
- [ ] 7. 契约测试 ≥10 全绿
- [ ] 8. 全量回归 0 新增失败
- [ ] 9. v1.1.85 + K-1/B-1~B-4/A-2/A-3/F-4 ✅ 同步
- [ ] 10. 设计文档落盘
