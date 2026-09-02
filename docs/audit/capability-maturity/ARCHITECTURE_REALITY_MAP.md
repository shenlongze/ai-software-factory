# ARCHITECTURE REALITY MAP — STEP 7

| 模块 | 分类 | 证据 |
|------|------|------|
| factory-console | A. Integrated Production Core | uvicorn 入口 + 371 API + E2E |
| factory-org | A. Integrated Production Core | console import 69 + SSOT |
| factory-exec | B. Integrated Supporting (部分) | console 79 处引用 + 真实执行记录; 独立 CLI |
| factory-core | E. Intentionally Independent (证据: 原则 P-MOD-01) | 全仓消费 0; 有完整 CLI+测试+ADR |
| factory-runtime | E./G. Intentionally Independent / UNKNOWN | 无运行痕迹 (57B) |

## 依赖维度
console↔org: STATIC(69)+RUNTIME+STORAGE(同 ~/.factory) = 强集成
console→exec: STATIC(79)+RUNTIME(懒装配)+STORAGE(exec/*.json) = 集成
console→core: 0 | console→runtime: 0
→ 真实运行时 = console+org+exec (三模块集成核); core/runtime = 独立包 (意图独立)
