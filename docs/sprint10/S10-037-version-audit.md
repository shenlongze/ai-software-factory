# S10-037 Task 001 — Release Version Audit

> 日期:2026-08-14 | Sprint: S10-037 Release Metadata Alignment | 只读审计, 未修改
> 原则: 不删除历史 tag/release; 只建立正确版本体系

---

## 1. 当前版本关系

| 项 | 当前 | 位置 |
|---|---|---|
| 历史 tag | v1.0.0-rc1 (commit d264408, 2026-08-06) | git tag + 远端 refs/tags |
| GitHub Release | "AI Software Factory v1.0.0-rc1" (Latest) | GitHub Releases (2026-08-06) |
| pyproject version | 0.1.0 | pyproject.toml (S10-036 已改) |
| README version | v0.1.0 | README.md (S10-036 已改) |
| Release Notes | v0.1.0 | docs/releases/v0.1.0.md (存在) |
| Release Checklist | v0.1.0 | docs/releases/v0.1.0-checklist.md (存在) |

## 2. 版本关系分析

```
历史: v1.0.0-rc1 (2026-08-06 早期 RC, 当时代码基线 9cad09a)
目标: v0.1.0 (当前代码 977ba70+, 正式首个社区版本)

问题: v1.0.0-rc1 的"1.x"版本号与当前 v0.1.0 的"0.x MVP"策略冲突
      (1.x 暗示生产平台, 但产品仍是 MVP)
```

## 3. 是否需要调整

按用户指令(第二版): **不删除历史**。

| 项 | 处置 |
|---|---|
| 历史 tag v1.0.0-rc1 | 保留(历史快照, 不删) |
| GitHub Release v1.0.0-rc1 | 保留(历史发布记录) |
| 当前版本体系 | 以 v0.1.0 为准(S10-036 已统一) |
| 版本策略文档 | 缺失 → Task 002 新建 docs/releases/versioning.md |

## 4. 结论

- **代码/文档版本已一致(v0.1.0)** — S10-036 完成
- **历史 rc1 保留不删**(用户原则)
- **缺口**: 版本策略文档(解释 v0.x/v1.x/v2.x 含义, 让历史 rc1 与当前 0.1.0 的关系清晰)

---

> Task 001 完毕 | 只读 | 代码版本已统一 v0.1.0 | 历史 rc1 保留 | 缺版本策略文档
