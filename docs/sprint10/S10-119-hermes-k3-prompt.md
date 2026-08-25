# S10-119 · K-3 学习闭环（主线 M4 全 6 项）— Hermes 提示词（2026-08-25）

> 战役: K-3（docs/战役规划-统一路线.md §2 K-3）· 目标版本 v1.1.89（当前 HEAD v1.1.88）
> 交付后: 待办清单 K-3 ✅ + M4 主线 6/6 ✅ · 战役规划状态追踪 K-3 ✅
> Founder 已拍板: M4-6 快照/回滚提前并入 K-3（保证 M4 主线随 K-3 完成）

---

请作为 Hermes 派发 Sprint 任务给 Codex，遵守既有纪律（pre-flight → plan → dispatch → verify → acceptance → report）。

【任务】S10-119 · K-3 学习闭环（主线 M4 全 6 项）
版本目标：v1.1.89（从实际 HEAD +1；若并发消耗则顺延，不回退版本）

【背景（K-3 是什么）】
战役规划第三战役（依赖 K-1 路由 ✅ + K-2 质量分 ✅）。让 Agent 变强且可控：
"第二次同类任务引用第一次经验" —— 学习闭环 + 护栏 + 决策记忆 + 成本告警 + 画像分配 + 快照回滚。
合并项：M4-1~M4-6（主线全 6 项）+ B-7/E-1 经验回写 + D-6 成本可视化 + E-2 修复深化 + E-3 优化完善。

【现状（实事求是，pre-flight 必须核对，不限于此）】
1. 经验: memory/experience_store.py ExperienceStore + retrieval/unified.py retrieve_experience +
   actions.py trigger_learning (S10-067: 提取→模式/Agent 画像→审计) 已有 —— 但"执行完自动入库→
   下次路由/执行引用"断 (B-7)
2. 画像: UserPersonas (S10-066 产品用户画像) + agent_profiles (trigger_learning 产出) ——
   M4-5 画像优先分配需接 capability_router (K-1 已有 load 字段挂点 + K-2 已回写 quality_score)
3. 决策记忆: audit_event.py DECISION_LEARNED 事件已注册; evidence.py 提及组织记忆回流 (M1c) ——
   M4-3 需"审批决策 → DECISION_LEARNED → 组织记忆 → 下次少审"闭环
4. 成本: cost_ledger.py CostLedger (record/aggregate/estimate/cost_by_*) +
   budget.py ProjectBudget + BudgetEnforcer (check → ok/warn/review/block) 已有 ——
   M4-4 需 usage→聚合→告警/阻断→回填 闭环 + D-6 可视化
5. 快照/回滚: execution_replay.py L4 受限版 (git stash create 基线 → reset --hard 回滚;
   非 git 仓库 → ReplayError 明确) —— M4-6 需完整化 (非 git 工作区快照)
6. 修复/优化: repair_task.json + repair_task 命令已有; decomposition_evaluator (M3d 评估器) ✅ ——
   E-2 修复深化 / E-3 优化完善 需评估驱动闭环
7. K-2 挂点 ✅: quality_score 已回写 capability_router (学习样本数据源)

【设计与实现要求（先出设计文档 docs/sprint10/S10-119-k3-learning-loop-plan.md，批准后再实现）】
1. M4-1/B-7/E-1 经验闭环（核心）:
   - 执行完成后自动经验入库（结果+quality_score+上下文摘要, 确定性规则提取, 不依赖 LLM 做主判）
   - 下次同类任务: 路由/执行 prompt 引用命中经验（带 reason: "引用经验 X 因为 Y"）
   - 闭环可断言: 第二次同类任务 fixture 能查到引用
2. M4-2 学习护栏（必须, 防失控）:
   - 总开关: 关闭 → 学习/引用零行为变化 (向后兼容断言)
   - 样本可信度: 样本数 < 阈值 → 不主导/降权; 低质量样本 (quality_score 低) 不写入
   - 预算上限: 学习存储/引用成本超限 → 阻断 + 告警
   - 回滚: 学习导致的画像/经验可一键回退 (快照)
3. M4-3 决策记忆回流 E5: 审批决策 (approved/rejected) → DECISION_LEARNED 事件 →
   组织记忆落盘 → 下次同类审批少审/带历史 (可断言)
4. M4-4/D-6 成本告警闭环: CostLedger usage → 聚合 → 超预算 BudgetEnforcer 告警/阻断 →
   回填 (cost 关联 task/agent); board/CLI 成本可视化 (只读)
5. M4-5 画像优先分配 + 负载均衡: capability_router 排序纳入 agent_profiles 画像分 +
   load 均衡 (K-1 挂点字段已就绪; 排序规则确定性可解释)
6. M4-6 快照/回滚 L4 完整化: 非 git 工作区快照 (目录级压缩/复制基线 → 还原), 失败安全
   (不可快照 → 明确报错不静默); git 仓库路径沿用受限版
7. E-2 修复深化 / E-3 优化完善: 评估驱动 (复用 M3d/execution_quality) →
   至少一条可断言的修复/优化闭环 (如低分任务 → 自动修复建议 → 应用 → 复评提升)
8. 注册表门禁（P0-10/11 强制）: 新增 CLI 命令/意图/action/事件/API 必须同步注册表

【硬边界】
- 依赖 K-1/K-2 已交付 (capability_router quality_score/load), 不重造路由
- 学习核心用确定性规则; LLM 仅可选辅助, 规则分始终存在; 护栏必须真实生效
- 不破坏现有: ExperienceStore/retrieval/CostLedger/BudgetEnforcer/execution_replay 语义
  (复用扩展, 不重写); 不动 lifecycle_store (S10-115)/能力路由核心 (K-1)
- 护栏优先级最高: 任何学习路径都必须可开关、可回滚、有预算上限
- board 展示只读; 写操作走 CLI/API

【验收标准（独立可验证，非 Codex 自报告）】
1. 经验闭环: 两次同类任务 fixture → 第二次引用第一次经验 (断言: 引用存在 + reason 可解释)
2. 护栏: 关闭零变化 · 低样本不主导 · 低质量样本不写入 · 超预算阻断 (各 1 fixture)
3. 决策记忆: 审批 → DECISION_LEARNED → 组织记忆 → 下次少审 (断言链路)
4. 成本告警: usage→聚合→超预算告警/阻断→回填 (断言)
5. 画像分配: 高画像/低负载 Agent 优先 (capability_router 排序断言)
6. L4 完整化: 非 git 工作区快照/回滚 fixture (可还原); 不可快照 → 明确报错
7. E-2/E-3: 至少一条评估驱动修复/优化闭环可断言 (低分→建议→应用→复评提升)
8. 契约测试 ≥12（闭环/护栏/决策/成本/画像/L4/修复/注册表/只读/向后兼容）
9. 全量回归 0 新增失败（环境性失败如实标注, 与 HEAD 基线对照）
10. 版本 v1.1.89（pyproject + CHANGELOG + FEATURES + 版本断言 + 待办清单 K-3/M4-1~6/B-7/E-1/D-6/E-2/E-3 ✅ 同步）
11. 设计文档落盘 docs/sprint10/S10-119-k3-learning-loop-plan.md

【诚实记录】学习闭环任何环节无法确定性证明 (如引用不可断言) → 如实标注, 不假装闭环;
改动波及面超预期 → 列出并征询, 不擅自扩大
