# S7-002 — Artifact System（Completion Report）

> 日期: 2026-08-08 | 状态: 完成 | pytest 全绿 (≥5733)
> Sprint 7A: Execution Foundation (S7-002 Artifact System — 阶段产物完整生命周期)

## 实现概述

S7-002 把阶段产物从 S7-001 的基础占位 (create_artifact) 升级为完整 Artifact System:
**产物生命周期状态机 + 类型契约 + CRUD/组合查询 + 全转换审计事件**。每阶段产物 =
下一阶段输入 (PRD → Design → Code → Test → Release), 契约严格定义缓解
架构风险 1 (阶段间 Artifact 契约需严格定义 — sprint7-architecture §6)。

设计依据: sprint7-architecture.md §1/§3/§6 (生命周期 CREATED→GENERATED→
VALIDATED→CONSUMED→ARCHIVED, 异常 INVALID 可重生成恢复)。

## 新增文件

```
factory-org/org/artifact.py        (ArtifactSystem 核心: CONTRACTS 类型契约 +
                                   validate_artifact 纯函数 + ArtifactRegistry
                                   CRUD/状态机/组合查询 + ArtifactError/StateError)
tests/s7/test_s7_artifact_model.py        (模型全字段/默认值/宽容解析/向后兼容)
tests/s7/test_s7_artifact_contract.py     (CONTRACTS 5 类型契约 + validate_artifact)
tests/s7/test_s7_artifact_registry.py     (CRUD + 软删 + 关联校验 + 查询组合)
tests/s7/test_s7_artifact_lifecycle.py    (状态机合法链/失败恢复/非法跳转/幂等)
tests/s7/test_s7_artifact_events.py       (6 事件 payload 契约 + 静默 + 兼容)
tests/s7/test_s7_artifact_cli.py          (artifact 子命令集成: create/get/list/
                                           query/update/archive/validate)
```

## 修改文件

```
factory-org/org/projects.py        (Artifact 扩展全字段 + ArtifactStatus 枚举 +
                                   ARTIFACT_TRANSITIONS 受控转换表 — 默认值向后兼容)
factory-org/org/events.py          (+6 record_artifact_* 转换/读命令审计函数)
factory-org/org/cli.py             (artifact 子命令 create/get/list/query/update/
                                   archive/validate + --json 输出 + rc 语义)
factory-core/events/models.py      (EventType +6 org.artifact.* 枚举成员) — 允许例外
tests/s7/conftest.py               (registry/no_logger_registry fixtures)
tests/s7/s7_helpers.py             (make_artifact_full 完整模型构造工厂)
```

约束遵守: Core/Runtime/Desktop diff = 0 (events/models.py 枚举 +6 允许例外);
未触碰 scripts_diag_empty.py; 零 LLM/零执行副作用 (真实生成留给 S7-005 编排壳);
不删既有能力 (S7-001 create_artifact 原样保留, 与 Registry 共享 store)。

## 数据模型

```
Artifact (org/projects.py, S7-001 基础字段 + S7-002 扩展全默认值 — 加载零破坏):
  id / stage_id / type (prd|design|code|test|release) / ref          [既有]
  project_id / task_id        关联维度 (task 须经 ProjectTaskLink 关联该项目)
  producer_role / producer_agent   生产者 (role 经 exec 注册表校验, 未安装跳过)
  version (默认 "1") / location (file:// / ref://)
  status (默认 created) / metadata (契约校验载荷 dict)
  created_at / updated_at / archived_at (软删时间) / invalid_reason (失败审计)
  is_archived 属性 (archived 终态判断)

状态机 (ARTIFACT_TRANSITIONS 受控转换表, 非法跳转 → ArtifactStateError):
  created   → generated, invalid
  generated → validated, invalid
  validated → consumed, archived, invalid
  consumed  → archived, invalid
  invalid   → generated (重生成恢复), archived (废弃)
  archived  → () 终态
  ★ CREATED 不能直接 ARCHIVED (软删须经受控链); 同状态转换幂等 (不发事件)

类型契约 (CONTRACTS 声明式, artifact.py — 契约与枚举同源):
  prd:      problem/user/features      design: architecture/api/database
  code:     files/changes              test:   results/bugs
  release:  version/notes/artifact_ref
  validate_artifact 纯函数 → ValidationResult (missing/errors; 调用方决定置 INVALID)
```

