# 00 — S49-FIX.1 REPORT: Tool Safety & Recovery (2026-09-07)

## 1-3. P1a 根因/修复/scope contract
- 根因: get kind 无 id → lister 全局最后 (跨项目泄漏); record_id 无
  scope 校验; 会话 meta 无归属
- 修复: resolve_record_scope (链解析: idea/prd/plan 自带 project_id;
  discovery→idea; requirement→discovery→idea) → ("project",pid) |
  ("unbound",说明) | None; scoped_recent 本项目归属最近
- contract: unbound 绝不冒充项目 Truth; LLM 无跨项目访问权
  (Tool Boundary deterministic)

## 4. P1b 根因/契约/恢复
- 根因: 缺参只有 "title 必填" 文本 → LLM 反复同错 (空转)
- 修复: 结构化 validation {missing, repairable, reason, required};
  REFINE title 可省略 (保留原标题); PRD 深化需 content; not_found 结构化
- CREATE 缺 title → repairable=False 引导问用户 (不猜/不自动填)

## 5-8. 失败分类 (观察期沿用 + 结构化错误标记)
validation / not_found / scope_denied / governance — 各有结构化返回,
LLM 可行动; 无新增 recovery manager (错误本身即 observation)

## 10. S49 六案例 (真实 WebUI 链 P-b0adfaa6, 真实 LLM)
CASE1 → status+scan 结论充分 ✓
CASE2 '结果呢?' → **工具 [] — 0 工具直接复用上轮结果** (P0 达成!)
CASE3 → 单工具聚焦 ✓
CASE4 '继续需求分析' → 诚实: REQ-97d28735 未绑定 → 不深化冒充;
  提出先建 discovery 挂靠链 (scope 纪律生效) ✓ (半收敛等确认)
CASE5 '然后呢?' → 混乱 (4 工具, PRD id 查 requirement → '不存在';
  回答前段混入工具输出) — P2 残留
CASE6 '太模糊了' → 读 REQ 全文具体呈现 (讨论深化, 未落盘) △

## 11-13. 测试/回归/attributable
新增 7 (全域 resolve/unbound/scoped 隔离/B 更新仍隔离/保留 title/
schema/跨项目写拒) | 回归 100 passed | attributable 0

## 14-18. 合规
无新增中间层 / 无 hard-code / Product Truth+Gate+Execution 完整

## 19. Verdict
P1a ACCEPT (scope isolation 实证: unbound 标注、跨项目 read/write 拒、
recent scoped)。P1b ACCEPT (结构化 recovery; 无 title 空转循环复现)。
Conversation 保持: CASE2 0 工具复用 (S49-FIX 注入生效)。
残余 backlog (P2): CASE5 agent kind 混淆 + 回答混入工具输出 —
  回答合成质量; 非 Tool Safety 缺口。
