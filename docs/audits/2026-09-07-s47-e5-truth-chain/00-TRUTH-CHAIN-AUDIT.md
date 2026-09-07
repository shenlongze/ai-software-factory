# 00 — Product Truth 全链路 Read/Write/Refine/Continue 审计 (2026-09-07, READ-ONLY)

## 目标
IDEA→Discovery→Requirement→PRD→Plan 每一阶段产出能否被下一阶段真实
读取/理解/修改/继续生产 (E4 规律: Write API 有了还不够, 须 Read/Refine/
Continue 齐)。

## 函数矩阵 (product_truth.py 取证)
| 域 | create | get/list | update (Refine) | transition (Continue) | 会话工具 Read | 会话工具 Write |
|---|---|---|---|---|---|---|
| idea | ✓ | ✓ | ✗ | ✓ (created/refined/validated) | get_product_record (kind=idea 未暴露) | ✗ 无 create_idea 工具 |
| discovery | ✓ (需 idea_id) | ✓ | ✗ | ✗ 无 transition_discovery | get_product_record ✓ | save ✓ (需 idea_id) |
| requirement | ✓ | ✓ | ✓ (E4) | ✓ | ✓ | ✓ |
| prd | ✓ | ✓ | ✗ | ✗ 无 transition_prd (状态表 _PRD_T 存在但无函数) | get_product_record ✓ | ✗ save 拒绝 (引导 plan_development) |
| plan | ✓ | ✓ | ✗ | ✗ 无 transition_plan | get_product_record ✓ | ✗ save 拒绝 |

## 会话写工具现状 (agent_loop)
- save_product_record: requirement ✓ / discovery △(需 idea_id) /
  prd ✗拒绝 / plan ✗拒绝 (引导 plan_development → 但 plan_development 产出
  走 session_plans/PendingPlanStore — 非 canonical PLAN-*, 旁路!)
- plan_development: 会话计划 (审批流) — 与 canonical plan 域不直连
- create_idea: 无工具 → canonical 链头无法从会话建立

## 缺口 (按层)
1. **idea 链头**: canonical 链从会话不可起始 (无 create_idea 工具;
   get_product_record kind=idea 未暴露)
2. **Refine 覆盖**: 仅 requirement 可 update; idea/discovery/prd/plan
   内容不可改 (draft 期也须版本化?) — 与 E4 规律冲突
3. **Continue/推进**: transition_discovery/prd/plan 公共函数缺失
   (状态表在但无 API) → 阶段推进 (pending→completed / draft→approved)
   不可从会话做
4. **PRD/Plan 会话产出旁路**: save 拒绝 + plan_development 非 canonical →
   E4 前同款 Write/Read 不对称 (写不进 canonical 或写进旁路)
5. requirement 无 project_id 绑 (经 idea/discovery 链) — 单建 REQ 归属弱
   (7daccf2c 已用"存在·未绑定"诚实显示; 链完整后可消)

## 建议 (待批准实施, 非本报告执行)
- 工具层: create_idea 会话工具 + save_product_record 支持 idea;
  get_product_record 暴露 idea; save/update 按域对齐 Refine
- product_truth: + transition_discovery/prd/plan + update_idea/discovery/
  prd/plan (draft 期) — 统一 _update_content/_transition 封装
- PRD/Plan 会话产出: 决策 — plan_development 改走 canonical plan writer
  或新增 plan 会话工具直连 create_plan (消除旁路)
- FACT/INFERENCE/PROPOSAL/TO_CONFIRM 分层 (E4 治理项 1) 在产出结构落地

## 判定
产品主链 Truth 的 Read ✓ / Write △ / Refine △(仅 req) / Continue △
(仅 req/idea) — 存在对称性缺口; 下一阶段建议按上列补全后, 再验证
跨阶段 (REQ→PRD→PLAN) 真连续生产。
