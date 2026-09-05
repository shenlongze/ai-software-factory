# 00 — FINAL ACCEPTANCE (P0-F4, 2026-09-05, READ-ONLY)

> 性质: P0-F4 Implementation 最终只读验收
> 基线: 794e24d7 (F3) + F4 working tree (未提交)
> 方法: 代码取证 + 持久化事实 + 测试 + 真实 E2E (fresh 复跑)

---

## 1. 验收判定

| 验收项 | 判定 | 证据 |
|---|---|---|
| A1 Artifact 唯一 writer | **PASS** | create_artifact 调用者仅 3: node_runtime:275 (I8 收纳) / :538 (execute) / rollback_service (恢复域) |
| A2 无旁路创建 | **PASS** | API/CLI/WebUI 零 create_artifact; 直接 _write 仅 artifact_lifecycle 内 |
| A3 EXS→canonical art | **PASS** | finalize 收纳 (exs_id) → art-*; gateway/executor 零 ART-* 写入 |
| I8 执行 contract | **PASS** | _absorb 仅 finalize 内 (node_runtime:441); finalize 仅 agent_loop 委派回调 (2 处); 无独立 registration API |
| Artifact lifecycle | **PASS** | S2 8 态原样复用; E2E-1 art state=GENERATED (合法起点) |
| TaskRun→Artifact | **PASS** | art.node_run_id = run-* (S2 字段 + E2E-1/4 实证) |
| EXS→Artifact | **PASS** | art.exs_id = EXS-* (F4 新字段, 无冲突; E2E-1 实证) |
| Verification relation | **PASS** | ver.artifact_ids → art-* (F3 未改; F4 加字段) |
| Verification 读 canonical | **PASS** | ver.artifact_ids 来自 canonical art-* (收纳返回值); 不读 legacy ART-*/EXS patch/NodeRun snapshot |
| EXS/ver 独立 | **PASS** | E2E-2: EXS SUCCESS + ver FAIL (不自动 PASS); UNKNOWN 语义 F3 冻结 |
| Evidence SSOT | **PASS** | EVD-* 唯一 (materialize_evidence 仅 node_runtime:384); ev-* 写入方仍 M3 (repo_mode/orchestrator/backlog_sweeper), 无转换 |
| Evidence 真实 | **PASS** | EVD 内容 = 真实 pytest 输出 (E2E-1); 无内容不伪造 (测试) |
| Shared Evidence | **PASS** | attach_evidence 追加 refs (schema 支持 M:N, 非 1:1) |
| Idempotency | **PASS** | create_artifact 锁内 exs 幂等; EVD 同源幂等; E2E-3 art/ver/EVD 1→1 |
| Recovery | **PASS** | E2E-4: TaskRun-2 不覆盖 art-1/ver-1 (各唯一 id + node_run_id 隔离) |
| Failure semantics | **PASS** | EXS FAILED → finalize 失败分支不产 art (测试); ver FAIL 不误 COMPLETED |
| Legacy isolation | **PASS** | exec ART-*/org/EXS patch/ev-*/EXR 等零迁移零重连 (代码 + 测试) |
| WebUI projection | **PASS** | WebUI 只读 GET /api/artifacts (S9 org 投影); 零写入 canonical |
| Audit boundary | **PASS** | ver emit_audit observation; domain→audit 单向 |
| Double-exec | **PASS** | finalize 不调 executor_fn (F2 边界保持); 只有 execute_node_run 执行 |
| Regression | **PASS** | F1 16 + F2 8 + F3 17 + F4 14 = 55/55; F4 attribution = 0 (stash 对照) |
| Real E2E | **PASS** | 4/4 (fresh 复跑) |

**总体: PASS**

---

## 2. 唯一核心问题回答

> 当前系统是否已经能够从一个真实 TASK-*，沿 TaskRun → EXS → art-* → ver-* → EVD-*，
> 得到一条唯一、真实、持久、可验证、可审计、幂等、可恢复且不会产生第二事实的
> Production Truth Chain？

**YES** (fresh E2E-1 实证: TASK-f4e1 → run-* → EXS-ccf5e6c5 → art-* (GENERATED,
exs_id+node_run_id) → ver-* PASS (artifact_ids=[art]) → EVD-* (真实 pytest 输出);
全 ID 反查 + 幂等 (E2E-3) + 恢复隔离 (E2E-4))。

## 3. 本阶段遵守

No code changes | No data changes | No commit | No push | No reset | No clean |
concurrent noise (demo/unused) 未触碰。
