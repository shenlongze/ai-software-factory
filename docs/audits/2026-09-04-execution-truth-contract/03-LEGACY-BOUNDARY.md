# 03 — LEGACY BOUNDARY (P0-F0, 2026-09-04)

> Legacy / Historical / Current 边界 — 不强行重连历史数据

---

## 1. 对象分类表

| 对象 | ID 示例 | 判定 | 说明 |
|---|---|---|---|
| M3 orchestrator Task | task-e1-core, task-client-ui | **LEGACY** | orchestrator.py (CLI 旧体系); 最近事件 8/18; 代码仍被 CLI 路径引用但 Web 主链不经它 |
| M3 project 数字目录 | 1787033426 | **LEGACY** | orchestrator.py:3223 project_dir.name |
| 旧 TASK_STARTED/COMPLETED audit | (8/18 事件) | **HISTORICAL** | 只读保留; 不迁移/不重连当前 TASK-* |
| EXR 请求 | EXR-d606d3a1 (86 条) | **ADAPTER→LEGACY** | exec 域请求视图; output_refs 0/86 无链接; 保留只读 |
| execution_records (EXS) | EXS-2f301554 (100) | **CURRENT (结果记录)** | 保留; F1 加 task_run_id/task_id 锚点; 旧记录不清除 |
| exec/results.json | (85) | **PROJECTION** | EXS 子集投影 (85/100) |
| TASK-GW 委派 | TASK-GW-47d2c100 (9) | **ADAPTER (CURRENT)** | 委派控制面 (gateway); 保留其控制面职责; 不是 canonical execution |
| session_exec | (6, E2E) | **ORCHESTRATION STATE** | 会话编排; 现 6 文件为 E2E 测试痕迹; 处置待用户决定 (标记/清理) |
| execution_plan T-* | T-* | **HISTORICAL** (STEP10 D-9 已冻) | 冻结写入 |
| factory.db events | (7825) | **EVENT MIRROR** | 与 audit_events.json 并存; canonical authority 未声明 → 见 §3 |
| org/product artifacts | (24/10) | **OTHER DOMAIN** (org/product 工作流) | 不动 |

## 2. 边界原则 (冻结)

```
Legacy Runtime (M3 orchestrator / task-e1-* / 数字 project / 8-18 audit)
      ║
      ║  historical only — 只读保留为证据; 不进入 canonical chain
      ║  不迁移 / 不重连 / 不复制到当前 TASK-* 链
      ▼
Current Canonical Runtime
      Session → Plan → Task(TASK-*) → TaskRun(run-*) → Execution(EXS) → Artifact → Verify → Evidence → Audit
```

- **禁止**: 把 task-e1-* audit STARTED/COMPLETED 映射为当前 TASK-* 的执行证据
- **禁止**: 把 EXR (T001/T002) 记录重连为 backlog 任务的执行记录
- **允许**: 保留读取/查询 (历史审计可查), 不做写迁移
- **清理**: 6 个 E2E session_exec 遗留 → 需用户决策 (标记 abandoned 或清理); 本契约不代决

## 3. 事件存储 Canonical Authority 决策

| 存储 | 内容 | Canonical? |
|---|---|---|
| audit_events.json (5172) | AuditEvent (append-only, 全域动作) | **✓ CANONICAL AUDIT** (查询/追溯入口) |
| factory.db events (7825) | 事件镜像 (console.viewed/org.execution.*/intelligence.*) | **EVENT MIRROR (非 canonical; 只读消费; 不双写 canonical 事实)** |

决策: Audit 事实唯一 canonical = audit_events.json (AuditEmitter 统一写入);
factory.db = 镜像/次要事件存储, 不得作为 domain truth 来源; 两存储并存是历史事实,
本契约声明 authority, 不要求合并 (F 系列不迁移历史)。
