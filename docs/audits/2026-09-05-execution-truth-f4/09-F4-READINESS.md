# 09 — F4 READINESS (P0-F4 AUDIT, 2026-09-05, READ-ONLY)

> 20 audit questions + 分类 + GO/NO-GO

---

## 1. 20 问逐项回答

1. Artifact domain 已存在? **是 — 4 套** (S2 art-* lifecycle / exec ART-* / org / EXS patches)
2. 多 SSOT? **是 — 4 套互不相连**
3. Artifact identity? **art-* / ART-* / P-…-TYPE / EXS-.patch 四套并存**
4. Artifact↔TaskRun? 仅 S2 node_run_id 字段 (0 真实); 其余无
5. Artifact↔EXS? 仅 exec path 隐式 (非 FK)
6. Artifact↔Verification? **无任何引用**
7. 独立生命周期? 仅 S2 有 (8 态完整); exec/org/patches 无
8. 表达 generated/staged/…? S2 已表达全部 (GENERATED→…→RELEASED) — 不需重造,
   但真实数据不经过它
9. Evidence domain 已存在? **单套** (ev-* EvidenceBundle, M3)
10. identity/写/读/持久化/多 SSOT? ev-{hex8} / EvidenceBuilder+orchestrator /
    CLI+backlog_sweeper / projects/{slug}/evidence/ / **单套 (非多 SSOT)**
11. Evidence 是"证据"还是别名? = M3 审批包 (diff+decisions, status 审批) — 
    是"变更审批证据", 非 F4 目标 "支撑 Ver/Artifact 的事实依据" 语义
12. test_result/verification/artifact/audit/experience 关系? 无统一关系 —
    test_result 散 exec ART + EXS test.txt; verification=F3 ver-*; artifact 4 套;
    audit=观察; experience=M3 经验域 — 各自为政
13. 历史 M3/M4 与 Production Core 冲突? **是** — I8 (外部产物必须走 lifecycle)
    被现实违反 (exec ART/patches 绕过); org registry/M3 evidence 平行存在
14. legacy (EXR/TASK-GW/task-e1-*/T-*/task-chg-*) 被错误连接? **否** (零重连 —
    但真实 exec ART task_id 含 task-e1-* 说明 exec 域曾服务 M3)
15. 旧系统偷偷承担 SSOT? exec ART-*(225) + org(24) 是**事实上的**真实产物账本,
    虽无 SSOT 之名 — 不能忽略
16. API/CLI 暴露? API: /api/artifacts (org 域, S9) + /api/projects/{id}/artifacts;
    CLI: evidence list/show (M3) + external-ai; ver-* (F3) CLI 已建
17. WebUI 只投影? **是** (domain.ts 仅类型/展示; 无本地 truth)
18. localStorage 当 truth? **否** (仅 UI 偏好, F1/F2/F3 已查)
19. 支持真实 E2E? **否** — 无法构造真实 Task→run→EXS→Artifact→ver-*→Evidence 链
    (Artifact 无 canonical; Evidence 无链接)
20. 需改 F0-F3 contract? **不直接改** — 但 F0 的 Task→TaskRun→EXS→Artifact→…
    链的 Artifact 段从未冻结 (F0 只冻结到 EXS/Final State; Artifact 归属 F4 时定) —
    需补 Artifact canonical 决策, 非改已有语义

## 2. 分类

### P0
- **A1: Artifact 4 套 SSOT 互不相连** (S2 art-* / exec ART-* 225 / org 24 / EXS patch 75)
- **A2: 真实外部产物绕过 S2 lifecycle (I8 契约被现实违反)** — gateway/agent_runtime
  产物 300+ 从未走 art-* lifecycle

### P1
- **A3: Artifact↔Verification↔Evidence 三链全断** — 无任何 FK
- **A4: Evidence 语义错位** — ev-* 是 M3 审批包, 非 F4 目标证据; 且与 ver-*/art 零关联

### P2
- A5: org registry / exec ART 的 task_id 用 exec 内部 id (T001/task-e1-*) — 历史遗留
- A6: API /api/artifacts 暴露 org 域 (非 canonical) — 未来 canonical 化后需对齐

### UNKNOWN
- U1: exec ART-*/EXS patch 是否应整体并入 S2 lifecycle (迁移量 300+) 还是保持
      外置+引用 — 产品级决策
- U2: Evidence 语义: 泛化 EvidenceBundle 为新 Evidence domain vs 新建 evd-* —
      产品级决策
- U3: S2 art-* 的 approval gates (APPLIED/COMMITTED/RELEASED) 是否适用于真实
      委派链 (gateway 产物) — 需产品决策

## 3. F4 = NO-GO (STOP)

触发 STOP conditions:
- **#1: Artifact 存在无法解决的多个 SSOT** (4 套; 选 canonical = 需迁移 300+ 真实
  产物决策, 非实现可自决)
- **#13: 发现新的第三套/第四套事实账本** (org registry / EXS patches)

阻塞点: 缺 Artifact canonical 单一 owner 决策 + Evidence 语义决策 — 均为
**架构/产品级决策**, 不是 F4 实现代码问题。

## 4. 解除阻塞所需决策 (建议下一步)

**D1 (P0): Artifact canonical = 哪套?** 推荐 S2 art-* (唯一 lifecycle + I1-I12 契约 +
run-* FK) — 但需批准: ① exec ART-*/EXS patch 如何收纳 (建议: 新真实执行改走
art-*, 旧数据保留为 legacy 外置引用) ② org registry 保持 M3/S14 域隔离
**D2 (P1): Evidence 语义与 ID** — 泛化 EvidenceBundle 为 canonical Evidence (ev-*)
挂 ver-*/art-*, 还是新 evd-*?
**D3 (P1): Artifact↔Verification FK 方向** — art.verification_id? ver.artifact_id?
  建议: ver-* 增 artifact_id (验证的对象), art 保留 evidence_ids (支撑证据)
**D4 (P2): I8 执行** — 真实委派产物强制 GENERATED 起步 (可自动 STAGED→…)?

F4 implementation 在这些决策批准前 **不得开始**。
