# S10-028 Task 006 — Release Strategy

> 日期:2026-08-14 | Sprint: S10-028 Platform Architecture Freeze | 战略分析,未修改代码
> 目标:分析当前 CLI-first 之后的发布形态

---

## 1. 当前状态

- CLI first(17 命令,唯一入口 ./bin/factory)
- 安装:bash scripts/setup.sh(venv + editable install + 可选 npm)
- 分发:私有仓库(最大阻塞,S10-027 已识别)
- 版本:v1.0.0-rc1(tag 已存在)

## 2. 五种发布形态评估

### A. Python Package(PyPI)

| 维度 | 分析 |
|---|---|
| 内容 | pip install ai-factory(源码包 + console scripts) |
| 优势 | 安装最简单;Python 用户自然路径 |
| 劣势 | 前端 dist 需打包;依赖 node 构建;企业环境 pip 受限 |
| 适用 | 开发者/早期用户;Router/ControlPlane 独立产品(纯 Python) |
| 前置 | pyproject.toml 已就绪(editable install 在用);需加 console script 完整注册 |
| 优先级 | **第一优先** — 成本最低,打通分发 |

### B. Docker

| 维度 | 分析 |
|---|---|
| 内容 | ai-factory 镜像(后端 + 前端 dist + 内置运行时) |
| 优势 | 企业部署友好;环境一致;免 node 依赖 |
| 劣势 | 桌面用户不便;本地 LLM(ollama)需网络连通 |
| 适用 | 企业私有化部署;RAG/向量库集成场景 |
| 前置 | Dockerfile + 前端构建进镜像 + healthcheck |
| 优先级 | **第二优先** — 企业部署关键路径 |

### C. Desktop Installer

| 维度 | 分析 |
|---|---|
| 内容 | DMG(Windows/MSI、Linux/AppImage)本地应用 |
| 优势 | 最终用户体验好;自带 Python 运行时 |
| 劣势 | 打包成本高(需 PyInstaller/Tauri);每平台维护 |
| 适用 | 单机用户(MarkPad 已走过此路 — 未签名 DMG 内测) |
| 优先级 | 低(先 CLI/PyPI/Docker;桌面后续) |

### D. Cloud Version

| 维度 | 分析 |
|---|---|
| 内容 | SaaS 托管(多租户) |
| 优势 | 最大市场;订阅收入 |
| 劣势 | 运营成本;多租户隔离;合规;与"私有化"定位冲突 |
| 适用 | 远期(产品验证后);Router/Governance 拆出产品可能先 SaaS |
| 优先级 | 远期(12 月+);不阻塞当前 |

### E. Enterprise Deployment

| 维度 | 分析 |
|---|---|
| 内容 | 私有化部署包(离线安装/内网) |
| 优势 | 企业合规;数据不出内网 |
| 劣势 | 交付成本高;需文档/支持 |
| 适用 | Governance OS 企业版;金融/政企 |
| 优先级 | 中(与 Docker 组合,Governance 产品化时) |

## 3. 发布策略决策

```
Phase 1 (现在 → 1 月内): Python Package (A)
  - 打通分发 (解决私有仓库阻塞)
  - pip install + console scripts + 前端 dist 打包
  - 目标: 陌生用户能装能用

Phase 2 (1-3 月): Docker (B) + Enterprise 前置 (E)
  - 企业部署镜像 (后端 + 前端 + 可选内置向量库)
  - 离线安装包文档

Phase 3 (6 月+): Desktop (C) / Cloud (D)
  - Desktop: 基于独立产品 (Router/Governance) 而非母平台
  - Cloud: 独立产品 SaaS (Router/Governance 先试)
```

## 4. 各形态决策矩阵

| 形态 | 成本 | 覆盖面 | 企业适配 | 独立产品适用 | 优先级 |
|---|---|---|---|---|---|
| A. PyPI | 低 | 开发者 | 中 | ✅ Router 独立包 | **1** |
| B. Docker | 中 | 企业 | 高 | ✅ 全产品 | 2 |
| C. Desktop | 高 | 最终用户 | 低 | ⚠️ 远期 | 4 |
| D. Cloud | 高 | 大众 | 中 | ✅ Router SaaS | 5 |
| E. Enterprise | 中 | 政企 | 高 | ✅ Governance | 3 |

## 5. 发布就绪清单(承接 S10-027)

```
P0 (阻塞):
  [ ] 仓库转公开 / 或 PyPI 发布 (解决分发)
  [ ] console script 完整注册 (pip install 后 factory 可用)
  [ ] 前端 dist 打入 Python 包 (无 node 用户也能 start)
  [ ] README 四步指引 (clone→setup→init→start) + LLM key 说明

P1 (质量):
  [ ] factory version 命令
  [ ] Dockerfile + 镜像构建
  [ ] CHANGELOG / 发布说明

P2 (扩展):
  [ ] Router 独立包发布 (pip install ai-router)
  [ ] Governance 企业包 + 离线部署文档
```

## 6. 结论

**发布策略:CLI-first → PyPI 先行 → Docker 企业 → 独立产品 SaaS/桌面。**

- **PyPI 是当下唯一正确第一步**(成本最低,打通分发,验证市场)
- Docker 紧随(企业部署,免 node)
- Desktop/Cloud 是独立产品化后的事,不阻塞母平台
- 独立产品(Router/Governance)天然适合 PyPI + SaaS 双轨

---

> Task 006 完毕 | 发布策略分析完成 | 推荐: PyPI 先行 → Docker 企业 → 独立产品双轨
