# S10-035 Task 004 — Release Version Review

> 日期:2026-08-14 | Sprint: S10-035 | 基于 pyproject.toml 实际检查

---

## 1. Package 元数据

| 项 | 值 | 状态 |
|---|---|---|
| name | ai-software-factory | ✅ 合法(PyPI 风格) |
| version | 1.0.0-rc1 | ⚠️ 预发布语义; 正式首版建议 0.1.0(或按用户选择) |
| description | "AI Software Factory — 四层架构 AI 软件工厂..." | ⚠️ 技术向; 建议用户向一句话 |
| readme | README.md | ✅ 用户向(S10-031/034) |
| requires-python | >=3.12 | ✅ |
| license | Apache-2.0(LICENSE 文件) | ✅ |
| console script | factory = factory_console.cli_factory:main | ✅ 统一入口(S10-031 修复) |

## 2. Dependencies

| 依赖 | 用途 | 状态 |
|---|---|---|
| pydantic>=2 | 模型 | ✅ |
| rich>=13 | Dashboard | ✅ |
| pyyaml>=6 | 配置 | ✅ |
| httpx>=0.27 | Provider HTTP | ✅ |
| fastapi>=0.110 | Web 后端 | ✅ |
| uvicorn>=0.29 | 后端服务 | ✅ |

**依赖完整(6 个, 全部运行必需)。**

## 3. Entry Points

```
[project.scripts]
factory = "factory_console.cli_factory:main"
```
✅ 指向统一入口(17+ 命令); S10-031 已验证 pip install 后可用。

## 4. Package Include

| 项 | 状态 |
|---|---|
| package-dir 映射 | ✅ factory_console→factory-console; exec→factory-exec/exec; org→factory-org/org |
| packages 显式列表 | ✅ factory-core 子包 + factory_console* + exec* + org |
| 前端 dist 打包 | ✅ package-data |
| wheel 构建 | ✅ S10-031 验证(非空壳, 含全部代码) |

## 5. Release 判定

| 检查项 | 结果 |
|---|---|
| 可构建 wheel | ✅ |
| 可安装 | ✅(全新环境验证) |
| 可运行 | ✅(真实执行) |
| 依赖完整 | ✅ |
| 无敏感信息 | ✅(S10-035-001) |
| 版本语义 | ⚠️ rc1 是预发布; 正式发布改 0.1.0 |
| description | ⚠️ 技术向, 建议改 |

**结论: 技术上完全可发布; 发布前建议微调 version(0.1.0)+ description(用户向), 非阻塞。**

---

> Task 004 完毕 | pyproject 审查通过 | 微调项: version 0.1.0 + description 用户向(可选)
