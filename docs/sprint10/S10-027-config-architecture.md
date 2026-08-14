# S10-027 Task C — Configuration Architecture Audit

> 日期:2026-08-14 | Sprint: S10-027 Hardening | 只读审计
> 目标:确认配置层不冲突;检查未来 OpenClaw/Claude Code/Hermes 集成冲突风险

---

## 1. 目标配置结构(现状)

```
优先级高 → 低:
1. 环境变量 (os.environ)         最高优先级 (ConfigProvider.get 第一层)
2. 项目 .env (factory-console/.env)  开发环境 (第二层)
3. ~/.factory/config.json        Factory runtime (第三层 — 白名单: data_dir/port/frontend_port)
4. 默认值 (config.py PROVIDER_DEFAULTS)  兜底

独立配置文件 (不分层, 各司其职):
~/.factory/providers.json   LLM Provider 生命周期 (LLMControlPlane)
~/.factory/models.json       Model Catalog (ModelCatalog)
agent.yaml                   Agent Policy (AgentPolicyStore — L2)
skill.yaml                   Skill Policy (AgentPolicyStore — L2)
project.yaml                 Project Policy (LLMRouter — L3)
```

## 2. 配置源冲突检查

### 2.1 重复配置源排查

| 配置项 | 可能来源 | 是否冲突 | 结论 |
|---|---|---|---|
| provider | providers.json / config.json(llm.provider 被拒) / env LLM_PROVIDER / .env | ⚠️ 潜在 | config.json 已红线禁止;但 **env/.env 仍可覆盖 providers.json**(ConfigProvider 分层优先于 ControlPlane 文件读取) |
| model | models.json / env LLM_MODEL / .env | ⚠️ 潜在 | 同上:env 优先于文件 |
| base_url | providers.json / env LLM_BASE_URL / .env | ⚠️ 潜在 | 同上 |
| api_key | providers.json api_key_ref / env LLM_API_KEY / .env | ✅ 设计意图 | key 优先 env(S10-007 分层),providers.json 只存 ref |
| data_dir/port | config.json / env DATA_DIR/PORT | ✅ 分层设计 | 无冲突 |
| agent policy | agent.yaml(唯一) | ✅ 唯一来源 | 无 |
| skill policy | skill.yaml(唯一) | ✅ 唯一来源 | 无 |
| project policy | project.yaml(唯一) | ✅ 唯一来源 | 无 |

### 2.2 核心发现:env/.env 与 providers.json 的潜在冲突

**现状**:ConfigProvider.get_llm() 读 env/.env(高优先)→ LLMControlPlane 读 providers.json(文件)。
两条路径都存在,但**装配点 workflow_runner._resolve_llm_config() 先走 Router(providers.json 系),未命中才走 get_llm()(env 系)**。

**风险场景**:用户配了 providers.json(deepseek enabled + key_ref),同时又设了 env LLM_PROVIDER=openai。
→ Router 命中 deepseek(S10-021 逻辑),env 被忽略 → **用户以为 openai 生效,实际 deepseek 生效**。

**结论**:不是设计缺陷(有明确优先级:Router/providers.json 优先),但**文档缺失** — 用户不知道 env 是 fallback 而非 override。

### 2.3 建议(记录不实现)
1. `factory config check` 增加"多源冲突检测":env LLM_PROVIDER ≠ providers.json enabled → WARN 提示
2. README/init 明确优先级:providers.json(Router 链)优先于 env(get_llm fallback)

## 3. 未来外部工具集成冲突风险

### 3.1 OpenClaw / Claude Code / Hermes 集成场景

| 外部工具 | 冲突点 | 风险等级 | 分析 |
|---|---|---|---|
| Hermes | ~/.hermes/.env 的 DEEPSEEK_API_KEY | 中 | 项目显式"不读 ~/.hermes"(S10-007 注释);但用户可能手动 export → env 层被覆盖。**建议:明确文档化"AI Factory 不读外部工具 env"** |
| OpenClaw | 若也读 ~/.factory/ | 低 | 目录不冲突(OpenClaw 用自己数据目录);若 OpenClaw 未来读 providers.json → 需约定命名空间 |
| Claude Code | .claude/ 目录 + CLAUDE.md | 低 | 数据目录独立;CLAUDE.md 是 prompt 非配置,无冲突 |
| 通用风险 | 多工具共享 ~/.factory/ | 中 | **建议:AI Factory 的 ~/.factory 前缀已是命名空间隔离**;未来每工具子目录(providers/ 等) |

### 3.2 结论
- **当前无实际冲突**:配置文件各自独立(~/.factory 前缀命名空间)
- **未来风险点**:env 层是"公共面",任何工具 export LLM_* 都会影响 AI Factory(设计如此,fallback 语义)
- **建议动作**:config check 多源检测 + 文档化优先级(记录,不实现)

## 4. 配置架构评分

| 维度 | 评分 | 说明 |
|---|---|---|
| 单一来源 | 8/10 | 各文件职责清晰,config.json 红线已落实 |
| 分层明确 | 9/10 | env > .env > config.json > 默认 |
| 冲突防护 | 7/10 | 红线防了 config.json,但 env 覆盖未文档化 |
| 扩展性 | 8/10 | config.json 未来可加 services/demo 段;政策文件各司其职 |
| 外部集成 | 7/10 | 命名空间隔离良好,env 公共面需文档 |

**总分:7.8/10 — 配置架构健康,无阻塞问题**

---

> 审计完毕 | 只读 | 建议项记录不实现
