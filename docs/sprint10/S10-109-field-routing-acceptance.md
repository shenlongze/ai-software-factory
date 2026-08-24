# S10-109 — 需求分析字段错位修复（T9）：独立验收报告

> 日期: 2026-08-24 | 版本: v1.1.48 | 验收人: Hermes (CTO, 独立验证 — 非 Codex 自报告)
> 实现: `91d4004` (fix(S10-109))
> 前置: v1.1.47 · S10-108 已标注字段错位 bug

---

## 验收矩阵

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | T9 复现 → 字段正确 | ✅ | 问痛点答"给大学生用" → user; 答"支持扫码记账和月度报表" → core_features; 答"可以"(缺字段) → 不填 + "还缺 产品解决什么问题" 提示 |
| 2 | 正常回答零变化 | ✅ | 问 problem 答"记账麻烦, 月底对不上账" → problem; 问 user 答"给大学生用" → user; 问 features 答"扫码记账、月度报表" → features (逐字节同 v1.1.47) |
| 3 | 无 LLM 兜底同生效 | ✅ | env -u 机械路径: problem=None / user=给大学生用 / features 正确 / "可以" → "还缺" 提示 |
| 4 | 契约测试 ≥3 | ✅ | test_s10_109_field_routing.py **22 用例** (T9 机械+LLM 双路径/归类/确认词/零变化/优先级/无LLM/批量/误伤收敛/单元) |
| 5 | 全量回归 0 新增 | ✅ | console+api: **5097 passed / 1 skipped / 0 failed** |
| 6 | 版本 v1.1.48 | ✅ | pyproject = 1.1.48; 版本断言 + CHANGELOG + docs/FEATURES.md 同步; 安装环境已刷新 |

## 1. 独立验证实录（我的脚本 14/14 + env -u）

```
T9 复现 (修复后):
✅ user='给大学生用' · problem=None (不被污染)
✅ core_features=['支持扫码记账和月度报表'] (含扫码记账/月度报表)
✅ "可以" 不被当字段值 → 提示 "产品定义 2/3: … 产品解决什么问题待填" 还缺字段
✅ 仍处 DISCOVERY (可继续补答)

正常回答零变化:
✅ 答对 problem/user/features → 各归其位 (逐字节)

边界:
✅ "做报表" (非确认词开头) → core_features (整句匹配不误判)
✅ 分号批量 → 顺序填不受影响
✅ 字段齐后 "可以" → 正常进入确认 (PROJECT_CREATION)
✅ env -u 无 LLM: 同归类 + "还缺" 提示

已知行为 (按规格, 如实标注):
✅ 多命中 "给大学生用, 支持扫码" → user 优先 (字段归属正确); 整句填入最高优先级命中字段
   (值拆分属批量模式范畴, 本 Sprint 边界外 — 规格未要求)
```

## 2. 关键设计验证（反虚标）

- **确定性字段归属**: _FIELD_PATTERNS (user/core_features/problem) + _FIELD_MATCH_PRIORITY
  (user > core_features > problem) — 纯规则, 无 LLM 也生效 (env -u 实测)
- **确认词整句匹配**: 复用 discovery_guide.APPROVE_WORDS — "做报表" 不误判 (整句才触发)
- **两路径接入**: LLM field_answer 路径 (_apply_field_answer) + 机械单字段路径; 批量模式不动 (边界)
- **零变化保证**: 未命中模式 → 填当前字段 (正常回答逐字节不变, 既有 427 聚焦测试全绿)

## 3. 契约测试与既有更新

- 新增 test_s10_109_field_routing.py 22 用例
- 既有更新: test_s10_075_nl_entry.test_state_preserved_across_turns — **原依赖错位 bug**
  ("主要给程序员用"被错填进 problem 才通过), 改为逐字段答齐 + 断言正确归类 (诚实修正);
  版本断言 1.1.47→1.1.48 (6 文件)
- 全量: 5097 passed / 1 skipped / 0 failed

## 4. 诚实记录（工程资产）

- **边界保留**: LLM 分类本身 (field_answer 归类) 未改 — 规则优先、LLM 补充; 若 LLM 把产品描述
  误判 field_answer, 规则仍会归类 (规则兜底真实生效)
- **已知限制**: 单一回答含多字段信息 (如"给大学生用, 支持扫码") → 整句填入最高优先级命中字段,
  不做值拆分 (批量模式已支持分号拆分 — 用户可用分号)
- Codex 沙箱 7 个环境性失败 (wheel 网络/~/.factory 权限/端口) 经 HEAD 干净树验证为既有, 非本 Sprint

## 5. 结论

- **通过**。T9 字段错位修复: 答非所问智能归类 (user/features/problem 确定性模式), 确认词不当字段值
  (缺字段明确提示), 正常回答零变化, 无 LLM 同生效。
- 建议后续: 单一回答多字段拆分 (自动分号化) 可作为增强项; LLM field_answer 归属可作为规则补充。
