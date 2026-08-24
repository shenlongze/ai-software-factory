# S10-105 — CLI Markdown 渲染 + /preview + 多行输入：独立验收报告

> 日期: 2026-08-24 | 版本: v1.1.28 (规格 v1.1.26 — 并发会话消耗, 见 §4) | 验收人: Hermes (CTO, 独立验证 — 非 Codex 自报告)
> 实现: `242e141` (feat(S10-105))
> 前置: v1.1.25 · S10-099~104 产品发现/确认链已验收

---

## 验收矩阵

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | PRD/文档输出 rich 渲染可读 | ✅ | looks_like_markdown 保守启发式 (标题/表格/围栏); chat 回答/action 结果/产品流消息 5 处 print 点接入 render_message; 实测 "# 实现方案"+表格+代码围栏 → rich 渲染无 ANSI |
| 2 | /preview 渲染 + 错误路径 | ✅ | /preview PRD.md → rc 0 渲染; 无参 → rc 2 用法; 文件不存在 → rc 2 "❌ 文件不存在" |
| 3 | 多行输入正确处理 | ✅ | _read_input_line 行尾 "\" 续行拼接 ("line1\","line2\","line3" → "line1\nline2\nline3"); run 流程整条进对话 |
| 4 | 无 rich/prompt_toolkit 诚实降级 | ✅ | rich import 失败 → print 原样不崩; prompt_toolkit 缺失 → input() 降级 (续行检测方案) |
| 5 | 非 markdown 纯文本不变 | ✅ | 进度/建议列表/纯文本 → looks_like_markdown False → 原样输出 (精确相等断言通过) |
| 6 | 全量回归 0 新增 | ✅ | console+api: **5065 passed / 1 skipped / 0 failed** (含并发会话 S10-106 /board 改动) |
| 7 | 版本 | ⚠️ v1.1.28 (见 §4) | pyproject = 1.1.28; 安装环境已刷新 |

## 1. 独立验证实录（我的脚本 13/13）

```
渲染启发式:
✅ markdown 文档(标题/表格/围栏) → True
✅ 进度消息/建议列表/纯文本 → False (保守 — 非 markdown 零变化)

render_message:
✅ markdown → rich 渲染 (标题文本可见, 非终端无 ANSI)
✅ 纯文本 → 原样 (精确相等)
✅ rich import 失败 → print 原样降级

/preview:
✅ 有参 → rc 0 渲染 · 无参 → rc 2 · 文件不存在 → rc 2 "❌ 文件不存在"

多行输入:
✅ _read_input_line: "line1\","line2\","line3" → "line1\nline2\nline3"
✅ run() 流程整条进入对话
```

## 2. 关键设计验证（反虚标）

- **保守启发式**: looks_like_markdown 只认强信号 (围栏/标题/表格) — 发现流程的建议编号列表/进度消息
  保持纯文本 (验收 5 严格成立); rich 非终端自动去 ANSI, 测试输出仍可断言
- **诚实降级**: rich 可选导入 (已装但缺失不崩); prompt_toolkit 未装 → 续行检测 + input() 降级
- **/preview**: 路径解析 绝对/相对(cwd→workspace→current_project); 错误路径友好 rc 2 不崩
- **多行**: 行尾 "\" 续行, 拼接 "\n" 后整条进既有 _dispatch (产品流/chat 天然支持多行)

## 3. 契约测试

- 新增 `test_s10_105_markdown_preview.py` 35 用例 (计划 §2 契约 1-7)
- 既有更新: 版本断言 + 默认 slash 命令表 (+/preview, +/board — S10-106 并发注册); 消息断言均 `in` 包含, 无精确相等被渲染破坏
- 全量: 5065 passed / 1 skipped / 0 failed (console+api, env -u)

## 4. 诚实记录（工程资产 — 并发版本线）

- **规格版本 v1.1.26 → 实际落地 v1.1.28**: 实现期间其他会话并发提交 S10-106 任务监控面板
  (8f5c6fb, v1.1.27) 及 docs, 版本号被先行消耗; Codex 从实际 HEAD (1.1.27) patch+1 → 1.1.28。
  patch+1 纪律保持, 仅目标值被并发改写。验收按功能完成度判定, 版本以实际落地 1.1.28 为准
  (安装环境已刷新至 1.1.28)。
- Codex 沙箱 1 个网络性失败 (wheel 构建) 带网络后通过 — 非本 Sprint

## 5. 结论

- **通过**。3 项能力落地: markdown 文档会话内 rich 渲染 (不再看源码), /preview 渲染 + 错误路径,
  多行续行输入; 无 rich/prompt_toolkit 诚实降级; 非 markdown 纯文本零变化。
- 建议后续: prompt_toolkit 完整增强 / /preview HTML 导出 / Web 富文本 (backlog)。
