# RUNTIME PROOF — STEP 3 (2026-09-02)

> 真实运行数据源: ~/.factory (本次读取, 非 fixture)

## 运行时数据证据 (2026-09-02 读取)

| 存储 | 规模 | 证明 |
|------|------|------|
| audit/audit_events.json | 5160 条 | 事件/审计真实运行 |
| console_sessions.json | 812KB | 会话事实 |
| session_topics/ | 81 会话 | 会话主题事实 |
| session_exec/ | 6 执行链 | ExecState 投影真实产生 |
| session_progress/ | 9 | 进度卡真实产生 |
| exec/execution_records.json | 100 条 | **factory-exec 真实执行** (agent.execute_task, 2026-08-14) |
| exec/results.json | 212KB | 真实 artifacts (patch, ART-xxx, event_refs) |
| exec/external_tasks.json | 1 | 外部任务 |
| agents/agents.json | 8 agents | backend-1/flutter-dev/tester-1/pm/architect/qa/frontend |
| skills/skills.json | 2.5MB | skills 注册 |
| requirements/requirements.json | 7 req | **Requirement 落盘 (VALIDATED, req_xxx, project 关联)** |
| memory/experience_store.json | 84 | 经验事实 |
| providers.json | deepseek | LLM provider 真实配置 (api_key_ref=env) |
| providers/usage.json | records | LLM 使用记录 (hermes 超时失败 2026-08-06) |
| org/projects.json | 27KB | 项目事实 |
| workspace/projects/ | 37 目录 | 工作区项目 |
| factory.db | 3.3MB | SQLite 文件存在 (用途 UNKNOWN) |

## RUNTIME_PROVEN 能力 (直接证据)

| 能力 | 证据 |
|------|------|
| Requirement 落盘 | requirements.json 7 条 VALIDATED (req_xxx id, session/project 关联) |
| Agent 注册 | agents.json 8 agents (backend-1 等, status=AVAILABLE) |
| Agent 执行 (exec) | execution_records 100 条 (intent=run_task, action=agent.execute_task, agent=backend-1) |
| Artifact 产生 | exec/results.json (patch, ART-9e472fd8, event_refs 1489-1498) |
| Provider 配置 | providers.json deepseek (base_url/api_key_ref) |
| LLM 使用记录 | providers/usage.json (hermes 300s timeout failed) |
| 会话运行 | session_topics 81 + console_sessions 812KB |
| 执行链投影 | session_exec 6 |
| 事件/审计 | audit_events 5160 |
| 经验 | memory/experience_store 84 |

## RUNTIME_UNVERIFIED

| 能力 | 原因 |
|------|------|
| factory-core | console→core=0; core 数据目录? (未在 ~/.factory 发现独立 core 区) |
| factory-runtime | 无运行痕迹 (runtimes/runtimes.json 57B) |
| LLMRouter | 生产消费=0 (STEP 2) |
| Release/Learning | intelligence/experiences 仅 1; learning 端点未验证 |
| 371 API | 仅部分验证 (会话/项目/执行 API 实测过; 大量管理/优化/learning API 未触发) |
| factory.db (SQLite) | 3.3MB 存在, 谁写谁读 UNKNOWN |

## 真实执行示例 (execution_records)

```
{'intent': 'run_task', 'action': 'agent.execute_task', 'agent': 'backend-1',
 'task': '登录功能', 'result': 'failed', 'result_id': 'EXS-221a1296',
 'timestamp': '2026-08-14T19:11:26', 'error': 'anthropic api key missing'}
{'agent': 'backend-1', 'task': '给 /tmp/s10049-app/main.py 加一个 hello 函数',
 'result': 'success', 'result_id': 'EXS-91f7abfe', 'timestamp': '2026-08-14T19:17:00'}
```
→ Agent 真实执行 (成功+失败), 时间 2026-08-14 (早于本轮会话)

## 触发入口 (execution_records 来源 — UNKNOWN 部分)

- records 有 intent/action/session 上下文, 但调用者 (CLI/会话/API) 未在本轮从数据反查
- exec/requests.json 仅 1 条 → 大部分执行记录来自更早系统版本
