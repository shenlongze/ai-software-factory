# ADR-0018 — Phase 6C: Git Integration Layer (Git 只读集成 + Task↔git 关联)

> 日期: 2026-08-06 | 状态: Accepted

## 背景

Phase 6C 给 Factory 加 **Task 与 Git 变更的可追踪关系**: `factory-core/git/`
四件套 (models/client/service/events) + CLI `git status/diff/commits` +
Dashboard Git View + git.* 审计事件。设计文档 phase6c-status.md 明令
**Git 只读 + 审计** — 禁止修改 Workflow Engine / Execution Runner、禁止自动
push/merge/rebase, 新增测试 ≥80 (1616 不回归)。

仓库现状: dashboard 层已有 FactorySnapshot 聚合 (ADR-0012/0016/0017 先例),
events 层已有 EventType 枚举增量扩展路径 (ADR-0001 决策 1)。本 ADR 界定
git 集成层的边界 (只读铁律、失败安全三态、task↔git 关联兼容), 并记录
Phase 6C 收尾 4 个失败测试的契约裁定 (实现缺信息 → 修实现; 夹具构造
不符合 YAML 语义 → 修夹具)。

## 决策

### 1. Git 只读 + 审计铁律: 零写命令, 读命令也发审计事件

- `GitClient` 只有 git 读命令 (rev-parse/status/diff/log/ls-files/symbolic-ref),
  无 add/commit/push/merge/rebase; 子进程形态 `git -C <repo> <args...>`
  (cwd 无关, 避免 chdir 副作用), `git_bin` 可注入 (测试命令缺失路径),
  capture_output + text + timeout 上限。
- CLI git 命令唯一副作用 = 审计事件 (ADR-0002): status→`git.status.viewed` /
  diff→`git.change.detected` / commits→`git.commit.viewed`, 事件类型 = 加
  EventType 枚举成员即可 (ADR-0001 路径, type 列存字符串不改表)。
- `bind_task_change` 是**唯一的写路径** (GitChangeStore JSON 追加 + 审计事件),
  不触碰仓库本身; CLI 读命令不装配 task_store、不写 changes.json (零写)。

### 2. 失败安全三态 + CLI 退出码语义

- **非 git 目录** (rev-parse --git-dir 失败) → `is_repo=False` + `GitContext.error`
  承载原因; **空仓库** (init 后无提交) → `is_repo=True`, `current_commit=None`,
  error 为 None (合法状态, 与"非 git 目录"区分); **正常** → 全字段。
- 只读查询失败不抛未处理异常 (FileNotFoundError/TimeoutExpired/OSError 统一
  防御); CLI `git status/diff/commits` 对非 git 目录 **rc 0 + error 经输出呈现**
  (只读查询执行成功, 失败安全), 项目/仓库解析错误才 rc 1/2/7:
  `--repo` 显式 > `--project` 的 project.yaml repository; 两者皆缺 rc 2,
  项目不存在 rc 7, 无 repository / 远程 URL rc 1。

### 3. 输出解析契约

- porcelain XY 码归一化五类 (untracked/added/modified/deleted/renamed, 重命名
  取目标路径); numstat 二进制占位 `-` → 0; untracked 走
  `ls-files --others --exclude-standard` 补充 (numstat 不含未跟踪); 空仓库
  `diff --numstat HEAD` 失败自动退化无 HEAD 版; log 用 `%x1f` 切列
  (subject 任意字符安全), `%aI` 严格 ISO8601。
- **untracked 文件行数经 `git diff --no-index --numstat /dev/null <path>`
  补充** (收尾修复, 见决策 7.1): 纯读命令不破只读铁律, 使
  bind_task_change 的文件级 insertions/deletions 对账覆盖 untracked
  (任务接管的新文件行数不再漏计为 0)。

### 4. task↔git 关联: Task 模型零改动, 关联只存 git 侧

- GitChange 单条 = task_id + files + insertions/deletions (从实时 diff 对账
  求和) + commits 哈希; `GitChangeStore` JSON 列表文件原子写
  (tmp + os.replace), 读损坏 → [] (失败安全: 关联是审计增强非核心状态,
  单条损坏跳过不拖垮整库)。
