# Hermes CLI 设计 vs AI Factory OS 会话层：差在哪、为什么差

> Founder 2026-09-26 问：「Hermes 的 CLI 全流程是如何设计的？为什么 AI Factory OS 差这么多，有什么不同」
> 证据来源：Hermes = 官方 skill/文档原文（`hermes-agent` skill，Docs: https://hermes-agent.nousresearch.com/docs/）✓
> AI Factory OS = 本仓库代码（`apps/cli/domains/{chat,welcome}.py`，逐条读过 ✓）
> 纪律：两边都**引原文/代码**，不凭印象 ✗

---

## 一句话结论

**不是"能力差"，是"范式差 + 定位错配"** ✓

- Hermes 的核心是 **"模型用结构化工具干任意事"**（tool calling ✓）
- AI Factory OS 的会话层是 **"解析模型写的文本行 ⇒ 转发给自家命令"**（文本协议 ✓）
- 而 AI Factory OS 又把**"会话唯一入口"**定为产品核心 ⇒ 最薄的一层被放在最关键的位置 ✗

**但 AI Factory OS 有 Hermes 没有的东西**：任务树拆解 · 多 agent 派工 · 公司/部门/项目归属 ·
全链审计与经验回流 · 需求→PRD→架构→拆解的门禁。这些是它真正对标 SAP 的部分 ✓。

---

## 一、逐维度对比（每条都有出处 ✓）

| 维度 | Hermes（官方原文） | AI Factory OS 会话层（代码现状） |
|---|---|---|
| **模型↔运行时** | **结构化工具调用**：`run_conversation()` 调 LLM（OpenAI 格式 **tool schemas**）⇒ `tool_calls` 由 `handle_function_call()` 派发 ⇒ 结果回灌 ⇒ 循环 ✓ | **文本行协议**：模型输出里写 `RUN: <命令>` / `SESSION: …` ⇒ 用字符串切分解析 ✓ 脆 ✗（实测: `RUN: SESSION:` 就漏成命令 ✓） |
| **动作面** | 约 30 个工具集（terminal / file / web / browser / code_exec / vision / delegation / cron / kanban…）+ 自动发现 + `check_fn` 按依赖开启 ✓ | 约 50 个 `factory` 子命令 + `sh <cmd>`（须批准 ✓）；**没有"工具注册表 → 模型可见"的机制** ✗ |
| **权限模型** | **三档**：`approvals.mode = manual / smart / off` ✓；`smart` = 辅助模型判低风险**自动放行**、高风险才问 ✓；`--yolo` 单次绕过 ✓ | 原先**全要点头** ✗（我今天才加"只读命令白名单" ✓）；没有 smart 档、没有风险分级 ✗ |
| **环境事实** | `agent/prompt_builder.py::build_environment_hints()` 主动注入 OS / `$HOME` / cwd / 终端后端 / shell ✓（远端后端还会抑制宿主信息 ✓） | 只注入"会话归属 X" ✗（今天我补了**仓库真路径**+需求原话 ✓）；没有 cwd/系统/工具清单注入 ✗ |
| **会话状态** | SQLite（`state.db`）+ FTS5 全文检索 ✓；子命令 list / browse / export / rename / delete / prune / stats ✓ | JSON 文件（`conversations/*.json`）+ 我做的 `/project` 归属 ✓；无检索/无压缩/无分支 ✗ |
| **上下文管理** | 自动压缩（`compression.threshold` 0.5 ⇒ 压到 0.2 ✓）+ **禁改缓存**纪律 ✓ | 无 ✓（长会话必然爆 ✗） |
| **可打断/流式** | 真流式 + 忙指示 + `/stop`（杀后台进程）+ `/queue` `/steer` `/background` ✓ | 五区渲染 + 忙指示 + 可打断本轮 ✓（**这块照 Hermes 抄得不错** ✓） |
| **多 agent** | `delegate_task`（leaf/orchestrator、并行上限、深度上限）+ **kanban 队列**（含**回收陈旧认领**、`failure_limit` 自动 block、dispatcher 内嵌 gateway）✓ | **任务树 + 调度器 + 派工 + CAS 认领 + runlock + 卡死执行回收** ✓✓（**这块 AI Factory OS 更强** ✓ 公司/项目/角色化更强 ✓） |
| **自我改进** | skills（agent 自己写/改/归档 ✓）+ memory（跨会话 ✓）+ curator（后台维护 ✓） | 有"经验库/知识/事实" ✓ 但**不回灌到会话** ✗（会话每次从零猜 ✓） |
| **命令发现** | 单一注册表 `hermes_cli/commands.py` ⇒ 帮助/补全/菜单全派生 ✓ | 有命令表 ✓ 但**会话不知道有哪些命令** ✗（提示词里没有清单 ⇒ 只能猜 ✓） |

