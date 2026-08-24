# S10-113 Hermes 提示词 — M5-1 执行重放/回滚（dry-run / re-exec / 对比报告）

> 用途: 复制给 Hermes，独立分析 → 派 Codex 实现 → 独立验收。
> 主线: 待办清单 M5-1（Founder 判断"执行节点能力不足"）。

---

## 任务标题
**S10-113 M5-1 执行重放引擎**: dry-run 重建 / re-exec 重跑 / 两次对比报告（+ L4 快照回滚可选）

## 背景（Founder 判断）

Founder 全链路深度评估: 11 个节点里 7 个"有功能但浅", **执行节点最影响可靠性**
—— 失败只能重来, 不能"看完证据 → 重演一遍 → 敢签字"（§5.6.3 L3 企业要求）。

当前基础:
- execution_records.json（85+ 条: intent/action/agent/task/result/result_id/timestamp/error）
- audit 事件（TASK_STARTED/COMPLETED/FAILED 等, 时间线可重建）
- 沙箱可回滚（git 追踪 + patch 导出/apply/revert）
- 版本 v1.1.81 · 全量 ~12500 passed

## 规格（§5.6.3 L3/L4）

### 1. dry-run（逐事件重建展示）
- 入口: `/board replay <exec_id> --dry-run` 或 `/exec replay <exec_id>`
- 读 execution_records + audit 事件 → 按时间线重建执行过程（步骤/agent/任务/结果/耗时）
- 输出: 重放时间线（可读, 类生命线但按单次执行聚合）

### 2. re-exec（同输入重跑）
- 入口: `/board replay <exec_id> --re-exec` 或自然语言"重跑 <exec_id>"
- 从记录取原始输入（intent/action/参数）→ 同输入重跑 → 新 exec_id 记录
- 失败安全: 输入不完整/参数缺失 → 明确错误（不瞎跑）

### 3. 对比报告（两次执行 diff）
- 入口: `/board replay <exec_id> --compare <exec2_id>` 或 --compare 对最近一次
- 对比: 步骤差异 / 结果差异（success vs failed）/ 耗时 / 产物差异
- 输出: markdown 对比报告（可 --save 落盘 docs/sprint10/）

### 4. 执行记录完善（重放数据源保证）
- 若现有记录缺"输入快照"（intent 参数/上下文）→ 补录（re-exec 需要完整输入才能重跑）
- 新增执行时记录完整输入（input_snapshot 字段）→ 保证未来可重放

### 5. L4 快照回滚（可选, 若实现简单）
- 执行前 git 快照 → 失败后可回滚到执行前状态（复用沙箱 revert）
- 不做则如实标注"L4 未做, 待后续"

## 范围声明（硬边界）

- ✅ 只改: 执行记录（input_snapshot）+ 重放/对比命令 + 沙箱快照（若做）
- ❌ 不改: 调度器/M3a-d、执行引擎核心逻辑、board 渲染、产品管线、ChangeControl
- ❌ 不扩展: 不做并行线程化、不做 RAG、不做消息平台
- 统一修改: 实现 + 契约测试 + CHANGELOG + 版本断言 + FEATURES.md 同 Sprint

## 验收标准（Hermes 独立验证）

1. **dry-run**: 对真实 exec_id 重建时间线（步骤/agent/结果/耗时可读）; 无效 id → 明确错误
2. **re-exec**: 同输入重跑生成新记录（可对比）; 输入缺失 → 明确错误不瞎跑
3. **对比报告**: 两次执行 diff（结果/耗时/步骤数差异）; --save 落盘
4. **记录完善**: 新执行记录含 input_snapshot（re-exec 可还原输入）
5. 全量回归 0 新增失败 · 版本 v1.1.82（pyproject + 断言 + CHANGELOG + FEATURES）
6. 待办清单 M5-1 标 ✅（L4 快照若未做, 如实标注 M5-1 部分完成）

## Codex 指令摘要

> 实现 M5-1 执行重放: ①dry-run 按事件时间线重建单次执行; ②re-exec 从记录取
> 原始输入重跑生成新记录; ③两次执行对比报告(markdown, --save); ④执行记录补
> input_snapshot 保证可重放。L4 快照回滚可选(简单则做)。入口 /board replay +
> /exec replay。契约测试 ≥6, 全量回归 0 失败, v1.1.82。不乱改、不扩展。

## 诚实纪律

- 如实标注: dry-run/re-exec 哪些真实重建/重跑, 哪些受记录缺失限制（如旧记录无
  input_snapshot → re-exec 不可用 → 如实报告）
- L4 快照回滚做/不做如实报告, 不伪称
- 对比报告必须真实 diff（不允许"看起来一样"）
- 不改执行引擎核心逻辑（只加重放/对比/记录增强）
