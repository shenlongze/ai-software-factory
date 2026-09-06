# 20 — ACCEPTANCE MATRIX (P2-D CONTRACT, 2026-09-06)

D1 obs canonical | D2 cand canonical | D3 promotion (治理) | D4 profile=
输出+version | D5 router 消费 | D6 RD provenance | D7 单向 (learning 不改
router 代码) | D8 profile versioning | D9 governance (human 默认) | D10
failure/recovery | D11 idempotency | D12 legacy 隔离 | D13 SSOT 唯一 |
D14 CLI/API (读经 canonical, 写经 service) | D15 WebUI projection |
D16 real-data 验收 (≥1 真实 anchored exp 触发 obs→cand→promo→profile→
RD 全链 E2E) | D17 P2-E boundary | D18 Hermes/AIF learning 分离

## Real-data 验收门槛 (D16 核心)
- E2E: 真实 RELEASE→exp(anchored) → obs → cand → (approval) promo →
  profile v1 → 下个同类任务 route → RD 记录 (profile_version=v1) →
  before/after agent 可对比
- 不满足 → P2-D 不算 PASS (禁测试 fixture 冒充)
