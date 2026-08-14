# AI Software Factory — LLM 能力专项审查报告

> 日期:2026-08-13 | 审查方式:只依据实际代码 + 测试 + 运行证据(不看设计文档)
> 证据基线:git 9cad09a | pytest 全量基线 7775(审查时另跑 LLM 相关 96 测试独立验证)
> 审查范围:LLM 配置 / 模型管理 / Runtime / Agent 调用链 / 测试覆盖

---

## 结论摘要

**LLM 能力当前完成度:约 35%**

- 代码层面:Provider 接口、真实 HTTP Adapter(OpenAI/Anthropic)、重试、成本估算 —— **结构完整、质量高**
- 运行层面:**从未真实调用过任何外部 LLM**。全链路证据显示每次执行都是诚实 FAILED(no LLM provider configured)
- 阻塞点单一明确:配置持久化缺失 + key 从未注入 → 产品在"空转工厂"状态

---

## 1. LLM 配置管理(Configuration Layer)

| 检查项 | 结论 | 证据 |
|---|---|---|
| Provider 是否存在 | ✅ 存在 | factory-exec/exec/provider.py(ProviderInterface/ProviderRegistry/ProviderConfigChecker);factory-core/providers/(另一套 ProviderStore + hermes adapter) |
| API Key 配置方式 | ✅ 环境变量 | OPENAI_API_KEY / ANTHROPIC_API_KEY(openai.py:106-114 读 env);分层来源 env > .env > ~/.factory/config.json(config.py:117) |
| Key 是否持久化 | ❌ **未持久化** | 实测:~/.factory/config.json 不存在、项目无 .env、providers/ 目录只有 usage.json(使用记录,无 key) |
| 是否支持多 Provider | ⚠️ 部分 | exec 注册表支持多 id(内置 anthropic+openai);workflow_runner._build_provider 支持 deepseek/openai/ollama/anthropic 但**每次只装配一个**;无路由 |
| 环境变量/数据库配置 | ⚠️ 部分 | 环境变量 + 分层配置文件(理论支持);无数据库配置;配置文件实际不存在 |
| 是否有配置校验 | ✅ 有 | ProviderConfigChecker.check()(provider.py:219);has_llm_key()/load_llm_key()(workflow_runner.py:75-105) |
| 启停状态管理 | ⚠️ 部分 | ProviderConfigStatus(configured True/False)存在,但无真正启停开关 |

**判定:部分完成(接口/校验完整,持久化为零)**
对应代码:factory-exec/exec/provider.py;factory-console/workflow_runner.py:75-105;factory-console/config.py:117
测试:21 个(test_exec_provider.py,全 mock)

---

## 2. LLM 模型管理(Model Management)

| 检查项 | 结论 | 证据 |
|---|---|---|
| Model Catalog 是否存在 | ❌ **不存在** | 全仓 grep ModelCatalog/model_catalog/models.json = 0 命中 |
| 模型信息是否结构化 | ⚠️ 极简 | factory-core/providers/definitions.py:36 有 models=["hermes-default"](仅 hermes CLI);exec 层无模型注册 |
| Agent 是否可以绑定模型 | ❌ 否 | Agent 模型无 model 字段;exec 层无 agent→model 映射 |
| 是否支持模型切换 | ⚠️ 仅构造参数 | OpenAIProvider(model=...)可传参(openai.py:84),workflow_runner 从 config 读 model;无运行时切换 |
| 不同 Agent 使用不同模型 | ❌ 否 | 全局单 provider 装配 |

**判定:未完成(仅构造参数级 model 覆盖)**
对应代码:factory-exec/exec/providers/openai.py:84;factory-core/providers/definitions.py
测试:0 个专项

---

## 3. LLM Runtime / Gateway

