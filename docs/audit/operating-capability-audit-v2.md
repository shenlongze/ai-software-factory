# AI Software Factory — Operating Capability Audit v2.0

> 日期: 2026-08-08 | 类型: 真实运行审计（实测命令 + 代码证据 + Sprint 6 结果）
> 基线: HEAD=469bba1 | pytest 5521 | 真实闭环已验证 (v4-pro SUCCESS)

## 一、真实能力审计

**选择: C. 半自动软件工厂**

```
原因 (基于实测):
  ✅ 能自动: 组织创建/任务拆解/LLM 执行 (v4-pro)/Patch 生成/沙箱测试/报告/经验
  ✅ 已证明: Task→Agent→v4-pro→Patch→Test→Evidence 闭环 SUCCESS (Sprint 6)
  ❌ 不能自动: 多阶段协作 (PM/设计/架构/测试自动接力)、apply 自动、
     UI/后端/数据库全栈、发布部署、自我维护
  ⚠️ 关键: 单任务自动执行 ✅ / 完整软件生产 ❌ / 人工审批闸门存在 (半自动)

不是 A (管理平台): 有真实代码产出 (patch/report)
不是 B (辅助工具): 有组织/审批/工作流/经验闭环 (非单任务工具)
不是 D (全自动): 5/6 角色仅 planning, apply 需审批, 无多阶段协作
```

## 二、用户实际使用流程（实测验证）

### 场景: 开发一个记账 APP

```
用户操作 ①: 初始化工厂
  $ export PYTHONPATH=factory-core:factory-org:factory-exec
  $ python -m cli.main --root ~/myfactory init
  ↓ 系统: 建目录骨架 + 事件库 (system.init 事件)
  → 结果: 工厂就绪

用户操作 ②: 创建公司
  $ python -m org.cli --root ~/myfactory company create --template software_company --name "记账公司"
  ↓ 系统: 建 Company + Department + 5 角色 (CEO/Product Manager/Architect/Developer/QA) + Authority
  → 结果: company_id=C-xxx (注意: 用返回的真实 id)

用户操作 ③: 雇佣开发者
  $ python -m org.cli --root ~/myfactory employee hire --company C-xxx --name "开发者1" --role Developer
  ⚠️ 实测注意: 角色名需精确匹配模板 (Developer 大写) — 大小写敏感
  → 结果: E-xxx (员工)

用户操作 ④: 提交需求 (任务)
  $ python -m cli.main --root ~/myfactory task create --title "记账 APP: 收支记录功能" --type feature
  → 结果: T-xxx (Task, 挂 feature-delivery workflow)

用户操作 ⑤: 执行 (真实 LLM)
  $ python -m exec.cli --root ~/myfactory run --task T-xxx --employee E-xxx
    --project-dir /path/to/项目 --objective "实现收支记录" --requirement "..."
  ↓ 系统: EmployeeExecutor → DeveloperAgent → v4-pro → 沙箱修改 → Patch → 测试 → 报告
  → 结果: ExecutionResult (patch + test_result + report 3 产物 + 经验记录)

用户操作 ⑥: 审批 + 查看
  $ python -m exec.cli --root ~/myfactory approval approve --execution EX-xxx
  $ python -m cli.main --root ~/myfactory dashboard / event logs
  → 结果: patch 应用 (审批后) + 证据链可查

内部真实发生 (⑤ 展开):
  Employee (E-xxx) 接任务 → EmployeeExecutor.execute → 角色匹配 (developer)
  → AgentRuntime → DeveloperAgent.work (Context 组装) → OpenAIProvider (DeepSeek v4-pro
  http://api.deepseek.com) → 结构化 Operation → 沙箱副本修改 → 验证循环 (语法+测试)
  → patch+report+test_result → ExperienceRecord (subject_id=E-xxx) + 上下文经验落库
```

## 三、已有软件维护流程（MarkPad Bug 场景）

```
1. Bug 进入系统: 用户发现 → task create --type bug (可挂 markpad 项目)
2. Task 创建: T-xxx + 验收标准 (acceptance)
3. Employee 执行: hire Developer → exec run --employee E-xxx --project-dir /markpad
4. Agent 工作: DeveloperAgent 组装 Context (ranking/progressive) → 定位文件 → 生成 Operation
5. 代码修改: 沙箱副本内 (源零修改) → patch 生成
6. 测试: 沙箱内验证循环 (语法 ast + 测试命令) → test_result 产物
7. Evidence: 事件链 (execution.*/validation.*) + ExperienceRecord + 上下文经验
   → 审批后 apply 到源 (沙箱外零修改铁律)

⚠️ 真实限制: markpad 大项目 (2.2G) 沙箱拷贝慢 (选择性复制 lib/ 已优化);
   v4-pro 对 Dart 复杂任务的真实成功率待 9 样本验证 (单 Python 任务已验证 ✅)
```

## 四、新软件开发能力检查（代码证据）

| 阶段 | 能力 | 状态 | 证据 |
|:-----|:-----|:----:|:-----|
| 需求 | 需求输入 | ✅ | task create (cli/main.py) |
| 需求 | 产品分析 | ✅ | product analyze/decide (product 模块 34 类) |
| 需求 | PRD | ✅ | product 链路 (Idea→PRD→Approval, 501 测试) |
| 设计 | UI 设计 | 🟡 | product UI 命令 (候选产物, 人工批准); UIDesigner 角色 planning |
| 设计 | 架构设计 | 🟡 | product architecture 命令; Architect 角色 planning |
| 开发 | 前端/后端/数据库 | 🟡 | Developer 可执行通用代码 (无前端/后端/DB 专门工具) |
| 测试 | 自动测试 | ✅ | 沙箱验证循环 + L1-L4 (validation 566 行) |
| 测试 | Bug 修复 | ✅ | v4-pro 真实闭环验证 (sum_list SUCCESS) |
| 发布 | Build | ❌ | 无 build 执行 (沙箱仅源码验证) |
| 发布 | Release | 🟡 | release workflow 模板 (manual); 无真实构建/发布 |

