# S10-111 — M3 收尾三件套：独立验收报告

> 日期: 2026-08-24→25 | 版本: v1.1.78 | 验收人: Hermes (CTO, 独立验证 — 非 Codex 自报告)
> 实现: `3b0d871` (feat(S10-111), 23 files, +1945/-66)
> 前置: v1.1.77 · M3 主线 4/7 → 本 Sprint 后 **7/7**

---

## 验收矩阵（14 项）

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| M3-5 ① | UX 无 12 行模板占位特征 | ✅ | deterministic ux 资产无 "规则占位"/"进入→操作→完成/反馈"; 含每功能具体流程/页面结构/信息架构 |
| ② | QA 无 10 行模板占位特征 | ✅ | 无 "规则占位"; 含测试层级 + 验证命令 + 每功能用例方向 |
| ③ | PRD 含用户故事+验收标准 | ✅ | "User Stories" + "Acceptance Criteria" 章节; 故事数=功能数 (手算: 2 故事≈2 功能) |
| ④ | 无 LLM 确定性兜底合理 | ✅ | llm_fn=None 路径产出 ux=317/qa=477/prd=662 字符真实资产 |
| M3-6 ⑤ | 提变更 → ChangeProposal | ✅ | propose("加导出功能") → request="导出" + status=proposed |
| ⑥ | 影响分析手算可枚举 | ✅ | 波及 T2(月度报表导出) + PRD 章节"数据导出"; 依赖边收敛 |
| ⑦ | y→PRD v2+新任务; n→不执行 | ✅ | y: PRD 含"变更记录 v2: 导出" + 新任务 (source=change_control, DecomposeEngine 真拆解) + plan.json 更新; n: PRD/tasks 原样 + proposal rejected |
| ⑧ | replan 后 plan.json 更新 | ✅ | plan.json tasks 3 项 (含变更任务, agent_type/verify_cmd 真实字段) |
| M3-7 ⑨ | prepare → pending_arch_review | ✅ | project.json status=pending_arch_review + arch_review 摘要 |
| ⑩ | approve→执行; reject→不执行+反馈 | ✅ | 审批 y→execution_ready→执行; n→保持 pending + feedback, 执行仍阻断 |
| ⑪ | 既有正常路径不受影响 | ✅ | 审批通过后与 v1.1.77 一致 (test_execute_after_approval_matches_v1_1_77) |
| ⑫ | 契约测试各 ≥3 (共 ≥9) | ✅ | test_s10_111_m3_finish.py **19 用例** (M3-5×4 / M3-6×6 / M3-7×5 + 版本/文档×4) |
| ⑬ | 全量回归 0 新增失败 | ✅ | console+api: **5229 passed / 1 skipped / 0 failed** |
| ⑭ | M3 待办 3 项 ✅ (主线 7/7) · v1.1.78 | ✅ | 待办清单 L30-32 ✅; FEATURES.md M3-5/6/7 ✅ v1.1.78; pyproject=1.1.78 |

## 1. 独立验证实录（我的脚本 25/25）

```
M3-5 (13): ux/qa 无占位标记 + 真引擎内容 + PRD 故事/验收 (手算) + 无 LLM 兜底
M3-6 (10): ChangeProposal / impact 波及 T2+数据导出章节 / y→PRD v2+新任务+plan.json / n→全不变+rejected
M3-7 (2): change_control 模块 OK + orchestrator 含审批检查
```

## 2. 三件套如实标注（反虚标）

- **M3-5**: ux/qa = 确定性规则真引擎 (从 ProductIntent 推导, 非模板占位; LLM system_prompt 已深化为可选路径);
  PRD 深度化 = 确定性规则 (无 LLM 兜底真实产出)
- **M3-6**: ChangeControl = 规则真引擎 (propose 解析 / impact 关键词匹配 / apply 复用 DecomposeEngine 真拆解,
  全部真实落盘; LLM 仅 propose 可选补充 — 规则优先)
- **M3-7**: 架构审批门 = 真实落盘门控 (pending_arch_review → y/n → execution_ready/feedback, 复用 ConfirmationGate,
  非 stub); orchestrator + action 双入口阻断

## 3. 契约测试与既有更新

- 新增 test_s10_111_m3_finish.py 19 用例
- 既有更新 (按新门控, 逐条注释): test_session_pipeline (status→pending_arch_review ×4)、
  test_session_orchestrator (插入"批准工程计划"审批 + _approve_arch 帮助 ×6)、版本断言 ×6
- 全量: 5229 passed / 1 skipped / 0 failed

## 4. 诚实记录（工程资产）

- **并发会话**: 实现期间其他会话未提交改动 (cli_factory.py / web/backend/fastapi_adapter.py /
  test_s10_110_board_project_lifecycle.py — Agent/Skill 管理) + 其先行版本提升至 1.1.78。
  Codex 提交仅含本 Sprint 23 文件, 他方 3 文件未扫入未破坏 (与规格 v1.1.78 巧合对齐)。
- 我的验收脚本 2 处夹具问题 (tasks/plan.json 真实格式为 dict; PRD 需含变更关键词) — 修正后 25/25, 非实现缺陷
- 边界遵守: market/competitive/architect 未改; 管线编排顺序未改; M3a-d 引擎内部未改 (验收 ⑪ 证明);
  无执行重放/回滚、无并行线程化

## 5. 结论

- **通过**。M3 主线 **7/7 完成**: ux/qa 真引擎 + PRD 深度化 (M3-5), ChangeControl 变更回流闭环
  (M3-6), 架构审批门 (M3-7)。"让 Agent 会干活"最后三块落地, 全部真实落盘、确定性兜底、无 LLM 诚实降级。
- 建议后续: M5-1 执行重放/回滚; 变更影响分析 LLM 深化 (当前规则关键词匹配, 手算可枚举即验收标准)。
