# R0 — AI Factory OS 真实生产入口审计

> Date: 2026-09-08 | 性质: 只读审计, 零代码改动 | 执行: Hermes
> 结论图例: 🟢 GREEN(真实统一) · 🟡 YELLOW(分叉可收敛 / 仅 fake 验证) · 🔴 RED(多套逻辑 / 断链 / 不可达)

---

## 0. 必读链完成

README.md / docs/00-index/README.md / CURRENT_SYSTEM_TRUTH.md /
STEP10_DOMAIN_FREEZE.md / golden-path-completion.md — 均已读(此前多轮 + 本轮复核)。

---

## Q1. factory CLI 当前真正进入哪个 Runtime? — 🔴 RED(进入 session/ 传统链, 非新域)

**证据链**:
- `pyproject.toml:29` → `factory = "factory_console.cli_factory:main"`
- `cli_factory.py:8445` `def main` — 无参数/`--interactive` → `InteractiveSession().run()`(:8463)
- `session/session.py:115` `class InteractiveSession`; `:36` `from .conversation import ConversationManager`
- `session/session.py:203` `run()` → `:341 _dispatch` → `:361 _dispatch_inner`
- `session/session.py:387-400`: 产品流程(conv.product_intent / DISCOVERY / PRODUCT_CONFIRMATION)由
  `ConversationManager.handle_product_answer/handle_product_confirm` 处理(:597/:1351)
- 其余自然语言 → `IntentParser.parse` → `IntentRouter.route` → Action(:420-470)

**结论**: CLI 裸启动 = `session/` 自足链(自己的 product_intent 产品发现 + Intent/路由/Action),
**零引用**新 Conversation Application 域:
`grep conversation_app|golden_path|product_understanding|semantic_proposal factory-console/session/*.py` → **无匹配**。
`factory chat` 子命令(:4460 chat_cmd)也走 legacy `conversation_os`(:4465 import create_conversation/send_message)。

---

## Q2. API 当前真正进入哪个 Runtime? — 🔴 RED(双 API 且新域无创建入口)

**证据**:
- **Legacy 活着**: `fastapi_adapter.py:6563` POST /api/conversations → `_co.create_conversation`
  (conversation_os); `:6572` POST .../messages → `_co.send_message`; `:6605/:6620` requirement/decision → `_co`
- **新域端点存在但只读既有 conv-**: `:6644` POST .../product-understanding/messages、`:6664` GET snapshot、
  `:6675` statement、`:6691` gaps、`:6704` messages、`:6716` context — 全部先
  `ConversationApplicationService(root).get(conversation_id) is None → 404`(:6654/:6669/...)
- **🔴 断链**: fastapi **无任何端点创建新域 conversation**(无 POST → ConversationApplicationService.create)。
  测试 `test_product_understanding_api.py:49` 是**先直建**(`ca.ConversationApplicationService(root).create`)
  再打 API — 真实 HTTP 客户端无法创建 conv- 会话, 新域 API 在真实路径**不可达**。

**结论**: API 层 = legacy conversation_os(conv_*, 可创建可发消息) + 新域 PU 端点(仅能操作已存在
conv-, 而 conv- 无法经 API 创建)。双 Runtime 并存且新域实际断链。

---

## Q3. WebUI 当前真正进入哪个 Runtime? — 🔴 RED(第三套: /api/sessions → agent_loop)

