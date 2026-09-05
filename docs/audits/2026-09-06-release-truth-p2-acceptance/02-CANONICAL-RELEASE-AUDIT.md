# 02 — CANONICAL RELEASE AUDIT (P2-A ACCEPTANCE, 2026-09-06)

## 1. Entity (release_truth.py)

release_id/status/task_id/task_run_id/exs_id/artifact_ids[]/verification_ids[]/
evidence_ids[]/reason/actor/idempotency_key/gate/history/created_at/updated_at/
metadata (git ref external)

## 2. SSOT 唯一性

- releases/release_truth.json = canonical (真实写 — E2E store 检查 4 记录)
- 无第二 SSOT: rel-* (M3, releases.json — 独立), production_run (M3 legacy),
  database mirror / session / WebUI local / event — 全非 Release truth
- 同文件 rel-* 冲突风险已规避 (独立 release_truth.json — 记录实现决策)

## 3. Writer 唯一

create/gate/execute/supersede/revoke 全在 release_truth 模块 (唯一);
CLI release-truth → rtrace_cmd → release_truth 函数 (无独立逻辑);
WebUI 无引用; 无 bypass (grep store 写零外部)

## 4. Lifecycle 实证

测试: gate PASS→GATED / fail→REJECTED / execute→RELEASED / supersede / revoke /
非法转换拒绝 (ValueError)
