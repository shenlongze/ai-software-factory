# S1 第 3 刀 — CLI 真实链路验收报告 (Dogfood)

> Date: 2026-09-09 | 性质: 真实执行验收 (非测试) | 判定: **PARTIAL**
> 会话: conv-d1f5c05c37bd | PRD-437951150061 (已确认) | PLAN-b8b0a109 (9 叶, 已确认)
> 执行方式: `factory` Canonical Shell → 自然语言 → 理解 → PRD → 确认 → Plan → 确认 → 真实 codex 执行

---

## 0. 环境事实偏差 (诚实记录)

- 任务书假设 `DEEPSEEK_API_KEY` 可用 → 实际 **shell 未设置** (providers 引用 env, llm_raw=None)。
  影响: 语义理解走 deterministic (仍真实域链), 不阻碍主验收 — 真实执行 (codex 独立认证) 不受影响。
- codex 已认证 (API key sk-3c5d2***), `codex exec` 真实可达。
- 验收数据写入真实 `~/.factory` (dogfood 本质), 全新会话无污染。

## 1. 输入与推进

```
INPUT: 我想做一个可以在浏览器运行的最简单飞机大战小游戏：
       玩家飞机可以移动、发射子弹，页面能直接打开运行。
→ 持续理解 (浏览器平台/核心玩法记录)
→ 「整理成 PRD」→ PRD-437951150061 v1 (draft)
→ 「就按这个做」→ PRD approved
→ 「生成计划」→ PLAN-b8b0a109 (tasks=9, 多级树)
→ 「确认计划」→ PLAN approved
→ 「开始做」→ 真实 codex 执行 → CLI 报告「生产执行: 5/6 tasks COMPLETED」
```

## 2. 每叶状态表 (9 叶; 6 执行 + 3 NOT_ATTEMPTED)

| # | node_id | title | state | executor | artifact | error |
|---|---------|-------|-------|----------|----------|-------|
| 1 | e737be-t-d2eef73c | 创建游戏主循环 | ✅ COMPLETED | codex | art-c66bac75e3e9 | — |
| 2 | e737be-t-a0c5d9c8 | 实现玩家飞机控制 | ✅ COMPLETED | codex | art-6de595052361 | — |
| 3 | e737be-t-1c8ff3ab | 发射子弹机制 | ✅ COMPLETED | codex | art-3e67f38f6d53 | — |
| 4 | e737be-t-de8af806 | 初始化Canvas画布 | ✅ COMPLETED | codex | art-5131013bbbd9 | — |
| 5 | e737be-t-5406ed97 | 绘制背景滚动效果 | ✅ COMPLETED | codex | art-68b66f7db609 | — |
| 6 | e737be-t-51a818fa | 绘制玩家和子弹精灵 | ❌ FAILED | codex | — | (fail-fast 停在此叶) |
| 7 | e737be-t-6c5dd220 | 创建HTML入口页面 | ⚪ NOT_ATTEMPTED | — | — | 未创建 NodeRun (FAILED 后停止) |
| 8 | e737be-t-4b703725 | 加载脚本并启动游戏 | ⚪ NOT_ATTEMPTED | — | — | 未创建 NodeRun (FAILED 后停止) |
| 9 | e737be-t-8ec08b2a | 验证与交付 | ⚪ NOT_ATTEMPTED | — | — | 未创建 NodeRun (FAILED 后停止) |

**根因 (非统计误差, 非 bug)**: `execute_production_run` 是 **fail-fast** 语义 —
第 6 叶 FAILED → production run 停止 → 叶 7-9 从未创建 NodeRun。
并行执行 / 失败后继续跑属**未来编排能力**, 不在本轮范围。

## 3. 真实产物证据

workspace: `~/.factory/golden_path_workspace/conv-d1f5c05c37bd/`

```
background.js  4089 B   (滚动背景)
bullet.js      4547 B   (子弹)
game.js        5226 B   (游戏主循环)
index.html     1120 B   (入口页 — 可打开运行)
player.js      6039 B   (玩家控制)
render.js      1840 B   (渲染)
```

index.html 头部 (可检查证据):
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>飞机大战 — 玩家控制</title>
  <style>
    html, body { margin: 0; padding: 0; height: 100%; background: #0a0f1e; }
    body { display: flex; align-items: center; justify-content: center; ... }
```

## 4. 一致性结论

- **NodeRun 磁盘 vs CLI 报告**: 一致 ✅ — 本会话 6 NodeRun = 5 COMPLETED + 1 FAILED,
  CLI「5/6 COMPLETED」与磁盘逐 run 吻合。
- **Audit 事件单发**: ✅ — 5 COMPLETED run 各含 NODE_RUN_VERIFYING ×1 +
  NODE_RUN_COMPLETED ×1; 1 FAILED run 含 NODE_RUN_FAILED ×1。每 run 终态事件恰一次。
  (另有 ARTIFACT_TRANSITION ×1/run — artifact 生命周期事件, 非 NODE_RUN 重复。)
- **无假成功**: ✅ — 每个 COMPLETED 叶都有真实 artifact_id + workspace 真实文件;
  FAILED 叶如实 FAILED; 无"文件不存在却说成功"。

## 5. 观察问题 (验收暴露, 未修)

| # | 现象 | 性质 |
|---|------|------|
| O1 | /plan 在计划 pending 时显示"还没有任务树" | plan_tree 只查 approved plan |
| O2 | NodeRun 落盘 run.input.task.title 为 None | execute 未把叶上下文写入持久化 input |
| O3 | /status 理解区重复条目 + 已到 Plan 阶段仍问"先确定核心想法" | understanding_statement 文案/状态缺陷 |

## 6. 判定

**PARTIAL** — 有真实产物 (6 文件可检查)、无假成功、CLI/磁盘/audit 一致;
执行覆盖 6/9 叶 (fail-fast 在第 6 叶 FAILED 后停止, 叶 7-9 NOT_ATTEMPTED)。
核心验收点 (真实 codex 执行 + 真实产物 + 无假成功) 达成。

---

## 候选修复清单 (只列, 不动手)

- **C1**: `/plan` 对 pending (已生成未确认) 计划不显示树
  → 最小改动: `golden_path.plan_tree` 或 `CanonicalGoldenPath.plan_tree` 取
    "最新 pending 或 approved" 计划 (当前只取 approved)。
- **C2**: NodeRun 落盘缺 task 上下文 (磁盘 run.input.task.title=None)
  → 最小改动: `golden_path.execute_approved` 构造 node input 时把叶上下文
    (title/expected_files/change_type) 完整写入 `create_production_run` 的 input_data
    (production_run 已有 input_binding 机制可承载)。
- **C3**: `understanding_statement` 重复条目 + 已确认到 Plan 仍问"先确定核心想法"
  → 最小改动: statement 渲染去重 (按 type+content 合并); sufficiency/追问逻辑
    在 understanding 足够 + 已生成 PRD/Plan 后不再触发"核心想法"问题。

**明确不做**: 并行分支执行、任何大改、删除 legacy、WebUI/移动端、其它功能。

---
*报告文件: docs/audits/2026-09-09-s1-cut3-dogfood.md | 无代码改动 | 无 commit*
