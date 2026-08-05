# MarkPad — Production Example (Phase 5A)

MarkPad 是 AI Software Factory 的第一个 **Production Example**: 一个真实的跨平台
Markdown 编辑器项目 (Flutter/Dart, 本地工作副本 `/Users/Shared/work/markpad`),
用于演示如何用 Factory 管理一个真实项目: 项目定义 → Agent/技能/工作流映射 →
任务下发 → 自动执行链路。

## 文件清单

| 文件 | 内容 |
| --- | --- |
| `project.yaml` | 项目定义: name/language/repository/tech_stack |
| `agents.yaml` | Agent 映射: flutter-developer / tester / architect (role + skills) |
| `skills.yaml` | 技能目录: flutter / dart / testing / architecture |
| `workflows.yaml` | 工作流映射: feature / bug-fix / release (步骤含 required_role/required_skill) |

## 设计约定 (ADR-0013)

- **严格匹配**: `workflows.yaml` 步骤的 `required_role`/`required_skill` 与
  `agents.yaml` 的 `role`/`skills` 必须 token 一致 (AgentMatcher 语义:
  role 精确匹配 + skills 命中 ≥1, ADR-0008)。三个 agent 覆盖全部步骤角色:
  - `architect` (product-manager) → feature.architecture
  - `flutter-developer` (developer) → 开发/修复/构建/发布步骤
  - `tester` (test-engineer) → 测试/复现/验收步骤
- 步骤 id 复用内置工作流 (feature-delivery/bug-fix/release) 的骨架,
  角色按 MarkPad agent 集合适配 — 换项目只改这 4 个 YAML, 不动 factory-core。
- 配置为**只读**声明: `factory project list/show` 只解析展示; agent/skill/workflow
  的实际注册仍走既有 CLI (`agent add` / `skill add` / `workflow add`) 或引擎 API。

## 接入方式

```bash
# 1. 查看 Factory 认识的项目
factory project list
factory project show markpad

# 2. 注册 MarkPad agent 与 workflow (echo runtime 冒烟)
factory agent add --id flutter-developer --role developer --skills flutter,dart
factory agent add --id tester            --role test-engineer --skills testing,dart
factory agent add --id architect         --role product-manager --skills architecture,flutter
factory runtime add --id echo --type mock

# 3. 创建 bug fix 任务并跑完整链路 (Task→Workflow→Assignment→Execution→Echo)
factory task create --id T-101 --title "修复编辑器光标位置错乱" --project markpad \
  --type bug --workflow bug-fix
factory workflow run --auto T-101
```

> 注: 示例工作流 (feature/bug-fix/release) 带 required_role/required_skill 元数据,
> CLI `workflow add` 目前只支持内置定义或纯步骤名; 带元数据的映射经
> `factory-core/project/loader.py` 读取后由引擎 API 注册 (见集成测试
> `tests/project/test_integration_markpad.py`)。

## 完整链路 (echo runtime)

`task create --project markpad` → `workflow run --auto`:

1. WorkflowEngine 启动运行实例 (`workflow.started`)
2. AgentMatcher 按步骤 role/skill 匹配 AVAILABLE agent
3. AgentAllocator 分配 + 置 WORKING (`agent.assignment.*`)
4. ExecutionService 经 EchoRuntimeAdapter 执行 (`execution.*`, 输入回显到 output)
5. 步骤完成 → agent 释放回 AVAILABLE; 全部完成 → Workflow COMPLETED
   (`orchestration.*` 全程审计)

生产环境将 echo 换成 hermes-runtime (`runtime add --id hermes-runtime --type agent`,
`FACTORY_HERMES_CMD` 指向 hermes CLI) 即接入真实 LLM 执行。

## 变更驱动工作流 (changeflow, Phase 6E / ADR-0020)

`factory change` 把 Git 变更与 4 规则评估串成"变更即发布"链路: 提交关联任务 ID 的
代码 → L4 验证 PASS → evaluate 四规则 (验证/关联提交/必需文件/runtime) 全 PASS →
自动启动并执行目标工作流 (如 release)。

```bash
# 1. 注册变更触发器 (事件 + 项目/类型限定 + 目标工作流; 声明式, 只落盘)
factory change triggers register --id TRIG-FEATURE-RELEASE \
  --event-type workflow.completed --project markpad --task-type feature \
  --required-validation PASS --target-workflow release

# 2. 查看已注册触发器 (发 change.trigger.viewed)
factory change triggers list

# 3. 创建 feature 任务 (task.workflow 与触发目标可不同 — 链式交付)
factory task create --id T-201 --title "新增暗色主题" --project markpad \
  --type feature --workflow feature-delivery

# 4. 提交关联代码 (commit message 含任务 ID → git 三来源解析命中)
git add . && git commit -m "T-201: add dark theme"

# 5. L4 验证 → PASS (证据 = 关联提交 + 标题/路径重叠)
factory change validate T-201

# 6. evaluate: 4 规则 PASS → 启动 release 工作流并执行 (默认 --execute;
#    缺省执行契约 = 装配 executor 才触发, 显式 execute=True 亦强制触发)
factory change evaluate T-201
factory change evaluate T-201 --no-execute   # 只评估不触发 (纯评估)

# 7. 查看触发链: 任务工作流 (feature-delivery) + 触发工作流 (release)
factory change workflows T-201

# 8. Change Flow 仪表盘视图 (Triggers / Evaluations / Workflow Links 三表)
factory dashboard --view changeflow
```

> 契约要点 (ADR-0020): evaluate 的 `execute` 缺省 = 引擎是否装配 executor —
> CLI `change evaluate` 默认装配 (执行), `change workflows`/纯评估场景不装配;
> 失败恢复不级联 (目标工作流未注册 / 任务已有 run → ERROR 评估, 不影响调用方);
> 无匹配触发器 → SKIP (旧 Task 兼容)。
