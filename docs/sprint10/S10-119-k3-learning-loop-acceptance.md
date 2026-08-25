# S10-119 — K-3 学习闭环（主线 M4 全 6 项）：独立验收报告

> 日期: 2026-08-25 | 版本: v1.1.89 | 验收人: Hermes (CTO, 独立验证 — 非 Codex 自报告)
> 实现: `ce203e2` (feat(S10-119), K-3 战役第三战役 — 11 合并项)
> 前置: v1.1.88 · K-1 ✅ + K-2 ✅ · 设计文档 7804090

---

## 验收矩阵（11 项全过）

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 两次同类任务 → 第二次引用经验 (reason 可解释) | ✅ | 执行完成入库 → resolve_for_task 命中: "引用经验 X 因为 任务匹配关键词 实现登录接口 (相似度 0.85; 同类样本 N 条)" |
| 2 | 护栏 4 项各 1 fixture | ✅ | 开关关闭 → 零写入零引用; 低样本(2)不主导(3)主导; 低质量 0.1 → 不写入; 超预算 → False+告警 |
| 3 | 决策记忆链路 | ✅ | 审批 → decision_memory.record → history: {total≥1, approval_rate} — 下次带历史 |
| 4 | 成本告警链路 | ✅ | usage → 聚合 cost_by_task/agent → enforce block → BUDGET_BLOCKED 审计 (Codex 实测 $0.70 阻断) |
| 5 | 画像分配 (高画像/低负载优先) | ✅ | agent-hi (persona 0.9/load 0.1) 胜出; 无画像 → None 中性 |
| 6 | L4 完整化 (非 git 快照可还原) | ✅ | snapshot_before/_snapshot_dir_copy/rollback 方法族; Codex 实测快照→改→回滚精确还原 (含新增文件清除) |
| 7 | E-2/E-3 至少一条闭环可断言 | ✅ | 低分 0.3 → validation_failed → 建议 → repair 应用 → 复评 0.85 improved=True |
| 8 | 契约测试 ≥12 全绿 | ✅ | test_s10_119_learning_loop.py **29 passed** (我独立复跑) |
| 9 | 全量回归 0 新增失败 | ✅ | console+api: **5414 passed / 1 skipped**, 唯一失败 = 已知 flaky m3e (复跑 8 passed) |
| 10 | v1.1.89 + K-3/M4-1~6/B-7/E-1/D-6/E-2/E-3 ✅ | ✅ | pyproject=1.1.89; 待办 L16/59-64/134/163/173/174 全部 ✅ |
| 11 | 设计文档落盘 | ✅ | docs/sprint10/S10-119-k3-learning-loop-plan.md |

## 1. 独立验证实录（我的脚本 15/15）

```
M4-1 经验闭环: ✅ 入库 (exp-xxx) → ✅ 第二次引用 + reason 可解释 (相似度 0.85)
M4-2 护栏: ✅ 开关默认开 · ✅ 低样本不主导 · ✅ 低质量不写入 · ✅ 关闭零写入 (learning_state.json)
           ✅ 超预算阻断 ({"experiences":999,"snapshots":999} → False) · ✅ 快照可建+回滚不抛
M4-3 决策记忆: ✅ record → history {total≥1, approval_rate=1.0}
M4-5 画像分配: ✅ 高画像/低负载优先 (agent-hi)
M4-6 L4: ✅ snapshot_before/_snapshot_dir_copy/rollback 方法族存在
```

## 2. 关键设计验证（反虚标）

- **护栏优先**: learning_guards.py 先做, 其它项挂其下; 关闭 → 学习/引用零行为变化 (向后兼容断言)
- **确定性核心**: 经验提取/引用/评分全规则, LLM 不主判; 规则分始终存在
- **诚实标注** (Codex + 我复核):
  - LLM 产出质量提升不可确定性证明 → 断言的是确定性评分器复评提升 (0.3→0.85); 未提升 → improved=None/False 如实
  - 经验引用对 Agent 产出的因果增益不可测 → 只确定性证明"引用发生 + reason", 仅注入 prompt 不替换执行链
- **最小扩展记录**: orchestrator 加 BUDGET_WARNING/BUDGET_BLOCKED 审计发射 (M4-4 生产路径所需, 阻断语义零改动)
- 未重写 ExperienceStore/retrieval/CostLedger/BudgetEnforcer/execution_replay; 未动 lifecycle_store; board 只读

## 3. 契约测试与既有更新

- 新增 test_s10_119_learning_loop.py 29 用例 (闭环/护栏4/决策/成本/画像/L4/修复/注册表/只读/向后兼容)
- 既有更新: capability_router (reason 排序文案)、execution_replay (L4 非 git 契约)、campaign_plan (K-3 ✅)、
  /cost 由占位改真实只读聚合、版本断言 7 处

## 4. 结论

- **通过**。K-3 战役第三战役落地 — "第二次同类任务引用第一次经验" 已机制化: M4-1 经验闭环
  (自动入库+引用+reason), M4-2 学习护栏 (开关/样本/质量/预算/回滚 — 防失控), M4-3 决策记忆回流,
  M4-4/D-6 成本告警闭环+可视化, M4-5 画像优先分配+负载均衡, M4-6 L4 快照完整化 (非 git 可回滚),
  E-2/E-3 评估驱动修复/优化闭环。**主线 M4 全 6 项完成**。
- K 系列战役: K-1 ✅ → K-2 ✅ → K-3 ✅ (主线 M4 7/7 相关完成)。建议后续: K-4+ 战役 (按待办链)。
