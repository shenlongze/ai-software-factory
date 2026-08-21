# AI Software Factory — Deployment 文档 (S10-074)

> 版本: 1.1.8 | 目标: macOS/Linux 本地部署 (wheel 分发)
> 本文档所有命令均经 Clean Environment E2E 真实验证 (scripts/deploy_e2e.sh)。

---

## 一、安装 (Install)

```bash
# 1. 构建 wheel (或从发布渠道获取)
python3 -m pip wheel . --no-deps -w dist/          # 在源码目录

# 2. 创建虚拟环境并安装
python3 -m venv .factory-venv
.factory-venv/bin/pip install dist/ai_software_factory-1.1.2-py3-none-any.whl

# 3. 验证
.factory-venv/bin/factory --version                # → AI Factory v1.1.8
```

要求: Python ≥ 3.12 (Node.js 仅 --dev 模式需要)。

## 二、配置 (Configuration)

三级配置 (优先级从高到低):

| 级别 | 位置 | 示例 |
|---|---|---|
| 环境变量 | 进程环境 | `LLM_API_KEY` `DATA_DIR` `PORT` |
| 项目 .env | 当前目录 .env | `LLM_PROVIDER=deepseek` |
| 用户配置 | ~/.factory/config.json | `{"llm": {"provider": "deepseek"}}` |

关键变量:

```bash
export DATA_DIR=~/.factory      # 数据目录 (默认)
export LLM_API_KEY=sk-...       # LLM Key (env > .env > config.json)
export LLM_PROVIDER=deepseek    # Provider
export PORT=8011                # 后端端口
```

## 三、Secrets 管理

- LLM_API_KEY 支持 `env:VAR` 引用 (`LLM_API_KEY=env:DEEPSEEK_API_KEY`)
- 源码/测试/日志均不落 Secret (Audit 脱敏 + 日志不打印 Key)
- 兜底链: provider 专属 env → OPENAI_API_KEY (开发环境)

## 四、初始化 (Init)

```bash
DATA_DIR=$PWD/.factory-data factory init            # 引导 Provider/模型配置
```

创建 `providers.json` + 数据目录结构。

## 五、启动 (Start)

```bash
factory start                                      # 后端 + 前端 (默认)
factory start backend --port 8011 --no-browser     # 仅后端 (无浏览器)
factory start --dev                                # 开发模式 (vite)
```

健康契约 (HTTP):

```bash
curl http://127.0.0.1:8011/health     # {"status":"ok","version":"1.1.8"}
curl http://127.0.0.1:8011/ready      # {"status":"ready","data_dir":"...","issues":[]}
curl http://127.0.0.1:8011/version    # {"name":"ai-software-factory","version":"1.1.8"}
```

## 六、停止 (Stop)

```bash
factory stop                                       # 读 pid 文件杀前后端 (干净)
```

- SIGTERM/SIGINT: 进程停止, 数据已落盘 (JSON/SQLite 原子写)
- 无 pid 文件 → 按端口 lsof 查找兜底

## 七、数据 (Storage)

```
~/.factory/
  ├── providers.json            # Provider 配置
  ├── config.json               # 用户配置
  ├── factory.db                # SQLite (核心状态)
  ├── audit/audit_events.json   # 审计事件
  ├── memory/experience_store.json  # 经验
  ├── projects/<slug>/          # 项目资产 (隔离)
  └── run/                      # pid + 日志
```

**卸载应用不删除数据** (uninstall ≠ purge)。

## 八、重启 (Restart)

```bash
factory stop && factory start
```

状态保留: Audit/Memory/Project/Experience 均持久化 (Clean E2E 已验证)。

## 九、升级 (Upgrade)

```bash
# 同数据目录升级: 数据保留
.factory-venv/bin/pip install --upgrade dist/ai_software_factory-<new>.whl
factory start                                      # 旧数据自动可用
```

- 存储为 JSON/SQLite 文件 (无 schema migration 需求 — 版本兼容由字段扩展保持)
- Upgrade E2E: 旧项目/Memory/Audit 在新版本可用

## 十、回滚 (Rollback)

```bash
# 升级失败 → 重装上一版本 wheel (数据目录不动)
.factory-venv/bin/pip install --force-reinstall dist/ai_software_factory-<old>.whl
factory start
```

- 数据目录与代码版本解耦 → 回滚安全 (文档化流程, 已真实验证重装路径)

## 十一、卸载 (Uninstall)

```bash
.factory-venv/bin/pip uninstall ai-software-factory   # 移除应用, 保留数据
rm -rf ~/.factory                                      # purge (仅确认后执行)
```

## 十二、常见问题 (Troubleshooting)

| 症状 | 原因 | 解决 |
|---|---|---|
| `No module named 'factory_console.audit'` | 旧 wheel 缺子包 | 重装 ≥1.1.2 wheel |
| start 找不到 python | 硬编码 .venv (已修复) | 升级到 ≥1.1.2 |
| /health 不可达 | 后端未起/端口错 | `factory doctor` + 检查 run/backend.log |
| CLI --version 无输出 | 源码态直接运行 | 用安装态 `factory` 命令 |

## 十三、验证 (Verification)

```bash
bash scripts/deploy_e2e.sh     # Clean Environment E2E (全自动)
```

覆盖: wheel 构建 → clean venv → init → start → /health /ready /version → stop → 数据保留 → uninstall。