## 五、自我维护能力

```
回答: ❌ 当前不能完整自修

能: 创建 Task → 分析 (DeveloperAgent 读自身代码) → 生成 patch → 测试 (pytest) → 提交
缺:
  1. 无 apply 自动 (审批门) — 自修需人工批准每次 patch
  2. 无"发现自身 Bug"机制 (无监控/自检任务生成)
  3. 经验循环不触发自身改进决策 (只记录, 不驱动)
  4. 沙箱测试只能跑项目内测试, 全仓 pytest 未接
```

## 六、工具调用能力

```
✅ 已支持:
  代码: 文件读取 (repo_index/context) / 文件修改 (Operation API: modify/create/delete/replace)
  Git: 沙箱内 git 操作 (init/add/commit/diff — git_bin)
  Shell: 沙箱内验证命令 (validation_command)
  测试: 语法 (ast) + 测试命令执行 (L1-L4 验证)
  外部: LLM API (DeepSeek v4-pro) / OpenAI 兼容端点

❌ 未支持:
  开发: Build (无编译器/打包器调用) / Package (无)
  扩展: MCP (空目录) / Skill (Core 有 Registry 未进执行) / 外部 API (除 LLM)
  部署: 无
```

## 七、角色能力分析

| 角色 | 真实执行 | 输入 | 输出 | 调 LLM | 调工具 | 原因 |
|:-----|:----:|:-----|:-----|:----:|:----:|:-----|
| ProductManager | ❌ planning | — | — | 否 | 否 | execution_kind=planning |
| UIDesigner | ❌ planning | — | — | 否 | 否 | 同上 |
| Architect | ❌ planning | — | — | 否 | 否 | 同上 |
| Developer | ✅ executable | task/objective/project | patch/report/test | ✅ | ✅ | 唯一 executable |
| Tester | ❌ planning | — | — | 否 | 否 | 同上 |
| DevOps | ❌ planning | — | — | 否 | 否 | 同上 |

```
为什么只有 Developer 可执行?
  roles.py execution_kind 设计: 只有 developer=executable
  (exec 引擎的 prompt/Operation 是代码修改导向)
如何补齐其他角色?
  1. 每个角色 = prompt 模板 + 输出协议 (PM→PRD 文档, 测试→验证报告)
  2. execution_kind 提升 (planning→executable) — 同引擎复用
  3. 工具集: Tester 需 test runner, DevOps 需 shell/build, UIDesigner 需 HTML 模板
  (Sprint 7-8 方向)

⚠️ 双角色体系 (实测发现): org 模板 5 角色 (CEO/PM/Architect/Developer/QA)
  vs exec roles.py 6 角色 (PM/UIDesigner/Architect/Developer/Tester/DevOps)
  — 未统一 (审计风险)
```

## 八、缺口优先级

```
P0 (必须补, 否则无法生产):
  1. 9 样本 Benchmark (v4-pro) 验证复杂任务成功率 (当前只验 1 个简单任务)
  2. 角色体系统一 (org 模板 vs exec roles.py) + 非 Developer 角色可执行
  3. 多阶段协作编排 (PM→Design→Arch→Dev→Test 接力 — 当前单任务直连)

P1 (提升自动化):
  4. Build/Package 工具接入 (沙箱内编译/打包验证)
  5. apply 自动 + 审批 (当前手工 apply)
  6. 大项目沙箱优化 (markpad 选择性复制已做, 需默认化)

P2 (未来扩展):
  7. Skill/MCP 进执行 / 外部 API / 自我维护闭环 / 多行业模板
```

## 九、用户操作手册 → docs/user-guide.md（已生成, 见下）

## 十、最终结论

```
Q1: 今天可以把软件开发任务交给 AI Factory 吗?
    部分可以: 单任务 (Bug 修复/小功能, Python/简单代码) ✅
    不能: 完整软件生产 (多阶段/全栈/发布) ❌
    适用: 已有代码的小型修复 + 简单任务, 人工审批兜底

Q2: 今天能自动完成到什么程度?
    单任务全自动: 需求→执行→patch→测试→报告→经验 ✅
    (需人工: 任务创建上下文, 审批 apply, 复杂任务验收)

Q3: 下一步最小必要开发是什么?
    1. 9 样本 Benchmark (v4-pro) → 确认复杂任务成功率 (1 天)
    2. 角色统一 + Tester/其他角色 executable (复用引擎) (3-5 天)
    3. 多阶段协作编排 (PM→Dev 接力) (1 周)
    → 之后才有"完整软件生产"雏形
```

---

## 附: 实测命令记录（2026-08-08, /tmp/factory-demo-2）

```
init ✅ (system.init 事件) → company create ✅ (5 角色自动建) →
hire --role Developer ✅ (大小写敏感, caps 未生效注意) → task create ✅ (feature-delivery)
发现的真实问题: ① 角色名大小写敏感 (Developer vs developer)
  ② employee hire --capabilities 显示 caps=0 (参数可能未生效 — 待查)
  ③ company id 是随机 (需用返回 id)
  ④ org 模板角色 (CEO/PM/Architect/Developer/QA) vs exec roles.py (6 角色) 未统一
```
