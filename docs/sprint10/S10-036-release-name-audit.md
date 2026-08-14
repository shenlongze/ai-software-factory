# S10-036 Task 001 — Release Naming Consistency Audit

> 日期:2026-08-14 | Sprint: S10-036 Release Finalization | 只读审计, 未修改代码
> 目标: 统一产品名 / 描述 / 版本

---

## 1. 产品名检查

| 位置 | 当前 | 目标 | 状态 |
|---|---|---|---|
| README.md 标题 | AI Software Factory | AI Factory | ⚠️ 混用 |
| README.md 正文 | AI Factory(11/13/21 行) | AI Factory | ✅ |
| README.md 37 行 | AI Software Factory | AI Factory | ⚠️ |
| docs/releases/v0.1.0.md | AI Factory | AI Factory | ✅ |
| docs/release/v0.1.0-release.md | AI Software Factory | AI Factory | ⚠️ |
| vision-en/zh.md | AI Software Factory | AI Factory | ⚠️(愿景语境可接受) |
| pyproject name | ai-software-factory(包名) | ai-software-factory | ✅ 包名保留 |

**结论: 展示名统一为 "AI Factory"; 包名 ai-software-factory 保留(技术标识)。**

## 2. 描述检查

| 位置 | 当前 | 目标 |
|---|---|---|
| README 一句话 | AI Workforce Operating System — 管理你的 AI 员工 | ✅ 一致 |
| pyproject description | "四层架构 AI 软件工厂..." | ⚠️ 技术向, 改用户向 |
| vision | AI Workforce Operating System | ✅ |

**目标描述: "AI Software Factory — An AI Workforce Operating System"**

## 3. 版本检查 ⚠️

| 位置 | 当前 | 目标 | 状态 |
|---|---|---|---|
| pyproject.toml | 1.0.0-rc1 | 0.1.0 | ❌ 需改 |
| README.md (7/126/137 行) | v1.0.0-rc1 | v0.1.0 | ❌ 需改 |
| docs/releases/v0.1.0.md | v0.1.0 | v0.1.0 | ✅ |
| docs/release/v0.1.0-release.md | v0.1.0 | v0.1.0 | ✅ |
| 12 个 docs 文件 | v1.0.0-rc1(历史引用) | 保留(历史文档) | ⚠️ 历史保留 |
| wheel 文件名 | 1.0.0rc1 | 0.1.0(下次构建) | ⚠️ 待构建 |

**结论: 当前版本应发布为 v0.1.0; pyproject + README 需更新; 历史 docs 保留 rc1 引用(不篡改历史)。**

## 4. 其他不一致

| 项 | 状态 |
|---|---|
| README.zh-CN.md | ❌ 不存在(Task 002 提及; 非本 Task 阻塞) |
| docs/release/ vs docs/releases/ | ⚠️ 两个目录并存; release 文档在 releases/(新)与 release/(旧) |

## 5. 修复清单(本 Sprint 执行)

| # | 修复 | 位置 | Task |
|---|---|---|---|
| 1 | 版本 1.0.0-rc1 → 0.1.0 | pyproject.toml | 004 |
| 2 | 版本 v1.0.0-rc1 → v0.1.0 | README.md | 002 |
| 3 | 展示名统一 AI Factory | README/docs/release | 002 |
| 4 | pyproject description 用户向 | pyproject.toml | 004 |
| 5 | Release Notes 更新 | docs/releases/v0.1.0.md | 003 |

**历史 docs 中 rc1 引用保留(不修改历史记录)。**

---

> Task 001 完毕 | 命名不一致: 版本 rc1→0.1.0 (pyproject/README) + 展示名统一 + description 用户向
