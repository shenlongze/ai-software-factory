# AI Software Factory — 小白使用教程

> 版本: 1.1.7 | 适用: macOS / Linux | 读完本教程即可安装、使用、排查问题
> 所有命令均经过真实测试验证 (Clean Environment E2E)

---

## 一、AI Factory 是什么?

一句话: **管理你的 AI 员工, 而不是用 AI 聊天。**

它能帮你:
- 用自然语言描述想法 → 自动完成"需求分析 → 规划 → AI 编程 → 测试 → 交付"全流程
- 记住历史经验, 下次遇到类似问题自动复用
- 审计 AI 干了什么、花了多少钱、为什么这么干

---

## 二、安装 (5 分钟)

### 前提

- Python ≥ 3.12 (macOS: `brew install python@3.12`)
- 有 LLM API Key (如 DeepSeek / Anthropic)

### 步骤

```bash
# 1. 拿到安装包 (wheel 文件, 后缀 .whl)
#    从发布渠道下载 ai_software_factory-1.1.7-py3-none-any.whl

# 2. 建独立环境 (推荐, 不污染系统 Python)
python3 -m venv factory-venv
factory-venv/bin/pip install ai_software_factory-1.1.7-py3-none-any.whl

# 3. 验证安装
factory-venv/bin/factory --version
# → AI Factory v1.1.7   (看到这个就装好了)
```

> 💡 以后所有命令都要带 `factory-venv/bin/` 前缀。
> 想让 `factory` 直接可用: 把 `factory-venv/bin` 加入 PATH:
> `echo 'export PATH="$HOME/factory-venv/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc`
> (之后直接敲 `factory` 即可, 本教程用 `factory` 表示)

---

### 一步到位: 一键安装 (推荐)

```bash
# 在源码目录 (或下载 install.sh 后):
bash scripts/install.sh                # 自动: 找 Python → 构建 wheel → venv → 安装 → 验证

# 常用选项:
bash scripts/install.sh --dir ~/factory-venv     # 指定安装目录
bash scripts/install.sh --wheel x.whl            # 用现成安装包 (不用源码)
bash scripts/install.sh --init --provider deepseek  # 安装后自动初始化 LLM
bash scripts/install.sh --deploy                 # 一键全自动部署 (安装+初始化+启动+健康检查)
```

`--deploy` 完成后系统已运行, 直接访问 http://127.0.0.1:8011 (或对话: `factory`)。

---
## 三、首次配置 (初始化)

```bash
factory init
```

它会引导你:
1. 检查环境 (Python/依赖)
2. 创建数据目录 `~/.factory`
3. 配置 LLM Provider (选 DeepSeek/Anthropic 等, 输入 API Key)

**重要**: API Key 只存"引用"不存明文 —— 推荐用环境变量:

```bash
# 先设置环境变量 (把 sk-xxx 换成你的 Key)
export DEEPSEEK_API_KEY=sk-xxx
# 再初始化, 选择 env:DEEPSEEK_API_KEY 引用
factory init
```

配置后自检:

```bash
factory doctor        # 全面诊断 (环境/Provider/模型/路由) — 全部 OK 即可继续
```

---

## 四、启动服务

```bash
factory start                    # 启动 后端 + 网页控制台 (浏览器自动打开)
factory start backend            # 只启动后端 (无浏览器)
factory stop                     # 停止 (干净退出)
factory status                   # 查看运行状态 (端口/进程/数据目录/LLM)
```

启动后验证 (健康检查):

```bash
curl http://127.0.0.1:8011/health
# → {"status":"ok","version":"1.1.7"}
curl http://127.0.0.1:8011/ready
# → {"status":"ready", ...}
```

---

## 五、日常使用 (两种方式)

### 方式 A: 直接敲命令 (适合确定要做什么)

```bash
# 查看项目
factory project list

# 执行一个任务 (把 AI 员工派给某个任务)
factory run --project /path/to/project --objective "实现登录接口" --requirement "支持手机号+验证码"

# 查看执行结果
factory run-status --id <结果ID>

# 查看审计 (AI 干了什么)
factory audit --limit 20          # CLI 最近事件
# 完整审计 (事件/决策链/解释) 在对话式里说: "查看审计记录" / "审计决策链" / "为什么停了"
```

### 方式 B: 对话式 (适合"我还不知道要什么")

```bash
factory
```

直接进入对话界面, 输入想法即可, 例如:

```
> 我想做一个台球计分 App
```

AI Factory 会:
1. 多轮澄清需求 (目标用户/核心功能/平台)
2. 确认后自动: 产品分析 → 市场分析 → 规划 → 分配 AI 员工 → 写代码 → 测试 → 交付
3. 过程中你可以随时问: "为什么停了?" "检查一下失败原因" "自动修复"

### 常用命令速查

