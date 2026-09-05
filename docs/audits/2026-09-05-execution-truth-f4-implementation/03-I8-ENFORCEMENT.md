# 03 — I8 ENFORCEMENT (P0-F4 IMPL, 2026-09-05)

> I8 = Production Core 硬约束 — 落地状态

---

## 1. 达成方式

**I8: Production artifact MUST NOT bypass canonical Artifact lifecycle。**

- chain 生产路径: finalize_node_run 成功分支内 _absorb_execution_artifact →
  create_artifact (GENERATED) — 与 EXS 吸收/ver 物化同函数同 pipeline,
  **属于 production execution contract** (D4 定义)
- 禁止的 "事后补登记" 路径不存在: 无独立 admin API 创建 art-*;
  art-* 唯一 writer = create_artifact, 仅被 execute/finalize (生产) + rollback
  (恢复) 调用

## 2. 幂等 (F4 §9)

create_artifact exs_id 幂等: 同 EXS 重复 finalize (retry/callback/恢复) →
同 art-* (锁内查+写, 原子防 race)。E2E-3: 重复 finalize art 1→1。
execute_node_run (workflow): I10 语义保持 — 每 attempt 新 art (修复历史), 不误合并。

## 3. Failure / Recovery

- 收纳失败 → 返回 None, run 仍 COMPLETED (失败安全, 不阻断) — 已知 limitation:
  收纳失败无重试 (记录于 Known Issues)
- Recovery: 新 TaskRun → 新 art (不覆盖旧 attempt) — E2E-4 实证

## 4. 未覆盖 (Known Limitation)

- gateway/agent_runtime 的 legacy 产物 (exec ART-*/EXS patch 文件) **未迁移**
  为 art-* — 保持 legacy (D1/F4 §21); 未来新执行已走 art-* (I8)
- 当前 chain 收纳 type 固定 "report" (执行输出快照); patch/test 类型产物收纳
  未接入 (gateway 不落 patch_text 到 EXS 记录 — 需未来 gateway 输出扩展)
