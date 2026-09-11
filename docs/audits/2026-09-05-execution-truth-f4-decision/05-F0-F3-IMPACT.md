# 05 — F0-F3 IMPACT (P0-F4 DECISION, 2026-09-05)

> 静态影响分析 — D1-D4 不得重定义 F0-F3

---

## 1. 逐项核对

| 冻结语义 | D1-D4 影响 | 结论 |
|---|---|---|
| Task = TASK-* | 无 (Artifact/Evidence 在 Task 之下新增, 不改 Task) | 无冲突 |
| TaskRun = run-* NodeRun | D1 复用 node_run_id 字段; 无新 run 类型 | 无冲突 |
| Task.exec_ref → EXS only | 无 (Artifact 不碰 exec_ref) | 无冲突 |
| EXS = EXS-* | art.exs_id 新增**引用** EXS (只读方向), 不改 EXS | 无冲突 |
| Verification = ver-* (F3 SSOT) | D3 ver.evidence_ref 填充 (F3 已预留字段), 不改 ver 状态机 | 无冲突 |
| NodeRun.verification = 快照非 SSOT | 无 | 无冲突 |
| Audit = observation | EVD/art 的 audit 事件保持 observation | 无冲突 |
| Legacy 隔离 | exec ART-*/org/ev-*/EXR 等全部保持 legacy | 无冲突 |

## 2. 需新增 (非重定义) 的字段/对象

- art.exs_id: create_artifact 新可选参数 (向后兼容, 旧调用不传 = 空)
- art.verification_refs 或 ver.artifact_refs: 多对多 join (F4 impl 选向; 不改
  ver/art 已有语义)
- EVD-* Evidence domain: 全新 (与 ev-* 分离)
- 这些是**扩展**, 非对 F0-F3 冻结语义的修改

## 3. STOP 检查

未触发任何 STOP condition:
- 无需改 Task/TaskRun/EXS identity
- 无需改 Verification SSOT 语义
- 无历史数据迁移/伪造要求 (D1-D4 全 legacy 隔离)
- Audit 保持 observation
- WebUI 保持 projection

## 4. 结论

**F0-F3 零冲突。** D1-D4 冻结不要求修改任何已提交契约 (d849a108 + 794e24d7)。
唯一代码级变化 (exs_id 参数 / FK join / EVD store) 全部属 F4 implementation 扩展。
