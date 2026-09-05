# 00 — F3 GAP AUDIT (2026-09-04)

> 状态: AUDIT COMPLETE — 进入 Contract Freeze + 实现
> 基线: HEAD d849a108 (F0/F1/F2 committed, P0-FINAL PASS)
> 方法: 全仓只读扫描 (code + data + tests)

---

## 1. 审计回答 (F3 §2 十问)

### Q1. Verification 当前是否已存在?
**部分存在 — 有真实执行器 (verification.py S5), 无 domain entity / 无 SSOT。**

### Q2. 它究竟是什么?
现状 = **execution metadata + 执行器返回值**, 分散在 4 处, 均非独立持久化事实:

| 位置 | 形态 | 持久化? | 语义 |
|---|---|---|---|
| verification.py (S5) | VerificationResult dict {verification_id: ver-*, status: PASS/FAIL/INCONCLUSIVE/BLOCKED} | **否** (返回即弃) | 真实 pytest/syntax subprocess 执行器 |
| EXS.verify (executor.py:288) | {method, result: pass/fail/unknown, score} | 是 (EXS 记录内嵌) | gateway auto_verify 回写 (执行元数据) |
| NodeRun.verification (node_runtime.py:153/289/293) | F2 finalize 吸收的 gateway verify dict | 是 (run 文件内嵌) | TaskRun 的 verify 元数据 |
| release checks/attempts (release_service) | chk-*/attempts 数组 | 是 (release 对象内嵌) | release 域验证 (S20) |

### Q3. 哪些地方执行 pytest/syntax/validation?
- verification.py: verify_python_syntax (ast.parse) + verify_pytest (subprocess)
- external_executor/executor.py: auto_verify (verify_hook subprocess / pytest)
- release_service._run_verification: 复用 verification.py
- effectiveness/health/recovery_service: 复用 verification.py
- factory-exec/exec/benchmark/verifiers.py: benchmark 专用
- session/answer_verify.py: 会话答案验证 (QA 域)

### Q4. 哪些地方产生 verification-like 数据?
见 Q2 表 (4 处: verification.py dict / EXS.verify / NodeRun.verification / release checks)。

### Q5. 哪些地方读取?
- gateway (final_ok 判定含 verify)、agent_loop finalize、release gate、
  effectiveness/recovery/health、WebUI (EXS verify 投影)、monitor (first_pass/verify_pass_rate)

### Q6. 是否存在多个 Verification SSOT?
**是 — 4 个平行 verification-like 事实源, 无语义统一, 无单一 SSOT:**
1. verification.py ver-* dict (不落盘, 最接近"执行器")
2. EXS.verify (result: pass/fail/unknown — 小写)
3. NodeRun.verification (result: PASS/FAIL — 大写, F2 finalize 写入)
4. release verification_attempts (result: PASS/FAIL)
状态词汇也不统一 (PASS/FAIL/INCONCLUSIVE/BLOCKED vs pass/fail/unknown)。

### Q7. F2 finalize_node_run 吸收的 verify metadata 是什么?
NodeRun.verification = gateway 返回的 verify dict ({method, result: pass/fail/unknown,
score, reason}) 原样存入 run 文件; 无独立 ver-* id (非 verification.py 的 ver-*),
**是 TaskRun 的执行验证元数据快照**, 不是 F3 要建的 Verification 事实对象。

### Q8. 该 metadata 是否可能与新 Verification 对象形成双重事实?
**是 — 若不处理**: NodeRun.verification (大写 PASS/FAIL) 与新 ver-* SSOT 并存会双真。
F3 必须: F2 metadata → F3 materialization 输入 (单一方向), ver-* 为唯一事实;
NodeRun.verification 保留为"展示快照"或指向 ver-* id (见 01-VERIFICATION-CONTRACT.md)。

### Q9. release_service verification 属于哪个层级?
release 域 (S20) 内嵌验证 — 属 **Release Gate 域**, 非 TaskRun 级 Verification。
F3 范围: 不并入 release; 标记为另一 domain (Release Verification), 验证执行器共用。

### Q10. WebUI 是否自行推断 verification 状态?
**否** — 只投影 EXS verify metadata (models/domain.ts:449 verify? 类型) 与执行证据展示
(AfWorkspace "暂无执行证据"); 无本地判断/无 localStorage verification truth。

## 2. 结论

- Verification **执行器已存在且真实** (verification.py / auto_verify / release checks)
- Verification **domain entity 不存在**: 无 ver-* 持久化对象、无 store、无唯一写者、
  无通用 audit 事件 (仅 RELEASE_VERIFICATION_*/NODE_RUN_VERIFYING)
- 4 处 verification-like 事实源语义不统一 → **F3 建 SSOT 必要性成立**
- WebUI 不拥有 truth; release 是独立域; legacy 无 verification (应保持 absent/UNKNOWN)

## 3. F3 最小范围界定 (不越界)

**建**: Verification domain (ver-* entity + store + 唯一写者), 挂 TaskRun/EXS,
真实执行路径复用 (verification.py + auto_verify), PASS/FAIL/UNKNOWN 语义,
F2 metadata 单向 materialization, audit 事件, API/CLI, E2E。
**不建**: Artifact/Evidence SSOT (F4), 不改 TaskRun/EXS/Task model, 不动 release 域,
不迁移 legacy, 不做 WebUI 大改。
