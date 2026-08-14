# S10-027 Task 3 — Configuration Architecture Finalization

> 日期:2026-08-14 | Sprint: S10-027 Hardening | 只读审计
> 目标:确认配置体系不随扩展冲突;分析未来 OpenClaw/Hermes/Claude Code 集成

---

## 1. 最终配置定义

### 1.1 Runtime — config.json(~/.factory/config.json)

| 项 | 说明 | 允许键 |
|---|---|---|
| 职责 | Factory Runtime Configuration | core.data_dir / core.port / core.frontend_port / (未来 runtime mode/logging) |
| 红线 | **禁止 LLM 偏好**(provider/model/api_key — S10-026 落实) | — |

```json
{
  "core": { "data_dir": "~/.factory", "port": 8011, "frontend_port": 5180 }
}
```

### 1.2 Provider — providers.json(~/.factory/providers.json)

| 项 | 说明 |
|---|---|
| 职责 | Provider 生命周期(enabled/models/base_url/api_key_ref/metadata) |
| 支持 | OpenAI / Anthropic / DeepSeek / Ollama(内置默认,config.py PROVIDER_DEFAULTS) |
| Azure | ⚠️ **未内置** — Azure OpenAI 走 openai 类型 + base_url 覆盖(OpenAIProvider 兼容端点);需手动配 base_url |

```json
{
  "providers": {
    "deepseek": { "enabled": true, "models": [...], "base_url": "...", "api_key_ref": "env:DEEPSEEK_API_KEY" }
  }
}
```

### 1.3 Model — models.json(~/.factory/models.json)

| 项 | 说明 |
|---|---|
| 职责 | Model 元数据(capabilities/context_window/cost/enabled) |
| 种子 | deepseek-chat / deepseek-reasoner / gpt-4o / claude-sonnet-4(ModelCatalog 自动 seed) |

### 1.4 Policy — agent.yaml / skill.yaml / project.yaml

| 文件 | 职责 | 管理者 |
|---|---|---|
| agent.yaml | 角色级路由偏好(preferred/fallback) | AgentPolicyStore (L2) |
| skill.yaml | 技能级路由偏好 | AgentPolicyStore (L2) |
| project.yaml | 项目级规则(default/task_types) | LLMRouter (L3) |

## 2. 重复配置源检查

| 配置项 | 来源 1 | 来源 2 | 冲突? | 结论 |
|---|---|---|---|---|
| provider | providers.json | env LLM_PROVIDER / .env | ⚠️ 潜在 | 设计为 fallback(env 高优先但 Router 链优先文件);需文档化 |
| model | models.json | env LLM_MODEL / .env | ⚠️ 潜在 | 同上 |
| api_key | providers.json api_key_ref | env LLM_API_KEY / .env | ✅ 设计意图 | key 优先 env(S10-007);文件只存 ref |
| data_dir/port | config.json | env DATA_DIR/PORT | ✅ 分层 | 无冲突 |
| 策略 | yaml 文件 | — | ✅ 唯一来源 | 无 |

**核心结论:无实际冲突。** 潜在冲突点(env 覆盖文件)是设计语义(fallback),非缺陷。
建议(记录):factory config check 加多源冲突检测(env LLM_PROVIDER ≠ providers.json enabled → WARN)。

## 3. 未来外部工具集成冲突分析

### 3.1 Hermes

| 项 | 分析 |
|---|---|
| 冲突风险 | **中** — ~/.hermes/.env 的 DEEPSEEK_API_KEY |
| 现状 | AI Factory **显式不读 ~/.hermes**(S10-007 注释);但用户可能手动 export → env 层覆盖 |
| 建议 | 文档化"AI Factory 不读外部工具 env";config check 检测 env 注入来源 |

### 3.2 OpenClaw

| 项 | 分析 |
|---|---|
| 冲突风险 | **低** — OpenClaw 用自己数据目录 |
| 未来 | 若 OpenClaw 也管理 ~/.factory(集成场景)→ providers.json 需约定读写权限 |
| 建议 | ~/.factory 前缀命名空间已隔离;集成时 OpenClaw 只读 AI Factory 配置,不写 |

### 3.3 Claude Code

| 项 | 分析 |
|---|---|
| 冲突风险 | **低** — .claude/ 目录 + CLAUDE.md(prompt 非配置) |
| 建议 | 无冲突;CLAUDE.md 可作为 AI Factory 项目的开发指引,与运行时配置无关 |

### 3.4 通用风险与对策

| 风险 | 对策 |
|---|---|
| 多工具共享 ~/.factory | 命名空间隔离(每个工具子目录:providers/ models/ org/);不共享单文件 |
| env 公共面 | env LLM_* 是"最高优先级覆盖",任何工具 export 都影响 — 文档化 + check 检测 |
| 配置格式漂移 | 每配置文件有 pydantic schema(ProviderConfigFile/ModelCatalogFile/...)— 损坏响亮报错 |

## 4. 配置架构评分

| 维度 | 评分 | 说明 |
|---|---|---|
| 单一来源 | 9/10 | 各文件职责清晰,config.json 红线落实 |
| 分层明确 | 9/10 | env > .env > config.json > 默认 |
| 冲突防护 | 8/10 | 红线+唯一来源;env 覆盖需文档化 |
| 扩展性 | 9/10 | 新模块(rag/governance)用各自配置文件或 config.json 子段 |
| 外部集成 | 8/10 | 命名空间隔离良好;env 公共面文档化即可 |

**总分:8.6/10 — 配置架构健康,无阻塞冲突。**

## 5. 未来扩展的配置落位(定义)

| 未来能力 | 配置位置 | 说明 |
|---|---|---|
| Router 增强(权重) | config.json llm.router 段 或 router.yaml | 决策参数 |
| RAG | rag.yaml(索引/embedding) | 独立能力配置 |
| Governance | governance.yaml(策略/RBAC) | 独立治理配置 |
| Evaluation | evaluation.yaml(评估器) | 独立评估配置 |
| Logging | config.json core.logging | 运行时配置(允许) |

**原则:运行时可配置 → config.json;能力专属 → 独立 yaml(如 rag.yaml);策略 → yaml 策略文件。不产生第 6 个 LLM 偏好源。**

---

> 审计完毕 | 只读 | 配置架构 8.6/10,无阻塞冲突
