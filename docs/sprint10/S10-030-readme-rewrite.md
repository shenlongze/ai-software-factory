# S10-030 Task 004 — README Product Rewrite

> 日期:2026-08-14 | Sprint: S10-030 MVP Release | 改造方案(不直接改 README)
> 目标:README 从"技术介绍"转为"用户向":解决什么问题 / 如何安装 / 5 分钟体验

---

## 1. 现状诊断

| 维度 | 现状 | 问题 |
|---|---|---|
| 定位 | 268 行技术文档 | 面向架构师,不面向用户 |
| 内容 | 四层架构/生命周期/理念/Quick Start(旧命令) | 用户不关心架构,只关心"能帮我做什么" |
| Quick Start | 旧命令(factory demo markpad 等) | 与新 CLI(init/doctor/start)脱节 |
| 首屏 | 架构图 + 定位 | 无"解决什么问题"的直觉回答 |
| 演示 | 终端脚本 demo.sh | 无"5 分钟体验"引导 |

## 2. 改造目标

README = 产品首页(用户 30 秒决定是否试用):
1. 解决什么问题(痛点共鸣)
2. 如何安装(2 分钟)
3. 5 分钟体验(第一个 Todo)
4. 完整能力(用户能继续探索)

## 3. 新 README 结构

```markdown
# AI Software Factory

> 一句话: 治理驱动的 AI 软件生产平台 —— 管理你的 AI 员工, 而不是用 AI 聊天。

## 它解决什么问题 (用户视角)
- 你的 AI 编码工具不可控? 没有审计? 成本失控?
- AI Factory 让 AI 像软件公司员工一样工作: 理解需求 → 规划 → 开发 → 受治理 → 可审计

## 5 分钟体验 (核心)
### 1. 安装 (2 分钟)
```bash
pip install ai-factory        # 或: git clone + bash scripts/setup.sh
factory init                  # 首次初始化 (配置你的 LLM Provider)
factory doctor                # 诊断环境
```
### 2. 第一个 Todo (3 分钟)
```bash
factory start                 # 启动
# 浏览器打开 → 输入 "创建一个Todo Web应用" → 看 AI 员工工作
# 或 CLI:
factory project create --name todo-app
factory run --task T-001 --agent backend-1
```
### 3. 看到什么
- 真实 LLM 执行 (不是 demo 数据)
- 审批门: AI 产出等你批准
- 全审计: 谁/什么/何时/哪个模型/多少钱

## 能力一览 (用户向)
- ✅ 多模型路由 (DeepSeek/OpenAI/Claude/Ollama 智能选择)
- ✅ 真实代码执行 + 人工审批
- ✅ 全事件审计
- ✅ 项目生命周期 (Idea → 产品 → 代码 → 测试 → 发布)
- ✅ CLI First (无 UI 也完整可用)

## 架构 (一句话, 技术读者)
治理底座 + 可插拔能力 (详见 docs/architecture/)

## 开发者
- 源码构建: docs/development.md
- 架构: docs/architecture/
- 测试: pytest 8116
```

## 4. 删除内容(从 README 移除)

| 删除 | 理由 | 去向 |
|---|---|---|
| 四层架构图细节 | 用户不关心 | docs/architecture/ |
| Lifecycle 12 阶段模型 | 深度内容 | docs/lifecycle-model.md |
| 四条核心理念 | 团队价值观(非用户向) | docs/vision.md |
| 旧 Quick Start(factory demo markpad) | 命令已变 | 新 5 分钟体验替换 |
| Feature Matrix 技术细节 | 用户向能力一览替换 | docs/feature-matrix.md |

## 5. 新增内容

| 新增 | 内容 |
|---|---|
| 5 分钟体验 | 安装 → 初始化 → 第一个 Todo(核心!用户最快见价值) |
| 安装选项 | PyPI / Docker / 源码(三种) |
| LLM key 配置说明 | export DEEPSEEK_API_KEY=...(具体示例) |
| 截图/GIF | 演示视频链接(发布后补) |
| 社区/联系 | GitHub Issues / 反馈渠道 |
| 企业 | 联系: 私有化部署/治理版(引导销售) |

## 6. 配套文档改造

| 文档 | 动作 |
|---|---|
| README.md | 全面重写(本方案) |
| docs/development.md | 新建: 源码构建/开发指引(承接原技术内容) |
| docs/vision.md | 新建: 理念/愿景(承接原 Philosophy/Vision) |
| docs/architecture/ | 保留(架构深度内容) |
| CHANGELOG.md | 新建: 版本记录 |

## 7. 验收标准

```
[ ] 30 秒内理解"解决什么问题" (无架构术语)
[ ] 5 分钟体验路径完整可跑 (安装→Todo)
[ ] 无死链 (所有命令真实存在)
[ ] 面向三类读者: 用户 (5分钟体验) / 决策者 (能力+企业) / 开发者 (docs 链接)
```

## 8. 结论

**README 改造 = 产品首页重写**:从"架构师视角的技术文档"转为"用户视角的产品入口"。
核心变化:首屏解决痛点 → 5 分钟体验(用户最快见价值)→ 能力一览(用户向)→ 深度内容移 docs。

---

> Task 004 完毕 | README 改造方案完成 | 用户向: 解决问题 → 安装 → 5 分钟体验