- **旧 Task 兼容**: Task 模型不加字段 (禁止改 tasks/), 关联只存在 git 侧
  (GitChange.task_id 引用 Task.id); 无关联 → task_id=None, 绑定查询返回空。
- store 默认路径禁用 cwd 相对 (`~/.factory/git/changes.json` 与 CLI
  DEFAULT_ROOT 一致), 调用方显式传 `<root>/git`; 构造器接受目录或文件路径。

### 5. Dashboard Git View: 默认关闭 + 单视图不并入 "all"

- collector 只加默认关闭开关 `include_git: bool = False` (同 include_workspace
  先例): 默认 False 时既有 dashboard 行为/成本完全不变; Git View 数据源 =
  FactorySnapshot.git (collector 只读聚合, 非 git 目录 → error 行照常展示)。
- 单视图不并入 "all" Group (零回归风险, 不拖慢既有渲染); 渲染器 VIEWS
  精确集合断言随视图扩展**数学上必然失败** (13→14), 最小化更新 + 本 ADR
  记录 (第三犯, 同 ADR-0014/0017 先例)。

### 6. git.* 审计事件 payload 契约

- `git.status.viewed`: repository/branch/current_commit/changes(计数)/
  is_repo/error — 失败安全时 result="ERROR" + payload.error 摘要。
- `git.change.detected`: change_id/repository/files/commits/insertions/
  deletions/status (bind_task_change 自动发, CLI diff 聚合事件发
  repository/count/error)。
- `git.commit.viewed`: repository/count/limit/**hashes** (只保留前 20,
  审计载荷上限) — CLI 与 `record_git_commit_viewed` 辅助共用同一契约
  (收尾修复, 见决策 7.2)。

### 7. 收尾修复: 4 个失败测试的契约裁定 (1809 → 1813)

1. **untracked insertions 漏计 (实现缺信息, 修实现)**: `bind_task_change`
   对 untracked 新文件 (如 wip.py 1 行) insertions 恒 0 — numstat 不含
   未跟踪, 实时 diff 对账漏掉文件行数; 测试期望 1 合理 (审计完整性)。
   修复 = `GitClient.diff()` 对 untracked 文件经 `git diff --no-index
   --numstat /dev/null <path>` 补行数 (决策 3), 事件/JSON 出口随之正确。
2. **commits 事件 payload 缺 hashes (实现缺信息, 修实现)**: CLI
   `cmd_git_commits` 直接 logger.record 漏了事件辅助函数
   `record_git_commit_viewed` 契约里的 hashes 键 — 补齐
   `hashes=[c.hash for c in commits[:20]]`, CLI 与服务层事件载荷一致。
3. **git status 空表输出重复占位 (输出契约, 修实现)**: 干净仓库时
   `_render_table` 空表占位 "(无记录)" 与 "(no changes)" 重复且无表头;
   修复 = `_render_table` 增 `empty=None` 选项 (空表仍渲染表头, 其他命令
   默认 "(无记录)" 不变), status 分支传 None — 变更表头恒定显示。
4. **夹具 repository 空值写 YAML None (测试夹具错, 修夹具)**: 测试 helper
   `_write_project(root, "p-norepo", "")` 写 `repository: ` → YAML 解析为
   None → pydantic 2.13 `str` 字段 string_type 校验失败 → WorkspaceConfigError,
   走不到 CLI 设计的 "no repository" rc 1 分支。修复 = repository 值双引号
   包裹 (`repository: ""`), 空字符串是 YAML 表达"空值"的正确形态; 实现
   (空 repository → rc 1 "no repository") 与测试期望一致, 未改。

## 验证

- pytest **1813 全绿** (1809 既有 + 4 收尾修复; Phase 6C 新增 197 个
  tests/git/ 测试全过, 含 mock 仓库真实 subprocess 夹具)。
- 冒烟: 临时 git 仓库 → `factory git status/diff/commits` (人类可读输出 +
  --json + 退出码 0/1/2/7 + 审计事件 git.* 落库) + `factory dashboard
  --view git` 渲染正常。
