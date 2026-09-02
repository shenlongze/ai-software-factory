# LLM CALL GRAPH — FACT DISCOVERY (2026-09-02)

> 扫描: grep llm_fn|llm_raw|chat_completion|completion(|.invoke(|llm_router|llm_gateway|router.route
> 范围: factory-console/session + factory-console 顶层 + factory-core
> 结果: **175 处命中, 其中直接调用形态 (llm_fn/llm_raw/chat_completion) 154 处 (88%)**

## 直接调用形态 Top 文件 (llm_fn/llm_raw/chat_completion)

| 文件 | 命中数 |
|------|-------|
| session/decomposer.py | 16 |
| session/discovery_intelligence.py | 14 |
| session/topic_ledger.py | 13 |
| session/reasoning.py | 13 |
| session/product_intelligence.py | 11 |
| session/agent_loop.py | 11 |
| session/actions.py | 9 |
| session/critical_path.py | 9 |
| session/workloads/backlog_sweeper.py | 8 |
| session/llm_intent.py | 8 |
| session/naming.py | 7 |
| session/query_engine.py | 6 |
| session/repo_mode.py | 6 |
| llm_router.py | 6 |
| session/change_control.py | 5 |

## 路由形态

| 形态 | 文件 | 命中 |
|------|------|------|
| llm_router | factory-console/llm_router.py (410 行) | 6 |
| llm_gateway | session/llm_gateway.py (460 行) | 4 |
| 直接 (llm_fn/llm_raw/chat_completion) | 分散 40+ 文件 | 154 |

## 事实

- 全仓库 LLM 调用点: 175+ (仅 session+core+console 顶层; 不含 exec/runtime/org)
- 经统一 Router/Gateway: ~10 (llm_router 6 + llm_gateway 4)
- 绕过 Router (直接 llm_fn/llm_raw/chat_completion): ~154
- 无法判断: factory-exec/factory-runtime/factory-core 部分 (未扫描)
