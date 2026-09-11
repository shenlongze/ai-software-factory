# S1 第 9 刀 — Flow Views 视图层 v0 (实施报告)

> Date: 2026-09-10 | 性质: 实施 | 基线: HEAD=dcf6c98e (cut5/6/7 未提交改动原封未动)
> 本文件是防反工记忆: 下个会话读此文件即可续接, 不重来。
> 手术单: /Users/agentdev/ai-company-os-planning/s1-cut9-flow-views-final.md
> 设计全景: /Users/agentdev/ai-company-os-planning/2026-09-10-dashboard-system-design.md

---

## 0. 模型图 (本刀交付)

```
视图层 (只读, 纯函数, 零新服务端依赖)
  build_conv_flow(root, cid)          → conv flow 视图模型 (9 阶段 + 树摘要 + sprint + node_runs + 审计)
  build_project_view(root, pid)       → project 聚合视图 (backlog 三态 + Sprint 卡 + 每 PRD 迷你流)
        │  (单一 Truth 源; 只读 conversations/ task_trees/ project_agile/ runs/ audit)
        ▼
  render_view(view, fmt) → md / todo / mermaid:{mindmap,gantt,flow,dataflow,
                            sequence,state,dag} / echarts:{graph,sankey} / html
  build_flow_for(root, scope, id, fmt)  ← CLI/API/shell 同源入口
  入口: cli_factory.py `factory flow` | api/flow.py flow_route | canonical_shell.py `/flow [fmt]`
```

## 1. 范围清单 (手术单 §一 — 5 项全交付)

| 项 | 文件 | 状态 |
|---|---|---|
| 1 | factory-console/flow_views.py (560→~690 行) | ✅ 完成 |
| 2 | factory-console/api/flow.py (新建) + api/__init__.py 导出 flow_route | ✅ 完成 |
| 3 | tests/console/test_flow_views_s2.py (新建) | ✅ 完成 (13 passed) |
| 4 | docs/audits/2026-09-10-s1-cut9-flow-views.md (本文件) | ✅ 本文件 |
| 5 | cli_factory.py `factory flow` + canonical_shell.py `/flow [format]` | ✅ 完成 |

## 2. 视图模型与渲染器 (手术单 §二/§三 — 全收录)

- conv flow: 9 阶段 (Idea/需求分析/架构选择/任务树/Sprint/执行/验证/交付/审计)
  派生状态 + 树摘要 (depth/叶/degraded/warnings) + active sprint 统计 +
  每叶 node_run (state/executor/artifact/真实时间戳) + 验证状态 + 审计事件数。
- project view: backlog 全量三态 (pending/in_sprint/closed 计数) + Sprint 卡
  (status/prd_ids/plan_ids/stats/per_prd_stats/prd_plan_map) + 每 PRD 迷你流
  (PRD→Plan→执行; 经 backlog.conversation_id 反查 trace) + active sprint 高亮。
- 12 格式全通: md 阶段表 / todo 叶清单 / mermaid 7 图 / echarts 2 图 / html。

## 3. 修复清单 (接手雏形时发现并修复)

接手时 flow_views.py 已有 560 行雏形 (上次会话被 signal 1 打断前创建, untracked)。
修复 5 个问题:

1. **import 模块名错误**: `from factory_console import product_agile as _pa`
   → `project_agile` (文件不存在 → import 必失败)。
2. **build_project_view 缺存在性/真实标题/backlog 三态**: 原实现调用
   project_agile_view (空项目也返回假视图, 无 title, backlog 只含 pending);
   改为 project_os.get_project 判存在 (缺失 → exists=False, 渲染 "(不存在)"),
   标题取自项目实体, backlog 用 project_agile._load 全量 (含三态计数),
   Sprint 卡含 per_prd_stats/prd_plan_map。
3. **gantt 时间戳破 mermaid 解析**: 原样输出 `2026-09-09T18:06:21+00:00`
   (含时区/微秒), mermaid dateFormat YYYY-MM-DDTHH:mm:ss 无法解析 →
   新增 _ts_gantt() 剥微秒与时区后缀。
4. **mindmap 孤儿节点 KeyError**: 父引用缺失时 `by_id[nid]` 抛 KeyError →
   `by_id.get(nid)` 防御跳过。
5. **空数据无灰块占位**: dataflow 无实体边输出空 flowchart (12 chars)、
   flow/sequence 对 project scope 输出空链 → 补 `未实现` 灰块节点/提示。
6. **(追加) _tree_full 内聚**: mindmap 需完整 nodes, 原实现由 build_flow_for
   事后补 (直接 build_conv_flow 渲染则缺) → build_conv_flow 返回自带 _tree_full。

## 4. 入口实现 (手术单 §三 CLI/API/shell)

