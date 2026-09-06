# 00 — CONTRACT OVERVIEW (P2-D LEARNING CONSUMPTION CONTRACT, 2026-09-06)

> 阶段: P2-D Learning Consumption Contract Freeze — 只冻结, 不实施
> 基线: 90caeb91 (HEAD; P2-C Implementation 未提交工作区 — 待验收, 不覆盖)
> 前置: P2-C Experience Bridge (Impl PASS, E2E 4/4)

---

## 1. 核心判定

```
Status: GO (contract 级 — 但以"先 P2-C Final Acceptance + Commit"为前提)
```

- canonical 边界清晰 (Experience=console memory; intelligence/=S9 legacy)
- Observation/Candidate/Promotion/Profile/Router contract 可冻结
- provenance 可闭合 (设计: exp anchor → obs → cand → promo → profile →
  router decision → next run)
- failure/recovery 可定义; 无 competing SSOT; P0/P1/P2-A/P2-C intact
- **真实数据 Reality: 全部 0** (obs/cand/promo/profile/routing=0) — 契约
  必须为 "从零建 chain" 设计, 不得因代码存在判成熟

## 2. 契约核心原则

> Learning is complete only when verified production experience changes a
> governed capability representation that changes a future production
> decision, with full provenance.

- Observation/Candidate/Promotion/Profile/Router = **全部新 canonical 域**
  (现有 learning_engine_v2/learning_loop 代码是 legacy/基础, 不直接升 canonical)
- Profile 是 Learning 的**输出** (经 promotion), 不是 SSOT
- RoutingDecision = 必须成为可审计事实 (现无 canonical 记录)
- Hermes Agent Memory ≠ AI Factory Learning SSOT (可插拔 provider)