| 检查项 | 结论 | 证据 |
|---|---|---|
| 统一 LLM 调用入口 | ✅ 有 | ProviderInterface.generate()(provider.py:83-93) |
| Provider Adapter | ✅ 有(真实 HTTP) | openai.py(POST chat/completions)、anthropic.py(Messages API)、hermes.py(subprocess 调 hermes CLI) |
| 重试机制 | ✅ 有(上层) | developer.py:618-688(max_retries 循环 + EMPTY_CONTENT 重试提示);Provider 层无 429 retry-after |
| 超时处理 | ✅ 有 | openai.py:85(timeout=120);workflow_runner:455(timeout=300) |
| 错误处理 | ✅ 有 | ProviderError 统一(稳定前缀 openai http/request failed/invalid response/empty response,openai.py:19-23) |
| Token 统计 | ✅ 有 | usage.prompt_tokens/completion_tokens 解析(openai.py:237-242) |
| 成本统计 | ✅ 有 | estimated_cost_usd(openai.py:116-129)+ usage.json 持久化 + _RecordingProvider(workflow_runner.py:467) |

**判定:部分完成(Runtime 本体质量高;缺多 Provider 路由/负载均衡/故障切换)**
对应代码:factory-exec/exec/providers/openai.py;factory-exec/exec/developer.py:588-688
测试:24 个(test_exec_provider_openai.py,全 MockTransport 零真实网络)

---

## 4. Agent → LLM 实际调用链

```
Task → Session → AgentExecutionLoop → LLMPlanner → ProviderInterface.generate
     → DeveloperAgent.work(内建重试) → ExecutionResult → Artifact
```

| 环节 | 代码 | 真实运行证据 |
|---|---|---|
| Task/Agent 校验 | ✅ agent_executor.py:122 | — |
| Session 生命周期 | ✅ runtime_session.py | sessions.json 有 6 条真实 session |
| LLMPlanner 决策 | ✅ execution_loop.py:164 | rs-3fb653f1/rs-eab8019e:decision_created = `{"type":"FINAL","reason":"no LLM provider configured (provider key missing)"}` |
| Provider 调用 | ✅ openai.py 真实 HTTP | **0 次成功** |
| DeveloperAgent 执行 | ✅ developer.py | 未到达(provider 缺失即 FAILED) |
| Artifact 产出 | ⚠️ 仅 rs-1788d4b2 | 该 session 事件仅 tool_called/output_generated,**无任何 LLM 痕迹**(非 LLM 链产出) |

**关键运行证据(usage.json 实测):**
- 7 条记录,provider_id 全部 = "hermes"(subprocess 调 hermes CLI,非 OpenAI/Anthropic/DeepSeek API)
- 6 次失败:hermes command timed out after 300s
- 1 次 success 但 prompt_tokens=0 / completion_tokens=0 / latency_ms=0 —— **空调用,非真实 LLM 输出**

**判定:调用链代码完整,但从未真实调用过外部 LLM —— 全部执行都是诚实 FAILED 或空转**
对应代码:factory-exec/exec/agent_executor.py:122-167;factory-exec/exec/execution_loop.py
运行证据:~/.factory/providers/usage.json;~/.factory/runtime-sessions/sessions.json;~/.factory/factory.db events(provider.execution.completed 仅 2 次,payload 为 hermes CLI 输出)

---

## 5. 测试覆盖

| 测试文件 | 数量 | 性质 |
|---|---|---|
| tests/exec/test_exec_provider.py | 21 | 单测,httpx.MockTransport 全 mock |
| tests/exec/test_exec_provider_openai.py | 24 | 单测,httpx.MockTransport 全 mock |
| tests/exec/test_exec_agent_executor.py | 12 | 单测(验证 FAILED 路径) |
| tests/exec/test_exec_execution_loop.py | 39 | 单测(含无 provider 诚实回退) |
| **合计** | **96** | **实跑 96 passed in 2.80s ✅** |

- 单元测试:✅ 96 个,实跑全绿
- 集成测试:❌ 无(无 provider→executor→artifact 全链集成测试)
- 真实 API 测试:❌ **零**(全仓无 live/REAL/network 标记测试;全部 MockTransport)

**判定:单测质量好但全是 mock,无任何真实调用验证 —— 这正是"看起来能跑、实际从未跑通"的测试盲区**

