# Hermes 提示词 — Sprint 规格（CLI Markdown 渲染 + /preview + 多行输入）

> 用途: 三部门循环第 ② 步 — Hermes(CTO) 产出 Sprint 规格，供 Codex(工程) 实现
> 日期: 2026-08-24 | 前置: v1.1.25 · S10-104 next_action/分割线/删除已验收 · 全量基线 0 回归

---

【AI Factory Sprint 规格 — CLI Markdown 渲染 + /preview + 多行输入】

## 角色
Hermes = CTO + 架构委员会。产出可执行 Sprint 规格，不写实现代码。

## 背景（Founder 询问 CLI 能力）
Founder 问: CLI 是否支持 markdown 格式/多行编辑/markdown 预览？
现状（诚实）:
- Markdown 格式: 🟡 能生成（PRD.md 等文件）但会话显示源码（纯 print 不渲染）
- 多行编辑: ❌ 纯 input() 单行（注释明说"高级交互后续可加 prompt_toolkit"）
- Markdown 预览: ❌ 无（依赖里有 rich>=13 有 Markdown 渲染, 但会话没用）

## Sprint 目标（3 项）
1. **会话 Markdown 渲染（🔴 低成本立竿见影）**: PRD/文档类输出 → rich.Markdown 渲染
   （标题/列表/表格/代码块可读, 不再看源码）
2. **/preview 命令（🟡）**: /preview <file> → 渲染 markdown 文件（PRD.md 等）
   - 终端 rich 渲染; 未来可扩展 HTML 导出
3. **多行输入支持（🟡）**: 用户可粘贴长需求/多行文本
   - prompt_toolkit 接入（多行+历史+补全）或简单多行粘贴检测
   - 与现有 input() 兼容（无 prompt_toolkit 环境降级 input()）

## 范围声明（§10.5.7.6）
- 本 Sprint 做: markdown 渲染 + /preview + 多行输入
- 明确不做: Web 端富文本 · 完整 markdown 编辑器 · 其他 CLI 命令行为
- 连带发现（进 backlog）: prompt_toolkit 完整交互增强（历史/补全/语法高亮）· HTML 导出
- 波及面: session.py(输出渲染/输入) + renderer + slash 注册表(/preview) → 会话输出/PRD 展示 → 会话+CLI 测试

## 规格必须包含（8 项）
1. markdown 检测与渲染（什么输出算 markdown → rich.Markdown; 非 markdown 纯文本不变）
2. rich 渲染接入（会话输出层; 失败安全: rich 渲染异常 → 原样文本兜底）
3. /preview 命令设计（slash 注册; 参数 file; 渲染 markdown; 文件缺失明确错误）
4. 多行输入方案（prompt_toolkit vs 简单检测; 兼容降级 input(); 不破坏现有输入流）
5. 渲染与分隔线/进度提示的兼容（S10-104 已有装饰不冲突）
6. 契约测试要点: markdown 渲染内容正确 / 非markdown不变 / /preview 渲染+错误路径 /
   多行输入合并 / 无 rich 降级 / 向后兼容
7. Codex 写 scope（最小改动）
8. 边界: 不改产品发现/确认逻辑 · 不改 Web

## 验收标准（Codex 完成后，你独立验证）
- 会话中 PRD/文档输出 → rich 渲染（可读, 非源码）
- /preview PRD.md → 渲染显示; 缺失文件 → 明确错误
- 多行输入（粘贴长文本）→ 正确处理（合并/多行）
- 无 rich/prompt_toolkit 环境 → 诚实降级（原样文本/单行 input）
- 全量回归 0 新增 + git clean
- 版本: 本 Sprint 完成后 bump v1.1.26

## 输出物
- 规格文档: `docs/sprint10/S10-105-markdown-preview-plan.md`
- 供 Codex 的指令摘要

## 关键纪律
1. 代码存在 ≠ 能力；自报告 ≠ 事实 — 独立验证（真实 PRD 渲染/多行输入实测）
2. 禁止 stub/fake；无 rich/prompt_toolkit 诚实降级
3. 复用 rich 依赖（已有）· slash 注册机制 — 不重造
4. 向后兼容: 非 markdown 输出纯文本不变; 单行输入仍可用
5. 版本: v1.1.25 → v1.1.26（patch+1）
