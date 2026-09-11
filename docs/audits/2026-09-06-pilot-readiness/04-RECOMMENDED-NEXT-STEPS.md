# 04 — RECOMMENDED NEXT STEPS (2026-09-06)

## 只允许提升 Idea→Deliverable 成功率的工作 (主线)

S1 (P0): 双链接合 — workflow_runner finalize 接 canonical 吸收
  (run-*/EXS 已有; 补 art/ver/EVD/RELEASE/exp) — 用户成品进 canonical 账本
S2 (P0): Acceptance 闭环 — WebUI preview/run 产物 + 用户 approve/request-change;
  request-change → 新 repair run (reuse 现有 ≤2 轮 loop, 加用户轮)
S3 (P1): 真实端到端 pilot 复现 — 用 canonical 链从真实 idea 到 dist zip 一次,
  全程 canonical 记录 (首个 REAL production record)
S4 (P1): 后端补 runtime/workflow 状态 API — 消除前端 mock fallback
S5 (P2): Delivery 升级 — RELEASE-* + git tag + 产物页下载

## POST-PILOT / SUPPORTING (不阻塞, 不得占主线)
Agent runtime 内部化 / MCP / Knowledge / Workforce 实时 / SRE / Enterprise /
Action Control Plane 扩展 / Learning 生产消费 (P2-D 已备, 待 canonical 旅程数据)

## 关键指标 (pilot 成功定义)
- 1 个真实新用户 idea → canonical 旅程 → 可运行成品 (dist/git) → 用户
  acceptance PASS → canonical 账本可查全链 (task→EXS→art→ver→EVD→RELEASE)
