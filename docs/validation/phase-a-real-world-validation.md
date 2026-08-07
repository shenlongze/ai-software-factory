# Phase A+ Real World Validation — 验证报告

- **日期**: 2026-08-07
- **验证工程师**: Hermes 子代理 (验证角色)
- **项目**: AI Software Factory (`/Users/Shared/work/ai-software-factory`)
- **约束**: 不新增架构 / 不扩展范围 / 不修改 factory-exec 核心 / 不触碰 markpad 生产目录
- **结果文件**: 本报告 + `run-data/phase-a-results.json` (结构化) + `run-data/factory/` (事件/产物)

---

## 0. 结论摘要 (TL;DR)

| 维度 | 结果 |
|---|---|
| 真实测试项目 | ✅ markpad `lib/editor/` 子模块 (30 文件 / 8071 行) + 1 个真实 Bug 任务 (自然语言, 禁答案) |
| 真实 Provider | ⛔ **BLOCKED** — 无 `ANTHROPIC_API_KEY` (env/rc/.env 均无), 诚实记录, 未假装成功 |
| 全链路 (mock) | ✅ org → hire → run → report → 审批 → apply 全通, 事件链完整 |
| Sandbox | ✅ 生产目录**逐字节零修改** (sha256 前后一致) / patch-only / 未批 apply 硬拒绝 |
| Agent 能力 (五维) | ⚠️ 链路与门禁 4-5 分; 智能质量维度 **待 key 重测** (mock 标注) |
| Human Experience | ⚠️ 骨架可用, 但 CLI 缺 `approval request` 命令 → 纯 CLI 人工流程**无法闭环** |
| 成功标准 (每日使用) | ❌ **现在不会** — 真实交付质量未验证 + Agent 无读文件能力 + 流程缺口 |
| Phase B | ⏸ **有条件进入**: 先解锁 key + 修 3 个阻塞缺口 (见 §7) |

---

## 1. 真实测试项目定义 (禁人工答案)

### 1.1 项目规模

| 项 | 值 |
|---|---|
| 模块 | `markpad/lib/editor/` (Flutter Markdown 编辑器子模块) |
| 文件数 | 30 个 `.dart` |
| 行数 | 8,071 (lib 全量 75 文件 / 26,741 行; test 84 文件 / 19,139 行) |
| 复本 | `docs/validation/run-data/projects/markpad-editor/` (git 仓库, 基线提交 `eb39cd2`) |

> 生产目录 `/Users/Shared/work/markpad/lib/editor/` 全程只读 — 验证只对复本操作。

### 1.2 任务: T-MKP-001 (真实缺陷, 人工验证但答案不进提示词)

**缺陷本体 (验证工程师从代码阅读确证, 不写入任务描述)**:
`lib/editor/services/search_service.dart:100` — `SearchService.replaceCurrent(void Function(String) onContentChanged)` 直接把替换词作为**整篇文档**回调 `onContentChanged(_replaceQuery)`, 会把用户文档全部内容替换成替换词, 而非只替换当前匹配。该方法缺少全文参数, 结构上不可能做单匹配替换 (对照 `replaceAll` 与页面层 `editor_page.dart:1832 _replaceCurrent` 的正确实现, 均用 `replaceRange`)。生产文件该处 mtime 2026-07-28, 为历史遗留缺陷。

**任务描述 (喂给 Agent 的原文, 不含答案)**:

> MarkPad 编辑器的查找/替换面板中,「替换当前匹配项」(Replace current match) 功能行为异常: 用户点击替换按钮后, 整个文档内容被替换成了替换文本, 而不是只替换当前选中的那一个匹配。请定位并修复此缺陷。修复后, 单次替换应只改变当前匹配位置对应的文本, 文档其余部分原样保留。

**验收标准 (喂给 Agent)**:

> 1) 单次替换只作用于当前匹配范围, 文档其余部分不变; 2) 与全部替换 (replaceAll) 的 offset 保护语义对齐; 3) 最小改动, 不重构无关代码; 4) 保持现有代码风格与注释语言。

**验收判定 (验证方)**:
1. 修复后方法签名接收全文参数 + 回调 (镜像页面层正确实现)
2. 方法体对当前匹配范围 `replaceRange`, 无整体替换反模式
3. 补丁为合法 unified diff, 沙箱 `git apply` 可应用
4. 沙箱验证命令 (静态语义检查) 通过 — 见 `tools/verify_search_fix.py`

