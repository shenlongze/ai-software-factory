# 02 — D2 EVIDENCE SEMANTIC (P0-F4 DECISION, 2026-09-05)

> D2 = APPROVED: 现有 ev-* = LEGACY approval package; 未来 Evidence = 独立 EVD-* 域

---

## 1. 冻结决策

**现有 ev-* EvidenceBundle 不升级为 Evidence SSOT。**

- 现有 9 条 ev-* 语义 = **M3 approval bundle / approval package**
  (diff + decisions + status pending/approved/rejected/applied — 审批包, 非证据支撑)
- 分类: LEGACY / APPROVAL PACKAGE
- 不 retroactively 连接 ev-* → ver-*/art-*/EXS-*/run-*
- 不改写历史语义/数据

**未来 canonical Evidence = 独立 Domain Fact**

- 职责: 保存**支撑 Verification 结论可信度**的可追溯事实 (为什么这个结论值得相信)
- Evidence ≠ Verification ≠ Artifact ≠ Approval ≠ Audit
- canonical identity: **EVD-{hex}** — 仓库无 EVD-*/evd-* 冲突 (grep 零命中),
  与旧 ev-* (EvidenceBundle) 前缀区分, 无语义混淆

## 2. 边界

```
旧 ev-* EvidenceBundle (M3 审批包, 9 条)  → LEGACY, 冻结, 不迁移不重连
新 EVD-* Evidence domain                   → F4 implementation (本阶段不建)
```

## 3. 关键问题回答

1. identity: EVD-{hex} (新; 与 ev-* 区分)
2. store: F4 impl 定义 (建议 <root>/evidence/ 独立域, 仿 verification store)
3. writer: F4 impl 定义唯一写入口 (仿 verification_domain.materialize)
4. reader: CLI/API/溯源 (F4 impl)
5. Verification → Evidence: EVD.verification_id FK (1 Verification → 多 Evidence)
6. Artifact → Evidence: EVD 可含 artifact_ref (支撑 artifact 相关结论时) — 可选
7. EXS → Evidence 直接 FK: **不需要** (经 Verification/Artifact 可达; 避免网状 FK)
8. evidence_type: 可溯源验证证据 (pytest 输出/语法报告/验证器日志/命令记录/快照) —
   F4 impl 定义枚举, 不在此冻结
9. evidence_source: 产生方 (verifier/runner/路径引用) — F4 impl
10. immutability: EVD 不可变 (I10 同精神; 修改=新记录)
11. idempotency: 同 (verification_id, type, source-hash) → 单 EVD (F4 impl)
12. retention: 与 Verification 同生命周期保留 (F4 impl 定义清理策略; 默认不删)
13. provenance: 记录 source + created_at + actor (审计可溯)
14. 多 Verification 复用同一 Evidence: **允许** (EVD 可被多 Verification 引用,
    但 EVD 不可变 — 复用=共享引用, 非复制)

## 4. 禁止

- 把 EVD-* 造成"另一个结果" (Verification 才是 PASS/FAIL/UNKNOWN;
  Evidence 只解释为什么可信)
- ev-* → EVD-* 迁移 (本阶段 + F4 impl 都不做; 除非另立 migration phase)
