# AI Factory Versioning Strategy

> 位置: docs/releases/versioning.md | Sprint: S10-037 | 版本策略定义

---

## 版本语义

```
v0.x — MVP / Community
v1.x — Production Platform
v2.x — Enterprise Platform
```

## 各版本阶段

### v0.x — MVP / Community(当前)

| 项 | 说明 |
|---|---|
| 目标 | 社区验证 / 种子用户 / 产品市场契合(PMF)探索 |
| 能力 | CLI First, 真实 LLM 执行, Router, 审计基础 |
| 稳定性 | 功能可能变动; API 不保证向后兼容 |
| 示例 | **v0.1.0**(当前, 首个公开版本) |
| 节奏 | 里程碑式发布(非持续) |

### v1.x — Production Platform

| 项 | 说明 |
|---|---|
| 目标 | 生产可用 / 企业采用 / API 稳定承诺 |
| 能力 | v0.x 全部 + 稳定 API + 完整文档 + 迁移路径 |
| 稳定性 | 向后兼容承诺(SemVer); 破坏性变更须主版本升级 |
| 节奏 | 定期发布(月度/季度) |

### v2.x — Enterprise Platform

| 项 | 说明 |
|---|---|
| 目标 | 企业级治理 / 规模化部署 |
| 能力 | v1.x 全部 + Enterprise(Governance/RBAC/合规/分析) |
| 稳定性 | 最高; LTS 支持 |
| 节奏 | 企业发布通道 |

## 历史版本说明

| 版本 | 状态 | 说明 |
|---|---|---|
| v1.0.0-rc1 | 历史(保留) | 2026-08-06 早期 Release Candidate, 当时代码基线早期; 版本号语义超前于产品阶段, 现以 v0.1.0 为正式起点 |

## 发布规则

1. **不删除历史 tag/release** — 历史是审计记录, 保留
2. **当前版本 = 产品阶段最小版本** — 产品是 MVP 就发 v0.x, 不虚标 v1.x
3. **SemVer 语义**: MAJOR.MINOR.PATCH
   - MAJOR: 破坏性变更 / 阶段升级(0→1→2)
   - MINOR: 向后兼容的新功能
   - PATCH: 修复
4. **RC 预发布**: vX.Y.Z-rcN 用于发布前验证; 正式发布去掉 -rcN

## 当前版本

```
v0.1.0 — First public release (2026-08)
```

---

> Task 002 完毕 | 版本策略定义: v0.x MVP / v1.x Production / v2.x Enterprise
