# S10-078 — Provider 配置链 + Error UX 分层

> 日期: 2026-08-17 | 开箱即用体验 | User-facing Error ≠ Developer Diagnostic

---

## 1. Reality Audit

```
用户环境 providers.json: deepseek enabled + api_key_ref=env:DEEPSEEK_API_KEY ✅
环境变量: DEEPSEEK_API_KEY 已设置 ✅
安装态 select → deepseek ✅ | _default_llm_fn → 真实 DeepSeek 回答 ✅
用户看到的 "anthropic key missing" 来自旧环境/旧版 (当前已修复)
cli_doctor 缺 wheel 模式判断 → 部署态误报 .venv/node_modules
ChatService 错误含内部异常 (默认输出)
```

## 2. 根因

- ChatService 默认输出 (细节: 内部异常) — 污染普通用户
- logger.warning 打到 stderr — REPL 混入 "chat answer failed"
- cli_doctor 无 wheel 模式判断 — 部署态误报

## 3. Provider 配置链 (真实, 安装态验证)

```
providers.json (api_key_ref=env:DEEPSEEK_API_KEY) → 环境变量解析 → LLMControlPlane.select
→ exec provider registry → provider.generate
优先级: 环境变量 > 项目 .env > config.json > providers.json > 默认 (代码事实)
doctor / init / factory 同一配置源 ✅
```

## 4. factory doctor 行为 (真实)

```
✓ [PASS] provider: 1 enabled, key 可解析 (deepseek)
✓ [PASS] router: deepseek/deepseek-chat
⚠ [WARN] 修复: wheel 模式不再误报 .venv/node_modules (S10-078)
```

## 5. factory init 行为 (真实)

```
✓ 环境检查 → workspace 就绪 → 显示当前 Provider (enabled/models/api_key_ref, 不泄 key)
✓ 非交互保持现有配置; 校验通过
```

## 6. Provider resolution

- select 读 providers.json (env ref) ✅
- 不落明文 key (仅 env:DEEPSEEK_API_KEY 引用) ✅

## 7. Error UX

```
默认 (用户): 简洁明确:
  AI 对话服务当前不可用。
  原因: LLM Provider 尚未配置或 API Key 缺失。
  建议: 1. factory doctor 2. factory init
  系统命令不受影响。
verbose (开发者): 含 (细节: ...) 内部原因
细节日志: logger.debug (默认不显示)
stderr: 干净 ✅
```

## 8. Error Sanitization

- 默认输出无: Traceback / 类名 / Provider constructor / 内部异常 ✅
- REPL stderr 干净 (debug 级别) ✅

## 9. Security

- 绝不输出 API Key 值; providers.json 仅 env ref ✅

## 10. Query 不依赖 LLM

- Provider 缺失: 项目列表/当前项目 正常 (S10-077 保持) ✅

## 11. Chat Provider behavior

- 已配置: 你好/什么是 Docker → 真实 AI 回答 (安装态实证) ✅
- 未配置: 简洁提示 (不伪装目标不明) ✅

## 12. 测试数量

新增 10 (test_s10_078_provider_ux.py); console+api 4498 passed; 全量 11755 passed (零回归)。

## 13. 真实安装态 E2E

```
Provider 已配置 (deepseek):
> 你好 → 你好！我是你的 AI 软件开发助手... (真实回答) ✅
> 什么是 Docker → 真实回答 ✅
> 现在有什么项目 → 项目列表 ✅

Provider 缺失 (模拟):
> 你好 → AI 对话服务当前不可用。原因:...建议: doctor/init ✅ (stderr 干净)
> 现在有什么项目 → 项目列表 ✅ (零 LLM)
```

## 14-17. Git

```
5c4b4a4 feat(S10-078): provider error UX layering + wheel-mode doctor fix
c4aae75 fix(S10-078): chat failure detail to debug log — clean REPL stderr
git clean ✅ | HEAD == origin/main ✅ | 已 push ✅
```