| 命令 | 作用 |
|---|---|
| `factory init` | 初始化/重新配置 |
| `factory doctor` | 诊断环境问题 |
| `factory start` / `stop` / `status` | 启动/停止/查看服务 |
| `factory config check` | 检查配置 |
| `factory run --project X --objective "..."` | 执行任务 |
| `factory run-status` | 查看执行结果 |
| `factory project list` | 项目清单 |
| `factory audit --limit N` | 查看审计记录 (最近事件) |
| 对话式: "查看审计记录"/"审计决策链" | 完整审计 (决策链/解释) |
| `factory demo init` | 创建演示环境 (零污染) |

---

## 六、数据都在哪?

```
~/.factory/
  ├── providers.json          # LLM 配置 (Key 引用, 非明文)
  ├── config.json             # 你的配置
  ├── factory.db              # 核心状态 (SQLite)
  ├── audit/audit_events.json # 审计事件 (AI 干了什么)
  ├── memory/experience_store.json  # 经验 (AI 学到什么)
  └── projects/<项目名>/      # 每个项目的资产 (PRD/计划/代码)
```

- **重启不丢数据**: stop 后再 start, 项目/经验/审计全都在
- **换机器**: 把 `~/.factory` 整个拷走即可 (迁移 = 复制目录)

---

## 七、注意事项 (重要!)

### 1. API Key 安全
- ✅ 推荐 `env:DEEPSEEK_API_KEY` 引用 (Key 只在环境变量里)
- ❌ 不要把 Key 写进 providers.json / config.json / 代码
- Key 不会出现在日志/审计中 (系统自动脱敏)

### 2. 多项目隔离
- 每个项目的数据独立存放 (`~/.factory/projects/<项目名>/`)
- A 项目的经验/审计, B 项目**看不到** (系统强制隔离)
- 只有"全局经验"所有项目共享

### 3. 预算控制 (防烧钱)
- 系统有预算闸: 预算耗尽 → 自动暂停 → 请求你审批
- 需要时配置: `factory config` (设置 max_total_cost 等)

### 4. 端口冲突
- 默认后端 8011 / 前端 (自动)
- 冲突时: `factory start backend --port 9001` 换端口
- 异常退出后起不来: 先 `factory stop` 再 `factory start`

### 5. 升级 / 回滚
- 升级: 直接安装新 wheel (数据不动, 自动兼容)
- 回滚: 重装旧 wheel (数据目录不动, 安全)
- 卸载 ≠ 删数据: `pip uninstall` 只删程序; 数据在 `~/.factory`, 确认后才手动删

### 6. 首次使用建议
- 先 `factory demo init` 玩演示环境 (零污染), 熟悉后再用真环境
- 一切异常先跑 `factory doctor` 看诊断
- 日志在 `~/.factory/run/*.log` (排查问题时给日志)

---

## 八、常见问题 (FAQ)

| 问题 | 解决 |
|---|---|
| `factory` 命令找不到 | 检查 PATH (见安装第 3 步) 或直接用 `factory-venv/bin/factory` |
| init 时 Key 配置失败 | 先 `export 你的_KEY=sk-...` 再 init; 确认 Provider 名称正确 |
| start 后网页打不开 | `factory status` 看端口; 浏览器访问 http://127.0.0.1:8011 |
| 任务一直"处理中" | 看 `~/.factory/run/backend.log` 尾部; 常见是 LLM Key 无效 |
| 预算突然停了 | 这是保护: `factory audit events` 看 BUDGET_BLOCKED, 调整预算后继续 |
| 升级后报错 | 大概率旧 wheel 缓存: 重装新 wheel 并 `factory doctor` |
| 想彻底卸载 | `pip uninstall ai-software-factory`; 数据确认后 `rm -rf ~/.factory` |

---

## 九、从零开始完整示例 (10 分钟体验)

```bash
# 1. 安装 (见上文)
# 2. 初始化
export DEEPSEEK_API_KEY=sk-xxx
factory init --provider deepseek --non-interactive
factory doctor

# 3. 对话创建产品 (交互式)
factory
# > 我想做一个记账 App
# > 核心功能: 记支出、看统计
# > ... (按提示确认)

# 4. 或者用命令直接跑任务
factory run --project ~/.factory/projects/记账 --objective "写一个支出录入接口" --test-cmd "pytest"

# 5. 看 AI 干了什么 (对话式)
#    (在 factory 对话里说: "查看审计记录" / "这个项目花了多少钱")
factory audit --limit 10
factory run-status

# 6. 用完关服务
factory stop
```

---

*更多开发细节见 docs/DEPLOYMENT.md (安装/升级/回滚) 与 docs/sprint10/ 各 Sprint 报告。*
*遇到问题: 先 `factory doctor`, 再查 `~/.factory/run/*.log`, 最后反馈日志。*
