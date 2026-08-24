# S10-113 — M5-1 执行重放引擎：独立验收报告

> 日期: 2026-08-25 | 版本: v1.1.82 (与并发 S10-114 Skill 真调用共享) | 验收人: Hermes (CTO, 独立验证 — 非 Codex 自报告)
> 实现: `98eb351` (feat(S10-113))
> 前置: v1.1.81 · M3 7/7 · P0-10/11 ✅

---

## 验收矩阵（6 项）

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | dry-run: 真实 exec_id 重建时间线; 无效 id → 明确错误 | ✅ | ReplayTimeline 含步骤/agent/结果/耗时 (真实计算 1.0s/14.0s/15.0s 总 30.0s); "执行记录不存在: NOPE" 明确错误 |
| 2 | re-exec: 同输入重跑 → 新记录; 输入缺失 → 明确错误不瞎跑 | ✅ | 新 result_id res-REXEC-1 + 记录; 旧记录 → "旧记录无输入快照, 无法重跑" (runner 未被调用) |
| 3 | 对比报告: diff (结果/耗时/步骤数); --save 落盘 | ✅ | "# 执行对比报告: res-E1 ↔ res-E2 · 真实 diff" success vs failed + 耗时; --save 文件存在含真实内容 |
| 4 | 记录完善: 新记录含 input_snapshot | ✅ | actions.py 记录构建含 input_snapshot (可序列化过滤, 失败安全) |
| 5 | 全量回归 0 新增失败 · v1.1.82 | ✅ | console+api: **5277 passed / 1 skipped / 0 failed**; pyproject=1.1.82 + 断言 + CHANGELOG + FEATURES |
| 6 | 待办清单 M5-1 ✅ (L4 如实标注) | ✅ | M5-1 行已标 ✅; L4 快照回滚**已做但受限** (见 §2) |

## 1. 独立验证实录（我的脚本 9/9, 真实 tmp workspace + 记录）

```
✅ dry-run: ReplayTimeline(exec_id=res-E1, record={intent/action/agent/...}) 含步骤+耗时
✅ dry-run 无效 id → "执行记录不存在: NOPE"
✅ re-exec: runner 返回含 result_id 新记录 → res-REXEC-1 (引擎校验 runner 返回有效性 — 好行为)
✅ re-exec 缺快照 → "旧记录无输入快照, 无法重跑 — 请确认记录版本 (v1.1.82+ 新执行记录含 input_snapshot)" (runner 未被调用)
✅ 对比报告: 真实 diff (success vs failed) + 耗时 + --save 落盘
✅ actions.py 含 input_snapshot 字段
```

## 2. L4 快照回滚 — 如实标注（部分完成）

- **已做**: `snapshot_before` (git add -A + git stash create 基线, 复用 sandbox 同源 git 机制) →
  `rollback` (git reset --hard + git clean -fd 恢复执行前状态, 含未跟踪文件)
- **受限**: 要求项目目录为 git 仓库 (记录需含 input_snapshot.context.project);
  数据工作区 (~/.factory) 本身非 git 仓库时明确报错不静默
- 待办清单 M5-1 按"部分完成"口径标注

## 3. 关键设计验证（反虚标）

- **dry-run 真实重建**: records + audit 事件 (TASK_STARTED/COMPLETED/FAILED) 按 timestamp 合并;
  耗时=相邻时间戳差 (真实计算, 非占位)
- **re-exec 失败安全**: input_snapshot 缺失 → ReplayError 明确错误, runner 不被调用 (不瞎跑)
- **对比真实 diff**: 结果/耗时/步骤差异来自两次执行记录, 非"看起来一样"
- **input_snapshot**: 可序列化过滤 (JSON 安全值, 失败安全 → 字符串); 幂等追加 (result_id 去重)
- **入口**: /board replay <id> (dry-run 默认 + --re-exec/--compare/--save) + 自然语言 "重跑 <id>" → replay_exec 意图路由

## 4. 契约测试与并发

- Codex 新增 test_s10_113_execution_replay.py (≥6 契约)
- **并发说明**: 仓库共享工作区 — S10-114 (Skill 真调用) 并行提交 7c78d48 (v1.1.82 版本文件);
  CHANGELOG v1.1.82 条目与 FEATURES M5-1 行由 Codex 写入、被其 commit 一并捕获;
  Codex 修正了 S10-114 漏改的 test_s10_111 版本断言; 最终 HEAD: M5-1 + Skill 双内容共存 v1.1.82
- Codex 沙箱 7 个环境性失败 (写 ~/.factory/dist) 非沙箱复跑 102 passed — 我环境 0 failed

## 5. 结论

- **通过**。执行节点可靠性提升: 失败后可"看完证据 (dry-run) → 重演一遍 (re-exec) → 对比确认 (compare) → 敢签字"。
  L4 快照回滚部分完成 (git 仓库受限, 如实标注)。
- 诚实纪律: 旧记录无 input_snapshot → re-exec 明确不可用 (如实); 新记录起全量可重放。
- 建议后续: L4 完整化 (非 git 工作区快照); input_snapshot 覆盖所有执行路径。
