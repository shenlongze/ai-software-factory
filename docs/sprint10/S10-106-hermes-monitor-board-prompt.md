# Hermes 提示词 — Sprint 规格（任务监控面板：todolist + 进度条 + 标签 + 主线管理）

> 用途: 三部门循环第 ② 步 — Hermes(CTO) 产出 Sprint 规格，供 Codex(工程) 实现
> 日期: 2026-08-24 | 前置: v1.1.26 · S10-105 Markdown 渲染进行中 · 全量基线 0 回归

---

【AI Factory Sprint 规格 — 任务监控面板（Founder 需求）】

## 角色
Hermes = CTO + 架构委员会。产出可执行 Sprint 规格，不写实现代码。

## 背景（Founder 实测痛点）
Founder: "测试过程中总会脱离主线, 完善周边必要功能, 做多了, 很多线可能没走完,
脑袋记不住了" — 需要:
1. **监控面板**: 类似 todolist + 进度条 + 标签, 实时监控 AI Factory 项目进展
2. **主线管理**: 区分 主线(必须走完) vs 周边(做多了的), 提醒主线未完成
3. **同步 Hermes**: 任务完成 → 面板更新 → 可汇报

## 现有基础（复用不重造）
- `factory-core/dashboard/` DashboardCollector 已收集: tasks/agents/workflows/
  executions/checkpoints/projects/catalog/metrics/events/agent_utilization/runtime_usage
  （数据层就绪, 无 CLI 展示）
- 待办清单 `docs/sprint10/待办清单-已发现未落地.md`: M1-M7 + P0-1~P0-11（主线任务源）
- §5.10 递归进度 · §5.11 多维视图 · §5.7 可视化（设计）
- rich 依赖（进度条/表格/标签渲染可用）

## Sprint 目标（3 项）
1. **/board 命令（🔴）**: 终端监控面板
   - 主线任务（M 里程碑 + P0 待办）todolist + 进度条（[████░░] 3/5）
   - 标签（P0/P1/P2 · 主线/周边 · ✅/🚧/📐）
   - 实时: 执行中项目/任务进度（DashboardCollector 数据）
2. **主线 vs 周边管理（🔴）**: 待办清单主线标记（主线=必须走完）;
   /board 显示"主线未完成"提醒 + 周边任务单独区（做多了的, 不丢但标周边）
3. **汇报导出（🟡）**: /board --report → 生成给 Hermes 的进度汇报
   （主线完成/进行中/未开始 + 周边列表 + 下一步建议）

## 范围声明（§10.5.7.6）
- 本 Sprint 做: /board 面板 + 主线/周边标记 + --report 导出
- 明确不做: Web 监控大屏（§5.7 设计, 后续）· 自动任务规划 · 通知推送
- 连带发现（进 backlog）: Web 大屏 · 实时刷新（SSE）· 与消息渠道联动
- 波及面: 新增 board 模块/命令 + 待办清单主线标记 → 会话/CLI → 会话+CLI 测试

## 规格必须包含（8 项）
1. 面板数据结构（主线清单/进度/标签/执行数据 来源与聚合）
2. /board 渲染（rich: todolist + 进度条 + 标签表格; 终端宽度适配）
3. 主线 vs 周边标记（待办清单加 tag: 主线/周边; 面板分组显示）
4. 实时性（每次 /board 实时聚合 DashboardCollector + 待办清单, 非缓存）
5. --report 导出（markdown 汇报, 对齐 Hermes 汇报格式）
6. 契约测试要点: 面板渲染内容/主线提醒/周边分组/--report 输出/无数据容错/向后兼容
7. Codex 写 scope
8. 边界: 不改产品发现/执行逻辑 · 不做 Web

## 验收标准（Codex 完成后，你独立验证）
- /board 显示主线 todolist + 进度条 + 标签, 主线未完成有提醒
- 周边任务单独区（做多了的不丢, 标周边）
- --report 生成 markdown 汇报（主线完成/进行中/未开始 + 周边 + 建议）
- 实时: 项目执行后 /board 数据更新
- 全量回归 0 新增 + git clean
- 版本: 本 Sprint 完成后 bump v1.1.27

## 输出物
- 规格文档: `docs/sprint10/S10-106-monitor-board-plan.md`
- 供 Codex 的指令摘要

## 关键纪律
1. 代码存在 ≠ 能力；自报告 ≠ 事实 — 独立验证（真实 /board 渲染 + --report 实测）
2. 禁止 stub/fake；无数据/无 rich 诚实降级（纯文本面板）
3. 复用 DashboardCollector / rich / 待办清单 — 不重造
4. 向后兼容: 待办清单格式兼容（加 tag 字段, 旧条目默认主线）
5. 版本: v1.1.26 → v1.1.27（patch+1）