> **禁答案说明**: 缺陷位置/修复方案只存在于本报告与验证夹具中; 任务提示词仅含自然语言需求。mock 返回的修复补丁是**测试夹具** (确定性演示), 不构成对 LLM 盲测的污染 — 真实盲测需 key 解锁后重跑 (见 §3)。

---

## 2. 真实 Provider 验证 (诚实: BLOCKED)

### 2.1 Key 检查

| 来源 | 结果 |
|---|---|
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` (env) | 未设置 |
| `~/.zshrc` `~/.bashrc` `~/.zprofile` `~/.profile` | 无 |
| 工厂/markpad `.env` | 不存在 |
| `env` 全量扫描 (api_key/anthropic/openai) | 无 |

### 2.2 真实调用尝试 (失败路径演示, 未伪造)

用**真实** `AnthropicProvider` (httpx, `api.anthropic.com/v1/messages`, model `claude-sonnet-4-5`) 发起调用:

```
anthropic api key missing: ANTHROPIC_API_KEY 未设置
(export ANTHROPIC_API_KEY=... 或构造 AnthropicProvider(api_key=...))
```

| 记录项 | 值 |
|---|---|
| Status | **BLOCKED** (ProviderError, 响亮不静默) |
| Model (配置) | `claude-sonnet-4-5` |
| Endpoint | `https://api.anthropic.com/v1/messages` |
| Tokens | **无记录** (调用未发生) |
| Cost (USD) | **无记录** |
| Latency | 0.0s (未发起网络请求) |
| Success | false |

### 2.3 链路演示 (mock, 标注非真实)

因 BLOCKED, 全链路用 mock provider (FakeProvider 风格夹具) 演示 — **usage 为模拟值, 非计费数据**:

```
usage = {'input_tokens': 1842, 'output_tokens': 268, 'estimated_cost_usd': 0.009546}
exec run duration = 0.25s (mock 延迟 0.05s, 非真实 LLM 延迟)
```

> 真实 model/token/cost/latency 记录**待用户提供 key 后重跑** (driver 已就绪, 换 `--provider anthropic` + 真实环境变量即可)。

---

## 3. Developer Agent 能力评估 (五维, mock 链路 + 诚实标注)

评分口径: **链路/门禁维度为实测真值; 智能维度基于 mock 夹具 + 框架结构分析, 真实质量标注「待 key」**。

| 维度 | 分 (1-5) | 证据 / 说明 |
|---|---|---|
| 1. 理解任务 | **3/5 (链路) / 待 key (质量)** | Prompt 组装真实: objective/requirement/规范/项目上下文完整进入 Provider 请求; 输出格式契约 (摘要 + `<patch>`) 被正确解析。但 mock 内容为夹具, LLM 真实理解未验证 |
| 2. 代码定位 | **2/5** ⚠️ 结构性短板 | **项目上下文只有文件清单 (前 60 个文件名), 无文件内容**; DeveloperAgent 无读文件工具。真实 LLM 凭文件名无法定位/修改不熟悉代码库 — 这是真实场景最大阻塞 (见 §7-3) |
| 3. 修改质量 | **3/5 (夹具质量) / 待 key (LLM 质量)** | 夹具补丁与页面层参照实现一致 (签名 + offset 保护 + replaceRange), 25 行 diff 沙箱 `git apply` 一次通过, 括号配平/风格合规。真实 LLM 产出质量未验证 |
| 4. 测试能力 | **2/5** ⚠️ | 验证框架真实可用: 语法检查 (ast) + `--test-cmd` 自定义命令在沙箱内执行, test_result 产物 + 报告明示 PASS。但沙箱只有 lib/editor 子目录 (无 pubspec), 无法跑 `dart test`; 验证器是静态语义检查而非真实测试执行 |
| 5. 错误恢复 | **2/5** ⚠️ | 失败安全真实: 无 key → failed + 清晰错误不崩溃; 未批 apply → 硬拒绝; 重复 apply → 幂等拒绝; 全程 org.execution.* 事件链。但 MVP 为单次生成, **无失败重试/修复循环** (测试 FAIL 不自动迭代) |

**综合**: 执行骨架 (沙箱/审批/审计/产物) 是真实可用的 4-5 分水准; **Agent 智能核心 (定位/修改/测试/恢复) 受限于无读文件能力 + 单发无重试 + 无真实 LLM**, 为 2-3 分且标注「待 key」。

---

## 4. Sandbox 验证 (实测证据)

### 4.1 生产目录零修改 (逐字节)

