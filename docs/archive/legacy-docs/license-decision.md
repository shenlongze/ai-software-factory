# License 决策记录 (license-decision)

> 日期: 2026-08-06 | 归属: Phase 14A | 状态: 已决策 (Apache-2.0)

## 结论

**AI Software Factory 采用 Apache License 2.0** (见根目录 [LICENSE](../LICENSE))。
这是平台型开源项目的标准选择, 与 PostgreSQL / Elastic / Kubernetes 等生态一致。

## 为什么选 Apache-2.0 而非 MIT

| # | 理由 | 说明 |
|:-:|:-----|:-----|
| ① | **商业分层兼容** | 项目商业定位为 **Open Source Core + 商业服务** (见 [business-positioning.md](./business-positioning.md) §4: Personal/Team 协作付费, 开源底座永不阉割核心)。Apache-2.0 允许闭源衍生与商业再分发, 商业层 (协作/审计/托管服务) 可独立于开源底座授权, 互不污染。 |
| ② | **专利条款保护** | Apache-2.0 第 3 条是**明确的专利授权** (contributor 自动授予其贡献涉及的专利许可); 第 3 条末尾含**专利报复条款** — 若某贡献者起诉项目侵权, 其在本许可下获得的专利授权自动终止。对涉及算法/编排/经验学习等可专利领域的平台, 这是双向护城河。MIT 无任何专利条款。 |
| ③ | **贡献者协议明确** | 第 5 条 (Submission of Contributions): 任何人向项目提交贡献, 即默认按 Apache-2.0 授权, 无需额外 CLA — 贡献者署名 (第 4 条 c) 与授权边界 (第 1 条 Contribution 定义) 都写进许可证本身。MIT 靠默认版权法推断, 边界模糊。 |
| ④ | **生态一致 + 商标保护** | 平台类基础设施 (PostgreSQL、Elastic、Kubernetes、Apache 系) 均用 Apache-2.0; 第 6 条商标条款保护项目名不被滥用于衍生品, 为将来品牌化留余地。 |
| ⑤ | **免责与责任边界** | 第 7/8 条提供与 MIT 同等的 "AS IS" 免责与责任限制, 不增加采用者的合规负担, 但文本更严谨 (明确 NOTICE 文件机制)。 |

## MIT 被否原因 (记录在案)

MIT 是**过宽松许可**, 不适合本项目:

- ❌ **无专利条款** — 平台型项目无法防范专利风险, 也无法获得贡献者专利授权。
- ❌ **无商标条款** — "AI Software Factory" 名称可被任何衍生品冒用, 无法约束。
- ❌ **无贡献者协议** — 贡献授权依赖版权法默示推断, 多贡献者场景下边界不清。
- ❌ **与商业分层弱耦合** — MIT 本身不阻碍商业化, 但缺少专利/商标保护, 商业层 (含专有代码) 与开源底座之间缺乏明确的授权契约文本。
- ✅ 唯一优势是"极简" — 不构成选型理由。

## 影响

- 所有源文件保持现有版权归属; 新文件在头部标注 `Copyright 2026 The AI Software Factory Contributors` (社区贡献者共同署名, 见 LICENSE Appendix)。
- 商业服务层 (未来) 不受本许可限制, 可在开源底座之上另行授权。
- 第三方依赖许可合规不受影响: 项目依赖均为 MIT/Apache/BSD 类宽松许可, 与 Apache-2.0 兼容。

## 相关文档

- [business-positioning.md](./business-positioning.md) §4 — Open Source Core + 商业服务
- [CONTRIBUTING.md](../CONTRIBUTING.md) — 贡献流程 (Phase 14A 配套)
