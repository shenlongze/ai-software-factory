# 03 — IA REALITY (READ-ONLY)

## 实际页面
- Workspace 级: conversation (默认); (dashboard 曾存在)
- Project 级 7 页: overview / docs / todo / workflow / runtime / quality / ops
  (router.tsx PROJECT_ROUTES — 7 条真路由)
- 组件: 35 af + ds 设计系统; workspace shell/frame; preview window

## 判断
1. 用户真需要: overview / conversation / todo / workflow / runtime /
   quality / workspace(文件/产物/预览) + **缺验收/发布**
2. 历史遗留: 少 (workspace 页独立 conversation 与 project 页并存的
   作用域切换是设计)
3. 重复: conversation 存在 workspace 与 project 两作用域 (公司/项目) —
   有意设计 (SessionScope)
4. 无真实数据页: 无 (均有 API); workflow/runtime 可能落 mock fallback
5. 核心生产能力无入口: ACCEPTANCE + RELEASE (最大 IA 缺口); Request
   Change; 证据/审计入口弱
6. 应合并: 暂无
7. 应保留: 现状 2 级 IA (workspace 公司层 + project 层)

## 建议 (不重构, 补缺口)
- Project 页加 "验收/发布" (或并入 quality→acceptance→release 纵向流)
- workspace 产物/代码/预览 = S46 成品查看入口, 已基本可用
