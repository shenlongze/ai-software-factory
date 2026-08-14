# S10-036 Task 004 — Git Tag Preparation

> 日期:2026-08-14 | Sprint: S10-036 | 版本元数据检查 + 更新

---

## 1. 版本信息检查

| 项 | 检查前 | 更新后 | 状态 |
|---|---|---|---|
| pyproject version | 1.0.0-rc1 | **0.1.0** | ✅ 已改 |
| pyproject description | 四层架构(技术向) | **AI Software Factory — An AI Workforce Operating System** | ✅ 已改 |
| wheel 构建 | — | **ai_software_factory-0.1.0-py3-none-any.whl** | ✅ 验证 |
| README 版本 | v1.0.0-rc1 | v0.1.0(Task 002 已改) | ✅ |
| Release Notes | v0.1.0 | v0.1.0 | ✅ |

## 2. 版本一致性确认

```
pyproject.toml:  0.1.0
README.md:       v0.1.0
release notes:   v0.1.0
wheel:           ai_software_factory-0.1.0
目标 tag:        v0.1.0
```

**全部一致(rc1 仅在历史 docs 中保留, 不修改历史)。**

## 3. Tag 准备

- 目标 tag: `v0.1.0`
- 打 tag 时机: 发布确认后(用户决策), 或本 Sprint 完成后
- tag 内容: Release Notes(docs/releases/v0.1.0.md)已就绪

## 4. 结论

**版本元数据已统一为 0.1.0, wheel 构建验证通过, 可打 tag v0.1.0。**

---

> Task 004 完毕 | version 0.1.0 统一 | wheel 构建成功 | tag v0.1.0 就绪
