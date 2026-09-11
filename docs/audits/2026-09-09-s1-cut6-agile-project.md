# S1 第 6 刀 — 项目级敏捷管理闭环 (Agile Project Management)

> Date: 2026-09-09 | 性质: 实施 (A-F 全量一次完成) | HEAD 基线: dcf6c98e
> 本文件是防反工记忆: 下个会话读此文件即可续接, 不重来。

---

## 0. 模型图 (本刀交付的领域结构)

```
Project (P-* / project_*)                      [project_os 实体, legacy 保留]
  │  ← conversation.project_id (F3 锚点: conversation 元数据)
  ▼
project_agile/{pid}.json   [本刀新域, canonical]
  ├─ backlog: [{prd_id, conversation_id, status: pending|in_sprint|closed}]
  └─ sprints: [{
       sprint_id SPRINT-*, status: planned→active→review→closed,
       prd_ids[], plan_ids[], per_prd_stats{}, stats{total/completed/failed/blocked},
       created_at/started_at/closed_at }]

Golden Path 挂接 (golden_path.py, 幂等/失败安全):
  approve_prd  → PRD 自动入 backlog        (conversation attach 项目时)
  generate_plan→ approved Plan 绑 active sprint (plan_ids + prd_plan_map)
  execute_approved → 结果回写 sprint stats  (按叶状态计数)

Sprint 状态机: planned →(start)→ active →(mark_review)→ review →(close)→ closed
  close 时: per_prd_stats 完成的 PRD → closed; 未完成 (FAILED/BLOCKED/未做) → 回 backlog
```

## 1. 关键决策

1. 新域文件 `project_agile.py`, 数据 `project_agile/{pid}.json` — 不改造 project_os
   entity 系统 (它按 task 级 sprint, 本刀是 PRD 级 backlog/sprint), 不复用避免破坏 legacy。
2. conversation.project_id 存于 conversation 底层 doc (非 public 视图), 经
   product_understanding._load_conv/_save_conv 原子读写。
3. Sprint 状态 planned→active→review→closed; 验收 = 用户 close (沿用 approval 语义,
   不做每 Sprint 独立硬 Gate)。
4. 执行演示用 capability 注入 (真 codex 前几刀已验收); 本刀核心 = 敏捷流转。
5. llm_semantic_interpreter._PRODUCT_HINT_RE 补业务词 (加/积分/会员/下单/兑换/支付/
   订单/购物/电商/商城/优惠/折扣/金额/实现/支持/需要/可以/想要/希望) — 修复 CT F2 P2
   "预筛正则漏委婉表达": "给电商系统加会员积分" 原被误判寒暄 → 降级"嗯我在"。

## 2. A-F 验收对照

- A ✅ 项目锚点: attach_project / get_project_by_conversation / conversation_project_id;
      CanonicalGoldenPath.create_conversation(project_id=) / attach_project / project_view。
- B ✅ Backlog: add_prd_to_backlog (幂等) / list_backlog; approve_prd 成功后自动入
      backlog (attach 时); 未 attach → 零副作用 (兼容单会话)。
- C ✅ Sprint 生命周期: create_sprint (从 backlog 拉) / start_sprint / mark_review /
      close_sprint; close 时未完成回 backlog (per_prd_stats 判定), 完成不回。
- D ✅ Golden Path 挂接: approved Plan 绑 active sprint; execute_approved 回写
      sprint stats (COMPLETED/FAILED/BLOCKED/总数 如实)。
- E ✅ 视图: project_agile_view / CanonicalGoldenPath.project_view / sprint_view;
      canonical_shell /project /sprint; factory trace 带 project/sprint 上下文。
- F ✅ 本文档 (防反工)。

## 3. 真实闭环演示 (电商加会员积分 — 全流转)

数据 root: /var/folders/.../s1c6-i2fplq70 (tmp; 真实 LLM semantic=True)
项目: project_90d5e7e29c73 (演示电商系统)

```
[0] 建项目 project_90d5e7e29c73
[1] 会话1 (conv-c705f1d0d6df) attach 项目
    LLM 理解 (semantic=True): 3 ops → facts:
      IDEA:        给电商系统增加会员积分功能
      REQUIREMENT: 会员下单可获得积分
      REQUIREMENT: 积分可用于抵扣现金
[2] PRD1 PRD-7c884c05f0d2 approved → 自动入 backlog
[3] 会话2 (conv-f4ad50abf405) "积分可兑换优惠券:100积分换5元券"
    PRD2 PRD-81aaa67b9060 approved → backlog = [PRD1, PRD2]
[4] Sprint1 SPRINT-20593418 created (拉 backlog 全量) → start
[5] Plan1 PLAN-043a1b63 generated + approved → sprint plan_ids=[PLAN-043a1b63]
[6] 执行 Plan1 (capability 注入 — 演示流转):
    execute state: COMPLETED | sprint stats {total:3, completed:3, failed:0, blocked:0}
      实现功能: 会员下单可获得积分 → COMPLETED
      实现功能: 积分可用于抵扣现金 → COMPLETED
      验证与交付 → COMPLETED
[7] Sprint1 review → closed:
    backlog after close = [PRD-81aaa67b9060]   (PRD1 完成不回; PRD2 未做回 backlog)
[8] Sprint2 SPRINT-b43f59e1 created (拉剩余 PRD-81aaa67b9060) → start
    项目视图: backlog=0, sprints=2, active=Sprint2-积分商城
```

factory trace 输出含: 理解 v?/facts → PRD → Plan → 5 类认知审计事件
(PRODUCT_INTELLIGENCE/PRD_CREATED/PRD_APPROVED/PLAN_CREATED/APPROVAL_DECIDED)
+ project (backlog/sprint 上下文)。

## 4. 测试与回归

- test_project_agile_s2.py: 12 passed (A anchor 2 / B backlog 3 / C lifecycle 3 /
  D attach 2 / E views 2)
- test_llm_semantic_interpreter.py: 13 passed (含 TestProductHintRegex 2: 委婉业务词
  触达 LLM / 寒暄不调 LLM)
- 全组回归: 146 passed (17 文件, 第 1-6 刀相关全绿)
- ruff: 改动文件全过; cli_factory 21 pre-existing 基线不变

## 5. 后续刀候选 (不在本刀)

- 真 codex 执行敏捷闭环 (本刀用 capability 注入; 真 codex 需长时跑)
- Sprint 级验收报告/交付物 (M5)
- WebUI 项目视图
- 多层递归 task tree (LLM 主导, 用户已拍板方向 — 待排期)

---
*Commit: (见 git log) | 工作区 tracked clean*
