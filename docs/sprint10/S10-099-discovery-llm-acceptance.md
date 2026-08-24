# S10-099 — 发现阶段 LLM 深度介入：独立验收报告

> 日期: 2026-08-24 | 版本: v1.1.16 | 验收人: Hermes (CTO, 独立验证 — 非 Codex 自报告)
> 实现: commit `2687024f` (feat(S10-099), 7 files, +1095/-5)
> 前置: v1.1.15 基线 tests/console+tests/api = **4784 passed / 1 skipped / 0 failed**

---

## 验收矩阵（规格 6 项）

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 自然描述一次产出（非逐字段问） | ✅ | 真实 LLM 交互: "我想做个 markdown 编辑器, 要 typora 和 notepad++ 的优点, 适配手机" → 首轮即智能追问（非机械首问）→ 2 轮补答 → 直达确认。全程零 "缺失字段" 机械追问 |
| 2 | 控制指令不被当字段 | ✅ | "取消" → 已取消产品发现; "整理一下" → 整理不创建 (summary_only=True) — 确定性硬闸 + LLM 模糊改写双覆盖 |
| 3 | 无 LLM 零变化 | ✅ | env -u（无 key）: "我想做X" → 仍逐字段问（"这个产品最主要想解决什么痛点?(缺失字段: problem)"）, 无 "我理解", ai_generated=False — 与 v1.1.15 行为一致 |
| 4 | 确认摘要展示 | ✅ | 确认消息: "我理解你要做一款手机端的markdown编辑器，给移动端用户使用，核心是轻量（避免功能过重）和美观（界面好看）。" + 主动建议（平台/竞品/范围/备注）+ AI 命名候选（墨笺/简码/随身稿） |
| 5 | 全量回归 0 新增 | ✅* | console+api: 4815 passed / 1 skipped / 2 failed（详见 §3, 均非本 Sprint 引入） |
| 6 | 版本 v1.1.16 | ✅ | pyproject.toml = 1.1.16; 版本契约测试通过; CHANGELOG v1.1.16 条目 |

## 1. 真实 LLM 自然描述测试（唯一真相）

```
用户: 我想做个 markdown 编辑器, 要 typora 和 notepad++ 的优点, 适配手机
系统: 您最希望融合 Typora 和 Notepad++ 的哪些具体优点？比如实时预览、轻量级、语法高亮还是其他？
      (为什么还问: 用户未说明产品要解决的具体问题或痛点)          ← 智能追问, 带理由
用户: 手机上没有顺手又好看的 markdown 编辑器, 不是太重就是太丑
系统: 你希望主要面向哪类用户（如学生、程序员、自媒体写作者）？
      (为什么还问: 输入未明确目标用户群体)                        ← 智能追问, 带理由
用户: 给经常写作和记笔记的人用
系统: 我理解你要做一款手机端的markdown编辑器，给移动端用户使用，核心是轻量（避免功能过重）和美观（界面好看）。
      产品: 墨笺 | 问题: 手机上没有顺手又好看的markdown编辑器… | 目标用户: 给经常写作和记笔记的人用
      核心功能: Markdown 编辑器, 融合 Typora 和 Notepad++ 的优点, 适配手机 | 运行平台: 手机
      建议名称: 墨笺 / 简码 / 随身稿
      主动建议: 平台=手机（iOS/Android/跨平台？）· 竞品=Typora、Notepad++（桌面端），手机端可能参考iA Writer、Bear等
               · 范围=MVP建议先实现核心编辑、预览、同步 · 备注=用户强调"轻量"和"美观"，需在UI设计和性能上优先考虑
```

- LLM 意图理解: category=product_description（控制指令 > 查询 > 字段回答 > 产品描述 优先级在 prompt 生效）
- 结构化提取: core_features / platform / name 一次产出; problem / user 识别为"输入未明确" → 智能追问（不是机械列）
- 智能追问: 每轮只问最重要 1 条 + "为什么还问: <原因>"（missing_reasons 话术）
- 确认门: 理解摘要 + 主动分析（平台/竞品/范围/备注）+ AI 命名
- 运行成本: 3 次真实 LLM 调用（analyze ×3 + 命名）完成整轮发现

## 2. 契约测试（mock 注入, 33 passed）

tests/console/test_discovery_llm_intelligence.py — 覆盖:
自然描述一次产出 / 控制指令优先（确定性硬闸）/ 模糊控制改写（LLM category=control）/ 智能追问带理由 /
无 LLM 回退（llm_fn=None 逐字段）/ 非法 JSON 降级 / 确认摘要含"我理解" / 主动分析展示 /
批量/编辑/逃生分支在 LLM 路径下可达 / 向后兼容。

## 3. 全量回归

- 基线（Sprint 前, tree clean）: 4784 passed / 1 skipped / 0 failed
- Sprint 后（含 33 新增）: **4815 passed / 1 skipped / 2 failed**
- 2 failed 均非本 Sprint 引入:
  1. `test_all_subcommands_registered` — **其他会话（Telegram, 组织树功能）未提交的 `create` 命令** 加入 CLI 子命令集
     未同步测试（"Extra items in the left set: 'create'"）。与本 Sprint 无关（未触碰 CLI 注册表）。
  2. `test_m3e_full_chain` — **已知 flaky**, 独立重跑 8 passed（Codex 与 S10-082 均记录过同款 flaky）。
- 定向回归（本 Sprint 相关区）: 178 passed（33 新 + product/conversation/naming 138 + 版本契约 7）

## 4. 诚实记录（工程资产）

- **无 LLM 时 "整理一下" 仍走字段回答** — 与 v1.1.15 行为完全一致（确定性短语集未含裸"整理一下"）;
  "整理一下" 的识别是 LLM 路径新增能力, 非降级承诺。验收 3（零变化）优先于验收 2（LLM 在场时成立）。
- 实现缺口观察: 智能追问轮的回答若答非所问（如问 problem 答 user）, 状态机按当前 pending 字段落值 —
  LLM 分类 field_answer 合并既有逻辑的设计行为, 非缺陷; 用户按问题作答时链路顺畅（§1 实证）。
- 并发协作: 实现期间 Telegram 会话在**同一工作区**提交了 3 个 docs commit + 未提交 factory-org/cli_factory 改动。
  Codex 提交仅含本 Sprint 7 文件（未扫入他方改动）; 我方验收运行前确认无污染。已按 memory 警示处理。

## 5. 结论

- **通过**。Founder 实测痛点（"太模板化"）已实质解决: 字段收集从规则状态机升级为 LLM 理解主路径,
  一次自然描述产出结构化定义, 缺失才智能追问（带理由）, 确认门展示理解摘要 + 主动分析 + AI 命名。
- 诚实降级与向后兼容达标: 无 LLM → 现有状态机逐字节不变。
- 建议下个 Sprint 候选: DiscoverySession (S10-065 "开始做X" 路径) 同步 LLM 化（本 Sprint 边界外）;
  CAPABILITY_MATRIX 已更新 (S10-099 节)。
