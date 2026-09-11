# 12 — FIX SPRINT ORDER (STEP11)

## 依赖图
```
FX-02 (execution_plan 冻结) ── 独立
FX-01 (exec→backlog 引用)   ── 地基
   ├── FX-04 (Run 挂 Artifact)   [依赖 Run ID 稳定 = FX-01]
   ├── FX-05 (Model Selection)   [依赖 Task capability = 需 Task 语义稳定]
   └── FX-06 (Agent 触发)        [依赖 FX-01 执行域对齐]
FX-03 (Requirement 引用)      ── 独立 (可并行)
FX-07 (分析落盘)              ── 独立
FX-08 (Verification 取证)     ── 先行取证 (D 类, 无代码)
```

## Sprint 划分 (建议)
| Sprint | Fix | 理由 |
|--------|-----|------|
| S-FX0 | FX-08 取证 (Verification SSOT 归属决定) | 消除 D 类不确定 |
| S-FX1 | FX-02 + FX-01 (Execution Truth 落地) | 地基: 消除 Parallel Truth |
| S-FX2 | FX-03 + FX-07 (Requirement 引用 + 分析落盘) | 上游链 (可与 S-FX1 并行) |
| S-FX3 | FX-04 + FX-06 (Artifact 挂载 + Agent 触发) | 依赖 S-FX1 |
| S-FX4 | FX-05 (Model Selection 接入) | 依赖 S-FX1 + S-FX3 部分 |

## 原则
- Contract → SSOT → Relation → Domain → API → CLI/UI → E2E
- 每 Sprint 独立验收 (Evidence Matrix §11)
- FUTURE (PRD 实体/Learning/Replan/Release) 不排入 Fix Sprint (M3/M4)
