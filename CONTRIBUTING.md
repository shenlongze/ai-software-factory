# Contributing — AI Software Factory 贡献指南

> 欢迎贡献! 在提交代码前, 请先读完本文档与三条铁律:
>
> 1. **不修改 Core 行为** — Core 是冻结的通用原语, 新能力一律走 Extension 声明式注册 ([docs/core-boundary.md](./docs/core-boundary.md) §4)
> 2. **测试先行, 只增不减** — 每个变更必须带测试 (pytest / Vitest), 基线用例数只增不减
> 3. **依赖单向向下** — 禁止反向依赖与循环 import; 跨包引用一律函数内延迟导入

---

## 1. 开发环境 (setup)

```bash
# 一键搭建 (幂等, 可重复执行): venv + editable install + 可选 frontend + init 冒烟
bash scripts/setup.sh

# 只读环境验证 (供 CI/安装冒烟, 不写任何文件)
bash scripts/setup.sh --check

# 手动初始化工厂根 (目录骨架 + 事件库)
.venv/bin/factory init
```

- 要求: **Python 3.12+** (macOS/Linux); 前端需要 Node.js + npm (缺失时 setup.sh 自动跳过, 不影响后端)
- 前端依赖单独安装: `cd factory-console/web/frontend && npm install`
- 环境就绪判定: `factory --help` 退出码 0 + `examples/markpad-demo/` 示例存在 (setup.sh --check 会逐项验证)

## 2. 测试 (pytest + Vitest)

```bash
# 后端全量 (4111 用例, 24 个域目录; 提交前必须全绿)
.venv/bin/pytest

# 单域调试 (例: 事件域 / 控制台域)
.venv/bin/pytest tests/events/
.venv/bin/pytest tests/console/

# 前端全量 (92 Vitest, 12 文件)
cd factory-console/web/frontend && npx vitest run

# 关键约束测试 (Core 零领域 import 断言, 新增 Extension 时尤其要跑)
.venv/bin/pytest tests/cli/ -k removal
```

**铁律: 基线用例数只增不减** — 新功能必须带新测试, 禁止删减既有用例; 提交信息中要标注测试计数 (见 §6)。

## 3. 代码结构

```
ai-software-factory/
├── factory-core/          # 全部 Python 源码, 四区单向依赖:
│   ├── events/ tasks/ workflows/ agents/ assignment/ execution/
│   │   runtime/ recovery/ orchestration/ validation/ metrics/
│   │   dashboard/ project/ workspace/ runtimes/ cli/   ← Core (冻结, 零领域依赖)
│   ├── understanding/ product/ providers/ git/ change/ changeflow/  ← Extension
│   └── intelligence/                                     ← Intelligence (只读复用)
├── factory-console/       # Human Layer: 人类审核台
│   ├── service.py  models.py  events.py
│   ├── api/               # 8 个只读 GET 路由
│   └── web/               # backend/ (FastAPI 适配器) + frontend/ (React 7 页, 92 Vitest)
├── examples/markpad/      # Production Example (project/agents/skills/workflows YAML)
├── examples/markpad-demo/ # Demo 输入 (idea.json / requirements.json / expected-flow.md)
├── docs/                  # 权威文档 30+ 篇 + adr/ (ADR-0001–0035)
├── tests/                 # 24 个域目录, 与 factory-core 模块一一对应
└── scripts/               # setup.sh / demo.sh 及验证脚本
```

依赖方向: **Human Console → Intelligence → Extension → Core (events)**, 单向向下。`cli/` 是组合根, 对领域包只允许函数内延迟导入 (有测试断言)。

## 4. Extension 开发方式

新能力先自问: **换一个领域/工具/模型, 这个能力还需要吗?** 需要 → Core; 否则 → Extension (判定流程见 [docs/core-boundary.md](./docs/core-boundary.md) §4, 四类扩展见 [docs/extension-model.md](./docs/extension-model.md))。

四类扩展:

| 扩展类型 | 回答的问题 | 接入载体 | Core 改动 |
|:---------|:-----------|:---------|:----------|
| Skill | 会做什么 | `SKILL.md` (五段式) + `meta.json` | 无 |
| MCP | 能连什么 | MCP server 声明 (JSON 工具清单) | 无 |
| Runtime | 谁去干活 | `RuntimeAdapter` 接口实现 + 注册信息 | 无 |
| Provider | 用什么脑子 | Provider 声明 + Adapter (Phase 8) | 无 |

**标准流程 — Capability 声明 → 注册 → 测试 → Removal Isolation 验证:**

1. **声明**: 编写声明式载体 (SKILL.md / catalog.json 能力描述 / workflow YAML / Provider 声明)
2. **注册**: 注册到对应 Registry (SkillRegistry / RuntimeRegistry / WorkflowStore / ProviderRegistry), 零 Core 代码改动
3. **测试**: 新包自带测试目录 (`tests/<domain>/`), 全量 pytest + Vitest 全绿
4. **Removal Isolation 验证 (铁律)**: 你的包**只允许延迟 import** Core 与其他领域包, 不得出现在 Core 模块的顶层 import 中; 删除你的包后 Core 必须照常运行 — 有自动化断言约束 (`test_product_removal.py` 等)。区内依赖单向: `change → git`, `changeflow → change`。

## 5. ADR 流程

设计决策先写 ADR, 新模型先补设计文档 (docs/), 再写代码。已有 ADR-0001–0035 见 [docs/adr/](./docs/adr/), 格式:

```markdown
# ADR-00XX — Phase XX: <标题>

> 日期: YYYY-MM-DD | 状态: Accepted
> 前置: ADR-00YY (如适用)

## 背景      # 为什么需要这个决策、约束是什么
## 决策      # 做了什么选择, 分条 + 必要结构图
## 边界      # 明确不做什么
## 验证      # 如何证明: pytest 计数 / 冒烟 / Core 零修改确认
```

规则: 编号递增 (当前至 0035); 一个 ADR 一个决策; 状态 Accepted/Proposed/Superseded; 命名 `00XX-<slug>.md`。

## 6. Commit 规范

**格式: `Phase <N>: <变更摘要> + <测试计数>`** — 阶段号 + 可读摘要 + 测试数, 每次提交独立可交付、可回退。

```text
# 示例 (取自仓库历史)
Phase 13A: Production Readiness & Release Prep — ... + 21 smoke 测试 + 4111 pytest
Phase 11B: Human Console Web UI — ... + 92 Vitest + adapter pytest + ADR-0035 + 4090 pytest
Phase 10A-3: Recommendation Engine — ... + 3803 pytest
fix: 移除 node_modules/dist 误提交 (Phase 11B .gitignore 补 Node 规则)
```

## 7. PR 流程

1. Fork → 分支: `feature/<phase>-<描述>` (如 `feature/14A-contributing`)
2. 变更 + 测试 (pytest 全量 + Vitest 全量, 用例数只增不减)
3. 填 PR 模板 ([.github/PULL_REQUEST_TEMPLATE.md](./.github/PULL_REQUEST_TEMPLATE.md)): 变更范围 / 测试证据 / ADR 引用 / **Core 零修改确认**
4. 合并前检查: 提交信息含阶段号与测试数; 依赖方向符合 §3; Removal Isolation 断言通过
