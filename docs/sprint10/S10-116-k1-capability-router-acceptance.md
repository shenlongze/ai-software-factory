# S10-116 — K-1 能力路由 + 员工管理：独立验收报告

> 日期: 2026-08-25 | 版本: v1.1.85 | 验收人: Hermes (CTO, 独立验证 — 非 Codex 自报告)
> 实现: `38ab504` (feat(S10-116), K-1 战役第一战役)
> 前置: v1.1.84 · 设计文档 aa51b38

---

## 验收矩阵（10 项全过）

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 统一路由 fixture 确定性 + reason 可解释 | ✅ | 2 skill/2 agent/2 mcp 同 capability → 同输入同输出; reason 含命中 capabilities + "priority desc → version desc → load asc → id" |
| 2 | skill 注入改为路由选中 | ✅ | developer.py 注入含路由; 有匹配 → 只注入选中 (含 reason); 无匹配 → 全注入 (兜底, 向后兼容) |
| 3 | agent 旧关键词不破坏 + 新 capability 生效 | ✅ | 前端→flutter-dev / 其余→backend-1 (逐字节); 多 agent capability 匹配生效 |
| 4 | factory mcp list/connect/remove + 路由选 MCP tool | ✅ | mcp 命令在注册表; connect→list→remove 真实往返 (MockMCPClient, 持久化); 路由 mcp 域命中 (mcp-db2 priority 高者) |
| 5 | board 员工 tab: 7 Agent + Skill + 装配状态 + 缺失提示, 只读 | ✅ | render_employees_html 渲染 (含 Agent 列表); 渲染后 mtime 不变 (只读铁律) |
| 6 | F-4 prompt 版本化可追溯 | ✅ | ROLE_DEFINITIONS 含 prompt_version/changed_at/change_summary |
| 7 | 契约测试 ≥10 全绿 | ✅ | test_s10_116_capability_router + campaign_plan: **34 passed** (我独立复跑) |
| 8 | 全量回归 0 新增失败 | ✅ | console+api: **5355 passed / 1 skipped / 0 failed** |
| 9 | v1.1.85 + K-1/B-1~B-4/A-2/A-3/F-4 ✅ | ✅ | pyproject=1.1.85; 待办清单 L13/114/115/126-129/187 全部 ✅ |
| 10 | 设计文档落盘 | ✅ | docs/sprint10/S10-116-k1-capability-router-plan.md |

## 1. 独立验证实录（我的脚本 17/17）

```
统一路由 (B-4):
✅ 确定性: priority 高者胜 (skill-B); 同输入同输出
✅ reason 可解释: "skill 'skill-B' 命中 capabilities {codegen} (共 4 候选...)"
✅ mcp 域命中 (mcp-db2) · 无匹配 → None · 全 disabled → None

B-1 skill 路由: developer.py 注入含路由逻辑 (选中+reason / 无匹配全量兜底)
B-2 agent 路由: 前端→flutter-dev / 其余→backend-1 (旧行为保留)
A-3: factory mcp 命令在 build_parser 注册表
A-2: render_employees_html 渲染含 Agent 列表; 渲染后 mtime 不变 (只读)
F-4: prompt_version/changed_at/change_summary 元数据存在
```

## 2. 关键设计验证（反虚标）

- **统一路由层**: CapabilityResource{id,type,capabilities,status,load,priority,version} +
  CapabilityRequest + Router.route — 纯规则确定性; status/load 只挂字段 (K-2/K-3 不做)
- **向后兼容**: skill 无匹配 → 全注入 (现状); agent 旧关键词优先 (前端/其余) 逐字节保留
- **只读铁律**: board 员工 tab 渲染函数只读数据源, mtime 实测不变; 管理动作走 CLI/API
- **注册表门禁**: mcp 命令同步 build_parser (P0-10 测试更新 test_console_cli.py)
- **诚实标注**: MCP 路由验证用 MockMCPClient (真实连接可选, 不伪称)

## 3. 契约测试与既有更新

- 新增 test_s10_116_capability_router.py + test_s10_116_campaign_plan.py (34 用例)
- 既有更新: test_console_cli (mcp 命令集合)、test_s10_114_skill_activation (注入断言改"路由选中+reason/无匹配全注入")、版本断言 7 处 → 1.1.85

## 4. 诚实记录（工程资产）

- 我的脚本 4 处 API 猜测修正 (intent.parameters 属性名 / render_board_html vs render_employees_html /
  agents 数据源 workspace/agents/agents.json + dict 格式) — 均脚本问题, 实现正确
- Codex 沙箱 7 环境性失败 + m3e flaky — 我环境 0 failed (flaky 本次也过)
- 边界遵守: 未做 K-2/K-3 (status/load 仅挂字段); 纯规则零 LLM; board 只读; 未动 S10-115 lifecycle_store;
  未改 ExpertFactory.assemble; 零新增依赖
- 安装环境已刷新 v1.1.85

## 5. 结论

- **通过**。K-1 战役第一战役落地: B-4 统一能力路由层 (agent/skill/mcp 三域可路由, 确定性 + 可解释 reason),
  B-1 skill 路由注入改造, B-2 agent capability-aware (兼容旧行为), B-3/A-3 MCP 路由+管理命令,
  A-2 board 员工 tab (只读), F-4 提示词版本化。Founder 核心问题"同技能多资产如何分配"已机制化。
- 建议后续: K-2 执行质量分+优选 (B-5/B-6, status/load 挂点已就绪); K-3 学习闭环/负载均衡。
