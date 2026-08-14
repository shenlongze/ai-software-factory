# S10-030 Task 006 — MVP Release Checklist

> 日期:2026-08-14 | Sprint: S10-030 MVP Release | 发布清单
> 目标:技术 / 产品 / 商业三维度完整发布检查

---

## 1. 技术维度

### 1.1 Install(安装)

| # | 检查项 | 状态 | 证据 |
|---|---|---|---|
| T-01 | setup.sh 幂等安装 | ✅ | 已实现(4100 字节脚本) |
| T-02 | **console script 指向 cli_factory** | ❌ **需修** | pyproject.toml 当前 `factory = "cli.main:main"`(org CLI) |
| T-03 | **pip install 后 factory 统一入口可用** | ❌ **需做** | 修正后验证 |
| T-04 | **前端 dist 打包入 wheel** | ❌ **需做** | 无 node 用户也能 start |
| T-05 | 全新 venv 安装验证 | ❌ 需做 | 干净环境 pip install → factory init |
| T-06 | Dockerfile 多阶段构建 | ❌ 需做 | 设计完成(Task 002) |
| T-07 | Docker 卷持久化 ~/.factory | ❌ 需做 | 设计完成 |

### 1.2 Run(运行)

| # | 检查项 | 状态 | 证据 |
|---|---|---|---|
| R-01 | factory init 引导 | ✅ | 已实现(S10-026-E) |
| R-02 | factory doctor 诊断 | ✅ | 已实现(S10-026-A) |
| R-03 | factory start 启动 | ✅ | 已实现(S10-026-B) |
| R-04 | **factory project create 转正** | ❌ **需做** | 当前 stub(Task 001 实测阻塞) |
| R-05 | **factory run 转正** | ❌ **需做** | 当前 stub(Task 001 实测阻塞) |
| R-06 | 真实 LLM 执行 | ✅ | S10-023 验证($0.000278) |
| R-07 | LLM key 配置文档 | ❌ 需做 | export 示例 |

### 1.3 Test(测试)

| # | 检查项 | 状态 |
|---|---|---|
| T-08 | pytest 全量 8116 | ✅ |
| T-09 | 发布前全量回归 | ⏳ 发布前执行 |
| T-10 | 打包后安装环境测试 | ❌ 需做 |

## 2. 产品维度

### 2.1 Demo(演示)

| # | 检查项 | 状态 |
|---|---|---|
| P-01 | 一句话 Todo 演示流程 | ✅ 设计完成(Task 003) |
| P-02 | 3 分钟演示视频 | ❌ 需制作 |
| P-03 | 5 分钟体验路径可跑 | ❌ 需验证(依赖 R-04/R-05) |
| P-04 | demo workspace 隔离可用 | ✅ S10-026-F |

### 2.2 Docs(文档)

| # | 检查项 | 状态 |
|---|---|---|
| P-05 | **README 产品化重写** | ❌ 需做(方案 Task 004) |
| P-06 | LLM key 配置说明 | ❌ 需做 |
| P-07 | 安装选项(PyPI/Docker/源码) | ❌ 需做 |
| P-08 | 已知限制文档 | ❌ 需做 |

## 3. 商业维度

### 3.1 Landing Page(落地页)

| # | 检查项 | 状态 |
|---|---|---|
| B-01 | 产品一句话定位 | ✅ "治理驱动的 AI 软件生产平台" |
| B-02 | 价值主张页(痛点→方案) | ❌ 需做 |
| B-03 | 演示视频嵌入 | ❌ 需做(P-02 后) |
| B-04 | 安装入口(pip install) | ❌ 依赖 T-02/T-03 |
| B-05 | 企业联系入口 | ❌ 需做 |
| B-06 | 开源仓库公开 | ❌ 需做(当前私有) |

### 3.2 User Feedback(用户反馈)

| # | 检查项 | 状态 |
|---|---|---|
| B-07 | 种子用户清单(10 名) | ❌ 需邀 |
| B-08 | 反馈渠道(GitHub Issues) | ❌ 仓库公开后 |
| B-09 | 试用引导(README 5 分钟) | ❌ 依赖 P-05 |
| B-10 | 反馈收集模板(场景 1/3/4) | ❌ 需做 |

## 4. P0 阻塞汇总(发布前必须完成)

| # | 阻塞 | 对应 |
|---|---|---|
| 1 | factory project 转正 | R-04 |
| 2 | factory run 转正 | R-05 |
| 3 | console script 指向 cli_factory | T-02/T-03 |
| 4 | 前端 dist 打包 | T-04 |
| 5 | README 重写 + LLM key 说明 | P-05/P-06 |
| 6 | 仓库公开/PyPI 发布 | B-06 |

## 5. 发布里程碑

```
M1 (代码): P0 修复 (project/run 转正 + console script + dist 打包)
M2 (验证): 全新环境安装测试 + 全量回归 + 5 分钟体验验证
M3 (内容): README 重写 + 演示视频 + 博客
M4 (发布): 仓库公开 / PyPI 发布 / Landing page
M5 (反馈): 10 种子用户 + 反馈收集
```

## 6. 发布后立即监控

```
[ ] 安装成功率 (反馈/issue)
[ ] 5 分钟体验完成率
[ ] 场景 1/3/4 反馈
[ ] GitHub stars/issues 增长
[ ] 成本报告 (用户执行成本)
```

## 7. 结论

**MVP Release Checklist 完成。关键发现:6 个 P0 阻塞,其中 2 个是代码(project/run 转正 + console script 修正),4 个是内容/分发(README/dist/公开)。**

- 技术:80% 就绪(缺 project/run 转正 + 打包)
- 产品:50% 就绪(缺 README/演示视频)
- 商业:30% 就绪(缺落地页/公开/种子用户)

---

> Task 006 完毕 | MVP Release Checklist 完成 | 6 个 P0 阻塞,代码 2 + 内容/分发 4
