# Hermes 提示词 — Sprint 规格（确认阶段 next_action 全覆盖 + 会话分割线 + 删除指令）

> 用途: 三部门循环第 ② 步 — Hermes(CTO) 产出 Sprint 规格，供 Codex(工程) 实现
> 日期: 2026-08-24 | 前置: v1.1.24 · S10-103 CLI 输入健壮性已验收 · 全量基线 0 回归

---

【AI Factory Sprint 规格 — 确认阶段 next_action 全覆盖 + 会话分割线 + 删除指令】

## 角色
Hermes = CTO + 架构委员会。产出可执行 Sprint 规格，不写实现代码。

## 背景（Founder 实测 v1.1.24 暴露 3 个问题）
Founder 实测:
1. **确认阶段 next_action 表达全覆盖不足（🔴 严重）**: 
   - "可以，先出prd文档" → next_action=prd ✅（S10-102 覆盖）
   - **"产出份prd文档" / "生成PRD" / "出个html" / "出份功能清单" / "给我出份功能清单" → 全被当改名!**（名称变成整句话）
   - 根因: S10-102 确定性表只覆盖"可以,先出X"模式, 用户实际表达变体全漏;
     LLM 确认分类可能没被调用或这些输入未识别
2. **会话多轮回复无分割线（🟡 设计）**: 多轮对话输出连在一起, 看不出轮次边界;
   Founder 建议像 Hermes 一样有分割线
3. **删除功能（🟡 待确认）**: Founder 说"删除功能有问题, 不能正确删除" — 
   可能是确认阶段"删除/清空字段"指令（如"把核心功能删掉"）或终端退格; 需检查

## Sprint 目标（3 项）
1. **确认阶段 next_action 表达全覆盖（🔴）**: 
   - next_action 类型扩展: prd / feature_list(功能清单) / html / docs
   - 表达覆盖: LLM 分类(analyze_confirmation)为主 + 规则补全变体
     ("生成PRD"/"产出.*prd"/"出.*功能清单"/"功能清单"/"出.*html"/"文档"/"先出X")
   - 规则: 含"prd/清单/html/文档"且非明确改名的确认阶段输入 → next_action
2. **会话分割线（🟡）**: 每轮系统回复之间加分隔线（如 ───）, 多轮可分清
   - 格式对齐 Hermes 风格; banner/首轮不加; 纯装饰不影响逻辑
3. **删除/清空字段指令（🟡）**: 确认阶段"把X删掉/清空X/删除X" → 清空对应字段值 →
   重新进入确认（不是当改名）; 终端退格检查（readline 是否在用户环境生效, 若否 → 记录）

## 范围声明（§10.5.7.6）
- 本 Sprint 做: next_action 表达全覆盖 + 分割线 + 删除/清空字段指令
- 明确不做: 终端交互升级(prompt_toolkit, 已在 backlog) · 其他 CLI 命令行为
- 连带发现（进 backlog）: 功能清单(feature_list)产出引擎 · 更多 next_action 类型
- 波及面: conversation.py(确认分流/渲染) → 影响 会话输出/确认两路径 → 验证 会话+发现+CLI 测试

## 规格必须包含（8 项）
1. next_action 类型与表达覆盖表（LLM 分类 + 规则补全, 不穷举但覆盖常见变体）
2. LLM 确认分类触发（analyze_confirmation 在确定性表未命中时调用; 无 LLM → 规则）
3. 分割线设计（格式/位置/是否每轮/对齐 Hermes 风格）
4. 删除/清空字段指令（确认阶段 + 发现阶段都支持: "把X删掉/清空X" → 字段清空 → 重新追问/确认）
5. 宿主接线（next_action=feature_list/html 的宿主执行? 或本 Sprint 只返回信号）
6. 契约测试要点: 各表达变体 → next_action / 删除字段 → 清空 + 重确认 / 分割线出现在轮间 / 明确改名仍走 / 无LLM规则兜底 / 向后兼容
7. Codex 写 scope
8. 边界: 不改终端 prompt_toolkit · 不改字段收集语义

## 验收标准（Codex 完成后，你独立验证）
- "产出份prd文档" / "生成PRD" / "出个html" / "出份功能清单" → next_action 正确, 名称不被覆盖
- 明确改名（"改名叫X"）→ 仍走改名
- 每轮系统回复间有分割线（多轮可分清）
- "把核心功能删掉" → 字段清空 + 重新确认
- 无 LLM → 规则兜底（常见变体表）
- 全量回归 0 新增 + git clean
- 版本: 本 Sprint 完成后 bump v1.1.25

## 输出物
- 规格文档: `docs/sprint10/S10-104-confirm-next-separator-plan.md`
- 供 Codex 的指令摘要

## 关键纪律
1. 代码存在 ≠ 能力；自报告 ≠ 事实 — 独立验证（真实 LLM 各表达变体实测）
2. 禁止 stub/fake；无 LLM 诚实降级（规则变体表兜底）
3. 复用 analyze_confirmation / passthrough 机制 — 不重造
4. 向后兼容: 明确改名 / 纯 y/N 行为不变; 分割线纯装饰不影响逻辑
5. 版本: v1.1.24 → v1.1.25（patch+1）
