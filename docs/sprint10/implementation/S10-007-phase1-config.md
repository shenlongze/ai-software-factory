# S10-007 阶段一 — AI Factory Configuration Layer (配置独立化)

> 日期: 2026-08-10 | 状态: 完成 | 基线: 2a60269 (pytest 6602) | 提交: 见 git log

## 一、背景与目标

S10-007 审计 (docs/sprint10/S10-007-plan.md) 定位两个 P0/P1 运行依赖问题:

| # | 耦合 | 严重度 | 本阶段处置 |
|---|---|---|---|
| 1 | `workflow_runner.py` load_llm_key 硬读 `~/.hermes/.env` 的 DEEPSEEK_API_KEY | **P0 产品运行依赖** | ✅ 解除: ConfigProvider 分层配置, 零 ~/.hermes 读取 |
| 2 | MODEL/BASE_URL 常量硬编码 DeepSeek | P1 不可配置 | ✅ 解除: provider 映射表 (deepseek/openai/anthropic/ollama) + 可覆盖 |
| 3 | factory-exec 3 个开发脚本读 ~/.hermes/.env | 非产品运行时 | 不动 (任务文件范围外; 开发演示脚本保留) |
| 4 | 开发环境依赖 Hermes 注入 OPENAI_API_KEY | P1 | ✅ 兼容: 进程环境 OPENAI_API_KEY 仍最高优先 |

用户要求: **禁止 Runtime 直接读 Hermes 路径; Config Provider 抽象; 未来支持
DeepSeek/OpenAI/Anthropic/本地模型 — 不写死 DeepSeek。**

## 二、配置层设计 (factory-console/config.py)

### 加载优先级 (逐 key 合并, 高 → 低)

```
1. 进程环境变量 (os.environ)    — LLM_PROVIDER/LLM_MODEL/LLM_BASE_URL/
                                   LLM_API_KEY/DATA_DIR/PORT/FRONTEND_PORT
2. 项目 .env (factory-console/.env)
                                   — 同 key 名 (KEY=VALUE; # 注释; export 前缀;
                                     引号剥离; 非法行响亮忽略)
3. 用户级 ~/.factory/config.json   — {"llm": {provider, model, base_url, api_key},
                                     data_dir, port, frontend_port}
4. 默认值                          — PROVIDER_DEFAULTS 映射表 + 模块常量
```

空串视为未配置 (逐层下落, 不阻断链)。整型非法值 (端口) → 响亮日志 + 默认 (失败安全)。

### LLM 多 Provider 映射表 (PROVIDER_DEFAULTS)

| provider | 默认 model | 默认 base_url | api_key_env (兜底) | key_env (注入目标) |
|---|---|---|---|---|
| deepseek | deepseek-v4-pro | https://api.deepseek.com/v1/chat/completions | DEEPSEEK_API_KEY | OPENAI_API_KEY |
| openai | gpt-4o | https://api.openai.com/v1/chat/completions | OPENAI_API_KEY | OPENAI_API_KEY |
| anthropic | claude-sonnet-4-20250514 | https://api.anthropic.com/v1/messages | ANTHROPIC_API_KEY | ANTHROPIC_API_KEY |
| ollama (本地) | qwen2.5:14b | http://127.0.0.1:11434/v1/chat/completions | — (无 key) | — (无 key) |

- `LLM_MODEL` / `LLM_BASE_URL` 显式覆盖 provider 默认 (本地 Ollama 换模型/端口可配)。
- 未知 provider → `logging.warning` 响亮警告 + 降级 deepseek 默认映射 (失败安全)。
- 费率 (input/output_rate_per_1k) 随 provider 映射, 仅成本估算非计费 (同 S8-005)。

### API key 语义

解析链 (get_llm()["api_key"]):
1. `LLM_API_KEY` (env > .env > config.json), 值支持 **`env:VAR` 引用**
   (如 `env:DEEPSEEK_API_KEY` — 先查进程环境, 再查项目 .env 内变量; 缺 VAR → 空, 诚实缺失)
2. provider 专属环境变量兜底 (deepseek → DEEPSEEK_API_KEY, anthropic → ANTHROPIC_API_KEY)
3. `OPENAI_API_KEY` 兜底 (历史 Hermes 进程环境注入目标 — 开发环境向后兼容)

注入目标 (workflow_runner.load_llm_key 进程内注入, 禁明文):
- deepseek/openai → `OPENAI_API_KEY` (OpenAI 兼容端点, OpenAIProvider._resolve_api_key 读它)
- anthropic → `ANTHROPIC_API_KEY` (AnthropicProvider 读它)
- ollama → 无 key (本地不校验)

### 方法与失败安全

- `get(section, key, default=None)` — section: "llm" (env 前缀 LLM_) / "core" (DATA_DIR/PORT/...)
- `get_llm() -> {provider, model, base_url, api_key, key_env, 费率}` / `get_data_dir()` /
  `get_port()` (8011) / `get_frontend_port()` (5180)
