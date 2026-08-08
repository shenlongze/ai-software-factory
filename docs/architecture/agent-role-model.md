# AI Software Factory — Agent Role Model

> 状态: DESIGN ONLY (蓝图, 未实现或部分实现 — 见 ../audit/architecture-reality-audit.md)

> 日期: 2026-08-07 | 状态: 设计 (Architecture Correction, Phase 17 实现)
> 核心修正: 能力 != 角色 — 不同专业需要不同 AI 员工

## 一、为什么 Agent 必须角色化？

```
错误模型: 一个 AI Agent 拥有所有能力 (超级 Agent)
正确模型: Organization → Role → Professional Agent → Capability

专业的人干专业的事:
- 公司不会让一个人同时当 CEO/架构师/开发/测试/法务
- AI 组织同理: 每个 Agent = 一个岗位 (Role), 有明确职责边界
- 角色化带来:
  1. 职责清晰 (谁负责什么)
  2. 可审计 (岗位行为可追溯)
  3. 可考核 (绩效按岗位评价)
  4. 可替换 (员工离职 → 新员工, 组织不变)
  5. 可治理 (权限按岗位分配)
```

## 二、Agent 完整模型

```python
class Agent(Pydantic):      # 专业 AI 员工
    identity: str           # Role 职位 (CEO/Product/PM/Architect/Developer/QA/Review)
    responsibility: str     # 职责 (该岗位做什么)
    capability: list[str]   # 专业能力 (声明式, capability.yaml)
    knowledge: list[str]    # 专业知识 (领域/文档/Skill)
    authority: list[str]    # 权限 (read_source/modify_workspace/run_test...; 默认 deny)
    experience: dict        # 历史经验 (ExperienceRecord 五域)
    performance: dict       # 绩效 (成功率/成本/评分, 10A-4)
```

```
示例角色:
  CEO Agent       职责: 战略方向/资源决策/最终批准 (无技术执行权)
  Product Agent   职责: 需求分析/市场/用户
  PM Agent        职责: 目标理解/拆解/规划/调度/进度/风险 (组织执行, 不执行)
  Architect Agent 职责: 技术方案/架构决策
  Developer Agent 职责: 技术实现 (无批准权)
  QA Agent        职责: 质量验证 (无实现权)
  Review Agent    职责: 独立审查 (无修改权, 执行权 != 审核权)
```

## 三、为什么 Analysis 和 Project Management 是不同职业？

```
Analysis Agent (分析岗)          Project Manager Agent (管理岗)
- 信息收集                       - 目标理解
- 数据分析                       - 项目拆解
- 风险分析                       - 任务规划
- 方案比较                       - 资源协调
- 输出: Analysis Report          - 进度管理
- 输出: Recommendation           - 风险跟踪
                                 - 动态调整
                                 - 输出: Project Plan/Task Graph/Schedule/Status

关系: 分析提供事实和建议 → 项目经理基于目标和约束组织执行
(分析是顾问, 经理是决策执行组织者 — 不同岗位, 不同职责, 不同能力)
```

## 四、Organization 如何驱动 Agent 协作？

```
Organization 定义岗位结构 → 每岗位一个 Professional Agent
协作 = 岗位间的工作流 (不是 Agent 任意互调):

Goal (Human)
  → CEO (确认目标/授权)
  → Product (需求分析 → PRD)
  → PM (计划 → Task Graph → 分配)
  → Architect (技术方案)
  → Developer (实现)
  → QA (验证)
  → Review (独立审查)
  → Human Approval (最终负责)

协作经: Artifact + Event (source_events 链) — Agent 间无直接信任/互调
```

## 五、如何避免超级 Agent 设计？

```
1. 岗位边界: 每 Agent 只有岗位职责对应的 capability/authority (默认 deny)
2. 权限隔离: Developer 无批准权; Review 无修改权; CEO 无技术执行权
3. 能力裁剪: 不把所有能力塞进一个 Agent; 缺能力 = 找专业同事 (其他 Agent)
4. 组织约束: 行为必须符合 Organization 结构 (越权 = 拒绝 + 审计)
5. 独立审查: 执行/审查分离 (Review Agent 独立于实现)
6. 人类最终: 关键节点 Human Approval (AI 无最终权)
```

## 六、MarkPad AI Software Company（第一个验证组织, Phase 17）

```
CEO Agent → Product Manager Agent → Project Manager Agent
→ Architect Agent → Developer Agent → QA Agent (+ Review)

Human 给目标 "开发 MarkPad 新版本":
  CEO 确认目标 → Product 需求分析 → PM 制定计划 → Architect 技术方案
  → Developer 实现 → QA 验证 → Review 验收 → Human Approval
```
