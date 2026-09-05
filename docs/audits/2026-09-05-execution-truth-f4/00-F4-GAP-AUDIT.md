# 00 — F4 GAP AUDIT (2026-09-05, READ-ONLY)

> 状态: AUDIT COMPLETE → **STOP (P0 — Artifact 多 SSOT 无法本地消解)**
> 基线: 794e24d7 (F3 committed) | 方法: 代码 + ~/.factory 真实数据只读取证
> 本文件 + 01-09 = F4 READ-ONLY 审计产物; 零代码/零数据/零 git 改动

---

## 1. 核心发现 (取证摘要)

### Artifact: **4 套事实账本, 互不相连**

| # | 账本 | Identity | 持久化 | 真实数据 | 生命周期 | 与 canonical (TASK-*/run-*/EXS) 关联 |
|---|---|---|---|---|---|---|
| 1 | S2 Artifact Lifecycle (artifact_lifecycle.py) | art-{hex12} | nodes 域? → `<root>/artifacts/xx/art-*.json` | **0 条** | 完整 8 态 (GENERATED→…→RELEASED) + APPROVAL_GATES + EVIDENCE_REQUIRED | 挂 node_run_id (F1 run-* 兼容); 创建点仅 execute_node_run (workflow 域, 从未真实运行) |
| 2 | exec AgentRuntime artifacts (exec/store + agent_runtime) | ART-{hex8} | exec/artifacts.json | **225 条** (75 patch + 75 report + 75 test_result) | 无 (快照落盘) | **0** (task_id = T001-5/task-*/task-e1-*; 无 run-*/TASK-*; 仅 path 隐式连 EXS) |
| 3 | org ArtifactRegistry (factory-org/org/artifact.py) | P-{id}-R{ms}-{TYPE} | org/artifacts.json | **24 条** | org 域 (stage 绑定) | **0** (task_id 全空; 挂 P-* project + STG-*) |
| 4 | EXS patch 文件 (external executor) | EXS-{hex8}.patch | exec/patches/*.patch | **75 文件** | 无 (外置产物) | 按 EXS id 命名 (文件名即 FK) |

### Evidence: **1 套, M3 legacy**

| 账本 | Identity | 持久化 | 真实数据 | 与 canonical 关联 |
|---|---|---|---|---|
| EvidenceBundle (session/evidence.py) | ev-{hex8} | projects/{slug}/evidence/ev-*.json | **9 条** | **0** (task_id = ai-factory 旧 slug, M3 体系; artifacts/test_results 字段全空) |

### Verification (F3): ver-* SSOT 已建, 真实数据 0 (刚提交, 尚无真实运行)

---

## 2. STOP 判定

任务书 STOP conditions:

1. **Artifact 存在无法解决的多个 SSOT** → **触发** (4 套: S2 art-* / exec ART-* / org / EXS patches; 各自 owner 不同域, 无法本地选一)
13. **发现新的第三套/第四套事实账本** → **触发** (org registry 第 3 套 + EXS patches 第 4 套; Evidence 第 1 套 M3)

→ **F4 = NO-GO (STOP)**

## 3. 为什么不能本地消解

- S2 art-* = 唯一带完整 lifecycle + EVIDENCE_REQUIRED + APPROVAL_GATES 的 domain
  (I1-I12 invariants), 但零真实数据 → 升级需迁移/重连 exec 225 + org 24 + patches 75
- exec ART-* / org registry / EXS patches = 三套真实产物, 各自 task_id 语义不同
  (T001 exec 内部 / P-* project / EXS 文件名), 无 run-*/TASK-* canonical 锚
- 选任一为 canonical → 其他三套必须迁移或降级 → 需人工架构决策 (非 F4 实现可自决)
- Evidence ev-* 是 M3 EvidenceBundle (审批包), 非"支撑 Ver/Artifact 的证据" — 
  需定义新 Evidence 语义 vs 复用 M3 bundle, 同样需决策

## 4. 已排除的"假闭环"

未做: 迁移 exec/org/patches 数据 / 伪造 art-* / 重连 task-e1-* / audit 当 SSOT /
WebUI 当 truth。所有关联率如实标记 0/UNKNOWN。
