# 13 — CLI / API / WEBUI CONTRACT (P2-C CONTRACT, 2026-09-06)

## 1. 现状 (已存在, 保留)

- CLI: factory experience list/get/retrieve/extract
- API: /api/experience (GET), /api/experiences/search
- WebUI: 展示型 (无业务写)

## 2. 冻结 (未来 Implementation)

- CLI/API **读** canonical exp store (保留现状读路径)
- CLI/API **写** = 禁止 (只有 ExperienceBridge 写; CLI 不直写 exp)
- WebUI = projection (保持; 无 experience business state)
- 可选: CLI trace (exp → run → release 反查) — 若需
