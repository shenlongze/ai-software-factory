# S10-034 Task 006 — PyPI Release Audit

> 日期:2026-08-14 | Sprint: S10-034 | 只读审计, 不发布
> 目标: 检查当前 package 是否适合发布 PyPI

---

## 1. Package 元数据检查

| 项 | 值 | 状态 |
|---|---|---|
| name | ai-software-factory | ✅ 合法(PyPI 名, 小写+连字符) |
| version | 1.0.0-rc1 | ⚠️ PyPI 接受 PEP 440 预发布版, 但正式首版建议 v0.1.0 |
| description | "AI Software Factory — 四层架构 AI 软件工厂..." | ⚠️ 技术向, 建议改用户向一句话 |
| readme | README.md | ✅ 已用户向(S10-031) |
| requires-python | >=3.12 | ✅ |
| license | Apache-2.0(LICENSE 文件) | ✅ |
| console script | factory = factory_console.cli_factory:main | ✅ 统一入口 |

## 2. 依赖检查

| 依赖 | 用途 | 状态 |
|---|---|---|
| pydantic>=2 | 模型 | ✅ |
| rich>=13 | Dashboard | ✅ |
| pyyaml>=6 | 配置解析 | ✅ |
| httpx>=0.27 | Provider HTTP | ✅ (S10-031 补) |
| fastapi>=0.110 | Web 后端 | ✅ (S10-031 补) |
| uvicorn>=0.29 | 后端服务 | ✅ (S10-031 补) |

## 3. Wheel 构建检查

| 项 | 状态 | 证据 |
|---|---|---|
| wheel 构建成功 | ✅ | ai_software_factory-1.0.0rc1-py3-none-any.whl |
| 含全部代码 | ✅ | factory_console 41 文件 + exec/org + dist |
| 前端 dist 打包 | ✅ | package-data |
| console script 可用 | ✅ | 全新 venv 验证 |

## 4. Clean Environment Install 测试

| 步骤 | 状态 | 证据 |
|---|---|---|
| 全新 venv 创建 | ✅ | python3.12 -m venv |
| pip install wheel | ✅ | 依赖自动解析 |
| factory 命令可用 | ✅ | 统一入口 |
| factory init | ✅ | workspace + providers.json |
| factory run | ✅ | 真实 DeepSeek 执行 (S10-031) |

## 5. 发布 PyPI 判断

**结论: 技术上适合发布(具备), 但有前置事项:**

| # | 事项 | 严重度 |
|---|---|---|
| 1 | version 建议改为 0.1.0(rc1 是预发布语义) | 建议 |
| 2 | description 改用户向(当前四层架构技术描述) | 建议 |
| 3 | PyPI 账号 + API token 配置 | 必需(用户决策) |
| 4 | twine 上传流程 | 简单 |
| 5 | CI token 权限(若 CI 发布) | 需 workflow scope |

**风险**: 无敏感信息(包不含 key); 无个人路径; 依赖完整。

## 6. 建议发布流程(用户决策后)

```bash
# 1. 改 version 0.1.0 + description 用户向 (pyproject.toml)
# 2. 构建
python -m build
# 3. 上传 (需 PyPI token)
python -m twine upload dist/*.whl
# 4. 验证
pip install ai-software-factory
```

---

> Task 006 完毕 | 审计结论: 技术上可发布, 前置 = version/description 微调 + PyPI 账号
