# R0 — AI Factory OS 真实生产入口审计

> Date: 2026-09-08 | 性质: 只读审计, 零代码改动 | 状态: 待执行
> 任务书: 让一个完全不了解 AI Factory OS 内部架构的用户, 通过自然语言把一件事真正做完。
> 本文件 = 给执行代理 (Hermes) 的 R0 第一刀指令。

## 0. 纪律 (必须遵守)

- **只审计, 不改任何代码、不 commit、不启动服务写数据。**
- 读完必读链再动手:
  1. `README.md`
  2. `docs/00-index/README.md`
  3. `docs/00-index/CURRENT_SYSTEM_TRUTH.md`
  4. `docs/audit/product-system-baseline/STEP10_DOMAIN_FREEZE.md`
  5. `docs/audits/2026-09-08-golden-path-completion.md`
- 每条结论必须给**代码/端点/入口证据 (文件+行号或路由)**, 禁止猜测。
- 不得因为"测试全绿"就把环节标 GREEN — 测试替身通过的环节一律标 YELLOW, 注明"仅 fake 验证"。
- 完成后 STOP, 等下一步指令。**不要开始修任何 P1。**

## 1. 背景

产品已收敛为 AI Factory OS (见 `e4eaa968` 文档校准)。
当前阶段唯一要回答的问题:

> 我能不能打开 `factory`, 像使用 Codex/Hermes CLI 一样, 用自然语言让它把一件事真正做完?

本审计回答"现在离这个状态差在哪", 不回答"还要造什么功能"。

## 2. 六个问题

### Q1. factory CLI 当前真正进入哪个 Runtime?
- 入口: `pyproject.toml` console_scripts → `factory_console.cli_factory:main` 之后实际调用链。
- 它走 `conversation_os` (legacy), 还是新 Conversation Application (`conversation_app` / `golden_path`), 还是直接调底层?

### Q2. API 当前真正进入哪个 Runtime?
- `/api/conversations/...` 新端点走 `ConversationApplicationService` 的完整链路是什么?
- 旧 `conv_*` 端点还活着吗? 它们和新域是否共享同一个 Domain/Runtime?

### Q3. WebUI 当前真正进入哪个 Runtime?
- 前端 (`factory-console/web/frontend`) 现在调哪些 API? 聊天/输入框是否接到新 Conversation 域?
- 是否存在 "WebUI 走 legacy、CLI 走新域" 的双轨?

### Q4. CLI / API / WebUI 是否最终进入同一个 Application → Domain → Runtime?
- 给出三入口各自的调用链终点, 指出分叉点在哪一层 (表现层 / 应用层 / 域层)。
- 明确回答: 现在是否存在三套业务逻辑, 还是只有一套?

### Q5. factory CLI 是否已经能像 Codex/Hermes CLI 一样以自然语言为主要交互?
- 现在 `factory` 裸启动是什么? REPL / OS Shell, 还是子命令分发器?
- 从 "我想做一个飞机大战游戏" 这句话到进入 Conversation 域, 现在 CLI 需要用户额外输入什么内部命令?

### Q6. 从 CLI 跑一个真实软件任务的闭环断点
- 链路: Idea → Understanding → PRD → Approval → Plan → Approval → Task Tree → Execute → Verify → Artifact → Evidence。
- 每一环标注: 真实代码证据 / 测试替身证据 / 缺失。
- 特别指出: 真实 LLM 解释器 (`llm_semantic_interpreter` → `llm_raw`) 当前在 CLI 路径是否可达;
  缺什么 (环境变量 / 装配 / 接线)?

## 3. 输出

- 落盘: `docs/audits/2026-09-08-r0-entry-audit/00-R0-AUDIT.md`
- 结论三色标注:
  - GREEN — 已统一 (真实路径, 非 fake)
  - YELLOW — 分叉但可收敛 (或仅 fake/测试替身验证)
  - RED — 多套逻辑 / 断链 / 真实路径不可达
- 报告末尾给一张三入口 × 13 维事实对比表 (Project / Conversation / Intent / Product Understanding / PRD / Plan / Task Tree / NodeRun / Agent-Model / Artifact / Verification / Evidence / Audit), 标出每格证据来源。
