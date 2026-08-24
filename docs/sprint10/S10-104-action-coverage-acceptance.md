# S10-104 — 确认阶段 next_action 全覆盖 + 会话分割线 + 删除指令：独立验收报告

> 日期: 2026-08-24 | 版本: v1.1.25 | 验收人: Hermes (CTO, 独立验证 — 非 Codex 自报告)
> 实现: `634f27d` (feat(S10-104), 13 files, +783/-33)
> 前置: v1.1.24 · S10-102/103 确认分流与命令分流已验收

---

## 验收矩阵

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | "产出份prd文档" → next_action + 名称不被覆盖 | ✅ | next_action="prd" + PROJECT_CREATION, 名称不变 |
| 2 | "改名叫X" 仍走改名 | ✅ | "改名叫墨笺" → name=墨笺 + next_action=None; "改名叫prd" 亦走改名 (RENAME_RE 最优先) |
| 3 | 每轮有分割线 | ✅ | run() 层: 两轮回复后各有 "─"×46 分割线, 退出消息后无; rc 0 |
| 4 | "把核心功能删掉" → 清空重确认 | ✅ | core_features=[] → 迁移 DISCOVERY + pending=[core_features] + 追问; 非改名 |
| 5 | 无 LLM 规则兜底 | ✅ | 全部规则确定性 (DIRECT_ACTION_PATTERNS / DELETE 指令), env -u 下全过 |
| 6 | 全量回归 0 新增 | ✅ | console+api: **5030 passed / 1 skipped / 0 failed** |
| 7 | 版本 v1.1.25 | ✅ | pyproject = 1.1.25; 版本断言通过; CHANGELOG v1.1.25 |

## 1. 独立验证实录（我的脚本 17/17 等效全过）

```
next_action 全覆盖 (确定性):
✅ "产出份prd文档" → next_action=prd + 名称不被覆盖
✅ "生成PRD" → prd · "出个html" → html · "出份功能清单" → feature_list (名称均不变)
✅ "改名叫墨笺" → rename (next_action=None) — RENAME_RE 优先级不变

删除/清空:
✅ "把核心功能删掉" → core_features=[] → 重进 DISCOVERY 追问 (非改名)
✅ "清空目标用户" → user=""
✅ 字段收集期 "把问题删掉" → problem 清空重问

分割线 (run() 层, mock input):
✅ 两轮回复后各有 SEPARATOR("─"×46), 退出消息后无, rc 0
```

## 2. 关键设计验证（反虚标）

- **DIRECT_ACTION_PATTERNS** (discovery_guide): 无确认前缀的动作短语正则 ("生成\s*prd"/"产出.*prd"/"出.*清单"/"出.*html")
  → 确定性命中; 顺序在 RENAME_RE 之后 (改名不被抢)
- **next_action 词汇扩展**: {prd, feature_list, html, docs}; analyze_confirmation prompt 同步 (LLM 补充分类为主);
  宿主: prd → generate_prd (既有), 其余 → "[已记录] 将生成X — 产出引擎 backlog" (不阻断创建)
- **删除指令**: _parse_delete_command 复用 _EDIT_FIELD_ALIASES, 两序匹配 ("把X删掉"/"清空X");
  必填清空 → DISCOVERY 重问; 绝不当改名
- **分割线**: SEPARATOR 仅 REPL run() 循环层 (纯装饰), 非交互 CLI 不受影响

## 3. 契约测试

- 新增 `test_s10_104_action_coverage.py` 37 用例 (契约 1-9)
- 既有更新: test_invalid_next_action_normalized (html 现为合法 → 改用 pdf 断言, 注释);
  版本断言 1.1.24→1.1.25 (3 文件); 分割线未破坏 run() 捕获断言 (均为 `in` 包含)
- 全量: 5030 passed / 1 skipped / 0 failed (console+api, env -u)

## 4. 诚实记录（工程资产）

- 我的验收脚本分割线检查先失败: 直接调 _dispatch 无分割线 — 因 SEPARATOR 在 run() 循环层 (设计如此),
  改 mock input 走 run() 后验证通过 (2 分割线 + 退出后无)
- Codex 沙箱 7-8 环境性失败 (~/.factory/socket/wheel/m3e 并发) 沙箱外全过 — 非本 Sprint
- 范围声明遵守: prompt_toolkit / feature_list 产出引擎 未做 (backlog; 本 Sprint 只传 next_action 信号)

## 5. 结论

- **通过**。🔴 next_action 表达全覆盖 (4 类型 + 规则变体 + LLM 补充), 名称不再被动作短语覆盖;
  🟡 分割线对齐 Hermes 风格 (REPL 层纯装饰); 🟡 删除/清空字段指令 (两序 + 必填重问)。
- 建议后续: feature_list/html/docs 产出引擎 (backlog); prompt_toolkit 交互升级 (backlog)。
