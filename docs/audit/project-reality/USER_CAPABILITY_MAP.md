# USER CAPABILITY MAP (2026-09-02, STEP 8)

## User CAN DO (production-proven)
- 创建/管理项目, backlog 任务 CRUD, sprint/milestone (M4)
- 会话中发自然语言 → 制定计划 → 批准 → 自动建任务 (M4, E2E)
- 任务按依赖自动执行 (Ready/Waiting/Blocked, M4)
- 停止任务 (CANCELLED), 崩溃后恢复 (recover), 失败重试 (FAILED→READY) (M4/M3)
- 计划自动完成聚合 (全 DONE→completed, 含 FAILED→failed) (M4)
- 查看审计事件/任务历史/进度卡 (M4/M3)
- 触发外部 Agent 执行 (gateway router) — 真实执行记录 (M3)

## User CAN PARTIALLY DO
- 需求捕获 (可存 requirements.json + 查询) — 但无法从需求追到任务
- 执行验证 — 有 exec test_result, 不闭环
- 从任务看产物 — 仅 exec 域, 会话链无关联
- 用专业角色 Agent (developer/pm 等) — 有注册+历史记录, 触发入口不明

## User CANNOT YET DO
- 需求 → PRD → 计划的产品链路 (PRD 实体不存在)
- 按任务/项目选择模型 (无动态模型路由)
- 需求变更 → 版本化 → 影响分析 → replan
- 从需求或任务完整反查到最终产物 (追踪链断裂)
- 让系统从经验学习改进 (无闭环)

## USER-FACING CAPABILITY EXISTS BUT NOT PRODUCTION-PROVEN
- 371 API 中未触发部分 (learning/optimization/release 等管理端点)
- Product Intelligence 分析 (模块可调, 分析结果不落盘)
- MCP/Plugin/Skill 深度能力 (注册有, 生产消费不明)
- WebUI 全功能 (仅核心流程浏览器验证过)

## FUTURE (产品自标里程碑, 非缺陷)
- Experience→Learning 闭环 (M4 承诺 L411)
- Replanning / 需求变更回流 (M3 承诺 L6620)
- Release 闭环 / PRD 深度化 (M3/M4)
