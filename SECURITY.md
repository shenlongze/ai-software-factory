# Security Policy — 安全策略

> 归属: Phase 14B | 状态: 生效 (placeholder 已清理, 渠道见下)

## 支持的版本 (Supported Versions)

| 版本 | 支持状态 |
|:-----|:---------|
| v1.0 (latest) | ✅ 安全修复 |
| 更早版本 | ❌ 不支持, 请升级 |

只有当前主线 (main) 与最新发布版本接收安全修复。

## 报告渠道 (Reporting a Vulnerability)

**不要为未公开的安全漏洞开公开 GitHub Issue** — 请通过以下渠道私密报告:

1. **GitHub Security Advisory**: 在仓库 `Security → Report a vulnerability` 提交
   (推荐, 支持私密讨论与联合修复)。
2. **贡献渠道**: 一般问题 / 公开讨论走 [CONTRIBUTING.md](./CONTRIBUTING.md) 的贡献流程
   (GitHub Issues / PR); 涉及潜在安全问题时仍请先通过 Security Advisory 私密提交,
   修复发布前请不要公开漏洞细节。

> 说明: 项目未对外发布独立的安全联系邮箱, 所有安全报告统一经 **GitHub Security
> Advisory** 受理 (维护者会收到通知)。如不便使用 GitHub, 可在 Advisory 中注明需要
> 其他联系方式, 维护者会在私密讨论中提供; 此处不虚构邮箱占位。

请在报告中包含 (KISS):

- 影响组件 (factory-core / factory-console / cli / docs)
- 漏洞类型与严重性判断 (如能给出)
- 复现步骤 / PoC (最小可复现)
- 你使用的版本与运行环境

## 响应时间 (Response Times)

| 严重性 | 首次响应 | 修复目标 |
|:-------|:---------|:---------|
| Critical (CVSS 9.0–10) | 24 小时内 | 7 天内发布修复 |
| High (CVSS 7.0–8.9) | 48 小时内 | 14 天内发布修复 |
| Medium (CVSS 4.0–6.9) | 5 个工作日内 | 30 天内发布修复 |
| Low (CVSS 0.1–3.9) | 10 个工作日内 | 随下一版本修复 |

响应时间承诺以维护者可用资源为上限; 如果无法按时, 会在回复中给出新的时间表。

## 漏洞处理流程 (Disclosure Process)

```
报告 → 确认 (维护者复现/评估) → 私密修复 + 回归测试 → 发布安全版本
     → 公开披露 (修复发布后, 写入 Release Notes)
```

1. **确认**: 维护者评估报告, 确认漏洞后创建私密修复分支 (未修复前不公开)。
2. **修复**: 修复必须附带回归测试, 与日常质量门一致 (pytest + Vitest 全绿)。
3. **发布**: 安全修复进入下一个 patch 版本, Release Notes 标注 `Security`。
4. **披露**: 默认 **90 天协调披露** — 修复发布后公开漏洞详情与致谢 (如需提前公开, 可在报告中注明)。

## 安全基线 (Baseline)

- 本项目无硬编码密钥; 配置中的 Provider API Key 仅存于本地配置 (见
  [docs/configuration-model.md](./docs/configuration-model.md))。
- 报告者获得 [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) 同等保护, 不因善意报告受报复。
- 安全相关变更必须引用本策略, 禁止"顺手改"绕过回归测试。
