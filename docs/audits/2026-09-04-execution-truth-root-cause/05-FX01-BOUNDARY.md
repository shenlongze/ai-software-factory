# 05 — FX-01 BOUNDARY (Execution Truth Root Cause)

> 取证日期: 2026-09-04 | READ ONLY | 只定义修复边界, 不写代码

---

## 1. FX-01 GO / NO-GO: **NO-GO (直接) → SPLIT**

FX-01 当前表述 ("exec 记录引用 backlog TASK-* ID") 预设了 "Task identity canonical, Execution identity canonical,
仅 callback/writeback 断"。取证结论否定该预设:

- Execution identity 不 canonical (EXR / EXS / TASK-GW / run_id 四本独立, EXR→EXS 链接 0/86)
- exec_ref 语义三义 (chain 写 TASK-GW / T-9 溯源读 EXR / model 注释=EXR-引擎 id)
- backlog TASK-* 与 execution 记录从未有稳定引用 (0/235)
- session_exec 是第 5 套编排状态 (非 TaskRun 非 Execution), 且现存实例均为 E2E 测试痕迹

直接实施 FX-01 = 在身份契约未冻结时把某两本账本钉死 → 会固化错误映射, 并可能把 legacy
M3/T001 记录误接为当前 TASK-* 的执行证据。

**FX-01 必须先拆为: 身份契约冻结 (F0) → 执行记录规范化 (F1) → 回写闭环 (F2)。**

## 2. MUST CHANGE (修复边界内)

1. **冻结 Identity Contract (F0, 零代码或最小代码)**
   - 声明每域唯一 SSOT + ID 前缀 (Task=TASK-* backlog / Run=run_id / Execution=EXS-* /
     Artifact=ART-* / Verification=ver-* 待建 / Evidence=ev-* / Audit=audit_id)
   - 声明 ID 方向: `session → plan → backlog TASK-* → EXS (execution) → ART → ver → ev`
   - 明确 `task.exec_ref` 唯一语义 = **EXS-* execution id** (废除 TASK-GW / EXR 混用)
   - 标记 legacy: M3 orchestrator task (task-e1-*/T001) 与 8/18 audit 链 = historical, 不进入 canonical chain

2. **Execution 记录规范化 (F1)**
   - EXS (execution_records.json) 增 task_id (backlog TASK-*) + session_id + plan_id 字段
   - gateway record_invocation 落 EXS 时携带来源 task/session 上下文
   - EXR.requests output_refs 链接修复 或标记 legacy (0/86 无链接是事实缺陷)

3. **回写闭环 (F2)**
   - chain_next / auto worker: gateway 返回后回写 `st.task.exec_ref = EXS-*` (非 TASK-GW)
   - finish_task_exec 只在 backlog_id 存在时调用 — 且当 backlog_id 缺失时**显式告警** (不静默跳过)
   - session_exec 收敛: 提供 completion 判定事件 / 超时 / 明确终态 (done/failed/abandoned)

4. **上下文传播**
   - chain_next 使用 `st.state["project_id"]` (chain_start 已存) 而非 dispatch 闭包 project_id
   - gateway 调用携带 project_id + 期望 project_dir; project_dir 缺失时 verify 结果明确标注 "无项目目录, 验证未执行" (已是诚实 unknown, 保持)

## 3. MUST NOT CHANGE

- **Legacy audit 记录** (8/18 task-e1-* STARTED/COMPLETED): 保留为历史证据, 不迁移/不重连
- **Historical execution_records / EXR / results.json**: 保留, 只加新字段不重写旧记录
- **现有 Artifact 生命周期** (exec ART-* / org artifacts / product artifacts): 不动, 只补 canonical FK 方向
- **WebUI 行为**: 不改前端
- **orchestrator M3 既有代码**: 不删不改 (标记 historical 即可, 迁移另立)
- **factory.db / audit_events.json**: 不改写历史事件
- **测试**: 不"修复"既有测试来迎合新契约 (新契约需新测试)

## 4. DEPENDENCIES

- F0 (Identity Contract) ← 无前置, 但需 STEP10 Contract 扩展/人工批准 (架构决策)
- F1 (EXS 规范化) ← F0 (字段语义先冻结)
- F2 (回写闭环) ← F1 + chain_next 上下文修复
- 不可并行先行: F2 若先做会继续用三义 exec_ref

## 5. PRECONDITIONS

- 人工批准 Identity Contract (扩展 STEP10 D-6/D-9/D-2 的实施层, 不推翻冻结)
- 明确 EXS = Execution canonical (或另立统一 execution ledger 迁移 EXR/EXS/TASK-GW)
- 确定 session_exec 的去留: 若保留 = Run 投影 (不持有 execution truth); 若废弃 = 迁移到 backlog+EXS 链
- 明确 6 个 E2E session_exec 遗留文件处置 (标记 abandoned/test 或清理 — 需用户决定, 审计不代决)

## 6. POSTCONDITIONS (达成后)

```
session_id → plan_id → backlog TASK-* → EXS-* (execution) → ART-* → ver-* → ev-* → audit_id
  ├─ task.exec_ref == EXS-* (唯一语义, 可 T-9 溯源)
  ├─ backlog done 任务必有 exec_ref (或显式 abandoned)
  ├─ audit 对每个 TASK-* 有 CREATED→(STARTED?)→COMPLETED/FAILED 生命周期
  ├─ gateway verify 有 project_dir 或明确 unknown 原因
  └─ legacy (task-e1-*/T001/8/18 audit) 与 canonical 链边界清晰
```

## 7. 最终建议次序 (供批准)

1. **P0-A 身份契约冻结** (文档/Contract, 零代码; 回答 EXS-canonical 或统一 ledger 迁移)
2. **P0-B chain_next 上下文修复** (用 st.state.project_id; 改 gateway 调用方)
3. **P0-C EXS 记录规范化 + exec_ref=EXS 写回** (即真正的 FX-01 主体)
4. **P0-D session_exec 收敛语义** (终态 + 事件; 处置 E2E 遗留)
5. **P1 Verification SSOT (FX-08) + Artifact FK 方向** — 需在 P0-A 之后