- **CLI** `factory flow <cid|--project pid> [--format ...] [--out f] [--json]`:
  cli_factory.py flow_cmd (仿 gp_trace_cmd) + parser + dispatch 分支。实测:
  md 输出 ✓ / 缺失项目 "(不存在)" RC 0 ✓ / --out html 写文件 ✓。
- **API** api/flow.py `flow_route(scope, id, format="md", kind="", root=None)`:
  kind 短写 (mermaid:gantt) 兼容; 未知 scope/format → {ok:False, error} 失败安全;
  已导出进 api/__init__.py (__all__ 登记 flow_route)。实测 3 例通过。
- **Shell** canonical_shell.py: `/flow` (默认 md 表格) + `/flow <format>`;
  html 在 shell 内禁用 → 提示走 CLI --out。只加分支, 未动既有分支。
  实测: md/mindmap 渲染 ✓ html 禁用提示 ✓ badfmt 回退 md ✓ 无会话提示 ✓。

## 5. 验收结果 (手术单 §五 A-L)

tests/console/test_flow_views_s2.py — **13 passed** (tmp fixture 真走 canonical 链:
理解→PRD→approve→递归树 decomposer 注入 4+层+data_entities→approve→
fake capability 注入执行→断言渲染):

| 验收 | 内容 | 结果 |
|---|---|---|
| A | md 9 阶段齐全 + 状态与 Truth 一致; 未做含"未实现" | ✅ |
| B | todo 复选框数=叶数; -[x] ⇔ COMPLETED | ✅ |
| C | mindmap 含 4+ 层嵌套, 与树一致 | ✅ |
| D | flow 阶段链含灰块节点 (架构选择[未实现]:::grey) | ✅ |
| E | gantt 仅真实时间戳叶, 无编造日期 | ✅ |
| F | dataflow 边来自 data_entities (orders/payments/products) | ✅ |
| G | sequence/state/dag 各出合法文本; 状态迁移=代码常量 | ✅ |
| H | echarts graph/sankey 可 json.loads, 与 md 同源 | ✅ |
| I | html 单文件含表格 (离线可读) + CDN 注记 | ✅ |
| J | project view: backlog/Sprint/每 PRD 迷你流与 project_agile.json 一致 | ✅ |
| K | API/CLI 同源: flow_route == build_flow_for 渲染一致; kind 短写 | ✅ |
| L | 诚实: 无验证→UNKNOWN; 缺失→灰块/"(不存在)"; 零假绿 | ✅ |

## 6. 回归与质量

- 手术单 §六 指定文件 + 相关: 8 文件 **69 passed** (test_flow_views_s2 13 +
  recursive_decomposition + project_agile + trace_query_s2 + golden_path_e2e +
  canonical_golden_path + llm_semantic_interpreter + task_decomposition)。
- ruff: 本刀 4 新/改文件 (flow_views/api.flow/canonical_shell/test) **全过**;
  cli_factory.py 19 错误与 HEAD 基线完全一致 (零新增, pre-existing);
  api/__init__.py 剩余 1 错误 (conflict_status, HEAD 已有, pre-existing)。
- 诚实铁律核对: 架构选择域无 Truth → 灰块; 无验证证据 → UNKNOWN;
  degraded/warning 上板; HTML 注 CDN 依赖 + 离线降级表格。零假绿。

## 7. 非目标 (本刀未做, 记录在案)

- 领导大屏跨项目指标集 (成本/人力/预测) — 需新数据域 (设计文档: 刀10+)。
- 项目/服务器运维域 (刀11/12, ops_deliveries/ops_servers 规划中)。
- WebUI 壳 + 控制按钮 (批准/重试/暂停 — 需 M4 真命令先行, 刀10)。
- 本刀未 commit (留待一次性 PR; 按纪律 commit 被拒即停手问用户, 不擅自提交)。

## 8. 已知限制 (诚实)

- fake capability 注入执行不写 verification → 9 阶段"验证"如实 UNKNOWN
  (真实 executor/LLM 链路才有 PASS 证据; 这是诚实的, 非缺陷)。
- echarts sankey project 级 value 为粗略计数 (PRD→Sprint 各 1), 完成量用
  sprint stats; 精确叶级 sankey 待 WebUI 壳 (刀10)。
- html 渲染为纯文本表格内嵌 + CDN 图型注释 (无真 ECharts/Mermaid 实例化),
  满足"离线可读 + CDN 注记"验收 I; 真图型实例化属刀10 WebUI 壳。

## 9. 收口状态

- **不 commit** — 与 cut5/6/7 改动一并留待一次性 PR (用户裁决中)。
- 工作区现状: HEAD=dcf6c98e; tracked 修改 7 (cut5/6/7, 未动) +
  flow_views/api.flow/cli_factory/shell (本刀, 文件数见 git status);
  untracked: flow_views.py, api/flow.py, test_flow_views_s2.py 等。
- 下一步: 用户裁决一次性 PR 提交策略 → 或刀10 (WebUI 壳 + 控制面)。