## API / CLI

```
ArtifactRegistry (factory-org/org/artifact.py):
  create(stage, type, *, project_id/task_id/ref/producer_*/version/location/
         metadata/artifact_id) — 关联校验 (stage/project 必须存在; task 须已 link)
  get / list(include_archived=False) / update(*fields)  — archived 不可改 (immutable)
  transition(to_status, *, reason, event_extra) — 受控转换 (审计事件)
  mark_generated / validate(payload?) → (artifact, result) / consume / fail / archive
  query(project/stage/task/type/status, include_archived) — AND 组合过滤, 软删语义

CLI (factory-org/org/cli.py, 子命令 artifact):
  artifact create|get|list|query|update|archive|validate
  rc 语义: 0 成功 (validate 校验失败也是 0 — 受控结果 result.ok=False)
           rc 1 业务错误 (非法转换/未知角色/archived immutable)
           rc 7 未找到 (stage/project/task-link/artifact NotFoundError)
  --json 输出 (ok/artifact/result/count/event_seq) + --metadata/--payload JSON
  每个 CLI 行为产生事件 (ADR-0002): 写路径 org.artifact.*, 读命令 org.artifact.viewed
```

## 事件 (org.artifact.* +6, 枚举 165 → 171)

```
org.artifact.created    既有 4 字段 (artifact_id/stage_id/type/ref) + project_id/
                        status/version 扩展 + 事件顶层 project_id/task_id (向后兼容)
org.artifact.updated    字段更新 (from=to) 或 →generated 转换; changed_fields/version
org.artifact.validated  →validated; missing/errors 明细
org.artifact.consumed   →consumed; from_status/version
org.artifact.failed     →invalid; reason + missing/errors (审计唯一事实源)
org.artifact.archived   →archived 终态; from_status/version
org.artifact.viewed     读命令审计 (count/filters, source="cli", ADR-0002)
logger=None 全静默 (同既有 org 模式); payload 可重建产物流转关键字段
```

## 测试结果

```
tests/s7: 224 passed (含 S7-001 既有 + S7-002 新增 ~123)
pytest 全量: 5745 passed, 0 failed (≥5733 目标达成)
Core/Runtime/Desktop diff = 0 (events/models.py 枚举 +6 允许例外;
tests/intelligence 枚举计数测试 165→171 同步更新 — S7-001 既定伴生模式)
修复: 11 个测试期望错 (created 直接 archive 违反设计状态机 / seed_stage 自身
产生 org.stage.created 致全量断言误报 / payload_of 取首条 updated) — 实现未改
```

## 对 Workflow Engine 支持 (S7-005)

S7-002 为 S7-005 组织级编排壳提供完整支撑:

```
1. 阶段产物即工作流上下文: 前一阶段 Artifact 自动成为下一阶段输入 —
   Registry.query(stage/type/status) 精确取上游产物, validate_artifact 校验
   契约后置 validated 才放行下一阶段 (人工闸门保持)
2. 失败恢复路径: 执行失败 → fail (invalid + invalid_reason) → 重生成
   (invalid→generated) 或废弃 (invalid→archived) — 编排壳直接映射
3. 审计闭环: 每转换 org.artifact.* 事件 (from/to/version/missing/errors) —
   编排可回放产物流转, 从事件重建失败原因 (唯一事实源)
4. 引用完整: stage/project/task 关联校验 — 编排壳创建产物时无需重复校验
5. 类型契约: CONTRACTS 声明式 (新增产物类型 = 枚举加成员 + 表加条目单点扩展)
```

## 下一步

```
S7-003 Architect Agent executable (依赖 S7-002 Artifact 作为 PRD 输入)
```
