# ISOLATED MODULES — STEP 4 (2026-09-02)

| Module | Code | Tests | Docs | API | CLI | Consumer | Runtime | 状态 |
|--------|------|-------|------|-----|-----|----------|---------|------|
| factory-core (138 py) | 大量 | tests/* (分组) | ADR 0036+ | — | core cli | **0 全仓** | NO | ISOLATED |
| LLMRouter | 410 行 | tests/llm | 设计文档 | — | — | 0 | NO | ISOLATED |
| factory-runtime | 12 py | tests/factory_runtime | runtime-design | — | cli | 0 | NO | ISOLATED |
| PRD | — | — | 文档多 | — | — | — | — | ABSENT |
| Learning | learning 模块 | 有 | 有 | 有 | — | UNKNOWN | UNKNOWN | ISOLATED/UNKNOWN |
| Release | release_service | 有 | 有 | 有 | — | UNKNOWN | UNKNOWN | ISOLATED/UNKNOWN |

## 注意 (反证)
- factory-exec 曾被怀疑孤立 — 实际 79 处引用 (深度集成) → NOT isolated
- factory-core tests 存在 (tests/agents/assignment 等) — 但那些测试文件 import core? 本扫描外部引用=0 → 测试可能直接路径引用或独立运行 (UNKNOWN 边界)
