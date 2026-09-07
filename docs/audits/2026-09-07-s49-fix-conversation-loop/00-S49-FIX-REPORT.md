# 00 — S49-FIX REPORT (2026-09-07)

## 1-4. 修改前 Context / 改了什么
- 前: hist 4 轮纯文本; 工具结果只存 meta.output (500) 从不注入下轮
  上下文 → '结果呢?' 只能重查/瞎说 (S49 P0 实锤)
- 改: _history_text 4→8 轮 (含 meta 工具结果 [工具 X 结果]);
  _tool_result_text 无条件注入最近 3 轮工具结果 (账本视图 bypass 修复);
  回答纪律 system (结论先行/复用事实/禁空转/不确定明说)

## 5-9. 跨轮复用 / Follow-up / 合成 / Truth
- 机制就位 (meta.output 持久化 ✓ + 注入 ✓ + 纪律 ✓)
- 真实行为: 部分生效 (CASE3 单工具聚焦; CASE4-6 有产出动作)
- 但 CASE2 仍重查 (见下)

## 10. 真实 6 案例结果 (P-b0adfaa6, 真实 LLM)
CASE1 现在项目什么情况 → status+scan, 结论充分 ✓
CASE2 结果呢? → 仍重查 status+scan (历史已含 CASE1 结果+注入, LLM 仍
  自证重查 — 纪律单条权重不足 / 20+ system 稀释)
CASE3 什么情况 → 单工具聚焦回答 ✓ (较前改善)
CASE4 继续需求分析 → get+save (但操作跨项目 REQ-97d28735 — 见下)
CASE5 然后呢? → save 失败 (kind/title 参数缺失) → 回答声称定稿但未存
CASE6 太模糊了 → save 失败循环 ('title 必填') 未自愈

## 新发现 (P1)
- get_product_record (kind 无 id) 返回全局最近 → 跨项目泄漏:
  P-b0adfaa6 会话操作 S48F 项目 REQ-97d28735 (需求归属/项目过滤缺失)
- save_product_record 参数失败无自愈 (agent 反复缺 title 空转 2+ 轮)

## 11-14. 成本
- context: 4 轮→8 轮 + 工具结果段 (预期 +40-80% 历史 token) — 允许
  (Correctness first)
- LLM calls 稳定 (每用户轮 1 主循环 + governor 1)

## 15-19. 合规
无 hard-code / 无新增中间层 / Product Truth+Gate+Execution 完整保留 /
测试 5+ 回归 42 passed / attributable 0 (1 pre-existing CLI 历轮确认)

## 20. Verdict
机制修复 ACCEPT (工具结果跨轮可见已就位 — 结构性根因消除)。
真实自然度: 部分 (CASE2 重查残留 = 指令权重/稀释问题; CASE5/6 =
get 泄漏 + save 参数自愈缺失 = 2 个 P1 工具治理项)。
残余 backlog:
  P1a: get_product_record 项目归属过滤 (kind 无 id → 本项目链最近,
       非全局)
  P1b: save_product_record 参数错误 → 工具返回结构化缺参提示,
       agent 引导修正 (防反复空转)
  P2:  回答纪律权重 (合并进单一高优指令贴 user, 降 20+ system 稀释)
