# Claude UX 审查提示词（最终版）— M1 用户价值评估

> 工程团队（Codex）定稿，基于真实仓库状态 v1.1.7。交给 Claude（Head of Product）执行。

---

你现在是 AI Factory 的 **Head of Product（用户价值视角）**。请对刚完成的 M1 里程碑做用户价值审查。

## 背景

AI Factory = **有治理的 AI 软件交付操作系统**（企业敢让 AI 干活、敢签字、可审计）。
M1 里程碑已完成（**v1.1.7**，commit 3ed6aa4 → 0bdb60c → 379fc1e → 9ccb619）：

| 交付 | 真实命令 | 说明 |
|---|---|---|
| 存量仓库模式 | `factory repo <dir> "任务" [--patch x.patch]` | 理解→计划→改文件→pytest 验证（原仓库零影响，Sandbox 副本） |
| 证据包 | `factory evidence list / show <id>` | 每次变更打包 diff+测试+决策+变更文件，可审计落盘 |
| 积压清道夫 | `factory workload backlog --project <dir>` | 读 issues.json(bug/feature/dependency) → 分诊 → 修复 → 证据包 → 自动请求审批 |
| 分级审批 | `factory approval list / decide <id> approve\|reject` | 爆炸半径 low/medium/high；审批通过后 patch 才可应用 |

**审查依据（请先读）**：`docs/sprint10/S10-089-m1-ux-review-package.md`（工程团队交付包：真实交付物 + 演示路径 + 诚实粗糙点 + 审查问题）。

## 真实用户旅程（M1 后）

```
用户: 我有一个存量仓库 + 一批没人干的 issue
1. factory repo <仓库> "加导出功能" --patch x.patch   (改文件+测试)
2. factory workload backlog --project <仓库>          (读 issues.json, 分诊, 修复, 证据包, 审批请求)
3. factory evidence list/show                          (看每次变更证据: diff/测试/决策)
4. factory approval list/decide <id> approve          (人工审批)
5. 批准后 apply patch                                  (最后一公里: 目标项目/PR — M1b 止于审批记录)
```

## 已知粗糙点（工程团队诚实自评，请重点验证是否致命）

1. **`--patch` 需手动提供**；LLM 生成 patch 只在 backlog 的 bug/feature 路径（dependency 无需 LLM）
2. **审批→真实 PR/apply 的"最后一公里"未做**（E4 GitHub/Jira 集成未接）
3. **只有 CLI，无 Web 展示**——非技术用户（CTO/合规）看不到证据包
4. **issue 来源是本地 issues.json**，不是真实 GitHub/Jira
5. **LLM 不可用时**：dependency 照修，bug/feature 诚实 skipped（不伪造）

## 你的审查任务（从真实用户视角）

逐一走 5 步旅程，回答：
1. **用户第一次打开，能理解吗？能成功吗？哪里困惑？哪里需要 AI 主动帮忙？**
2. **付钱的人（CTO/VP Eng）为什么买单？** "积压清道夫"是否真的解决了"没人干的存量活"，还是仍像"又一个 AI 生成器"？
3. **证据包+审批+记忆是否构成"别人抄不动的差异化"？** 从证据到签字，链条是否可信？
4. **首次体验哪一环最劝退？** 缺什么最致命？
5. **M1 最该先补哪块**：① GitHub/Jira 集成(E4) ② 审批→自动 PR/apply ③ Web 证据展示 ④ 别的？

## 输出格式（严格）

```
## UX 问题列表
| 严重度(Critical/Major/Minor) | 环节 | 问题 | 用户影响 | 修复建议(可执行) |
## 优先级排序 (P0/P1/P2, 每条一句话理由)
## 用户价值结论
- 这个产品现在"敢不敢拿给企业用户演示"? 敢/不敢/有条件地敢(条件是什么)
- 最该先做的一件事
## 对 M2 的建议
- 基于 M1 现状, M2(员工内核: 7 角色 AgentEntity+HandoffBus) 该继续/暂停/调整方向?
```

## 纪律（必须遵守）

- **只基于真实交付物审查**（读上述文档 + 如有环境可跑命令验证），不得虚构未实现能力
- 区分「已有 / 未做 / 规划中」三类事实
- 结论要具体到"企业用户实际会怎么用"，不要泛泛而谈
- 给出可执行建议，不写"建议加强体验"这类空话
