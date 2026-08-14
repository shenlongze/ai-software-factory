# S10-033 Task 001 — Public Repository Audit

> 日期:2026-08-14 | Sprint: S10-033 Public Release | 只读审计,未修改任何文件
> 目标:公开仓库前检查开源要素/敏感信息/可安装性

---

## 1. 开源文件检查表

| 项目 | 当前状态 | 问题 | 修复建议 |
|---|---|---|---|
| README.md | ✅ 113 行用户向(S10-031 重写) | 无 | — |
| LICENSE | ✅ Apache-2.0(201 行) | 无 | — |
| CONTRIBUTING.md | ✅ 125 行(贡献指南) | 无 | — |
| SECURITY.md | ✅ 63 行(安全策略) | 无 | — |
| CODE_OF_CONDUCT.md | ✅ 131 行 | 无 | — |
| CHANGELOG.md | ✅ 80 行 | 无 | — |
| .gitignore | ✅ 36 行(env/dist/venv/node_modules) | 无 | — |
| .env.example | ✅ factory-console/.env.example | 无 | — |
| .github/ISSUE_TEMPLATE | ✅ bug_report/feature_request/config | 缺 question.md | Task 007 补 |
| .github/PULL_REQUEST_TEMPLATE | ✅ 存在 | 无 | — |
| **CI workflow** | ❌ 缺失 | 无 GitHub Actions | **Task 新增**(pytest 门禁) |
| examples/ | ✅ markpad + markpad-demo | 与 demo 相关 | 保持 |

## 2. 敏感信息检查(重点确认)

| 检查项 | 结果 | 证据 |
|---|---|---|
| API key 明文 | ✅ 未发现 | 全仓扫描 sk-xxx / api_key= 无命中(排除 test 假 key) |
| 个人路径 | ✅ 仅注释提及 ~/.hermes(内容为"不读取") | config.py/workflow_runner.py 均是"解除依赖"说明 |
| .env 被跟踪 | ✅ 无 | git ls-files 无 .env/secret/pem |
| gitignore 覆盖 | ✅ 完整 | .env/dist/.venv/node_modules 全排除 |
| 仓库根未跟踪垃圾文件 | ⚠️ 中文 md 等(已知) | 公开前需 gitignore 或删除(见 §4) |

## 3. 可安装性检查(重点确认)

| 检查项 | 结果 | 证据 |
|---|---|---|
| 陌生用户可安装 | ✅(源码 setup.sh / wheel) | S10-031 全新 venv 端到端验证 |
| 全新环境可运行 | ✅ | pip install wheel → init → run 真实执行 |
| 依赖声明完整 | ✅ | pydantic/rich/pyyaml/httpx/fastapi/uvicorn |
| 版本元数据 | ⚠️ name=ai-software-factory v1.0.0-rc1 | description 是技术向(见 §5) |
| requires-python | ✅ >=3.12 | — |
| 前端 dist 打包 | ✅ 入 wheel | package-data 配置 |

## 4. 公开前必处理问题

| # | 问题 | 严重度 | 处置 |
|---|---|---|---|
| 1 | **仓库根 19 个未跟踪中文 md 垃圾文件**(CLI命令参考文档.md 等) | 高 | 公开前 gitignore 或删除(用户决策; 不 rm) |
| 2 | **无 CI workflow** | 中 | 新增 pytest 门禁(push 全绿) |
| 3 | pyproject description 是技术向(四层架构) | 低 | 改用户向一句话(S10-033 可做, 非代码) |
| 4 | 仓库私有 | 高 | 用户决策公开(外部无法 clone) |
| 5 | PyPI 未发布 | 中 | 用户决策(pip install 标"即将支持") |

## 5. 附加建议(公开质量)

| 项 | 建议 |
|---|---|
| 仓库 Topics | github 仓库设置: ai-agents/llm-router/software-factory 等(非代码) |
| About 描述 | 用户向一句话(非代码) |
| Badges | build/test/license(CI 后) |
| 分支保护 | main 保护 + PR 门禁(非代码) |
| 版本 tag | v1.0.0-rc1 已存在(2026-08) |

## 6. 结论

**公开就绪度:高(80%)**

- ✅ 开源要素齐全(LICENSE/CONTRIBUTING/SECURITY/CODE_OF_CONDUCT/CHANGELOG/README)
- ✅ 无敏感信息(key/个人路径/配置文件均安全)
- ✅ 陌生用户可安装可运行(S10-031 验证)
- ⚠️ 缺口:CI workflow + 仓库根垃圾文件 + question.md 模板

**本 Sprint(Task 002-007)补缺口:CI(可选)/question.md/快速开始/演示/愿景/发布清单。**

---

> Task 001 完毕 | 只读审计 | 公开就绪 80% | 无敏感信息, 可安装可运行
