# S10-120 — K-4 trace_id 贯穿：独立验收报告

> 日期: 2026-08-25 | 版本: v1.1.90 | 验收人: Hermes (CTO, 独立验证 — 非 Codex 自报告)
> 实现: `afe2595` (feat(S10-120), K-4 战役第四战役 — I-1 + F-9)
> 前置: v1.1.89 · 设计文档 8db50ef

---

## 验收矩阵（9 项全过）

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | CLI 一次请求 → 全部审计事件 trace_id 非空相同 | ✅ | Codex E2E: REPL 两次输入各三事件同 trace (不同输入不同 trace, 退出无泄漏); 我脚本 emit 自动填充 trace-EMIT 一致 |
| 2 | API (TestClient) → 事件 trace_id 一致 | ✅ | Codex E2E: TestClient 事件 trace == 响应 X-Trace-ID; X-Trace-ID 覆盖生效 |
| 3 | audit_trace 返回该链路全部事件; 决策链可用 | ✅ | get_chain(trace_id) 返回 {trace_id, root_event, children, related_events}; query(trace_id) 命中 2 事件 |
| 4 | 无上下文路径 → trace_id="" 零变化 | ✅ | 首次 emit (无任何 set) → trace_id="" (我脚本复现) |
| 5 | execution_records / cost_records 带 trace_id | ✅ | cost 记录文件含 trace-COST (contextvar 注入) |
| 6 | 契约测试 ≥8 全绿 | ✅ | test_s10_120_trace_chain.py **14 passed** (我独立复跑) |
| 7 | 全量回归 0 新增失败 | ✅ | console+api: **5429 passed / 1 skipped / 0 failed** |
| 8 | v1.1.90 + K-4/I-1/F-9 ✅ | ✅ | pyproject=1.1.90; 待办 L18-19 ✅ |
| 9 | 设计文档落盘 | ✅ | docs/sprint10/S10-120-k4-trace-plan.md |

## 1. 独立验证实录（我的脚本 13/13）

```
无上下文零变化 (先于任何 set): ✅ get='' · ✅ correlation='' · ✅ emit 无上下文 → trace_id=''
contextvar 基本: ✅ new_trace_id 非空 · ✅ set/get 一致 · ✅ with 内生效 · ✅ child_correlation (trace-A:2)
             ✅ with 退出恢复 (不跨请求泄漏)
emit 自动填充: ✅ trace-EMIT 填充 · ✅ 显式 explicit-1 优先
audit_trace: ✅ get_chain 链路事件 · ✅ query(trace_id) 命中 2
成本链路: ✅ cost 记录文件含 trace-COST
```

## 2. 关键设计验证（反虚标）

- **contextvar 机制**: 线程安全, with 退出自动 reset 恢复 — 不跨请求泄漏 (实测)
- **emit 自动填充**: trace_id/correlation_id 未显式传 → 读 contextvar; 显式优先不覆盖; 64 发射点零改动
- **失败安全**: 无上下文 → ""; contextvar 异常 → "" 不崩
- **诚实标注** (Codex + 我复核):
  - 历史 2408 条空 trace_id 事件**不回填** (只追加语义 + 不伪造)
  - 无入口包裹的路径 → trace_id="" 旧行为逐字节一致
  - agent_runtime 无法导入 trace 模块 → 降级 "" 不破坏执行链

## 3. 契约测试与既有更新

- 新增 test_s10_120_trace_chain.py 14 用例 (贯穿一致/API/audit_trace/无上下文零变化/父子关联/失败安全/records)
- 既有更新: campaign_plan (K-4 ✅) + 版本断言 8 处 → 1.1.90

## 4. 结论

- **通过**。K-4 trace_id 贯穿落地: 一次请求从入口 (CLI/API/命令/exec) 到执行全程同一 trace_id —
  审计可按 trace_id 追踪 (audit_trace 决策链激活), 执行/成本记录可关联; F-9 关键日志带 trace。
  "2408 条全空不可追踪" → 新事件全链路可追踪; 旧数据如实不回填。
- 建议后续: K-5 评测体系渐进 (依赖 K-4 已就绪); K-8 链路可视化/可控 (I-2/I-3)。
