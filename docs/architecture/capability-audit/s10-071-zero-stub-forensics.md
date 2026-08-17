# S10-071 — Zero-Stub Forensics

> 日期: 2026-08-17 | 第一步: 生产路径确认 (未重写代码)
> 方法: 代码事实扫描 — 只读, 确认哪些路径真实、哪些是桩

---

## 一、生产路径 vs 桩 总表

| ID | 能力 | 生产路径 | 当前实现 | 是否真实 | Stub 原因 | 风险 | 修复方案 | 验证方式 |
|----|------|----------|----------|----------|-----------|------|----------|----------|
| P0-1 | Debug 修复执行 | DebugPipeline.repair | `_default_execute_fn` 硬编码 `{"success": True, "note": "deterministic repair applied (no execution engine)"}` | ❌ STUB | 无默认真实执行器 | 自主修复是模拟 | WorkspaceRepairExecutor (真实文件修改) | 真实项目修改后 diff 验证 |
| P0-2 | Debug 验证 | DebugPipeline.validate | validator 注入 (测试传 result) | ❌ STUB | 默认无真实 pytest | 验证是模拟 | PytestValidator 接 Validator.validate_command (已存在真实 subprocess) | 真实 pytest exit_code/stdout |
| P0-3 | Memory 自动沉淀 | — | AutoLearner 存在, actions/orchestrator 均未调用 | ⚠️ PARTIAL | 未接生产钩子 | 经验靠手动 learn | execute_project/Debug 完成 → AutoLearner | 生产结束 experience_store 自动增长 |
| P0-4 | Audit 自动链 | actions 5 点 | orchestrator 无 AuditEmitter | ⚠️ PARTIAL | 生产链核心未接 | 无法审计执行 | orchestrator 关键点 emit | ScorePocket 全链 Audit 恢复 |
| P0-5 | ContextBudget 执行 | — | ContextLedger 无生产使用; llm_gap/product_intelligence 无 budget 引用 | ❌ STUB | LLM 调用绕过 | Context 无限增长 | LLM 调用统一 ContextLedger.check | 超预算调用被截断 |
| P0-6 | Retrieval 统一 | memory.ExperienceRetriever + debug.DebugExperienceRetriever (两套) | RetrievalOrchestrator 仅测试 | ⚠️ PARTIAL | 生产未统一 | 多 RAG 冲突 | Debug/Planning 检索经 Orchestrator | 生产检索走统一入口 |

## 二、已确认的现成真实能力 (可复用, 不重写)

| 资产 | 位置 | 真实度 |
|---|---|---|
| Validator.validate_command | session/quality.py:107 | ✅ 真实 subprocess pytest (timeout/exit_code/stdout/stderr/失败安全) |
| RepairManager.repair | session/quality.py:403 | ✅ 真实文件写入 (write_text) + subprocess |
| RepairManager.create_repair | session/quality.py:297 | ✅ 修复任务真实 |
| repair_manager_execute_fn 桥 | session/debug/debug_pipeline.py:91 | ✅ 薄调 RepairManager (默认未用) |
| AuditEmitter | audit/audit_emitter.py | ✅ 真实落盘 + 脱敏 + hash (5 action 接入) |
| AutoLearner | memory/auto_learn.py | ✅ 提取→存储→模式→trace (未接生产) |
| ContextLedger | session/context_ledger.py | ✅ 总预算模型 (未接生产) |
| RetrievalOrchestrator | retrieval/orchestrator.py | ✅ 去重/排序/Top-K/Budget (未接生产) |

## 三、硬编码桩扫描结果

```
factory-console/session/debug/debug_pipeline.py: 'deterministic repair applied' / 'no execution engine' (P0-1 铁证)
factory-console/session/gap_analyzer.py: 'not implemented' (需确认 — 见下)
```

### gap_analyzer 'not implemented' 确认

<details>
<summary>检查</summary>
需 grep 上下文 — 若为 LLM 模式占位 (deterministic 已实现), 属预期 fallback; 若为核心逻辑, 另记。
</details>

## 四、真实 E2E 可验证性确认

- ✅ quality.py 可真实跑 pytest (subprocess)
- ✅ RepairManager 可真实写文件
- ✅ 临时项目可构造真实失败 (bug + test)
- ✅ DebugPipeline 分析层真实 (分类/根因/经验/策略)

## 五、结论

6 个 P0 中:
- **2 个纯 STUB** (P0-1 修复执行, P0-5 ContextBudget 执行)
- **2 个 STUB 但有现成真实资产可复用** (P0-2 验证 → Validator.validate_command)
- **2 个 PARTIAL 缺生产接线** (P0-3 AutoLearner, P0-4 Audit, P0-6 Retrieval — 共 3 个接线型)

修复策略: P0-1+P0-2 共建 WorkspaceRepairExecutor + PytestValidator (复用 quality.py);
P0-3/P0-4/P0-6 为接线 (薄接 orchestrator/actions)。
