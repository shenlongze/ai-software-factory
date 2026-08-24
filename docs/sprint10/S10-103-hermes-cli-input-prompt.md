# Hermes 提示词 — Sprint 规格（发现流程命令分流 + CLI 输入健壮性）

> 用途: 三部门循环第 ② 步 — Hermes(CTO) 产出 Sprint 规格，供 Codex(工程) 实现
> 日期: 2026-08-24 | 前置: v1.1.23 · S10-102 确认分流已验收 · 全量基线 0 回归

---

【AI Factory Sprint 规格 — 发现流程命令分流 + CLI 输入健壮性】

## 角色
Hermes = CTO + 架构委员会。产出可执行 Sprint 规格，不写实现代码。

## 背景（CLI 全面检查发现的问题）
Codex 全面检查 CLI 发现:
🔴 **发现流程命令被当字段（严重逻辑 bug）**:
  - 发现流程中输入 "/status" / "/help" → problem 被填成 '/status'（slash 命令被当产品描述）
  - 输入 "exit" / "quit" → 被当字段, 推进到确认（想退出却成了产品定义）
  - 根因: handle_product_answer 只处理 取消/整理/逃生, 没处理 slash 命令和 exit
  - 用户"输入错误, 删除, 可能乱"的逻辑根源之一（输入被错当字段, 非终端乱）
🟡 CLI 命令层小问题:
  - project 无子命令提示漏 status（"project 需要子命令 (create / list / rename)" 实际支持 status）
  - create project 不强制 --name（会建"未命名项目"）
✅ 已排除: 模型层异常输入 12/12 不崩 · 取消→重来正常 · argparse 错误正常 · 终端 readline 可用

## Sprint 目标（2 项）
1. **发现流程命令分流（🔴 核心）**: 产品发现/确认流程中
   - "/" 开头（slash 命令）→ passthrough 交回命令处理（不当字段）
   - "exit"/"quit" → 触发退出（或"发现中, 确认退出?"）
   - 与控制指令（取消/整理）并列优先级（在字段收集之前）
2. **CLI 小修复（🟡）**: project 无子命令提示补 status · create project 校验 --name 非空

## 范围声明（§10.5.7.6）
- 本 Sprint 做: 发现流程 slash/exit 分流 + project 提示补 status + create project --name 校验
- 明确不做: 终端交互升级（prompt_toolkit, 记录进 backlog）· 其他 CLI 命令行为
- 连带发现（进 backlog 不顺手做）: prompt_toolkit 交互增强 · 会话历史持久化
- 波及面预期: conversation.py（控制短语）→ 影响 发现/确认两路径 → 验证 会话+发现测试

## 规格必须包含（8 项）
1. 命令分流优先级（slash > exit/quit > 控制短语 > 字段收集）
2. slash passthrough 机制（conversation 返回 passthrough 信号 → 宿主处理, 复用现有 passthrough 语义）
3. exit/quit 在发现中的处理（退出 vs 提示确认; 与主循环 EXIT_COMMANDS 一致）
4. project 提示补 status（cli_factory.project_cmd）
5. create project --name 校验（cli_factory.create_cmd, 缺失 → rc 2 明确提示）
6. 契约测试要点: 发现中 /status 不当字段 / exit 触发退出 / 确认中 slash 分流 / project 提示含 status / create 无 name 报错 / 向后兼容（字段收集不受影响）
7. Codex 写 scope（最小改动）
8. 边界: 不改终端交互 · 不改产品发现字段逻辑（只加命令分流）

## 验收标准（Codex 完成后，你独立验证）
- 发现流程 "/status" → 命令处理（显示状态, 不当字段）· "exit" → 退出（或确认提示）
- 确认流程 slash 同样分流
- project 无子命令提示含 status
- create project 无 --name → rc 2 明确提示
- 字段收集正常（普通回答仍填字段）
- 全量回归 0 新增 + git clean
- 版本: 本 Sprint 完成后 bump v1.1.24

## 输出物
- 规格文档: `docs/sprint10/S10-103-cli-input-plan.md`
- 供 Codex 的指令摘要

## 关键纪律
1. 代码存在 ≠ 能力；自报告 ≠ 事实 — 独立验证（发现流程 slash/exit 实测）
2. 禁止 stub/fake；无 LLM 诚实降级（命令分流是确定性, 不依赖 LLM）
3. 复用现有 passthrough / EXIT_COMMANDS 机制 — 不重造
4. 向后兼容: 普通字段回答不受影响
5. 版本: v1.1.23 → v1.1.24（patch+1）