**证据**:
- 前端聊天组件: `components/af/AfConversationPanel.tsx` + `ConversationContext.tsx`
- `ConversationContext.tsx:13` import api; `:303 api.createSession`; `:403 api.sessionSendStream`;
  `:488 api.sendSessionMessage`; `:529 api.sessionMessages` — 全部 **/api/sessions/***
- 前端 `client.ts` 中 legacy conversations 方法(`:146-152`)定义存在但**无调用方**
  (`grep sendMessage|conversations 前端 pages/` → 无); `:171-181` 项目走 `/api/projects-os` + `/api/tasks/{id}/approval`
- 后端: `fastapi_adapter.py:7192` POST /api/sessions → `sessions_store.create_session`
  (console_sessions.SessionStore, :1182); `:7568` POST /api/sessions/{id}/messages →
  `session.agent_loop`(:7595 `_agmod = _console_import("session.agent_loop")`)
- 前端 grep product-understanding / ConversationApplicationService → **零匹配**(真实前端不消费新域)

**结论**: WebUI 主链 = /api/sessions → console_sessions + session.agent_loop。与 CLI(session/
InteractiveSession)共享 `session/` 目录但走**不同 Runtime 实例**(agent_loop vs ConversationManager);
与 conversation_os / 新 golden_path 域完全隔离。三入口 = 三套业务逻辑(见 Q4)。

---

## Q4. CLI / API / WebUI 是否进入同一个 Application → Domain → Runtime? — 🔴 RED(四套逻辑)

| 入口 | 调用链终点 | Runtime 域 |
|------|-----------|-----------|
| CLI 裸启动 (`factory`) | InteractiveSession → ConversationManager + IntentRouter + Action | session/(conversation.py) |
| CLI `factory chat` | conversation_os.create/send_message | conversation_os(conv_* 实体) |
| API /api/conversations | conversation_os(同 chat) | conversation_os |
| API /api/sessions | console_sessions.SessionStore → session.agent_loop | session/(agent_loop) |
| API product-understanding* | ConversationApplicationService(仅对已存在 conv-) | **新域(不可达)** |
| WebUI | /api/sessions → session.agent_loop | session/(agent_loop) |
| golden_path (Golden Path 编排) | 生产代码 import = **零**(仅测试) | **新域(无入口)** |

分叉层: **表现层即分叉** — 各入口在 API 路由/CLI 分发处就选择不同域, 不是共享 Application Layer。
`conversation_app`(统一 Application Layer 声明)仅被 fastapi PU 端点引用, CLI/WebUI/主 API 均不经过它。

---

## Q5. factory CLI 是否已像 Codex/Hermes 一样自然语言为主? — 🟡 YELLOW(半: 有 REPL 但产品链自成一系)

- 裸 `factory` = REPL(InteractiveSession, session.py:203), 自然语言可进; **产品流程**
  (product_intent 完整 + 确认)确有多轮追问(product_discovery) — 但这是 **session/ 自己的产品链**
  (handle_product_answer/confirm, conversation.py:597/1351), **不是**新域 Understanding/PRD/Plan。
- `factory chat` 是**子命令分发器**(cli_factory.py:7891 action=new/send/status/... + --message),
  不是 REPL — 需用户输入内部命令词(action)。
- 从 "我想做飞机大战" 到进入**新 Conversation 域**(product_understanding/golden_path):
  CLI **无路径**。CLI 只能进 session/ 产品链(旧)或 conversation_os(旧)。

---

## Q6. 从 CLI 跑一个真实软件任务, 闭环断点逐环 — 🔴 RED(新链 CLI 不可达; 旧链 LLM 可达但非新 Golden Path)

任务要求链 Idea→Understanding→PRD→Approval→Plan→Approval→Task→Execute→Verify→Artifact→Evidence:

| 环 | 新 Golden Path(golden_path 域) | CLI 实际可达? |
|----|-------------------------------|--------------|
| Understanding | product_understanding(代码+测试真实) | ❌ CLI 不进新域 |
| PRD | application_formalization(真实) | ❌ 同上(CLI 走 session 旧 PRD 流程) |
| Plan | golden_path.generate_plan → product_truth PLAN-*(真实) | ❌ |
| Approval 双 Gate | golden_path(真实, 测试强断言) | ❌ |
| Execute/Verify/Artifact/Evidence | production_runtime/node_runtime(真实) | ❌ 经 golden_path 不可达 |

**LLM 可达性**:
- 旧链 CLI/WebUI: `console_sessions.llm_raw`(:104)→ ReasoningProvider → DeepSeek — **装配真实**,
  但依赖 `env:DEEPSEEK_API_KEY`(providers.json api_key_ref), 本机未设 → llm_raw=None。
- 新链 golden_path:**无 LLM 接线**(grep golden_path → llm_semantic_interpreter 零引用);
  `conversation_app.py:352` 支持 semantic=True → llm_semantic_interpreter, 但无入口调用它。

**结论**: 从任何真实入口都无法到达 Cognitive Golden Path 全链 — Golden Path 是**域+测试完备、
入口缺失**。真实任务若走旧链(session/)则无 Understanding/双 Gate/新 PRD-Plan 语义; 若想走新链,
CLI/API/WebUI 均需接线(创建 conv- + semantic interpreter + golden_path 编排)。

---

## 三入口 × 13 维事实对比表

| 维度 | CLI (`factory`) | API /api/conversations* | WebUI (/api/sessions) | Golden Path 域(代码) | 证据 |
|------|----------------|------------------------|----------------------|---------------------|------|
| Project | ✅ session 旧链 / project_os | conv_* 无 project | ✅ projects-os | — | cli_factory.py:420+ / fastapi 6805 / session/session.py |
| Conversation | ✅ session 自有会话 | ✅ conversation_os conv_* | ✅ console_sessions | ✅ conv- product_understanding | session/conversation.py / conversation_os.py:77 / console_sessions.py:243 / product_understanding.py:212 |
| Intent | ✅ IntentParser+Router | ✅ conversation_os INTENTS | ✅ session agent_loop | ❌ 无(golden_path 0 intent) | session/session.py:420 / conversation_os.py:36 / golden_path.py grep |
| Product Understanding | ❌(旧 product_intent 内存) | ❌ | ❌ | ✅ 持久化+supersession | session/conversation.py:54 内存 vs product_understanding.py |
| PRD | ✅ 旧流程(generate_prd 扫描兜底) | ❌ | ❌ | ✅ 结构化版本化 | session/session.py:404 / application_formalization.py:115 |
| Plan | ✅ 旧 session_plans | ❌ | ❌ | ✅ PLAN-* 正式域 | product_truth.py:680 / session/actions |
| Task Tree | ✅ 旧拆解 | ✅ K2 | ✅ | ✅ plan task → node | session/pipeline / task_tree / golden_path |
| NodeRun | 🟡 间接 | ❌ | 🟡 agent_loop runs | ✅ node_runtime | node_runtime.py:128 / golden_path execute |
| Agent-Model | ✅ agents.json | ✅ | ✅ | 🟡 plan_task node | agents.json / node_runtime |
| Artifact | ✅ 旧 exec | ❌ | 🟡 | ✅ production artifact | production_runtime.py |
| Verification | ✅ 旧 | ❌ | 🟡 | ✅ verification PASS | production_runtime.py / tests |
| Evidence | ✅ 审计 | ✅ 审计 | ✅ 审计 | ✅ | audit_events / production_runtime |
| Audit | ✅ 全事件 | ✅ | ✅ | ✅ | audit_events 5160+ |

---

## 三色总结

- 🟢 无一项真正全入口统一(审计/治理/证据链为既有横切能力, 真实但非入口统一)。
- 🟡 CLI 裸启动是自然语言 REPL(旧链), 新 Golden Path 域测试全绿但仅 fake/域级验证。
- 🔴 **核心结论**: 存在 ≥4 套业务逻辑(session/ConversationManager · conversation_os ·
  session/agent_loop · 新 conversation_app/golden_path), 分叉发生在表现层入口;
  新 Cognitive Golden Path 无任何真实用户入口(CLI/API/WebUI 零接线);
  LLM 语义解释在真实路径依赖未设置的 DEEPSEEK_API_KEY。

---

## STOP

审计完成, 零代码改动。等下一步指令(按序建议: 修 execute_approved 吞异常 →
真实 LLM 冒烟 → CLI dogfood 飞机大战 → API/WebUI 一致性)。
