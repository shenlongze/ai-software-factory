# ADR-0019 — Phase 6D: Change Intelligence Layer (Commit 关联 / L4 Change Validation / 执行快照关联)

> 日期: 2026-08-06 | 状态: Accepted

## 背景

Phase 6D 给 Factory 加 **Change Intelligence 层**: `factory-core/change/`
五件套 (models/linker/analyzer/service/events) + CLI `change commits/analyze/
validate` + Dashboard Change View (第 15 视图) + change.* / git.task.bound /
git.commit.linked 审计事件。设计文档 phase6d-status.md 明令 **Git 只读**
(零仓库写命令)、**runtime/execution 模型零改动** (快照关联存储)、旧 Task
兼容 (无 git 关联 → L4 SKIP), 新增测试 ≥80。

接续 Phase 6C git 只读层 (ADR-0018): Commit 解析 (message > execution >
branch 三来源)、任务路径分析 (禁 LLM, 确定性规则)、L4 Change Validation
(Task 描述 vs Git 变更证据)、执行完成时的 Git 快照关联。

本 ADR 界定 change 层边界与 L4 判定语义 (含收尾裁定: FAIL 须双条件缺失、
仓库级提交证据判定), 并记录 Phase 6D 收尾 12 个失败测试的契约裁定
(2014 → 2015 全绿)。

## 决策

### 1. 任务 ID 语法与三来源提交解析

- 任务 ID 语法: `MP-XXX-NNN` (MP-BUG-001, 类型段受控词汇
  BUG/FEATURE/TASK/EPIC/STORY/CHORE, 大小写不敏感归一大写) + `T-NNN`
  (Phase 1-3 遗留短编号); 归一化 `normalize_task_id` (去空白、类型段大写)。
- 三来源优先级: **commit message > execution context (显式注入执行任务) >
  branch name** (`feature/MP-FEATURE-002-login` 形态); 已带 task_id 的提交
  不覆盖 (幂等, `model_copy` 不动原对象)。
- 事件: 解析命中才发 `git.commit.linked` (未命中是常态 — 提交无任务 ID
  不刷审计噪声)。

### 2. 路径分析禁 LLM (确定性规则)

- 路径分段 → 模块链 (`change/analyzer.py` → `['change.analyzer', 'analyzer']`,
  最具体在后); 噪声目录过滤 (`__pycache__/.git/node_modules/dist/build/
  .venv/venv`); `.py` 去扩展名, 其他文件保留文件名段; 去重排序 + limit 上限
  防病态路径。
- 失败安全: 空输入 → 全空字段 (不抛)。

### 3. Execution Git Snapshot: 关联存储, 模型零改动

- `ExecutionGitSnapshot` (execution_id/task_id/project_id/repository/
  before_commit/after_commit/changed_files) 存 **change 侧** (ChangeStore
  JSON 列表 + 原子写 tmp+os.replace) — `ExecutionRequest/Result` 模型零改动
  (禁止改 runtime/execution), 旧执行记录无快照字段完全正常。
- `cmd_execution_run` CLI 层快照钩子: 执行完成后装配 ChangeService 调
  `snapshot_execution`; try/except 失败安全 (snapshot=None, run 结果不受影响);
  非 git 目录照常记录 (after_commit=None/files=[]) — 记录"执行发生在无仓库
  环境"的事实。
- 路径: 调用方显式传 `<root>/change` (缺省 `~/.factory/change/snapshots.json`,
  不依赖 cwd — 同 GitChangeStore 陷阱); `git_changes_store` 显式传 `<root>/git`
  (缺省与工厂根不一致时关联投影错位)。

### 4. ValidationEngine 注入式 L4 (接入但不默认启用)

- `change_service=None` 缺省: L4 规则根本不注册 (`len(started)==
  len(completed)==6` / `checks == 6` 类断言逐位不动); 装配时在 L1-L3 硬编码
  规则后追加 `rule_change` — 满足"加规则"与"禁改既有测试"双约束的唯一路径。
- `rule_change` (validation/rules.py) 只做结果包装 — 与 ChangeService.validate
  共用 analyzer 的 `l4_checks`/`l4_verdict`, 不复制逻辑 (DRY); 延迟导入避免
  模块加载环。