- 全链路 (run + 审批 + apply) 前后, 生产目录 `lib/editor/` 字节清单 sha256:
  - before = `bb130e91d486f4598e4f152852570aae717e3b31cc03341edb71ea940327b13e`
  - after  = `bb130e91d486f4598e4f152852570aae717e3b31cc03341edb71ea940327b13e`
  - **完全一致** ✅
- 附加佐证: 生产 `search_service.dart` `git diff` 为空, mtime 2026-07-28 (早于本会话); markpad 仓库其余 dirty 状态为会话前已有 (活跃开发仓库), 与本验证无关
- 直接证明: 对**生产目录**建沙箱 → 在沙箱副本内应用同一 patch → 沙箱 diff 含修复, 生产目录同时刻字节不变 ✅

### 4.2 Patch-only (Agent 唯一可写空间)

- Agent 产出 = patch 文本 (统一 diff), 落盘为 `patches/EXS-*.patch` 产物
- 沙箱副本位于系统临时目录 (`exec-sandbox-*/project`), 与生产隔离

### 4.3 审批硬门 (未批 apply 硬拒绝)

```
$ exec approval apply --id APR-258788b1      # 未审批
error: patch apply requires approved approval (current: pending) — 应用 patch 前必批 (exit=1)
$ exec approval approve --id APR-258788b1 --by alice
审批 approved
$ exec approval apply --id APR-258788b1
✔ patch 已应用 (diff 25 行)
$ exec approval apply --id APR-258788b1      # 重复
error: patch already applied: APR-258788b1 (applied_at=...) (exit=1)   # 幂等 ✅
```

### 4.4 事件链 (审计完整)

```
org.execution.requested(20) → started(21) → completed(22) → viewed(24,25) → approved(26) → applied(27)
org.company.created(1) → role.created ×5 → authority.granted ×8 → employee.joined(16) → role_assigned(17) → capability_added(18,19)
```

---

## 5. Human Experience 模拟 (普通开发者视角)

### 5.1 步骤与耗时 (实测, mock)

| # | 动作 | 命令 | 耗时 | 结果 |
|---|---|---|---|---|
| 1 | 建公司 | `org company create --name ... --template solo` | 即时 | C-755f91e1 |
| 2 | 雇 Developer | `org employee hire --role developer --capabilities python,dart --id dev-1` | 即时 | dev-1 |
| 3 | 提交 Bug 任务 | `exec run --project <复本> --task T-MKP-001 --objective ... --employee dev-1 --provider mock` | 0.25s | success |
| 4 | 查看结果 | `exec status --id EXS-3e4af931` | 即时 | success + 3 产物 |
| 5 | 提交审批 | **无 CLI 命令** (驱动脚本程序化调用 `ApprovalGate.request`) | — | ⚠️ 缺口 |
| 6 | 审批 | `exec approval approve --id APR-... --by alice` | 即时 | approved |
| 7 | 应用 | `exec approval apply --id APR-...` | 即时 | 25 行已应用 |
| 8 | 复核 | 副本 `git diff` + verifier | 即时 | 修复就位 |