- 失败安全: .env 读取失败 / config.json 损坏 (非法 JSON / 顶层非对象) / 非法行 /
  非法端口 → `logging.warning` 响亮日志 + 降级默认值, **绝不抛异常拖垮启动**。
- 构造参数可注入 (env_file / user_config_file / environ) — 测试与冒烟 hermetic;
  environ 缺省 os.environ (调用时实时读, monkeypatch.setenv 可见)。
- 进程级单例 `get_config()`; 消费方可 monkeypatch 注入 (测试)。
- **铁律: 本模块不读取任何 ~/.hermes 路径** (测试含静态守卫)。

## 三、解耦点 (workflow_runner.py)

| 旧 (Hermes 耦合) | 新 (ConfigProvider) |
|---|---|
| `MODEL`/`BASE_URL`/费率模块常量硬编码 DeepSeek | 删除常量, 一律 `get_config().get_llm()` (report/progress 的 model 字段同源) |
| `load_llm_key` 读 `~/.hermes/.env` 的 DEEPSEEK_API_KEY | ConfigProvider 解析链 + 按 provider 注入 (deepseek→OPENAI_API_KEY 等); 签名/语义兼容 (返回 key, 空=缺失) |
| `has_llm_key` = env OPENAI_API_KEY OR load_llm_key | env OPENAI_API_KEY 优先 (兼容) + config 解析; **ollama 本地无 key → True** |
| `_build_provider` 固定 OpenAIProvider + DeepSeek 常量 | provider 选择: anthropic → AnthropicProvider; deepseek/openai/ollama → OpenAIProvider (ollama 占位 key, 本地不校验) |
| 503 文案 "DEEPSEEK_API_KEY not found in ~/.hermes/.env" | "LLM_API_KEY not configured — 见 factory-console/.env.example" |
| `_RecordingProvider.provider_id` 类常量 "deepseek-v4-pro-rec" | property 随配置 (f"{provider}-rec") |

向后兼容: 开发环境 (有 ~/.hermes/.env, Hermes 曾注入 OPENAI_API_KEY) 因
"进程环境优先" 规则继续可用 — 本模块自身不读 Hermes 文件, 只认注入结果。

## 四、示例配置 (factory-console/.env.example)

全量注释: LLM_PROVIDER/LLM_MODEL/LLM_BASE_URL/LLM_API_KEY (env:VAR 两种写法)/
DATA_DIR/PORT/FRONTEND_PORT + 4 provider 默认映射 + ~/.factory/config.json JSON 示例。
`.env` 已在 .gitignore (`.env` 行) — 复制即用, 不会误提交。

## 五、测试 (tests/console/test_console_config.py, 28 个)

- **优先级** (5): env > .env; .env > 用户 config; 用户 config > 默认; 全空默认
  (provider/data_dir/端口); DATA_DIR/PORT/FRONTEND_PORT 覆盖
- **API key** (6): .env 直读 (HOME 隔离, 无 ~/.hermes); env:VAR 从进程环境;
  env:VAR 从 .env 内变量; env:VAR 缺变量 → 空; provider 专属 env 兜底;
  OPENAI_API_KEY 兼容兜底
- **provider 映射** (7): deepseek/openai/anthropic/ollama 四映射 (model/base_url/
  key_env/api_key); LLM_MODEL/LLM_BASE_URL 显式覆盖; 未知 provider 降级 + 警告
- **失败安全** (4): config.json 非法 JSON; 顶层非对象; .env 非法行 (合法行仍生效);
  非法端口 → 默认 + 警告
- **workflow_runner 解耦** (6): 纯配置环境 has_llm_key True (HOME 隔离);
  无 key → False; deepseek 注入 OPENAI_API_KEY; anthropic 注入 ANTHROPIC_API_KEY
  (不碰 OPENAI_API_KEY); ollama 无 key → True; 进程环境 OPENAI_API_KEY 优先;
  静态守卫 (源码无 `Path.home() / ".hermes"` 读取形态)

全量结果: **6630 passed** (6602 基线 + 28 新增), vitest 未触碰。

## 六、干净环境冒烟 (HOME 隔离)

模拟普通用户首启: 全新临时 HOME (无 ~/.hermes) + 项目 .env 配 key →
`has_llm_key() == True` + `start_project_workflow` 过 key 校验走真实链
(假链注入, 零 LLM 成本)。详见阶段验收记录 (冒烟脚本输出在会话记录)。

## 七、遗留与后续 (诚实边界)

- `fastapi_adapter.DEFAULT_ROOT/DEFAULT_PORT` 尚未改读 ConfigProvider (本阶段
  文件范围 = config.py + workflow_runner; 默认值同口径 8011 / ~/.factory,
  阶段二 CLI 启动时统一接线)。
- anthropic provider 的真实链路径 (AnthropicProvider + Messages API) 已装配但
  未做真实调用验收 (省成本; deepseek 链 S8-005 已验证)。
- factory-exec 3 个开发脚本仍读 ~/.hermes/.env (非产品运行时, 任务范围外)。
