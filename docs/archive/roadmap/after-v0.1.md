# AI Factory Roadmap — After v0.1.0

> 位置: docs/roadmap/after-v0.1.md | 创建: 2026-08-14 | Sprint: S10-039
> 基线: v0.1.0 (8148 tests green, CLI-first MVP)

---

## v0.2 — User Experience

目标: 让现有 MVP 更好用、可验证、可传播。

| 项 | 说明 |
|---|---|
| User experience | 安装/初始化/运行体验打磨 |
| UI improvement | Web 管理台增强(执行触发/审批视图) |
| Demo | 自动演示脚本(一句话建 Todo)+ 演示视频 |
| Feedback | 种子用户反馈闭环(收集 → 修阻塞) |
| 其他 | PyPI 发布 / 仓库公开 / CI 生效 |

**验收**: 陌生用户 5 分钟完成首次真实任务; 反馈渠道畅通。

## v0.3 — Intelligence

目标: 增加知识/评估/记忆能力。

| 项 | 说明 |
|---|---|
| Project RAG | 项目级知识库(自动索引/检索; Managed 先行, 外部向量库后置) |
| Evaluation | 评估平台(候选评估/质量门/CI 集成) |
| Memory | 跨会话经验/记忆(Experience 提取增强) |
| 其他 | 智能路由(usage 反馈学习, Phase 5) |

**验收**: 项目问答可用; 产出可评估; 经验可复用。

## v1.0 — Production Platform

目标: 生产可用 + 企业级治理。

| 项 | 说明 |
|---|---|
| Enterprise Governance | 企业级治理引擎(审批策略/流程编排) |
| Organization | 组织域增强(多用户/多角色/多租户) |
| Policy Engine | 策略引擎(RBAC/动态规则替代硬编码) |
| 其他 | API 稳定承诺 / 向后兼容 / LTS |

**验收**: 企业可采用; API 稳定; 治理完备。

## 版本语义(见 versioning.md)

```
v0.x — MVP / Community
v1.x — Production Platform
v2.x — Enterprise Platform
```

## 优先级原则

1. 用户反馈优先(先修 v0.1 阻塞)
2. 社区价值优先(开源获客)
3. 治理是护城河(Enterprise 差异化)
4. 不追求功能堆砌(每版聚焦)

---

> Task 002 完毕 | Roadmap 规划: v0.2 UX → v0.3 Intelligence → v1.0 Governance