人工步骤 5-6 步 (若 #5 有 CLI), 全程 < 1 秒计算耗时; 真实 LLM 耗时待 key。

### 5.2 困惑点 (哪里会卡住)

1. **【硬阻塞】无 `approval request` CLI 命令** — `exec run` 不自动创建审批记录, `ApprovalGate.request()` 只在编排层/程序化调用。按 CLI help (`approval approve|deny|apply|list`) 操作的开发者**无法发起审批**, 流程在 #5 卡死。
2. **审批目标默认 = 请求的 `project_dir`** — 若开发者把 `--project` 指向自己的真实仓库, approve 后 `git apply` 直接改工作区 (未提交)。设计如此 (可审计), 但需文档警示: 先看 report + patch 产物再批。
3. **项目上下文只有文件名** — 开发者会期望 Agent 能看代码, 实际 MVP 提示词只含文件清单; 真实任务定位依赖 LLM 已有知识。
4. `exec status` 输出精简, 报告需打开产物文件路径阅读 (可接受, 但非交互式)。
5. mock provider 不在默认注册表 — 普通用户无法 `--provider mock` (仅测试注入), 无 key 时只能得到 BLOCKED 错误, 属预期。

### 5.3 整体体验

骨架流畅、门禁直观 (拒绝/幂等错误信息明确)、审计完整。**但 #5 流程缺口 + 无 key + 无读文件能力** 使「普通开发者完成一次真实任务」尚不可行。

---

## 6. 成功标准评估 (愿否每日使用 — 诚实)

**结论: ❌ 现在不愿意** (框架可信, 交付不可用)。

### 愿意使用的理由 (真实)
- 沙箱/审批/审计闭环是真金白银: 生产目录逐字节零修改有 sha256 证据, 未批 apply 硬拒绝实测通过
- 事件链完整, 全流程可追溯
- 报告产物结构清晰 (做了什么/为什么/结果/验证/成本/耗时), 审批输入友好
- 命令简洁 (每步 1 条), 错误信息响亮明确

### 阻止使用的理由 (真实)
1. **真实交付质量未验证** — 无 key, LLM 产出为零实测 (mock 夹具不算数)
2. **Agent 无读文件能力** — 真实项目 (26k 行) 凭文件名清单无法可靠修 Bug
3. **人工流程缺一环** — `approval request` 无 CLI, 纯 CLI 无法闭环
4. **测试能力弱** — 沙箱无包上下文, 只能静态检查, 跑不了真实 Dart/Flutter 测试
5. **单发无重试** — 测试失败无修复循环, 真实场景一次成功的概率存疑

---

## 7. 下一阶段建议 (Phase B — 有条件进入)

**判定: 有条件进入。** 数据依据: 骨架验证全部通过 (安全/审计/门禁 = 生产级), 但 Agent 智能核心 3/5 维度 ≤2 分且 BLOCKED。Phase B 若继续在「无 key + 无读文件」下扩展, 会放大未验证的风险。

| 优先级 | 建议 | 理由 (数据) |
|---|---|---|
| P0 | **用户提供 `ANTHROPIC_API_KEY`**, 用本 driver 重跑 (真实 model/token/cost/latency + 五维重评) | BLOCKED 项唯一解锁手段; 真实质量是 Phase B 是否值得的前提 |
| P0 | CLI 补 `exec approval request --result-id` (或 run 后自动 request) | §5.2-1 硬阻塞, 人工流程闭环的必要条件 |
| P0 | Developer Agent 增加沙箱内**读文件**能力 (注入文件内容 / 工具调用) | §3-2 结构性短板, 真实任务不可用的根因 |
| P1 | 验证器扩展: 沙箱复制整个仓库 (含 pubspec) 或支持语言化 test 命令模板, 让 Dart 测试可执行 | §3-4; 静态检查 ≠ 测试 |
| P1 | 引入失败重试循环 (test FAIL → 反馈 → 重新生成, 上限 N 次) | §3-5; 单发成功率不可靠 |
| P2 | 审批 apply 增加 `--dry-run` 预览 + 应用前 diff 强制展示 | 5.2-2 安全体验 |
| P2 | 报告交互化 (CLI 直接展示 diff 摘要而非文件路径) | 5.2-4 |

---

## 8. 发现的问题清单 / BLOCKED 项

| # | 类型 | 问题 | 严重度 |
|---|---|---|---|
| 1 | **BLOCKED** | 无 `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` (env/rc/.env 全无) — 真实 Provider 调用无法进行, token/cost/latency 无记录 | 高 |
| 2 | 缺口 | `exec run` 后无 CLI 途径创建审批记录 (`approval request` 缺失), 人工流程不可闭环 | 高 |
| 3 | 设计限制 | Developer Agent 无读文件能力, 项目上下文仅文件清单 (前 60) | 高 |
| 4 | 设计限制 | 沙箱子目录副本无包上下文, 无法执行项目真实测试 (Dart/Flutter) | 中 |
| 5 | 设计限制 | 单次生成无重试循环 | 中 |
| 6 | 发现 (非缺陷) | markpad 生产仓库存在大量会话前未提交改动 (活跃开发), 与本次验证无关; 目标文件 `search_service.dart` 零 diff + mtime 佐证零修改 | — |

---

## 9. 复现方法

```bash
cd /Users/Shared/work/ai-software-factory
.venv/bin/python docs/validation/tools/phase_a_validation.py
# 产物: docs/validation/run-data/phase-a-results.json + run-data/factory/{exec,org,factory.db}
# 沙箱内验证器: docs/validation/tools/verify_search_fix.py
# 解锁真实 Provider: export ANTHROPIC_API_KEY=... 后改 driver 的 provider 注入为 anthropic
```

- 约束遵守: factory-exec/factory-org 核心零修改 (仅运行时 monkeypatch 装配点注入 mock, 为代码注释声明的测试机制); markpad 生产目录零写入 (sha256 证据); 测试未删除。