- `LEVEL_NAMES` 补 `"L4": "Change"` 映射 (用户期望 Validation 显示 L4), 但
  `by_level`/`to_text` 按 "results 实际出现的层 ∪ `_BASE_LEVELS=("L1","L2",
  "L3")`" 动态出层 — 缺省报告逐字不变, 装配后 L4 行自动出现。

### 5. ChangeContext: L4 输入快照 + 仓库级证据判定 (收尾裁定)

- `ChangeContext` = L4 规则输入快照 (task_id/task_title/repository/is_repo/
  **has_commits**/commits/files/insertions/deletions/affected_modules/error),
  ChangeService.change_context 失败安全装配 (永不抛)。
- **has_commits 字段 (收尾新增)**: 区分"仓库有提交但未关联本任务" (变更证据
  存在 → 可判 FAIL) 与"空仓库/无任何提交" (无证据 → SKIP, 不误报)。
  `change_context` 以 `bool(parse_commits(...))` 填充; 纯函数单测夹具
  `make_change_context` 在提供 commits 时同步置 True。

### 6. L4 判定语义: FAIL 须双条件缺失 (PASS 优先)

- **SKIP**: 无 git 关联 (非仓库 / 仓库无提交且无文件变更)。
- **PASS**: 关联提交存在 (commit 已解析出 task_id == ctx.task_id) **或** 任务
  标题 token 与路径/模块重叠 (中文标题整段保留, 英文按词; 单字符段不参与)。
- **FAIL**: 有变更证据 (仓库有提交或工作区有变更文件) **且** 无关联提交
  **且** 标题与路径/模块无重叠 — 双条件同时缺失才 FAIL (rule_change 契约:
  "有证据但无关联提交**且**标题与路径无重叠 → FAIL; 关联提交命中**或**标题
  重叠 → PASS")。
- 总判定顺序: ERROR 兜底 > 任一 PASS → PASS > 任一 FAIL → FAIL > 全 SKIP →
  SKIP。**关联提交命中时不被无关工作区文件 (如任务库 JSON) 的标题不重叠
  拉低为 FAIL** — 避免基础设施噪声文件误报 (收尾裁定, 见决策 10.1)。
- 标题 token 化: 中文整段保留 (无空格分词), 英文按词; 路径分段小写重叠即
  命中; 单字符段不参与匹配。

### 7. ChangeStore + 快照关联查询

- `ChangeStore` JSON 列表文件原子写; 损坏文件读 → [] (失败安全: 快照是审计
  增强非核心状态), 单条损坏跳过不拖垮整库; `list()` 支持 task_id/execution_id/
  project_id 过滤 (多项目隔离); 无关联 → [] (旧执行记录兼容)。
- 多项目: `ChangeService(project_id=...)` 传播到快照落库与 `snapshots()`
  查询过滤; 项目维度 L4 验证 (仓库只含 A 任务提交时, B 任务 → FAIL —
  证据在别处, 见决策 6)。

### 8. CLI change 命令契约

- `factory change commits [--repo] [--limit]` / `analyze TASK_ID [--repo]` /
  `validate TASK_ID [--repo]`; `--repo` 缺省 = 工厂根目录 (ctx.root, 单仓
  场景); 非 git 目录失败安全 (L4 SKIP / commits 空, 不抛错)。
- 退出码: validate PASS/SKIP → 0 (SKIP 非失败) / FAIL → 3 / ERROR → 1;
  用法错误由 argparse SystemExit(2) 承载 (测试断言用 `pytest.raises(SystemExit)`)。
- 事件: commits 发 `git.commit.linked` (命中) + `git.commit.viewed` (审计,
  ADR-0002); analyze 发 `change.analyzed`; validate 发
  `change.validation.completed` (result=判定)。命令结果 event_seq 须在
  `with ctx.logger_scope()` 块内取 (退出即关库, 块外 query 报 closed database)。

### 9. Dashboard Change View (第 15 视图)

- `ChangeSnapshot` (total/snapshots/validation_total/validations) +
  FactorySnapshot.change 默认空; collector `include_change` 缺省关 (同
  include_git 模式, 零回归); 数据源 = ChangeStore.list (只读) +
  `change.validation.completed` 事件聚合, 支持 project_id 过滤。
- VIEWS 精确集合断言随视图扩展数学上必然失败 (14→15), 最小化更新 + 本 ADR
  记录 (第四犯先例, 同 ADR-0014/0017/0018)。

### 10. Phase 6D 收尾修复: 12 个失败测试的契约裁定 (2014 → 2015)

1. **L4 总判定 FAIL 语义 (实现错, 修实现 + 1 个单测对齐)**: 原
   `l4_verdict` "任一 FAIL → FAIL" 会把"关联提交命中但无关工作区文件标题
   不重叠"误判为 FAIL (CLI `change validate` 对已关联任务 rc 3) — 违反
   本模块设计 docstring 与 rule_change 契约 ("既无关联提交、标题也无重叠")。
   修复 = PASS 优先 (决策 6); 单测 `test_any_fail_wins` 期望错 (编码了
   FAIL-first), 改为 `test_pass_any_rule_wins_over_fail` + 新增
   `test_fail_when_no_rule_passes`。
2. **SKIP 判定缺仓库级提交证据 (实现错, 修实现)**: `l4_checks` 原以
   "无关联提交且无工作区文件"判 SKIP — 有提交但未关联的任务 (多项目场景)
   被误判 SKIP 而非 FAIL。修复 = ChangeContext 增 `has_commits` (决策 5)。
3. **analyze 漏工作区变更 (实现错, 修实现)**: `ChangeService.analyze` 只取
   task↔git 绑定变更, 未提交/未跟踪文件 (wip.py/newfile.py) 不进分析 —
   分析必须反映"当前状态"。修复 = 合并 `client.diff()` 实时工作区变更
   (按路径去重 `_merge_changes`, 防行数重复求和)。
4. **bind_branch 非 git 目录不报 error (实现错, 修实现)**: 非 git 目录时
   `client.current_branch()` 失败安全返回 None → 误判 unbound; 违反
   linker 设计 docstring (error = 非 git 目录/查询失败)。修复 =
   branch 为 None 时先 `client.is_repo()` 检查, 非仓库直接 error。
5. **CLI 用法错误测试用 run_cli 形态 (测试期望错, 修测试)**: argparse 对
   未知子命令/缺子命令/缺 task_id 抛 SystemExit(2) (发生在 main 返回前),
   `rc = main(...)` 拿不到返回值。修复 = `pytest.raises(SystemExit)` 断言
   `exc.value.code == 2` (同 tests/recovery、tests/runtime 既有模式)。
6. **GitBranchContext(status=None) 单测缺 import (测试期望错, 修测试)**:
   Pydantic v2 对 `str` 字段 None 在 after-validator 前即 string_type 校验
   失败 (实测抛 ValidationError) — 测试只缺 `from pydantic import
   ValidationError`。
7. **failsafe 测试污染真实 ~/.factory/change/snapshots.json (测试非 hermetic,
   修测试)**: `_svc` 不传 change_store → 缺省落/读真实用户数据 (本机 8 条
   冒烟快照) → `test_missing_change_dir` 断言 [] 失败。修复 = `_svc` 注入
   `ChangeStore(<tmp>/change)` (库缺省 home 路径设计不变, 调用方显式传 —
   ADR-0018 决策 4 同款)。
8. **测试辅助 make_change_context 未填 has_commits (测试辅助数据语义, 修
   helper)**: 提供 commits 即代表"仓库有提交", helper 同步置 has_commits=True
   (决策 5), 单测 `test_checks_include_message_text` 等恢复证据判定。

## 验证

- pytest **2015 全绿** (2002 既有 + 12 收尾修复 + 1 新增单测), 含
  tests/change/ 全量 (真实 git subprocess mock 仓库夹具)、tests/validation/
  (L4 注入式门控零回归)、tests/dashboard/ (Change View)。
- 冒烟: 临时 git 仓库 (commit message 含 MP-BUG-001) → `factory change
  commits/analyze/validate` (退出码 0/3 + 人类可读 + --json) + `factory
  dashboard --view change` (快照 + 验证聚合渲染) 正常。
