# S10-021 LLM Infrastructure — Reality Check

> 日期:2026-08-13 | 只依据实际代码/测试/运行证据,不看设计文档
> 基线:git 9cad09a | 测试实跑(本检查新跑):tests/providers 571 passed + 2 failed;LLM 相关 exec 96 passed
> 前置审查:docs/audit/LLM-CAPABILITY-AUDIT-2026-08-13.md(总分 35/100,LLM 从未真实调用)

---

## 1. 当前已有文件

### A. factory-core/providers/(Phase 8A/8B 抽象层,2992 行,独立数据空间)
| 文件 | 行数 | 作用 |
|---|---|---|
| models.py | 235 | ProviderDefinition + Request/Response(统一 I/O) |
| provider.py | 70 | ProviderAdapter 抽象接口(generate/chat/stream) |
| registry.py | 175 | ProviderRegistry(register/get/find_by_capability/default) |
| store.py | 156 | ProviderStore — catalog.json 原子写(持久化机制✅) |
| definitions.py | 103 | 默认定义(仅 hermes) |
| selector.py | 494 | ProviderSelector 四层链(Project > Agent > Runtime > Default) |
| integration.py | 263 | ProviderCarrierAdapter / 载波 |
| usage.py | 446 | usage.json 原子写 + 统计 |
| feedback.py | 176 | 反馈记录 |
| capability.py | 152 | 能力画像 |
| costs.py | 189 | 成本模型 |
| events.py | 328 | provider.* 事件 |
| config.py | 89 | runtime_preferences 解析 |
| adapters/hermes.py | 9140B | HermesProviderAdapter(subprocess 调 hermes CLI) |

### B. factory-exec/exec/(Phase A 执行层,真实 HTTP)
| 文件 | 作用 |
|---|---|
| provider.py (259行) | ProviderInterface + Registry + ConfigChecker(检查 key 是否设置) |
| providers/openai.py (262行) | OpenAI 真实 HTTP Adapter(chat/completions,超时/错误/token/成本) |
| providers/anthropic.py | Anthropic 真实 HTTP Adapter(Messages API) |
| developer.py | DeveloperAgent(内建重试) |
| agent_runtime.py (607行) | AgentRuntime(execution 编排,依赖 provider 注入) |

### C. factory-console/(装配层)
| 文件 | 作用 |
|---|---|
| config.py | ConfigProvider 分层读取(env > .env > config.json)+ get_llm() |
| workflow_runner.py | load_llm_key()/has_llm_key()/_build_provider(按 provider 构建真实 Adapter) |

### D. 运行数据(~/.factory/providers/)
| 文件 | 状态 |
|---|---|
| usage.json | ✅ 存在(7 条记录,6 失败 1 空成功) |
| catalog.json | ❌ 不存在(store.py 设计写这里,从未落盘) |
| config.json | ❌ 不存在(config.py 设计读这里,从未创建) |

---

## 2. 当前已有能力

1. **Provider 抽象**:两套并存(exec 的 ProviderInterface + core 的 ProviderAdapter),都可用
2. **真实 HTTP Adapter**:OpenAI + Anthropic(超时/错误分类/空内容检测/token/成本估算)
3. **配置读取链**:env > .env > config.json(config.py 完整实现,支持 env:VAR 引用如 env:DEEPSEEK_API_KEY)
4. **key 检查/注入**:has_llm_key()/load_llm_key()(workflow_runner.py:75-105)
5. **Provider 选择器**:selector.py 四层链(Project > Agent > Runtime > Default)——**注意:路由骨架已存在但未接真实数据**
6. **usage/feedback 记录**:usage.py + feedback.py(usage.json 有真实记录)
7. **持久化机制**:store.py 原子写(os.replace)已实现,只是从未被调用产生 catalog.json
8. **测试**:tests/providers 573 个(571 过 + 2 挂)、exec LLM 96 个全过

---

## 3. 当前缺失能力(按 Phase 目标排序)

### Phase 1 缺口(配置层,P0)
1. **Provider 配置持久化** — catalog.json / config.json 从未创建。理论机制有(store.py),实际零文件
2. **Provider 启用/禁用** — enabled 字段无模型支持(ProviderDefinition 无此字段)
3. **has_llm_key() 恒 False** — 无任何配置来源 → _self_assemble_runtime() 返回 None → 全部诚实 FAILED
4. **API key 集中管理** — 仅散落环境变量;无统一 ref 概念(api_key_ref 不存在)

