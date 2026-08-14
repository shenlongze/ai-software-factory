# S10-030 Task 002 — Release Packaging Design

> 日期:2026-08-14 | Sprint: S10-030 MVP Release | 设计,未实现
> 目标:设计 Python package + Docker 两种发布形态

---

## 1. 现状

- pyproject.toml 已有:`factory = "cli.main:main"`(指向 org CLI — 需改)
- editable install 可用:`.venv/bin/factory`(org CLI)
- bin/factory 是统一入口(cli_factory.main)
- 前端 dist 已构建(8-13 05:13)

## 2. Python Package 设计

### 2.1 包结构

```
ai-factory (PyPI 包名)
├── pyproject.toml
├── factory-console/        # Console 层 (CLI + LLM 基础设施)
│   ├── cli_factory.py      # 统一入口
│   ├── cli_doctor.py / cli_services.py / ...
│   ├── llm_control.py / model_catalog.py / llm_router.py / agent_policy.py
│   └── web/                # FastAPI + 前端
├── factory-core/           # Core (冻结)
├── factory-exec/           # Execution
├── factory-org/            # Organization
├── factory-runtime/        # 沙箱
└── web-dist/               # 前端构建产物 (打包入 wheel)
```

### 2.2 console scripts 修正

```toml
[project.scripts]
factory = "factory-console.cli_factory:main"   # 统一入口 (替代 cli.main:main)
```

> ⚠️ 关键修正:当前 `factory = "cli.main:main"` 指向 org CLI,`pip install` 后用户得到的是 org CLI 而非统一入口。必须改为 cli_factory。

### 2.3 前端 dist 打包

- 前端构建产物 web-dist/ 打入 wheel(package_data)
- 运行时 factory start 优先从包内 dist 托管(static_dir=web-dist)
- 无 node 用户也能 start 前端(免 npm)

### 2.4 数据目录

- 运行数据:~/.factory/(HOME 可注入隔离)
- 包只含代码,不含用户数据

### 2.5 安装命令

```bash
pip install ai-factory          # 或 pipx install
factory init                    # 首次初始化
factory doctor                  # 诊断
factory start                   # 启动 (含前端)
```

## 3. Docker 设计

### 3.1 Dockerfile 架构

```dockerfile
# Stage 1: build (node + python)
FROM node:20 AS frontend-build
WORKDIR /src
COPY factory-console/web/frontend/package*.json ./
RUN npm ci
COPY factory-console/web/frontend/ ./
RUN npm run build                # → dist/

# Stage 2: runtime (python)
FROM python:3.12-slim
WORKDIR /opt/ai-factory
COPY --from=frontend-build /src/dist/ /opt/ai-factory/web-dist/
COPY . /opt/ai-factory/
RUN pip install -e .
EXPOSE 8011
VOLUME ["/root/.factory"]
ENTRYPOINT ["factory", "start", "--no-browser"]
```

### 3.2 服务模型(对接 Runtime Manager)

| 服务 | 容器内 | 说明 |
|---|---|---|
| backend | uvicorn 8011 | 内置 |
| frontend | 静态托管(web-dist) | 内置,免 node |
| runtime | 沙箱(可选) | 内置 |

### 3.3 卷与配置

```yaml
# docker-compose.yml
services:
  factory:
    build: .
    ports: ["8011:8011"]
    volumes:
      - factory-data:/root/.factory      # 数据持久化
      - ./projects:/root/.factory/projects  # 用户项目 (可选挂载)
    environment:
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}   # key 经环境注入, 不落盘
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8011/api/projects"]
```

### 3.4 企业部署形态

- docker-compose 单机(默认)
- docker stack / k8s(大规模,后续)
- 离线安装:docker save/load + 本地镜像仓库

## 4. 发布形态决策

| 形态 | MVP 优先 | 理由 |
|---|---|---|
| PyPI | ✅ 第一 | 开发者/创业团队自然路径;成本最低 |
| Docker | ✅ 并行 | 企业部署;免 node;版本一致 |
| tarball | ⚠️ 备选 | 私有仓库期可先发 GitHub release tarball |
| Desktop | ❌ 后续 | 成本高 |
| Cloud | ❌ 远期 | 单人无运维能力 |

## 5. 打包验证清单

```
Python:
  [ ] console script 指向 cli_factory (pip install 后 factory 是统一入口)
  [ ] 前端 dist 打包入 wheel (无 node 也能 start)
  [ ] 全新 venv 安装成功 (pip install ai-factory)
  [ ] factory init/doctor/start 在安装环境可用
  [ ] 8116 测试保持绿 (打包不影响)

Docker:
  [ ] 镜像构建成功 (多阶段)
  [ ] 容器启动 → 8011 健康
  [ ] 卷持久化 (~/.factory)
  [ ] key 环境注入 (不落盘)
```

## 6. 结论

**MVP 发布形态 = PyPI + Docker 双轨。**

- PyPI:开发者/创业团队,修正 console script + 打包前端 dist
- Docker:企业/无 node 环境,多阶段构建 + 卷 + key 环境注入
- 两者共用:CLI 统一入口 + ~/.factory 数据 + 8116 测试基线

---

> Task 002 完毕 | 发布包设计完成 | PyPI + Docker 双轨;关键修正 = console script 指向 cli_factory