---

## 6. 最终评分

| 维度 | 得分 | 理由(为何不是更高) |
|---|---|---|
| LLM Configuration | **12/20** | 接口/校验/分层读取完整,但持久化为零(config.json/.env 不存在),多 provider 无法并行装配 |
| LLM Management | **2/20** | 无 Model Catalog、无 Agent-模型绑定、无运行时切换,只有构造参数级 model 覆盖 |
| LLM Runtime | **14/20** | 单 provider 真实 HTTP + 重试/超时/错误/token/成本全齐,但无路由/故障切换/负载均衡 |
| Agent Integration | **4/20** | 调用链代码完整但**从未真实跑通过**(全部诚实 FAILED),无一次真实 LLM 调用记录 |
| Production Readiness | **3/20** | 无 key 持久化、无 API 认证、无 CI、从未真实调用 —— 无法对外演示"AI 在写软件" |
| **总分** | **35/100** | |

---

## A. 当前完成度百分比

**35%**(代码结构 70%,运行能力 0%)

## B. 已完成能力

1. Provider 抽象:ProviderInterface + Registry + ConfigChecker(provider.py)
2. 真实 HTTP Adapter:OpenAI + Anthropic(含超时/错误分类/空内容检测/成本估算)
3. DeveloperAgent 内建重试(EMPTY_CONTENT 重试信号)
4. 分层配置读取:env > .env > config.json(config.py)
5. LLMPlanner 诚实回退(无 provider → FINAL 带 reason,不伪造)
6. usage.json 调用记录 + 成本持久化
7. 96 个单元测试全绿

## C. 缺失能力

1. **Provider 配置持久化**(config.json / providers.json 均不存在)
2. **Model Catalog**(模型信息结构化注册)
3. **Agent ↔ 模型绑定与运行时切换**
4. **多 Provider 并行装配与路由**(能力/成本/延迟/故障切换)
5. **任何一次真实 LLM 调用**(运行证据为 0)
6. **集成测试 / 真实 API 测试**
7. API 认证(审计时 FastAPI 裸奔)

## D. 最大阻塞点

**配置持久化缺失 + key 从未注入 → 全链路从未真实调用 LLM。**

证据链:无 config.json/.env → has_llm_key()=False → _self_assemble_runtime()=None(service.py:395-408)→ AgentExecutor 诚实 FAILED → 所有 runtime-session 均为 "no LLM provider configured"。即使 key 存在,装配代码(workflow_runner._build_provider)也从未在运行中被验证过。

## E. S10-021 是否仍然必要

**是,绝对必要,且是当前唯一 P0。**

S10-021(LLM Activation)要解决的正是 C 中 1/2/3/5 四项:Provider 配置持久化 + Model Catalog + 真实执行。没有它,Phase 2 产品化、Phase 3 治理、融资 Demo 全部无从谈起。

## F. 如果继续开发,优先级排序

1. **P0 S10-021a:Provider 配置持久化** — 写 ~/.factory/config.json(provider/model/base_url/key_env 引用,禁明文)+ 装配验证。预计 1-2 天
2. **P0 S10-021b:真实执行冒烟** — 注入 DEEPSEEK key(已有)跑通 Task→LLM→Artifact 全链,记录 usage/事件,留下 curl + usage.json 证据。预计 1-2 天
3. **P1:Model Catalog** — 模型信息结构化(名称/能力/context/cost)+ Agent 绑定 + 运行时切换。预计 3-5 天
4. **P1:真实 API 集成测试** — env 标记的 live 测试(CI 可跳过),锁住真实调用链
5. **P2:多 Provider 路由** — 能力/成本/延迟/故障切换(Phase 3 治理增强)
6. **P2:API 认证** — 防暴露即被任意调用

---

> 审查完毕 | 依据:代码 + 测试实跑(96 passed)+ 运行数据(usage.json/sessions.json/factory.db)三方交叉验证
> 无设计文档引用;未修改任何代码