---

## 二、你实测遇到的每个坑，对应哪条差异

| 你看到的现象 | 对应的差异 |
|---|---|
| 「进入到项目」进了别的项目 | 环境事实缺失（不知道在哪个项目/有哪些项目）+ 没有"意图→动作"映射 ⇒ 模型猜 ✗ |
| 「我没有落地权 / 你点头我就跑」 | 动作面不明确 + 权限只有"全问"一档 ⇒ 模型不敢请求 ⇒ 退化成商量 ✗ |
| `RUN: SESSION:` 被当命令发 | 文本协议 + 解析只看行首 ⇒ 漏 ✗（结构化工具调用不会有这种问题 ✓） |
| 失败却报「执行完成（改动已落盘）」 | 结果判定靠"退出码 + 抓错字样" ⇒ 不可靠 ✗（工具调用返回的就是结构化结果 ✓） |
| 编「45 个自检脚本在根目录」 | 环境事实缺失 ⇒ 它手里没有"仓库里有什么" ⇒ 只能编 ✗ |
| 要你告诉它仓库路径 | 环境事实缺失（cwd/仓库路径没注入 ✓） |

---

## 三、为什么"差这么多"（诚实原因，不甩锅）

1. **定位不同 ⇒ 深度不同** ✓
   Hermes 的全部价值都压在"模型 + 工具"这条链上 ⇒ 它的会话层是**主战场** ✓
   AI Factory OS 的价值压在"组织 + 编排 + 审计"上 ⇒ 会话层被当成**入口薄壳** ✗
2. **范式落后一代** ✓
   Hermes（以及 Claude Code / Codex 同类）用**结构化工具调用** ✓；
   AI Factory OS 用**文本行协议** ✗ ⇒ 先天脆、能力窄、意图全靠模型即兴 ✓
3. **但我定的"会话唯一入口"把薄壳放在了门面位置** ✗
   ⇒ 用户 90% 的体感来自它 ✓ ⇒ 薄壳撑不住门面 = 你现在的不满 ✓（这是**战略错配** ✓）

---

## 四、可迁移的清单（按性价比，都是 Hermes 已验证有效的 ✓）

```
 甲) 动作面结构化
     把"会话能做什么"从文本行改成**动作清单**（意图 → 动作 → 参数 schema）✓
     并且**从命令注册表自动生成**（与 `_top_command_names()` 同源 ✓ 不手抄 ✗）
 乙) 权限分档（照 Hermes 三档）
     只读 ⇒ 直接跑 ✓（我已做一半 ✓）· 中风险 ⇒ 辅助模型判 ⇒ 自动放行 ✓ · 高风险 ⇒ 必问 ✓
 丙) 环境事实注入（照 prompt_builder）
     cwd / 项目 / 仓库路径 / 任务树 id / 命令清单 / 上一步结果 ⇒ 结构化喂给它 ✓
 丁) 结果结构化
     命令返回 {ok, code, stdout, stderr} ⇒ 会话按 ok 判成功失败 ✓（治"假成功"✗）
 戊) 经验回流（照 skills + memory）
     把"这次怎么做的"写回经验库 ⇒ 下次会话带着它开局 ✓
 己) 上下文压缩（照 compression）
     长会话自动压 ⇒ 不爆 ✓
 庚) 会话可检索/可续（照 sessions + FTS5）
     现在 572 个会话不可搜 ✓
```

---

## 五、边界说明（避免误读）

- Hermes 的 CLI 与 AI Factory OS 的会话层**不是同类产品**：前者是通用 agent 运行时，后者是企业 OS 的入口 ✓
- AI Factory OS 在**任务树 / 派工 / 组织归属 / 审计 / 需求门禁**上**胜过** Hermes ✓（Hermes 没有这些 ✓）
- 本文只比"会话层为什么体感差" ✓ 不构成"AI Factory OS 整体不如 Hermes"的结论 ✗