### Phase 2 缺口(模型管理)
5. **Model Catalog** — 不存在(exec 层零命中;core 层 definitions 仅 hermes-default)
6. **Agent ↔ 模型绑定** — 无
7. **"哪个模型适合这个任务"查询** — 无(capability.py 有画像但未接模型查询)

### Phase 3 缺口(真实执行)
8. **任何一次真实 LLM 调用** — 运行证据 0 次成功
9. **Task→Planner→Runtime→Provider→Response→Artifact→Audit 全链验证** — 未跑通

### Phase 4/5(路由)
10. Router v1 的四层链 selector.py 已有骨架,但**输入(usage/feedback/真实配置)全是空的**,当前不可用
11. 智能路由(动态权重/学习)按你的指示暂缓,不实现

---

## 4. 推荐实施顺序

```
Phase 1a: Provider 配置持久化模型 (新增 providers.json / catalog.json 落地)
   ↓
Phase 1b: API Key 管理 (api_key_ref + env 解析 + 不落明文 + 日志脱敏)
   ↓
Phase 1c: 装配接线 (has_llm_key 读新配置 → 自装配真实 provider)
   ↓
Phase 2: Model Catalog (deepseek-chat / deepseek-reasoner / claude-sonnet)
   ↓
Phase 3: 真实执行链激活 (接 DEEPSEEK key 跑通全链 + 记录 tokens/cost/latency)
   ↓
Phase 4: Router v1 (用户指定 > 项目规则 > 系统推荐 > 默认 fallback,基于已接好的 usage/feedback)
```

关键决策:**Phase 1 必须在 1 个 Sprint 内完成**,因为它是 Phase 3 的前置,而 Phase 3 是"AI Factory 真正能跑"的证明。

---

## 5. 第一批修改文件列表(Phase 1,P0)

### 新增文件
1. `factory-console/llm_config.py`(或 `factory-exec/exec/llm_config.py`)— Provider 配置模型 + providers.json 持久化 + 启停 + api_key_ref 解析
   - 结构:`{"providers": {"deepseek": {"enabled": true, "base_url": "...", "api_key_ref": "env:DEEPSEEK_API_KEY"}}}`
   - 支持重启恢复(读 providers.json)
2. `tests/llm/test_llm_config_persistence.py` — 持久化 + 重启恢复测试
3. `tests/llm/test_llm_key_management.py` — env/文件引用 + 日志不泄露测试

### 修改文件
4. `factory-console/config.py` — get_llm() 增加从 providers.json 读取 provider 列表(与现有 env/.env/config.json 分层合并,不破坏)
5. `factory-console/workflow_runner.py` — has_llm_key() 改读新配置(不再恒 False);_build_provider 支持 enabled 过滤
6. `factory-core/providers/models.py` — ProviderDefinition 增加 enabled 字段(可选,兼容现有默认)
7. `factory-core/providers/store.py` — 复用现有原子写,增加 providers.json 支持(或直接新建独立 store)

### 不动
- factory-exec/exec/provider.py(接口稳定,不重写)
- factory-exec/exec/providers/openai.py / anthropic.py(Adapter 已就绪,零改动)
- selector.py(Phase 4 再动)
- Agent 核心流程(execution_loop / agent_runtime)

### 关键设计约束
- 不硬编码:provider 列表来自文件
- 不依赖临时环境:providers.json 持久化在 ~/.factory/
- API key 不落明文:只存 ref(env:DEEPSEEK_API_KEY),解析在内存
- 日志脱敏:任何 logger 不打印 key 本体
- 兼容:现有 env > .env > config.json 分层读取优先,providers.json 作为新增来源

---

## 结论

- **骨架充足**:两套 Provider 抽象 + 真实 Adapter + 持久化机制(store.py)+ 选择器,代码资产丰厚
- **真实运行为零**:catalog.json/config.json 不存在 → 无配置 → 无 key → 无真实调用
- **第一步最小**:新增 1 个配置模块 + 3 个测试文件 + 改 3 个装配文件,即可让 has_llm_key() 从恒 False 变为可配置
- 风险:tests/providers 现有 2 个失败(test_period_field_reflected ×2,疑似日期字段问题)需顺带确认,但不阻塞 Phase 1

确认后开始 Phase 1 实现。
