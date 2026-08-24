# Hermes 提示词 — Sprint 规格（DiscoverySession 同步 LLM 化）

> 用途: 三部门循环第 ② 步 — Hermes(CTO) 产出 Sprint 规格，供 Codex(工程) 实现
> 日期: 2026-08-24 | 前置: v1.1.20 · S10-099 发现 LLM 深度介入已验收（DiscoveryIntentAnalyzer + conversation 集成）· 全量基线 0 回归

---

【AI Factory Sprint 规格 — DiscoverySession 同步 LLM 化】

## 角色
Hermes = CTO + 架构委员会。产出可执行 Sprint 规格，不写实现代码。

## 背景（S10-099 边界外遗留）
- S10-099 已把 conversation 产品发现 LLM 化（DiscoveryIntentAnalyzer: 意图优先级/
  结构化提取/智能追问/主动分析/理解摘要）— 验收通过
- **但 DiscoverySession（S10-065, "我想做X/开始做X" 路径）仍是纯规则逐字段追问**
  （problem → user → core_features → usage_scenarios → mvp_scope →
  non_functional_requirements）— 无 LLM
- 两条发现路径不一致: conversation 智能, DiscoverySession 机械

## Sprint 目标
**DiscoverySession 同步 LLM 化** — 复用 S10-099 的 DiscoveryIntentAnalyzer 能力，
让"开始做X"路径也: LLM 一次产出 + 智能追问 + 理解摘要 + 主动分析；无 LLM 规则兜底。

## 必须包含（参考 S10-099 模式）
1. **复用 vs 扩展**: DiscoveryIntentAnalyzer 是否可直接用于 DiscoverySession？
   （两路径字段集不同: DiscoverySession 多 usage_scenarios/mvp_scope/nfr —
   需扩展 analyzer 或 DiscoverySession 适配）
2. **LLM 一次产出**: "开始做个记账App" → LLM 理解 → 多字段一次填（不逐字段问）
3. **智能追问**: 缺字段 → 带理由追问（"为什么还问: ..."）
4. **理解摘要**: 确认前展示 "我理解你要做X, 给Y用, 核心是A/B/C"
5. **无 LLM 规则兜底**: 现有逐字段流程零变化（诚实降级）
6. **两路径一致性**: conversation 产品发现 vs DiscoverySession 行为对齐
   （避免两套心智模型）

## 规格必须包含（8 项）
1. DiscoverySession LLM 化架构（复用 analyzer vs 扩展 vs 独立）
2. LLM 提取字段集（DiscoverySession 的 7 字段 vs analyzer 的 5 字段 — 映射/扩展）
3. 智能追问集成点（process_user_input 改造, 状态机保留为兜底）
4. 理解摘要展示（确认前, 对齐 S10-099）
5. 无 LLM 兜底（现有逐字段零变化）
6. 契约测试要点: LLM 一次产出/智能追问/无LLM回退/摘要/两路径一致性/向后兼容
7. Codex 写 scope（最小改动, 复用 discovery_intelligence.py）
8. 边界: 不改 conversation 产品发现（已 LLM 化）· 不做多语言

## 验收标准（Codex 完成后，你独立验证）
- "开始做个记账App" → LLM 一次产出（非逐字段问）+ 智能追问 + 摘要
- 无 LLM → 现有逐字段零变化
- 两路径行为一致（conversation vs DiscoverySession 摘要格式对齐）
- 全量回归 0 新增 + git clean
- 版本: 本 Sprint 完成后 bump v1.1.21

## 输出物
- 规格文档: `docs/sprint10/S10-100-discovery-session-llm-plan.md`
- 供 Codex 的指令摘要

## 关键纪律
1. 代码存在 ≠ 能力；自报告 ≠ 事实 — 独立验证（真实 LLM "开始做X" 测试）
2. 禁止 stub/fake；无 LLM 诚实降级（规则逐字段兜底, 不伪造）
3. 复用 discovery_intelligence.py / conversation 模式 — 不重造
4. 向后兼容: 无 LLM 时现有 DiscoverySession 流程零变化
5. 版本: v1.1.20 → v1.1.21（patch+1）
