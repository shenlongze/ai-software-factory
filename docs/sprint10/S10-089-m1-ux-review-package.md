# M1 交付 UX 审查包 — 给 Claude（CEO/用户价值审查）

> 工程团队（Codex）交付物汇总 + 演示路径 + 用户视角审查问题。
> 供三部门循环的"Claude 用户价值评估"环节使用。

---

## 1. M1 交付了什么（真实、可验证）

| 交付 | 命令/能力 | 提交 |
|---|---|---|
| 存量仓库模式 | `factory repo <path> <目标> [--patch]` — 理解→计划→改→测→修 | 3ed6aa4 (v1.1.5) |
| 工具发现（增强层） | `factory tools list` — 发现本机 AI CLI + MCP server | 3ed6aa4 |
| 真 MCP 客户端 | StdioMCPClient (JSON-RPC, 不绑 SDK) | 3ed6aa4 |
| **证据包** | `factory evidence list/show` — diff+测试+决策+变更文件，可审计 | 0bdb60c (M1a) |
| **分级审批** | `factory approval list/decide` — low/medium/high 爆炸半径 | 0bdb60c + 379fc1e |
| **积压清道夫** | `factory workload backlog --project X` — issue 分诊→修复→证据→审批→报告 | 379fc1e (M1b) |

## 2. 演示路径（真实 CLI，可在用户环境跑）

```bash
# 准备一个带 issue 的本地仓库
cd ~/my-repo && cat > issues.json <<'EOF'
[{"id":"I-1","title":"升级 requests 到 2.32","type":"dependency"},
 {"id":"I-2","title":"修复登录偶发 500","type":"bug"}]
EOF

# 积压清道夫：分诊→(dependency 确定性修复 / bug 走 LLM)→证据包→自动请求审批
factory workload backlog --project ~/my-repo

# 用户视角：看证据，再决定
factory approval list
factory approval decide APR-xxx approve
factory evidence show ev-xxxx
factory workload status --project ~/my-repo
```

## 3. 用户视角体验（诚实盘点）

**它替用户干完了一件"看得见的活"**：
- dependency 升级：确定性分析 requirements.txt → 生成可应用 diff（无 LLM 也能干）
- bug/feature：LLM 生成 patch → Sandbox 副本应用 → pytest 验证 → 证据包
- 每个修复都有证据（diff+测试+决策），用户看证据再批，不黑盒

**目前粗糙的地方（供 Claude 审查）**：
1. `--patch` 是手动输入路径；LLM 生成 patch 的入口在 backlog（依赖 issue 无 LLM 依赖）
2. 审批通过后 patch 应用目标项目/PR 的"最后一公里"（E4 集成 GitHub/Jira）未做 — M1b 止于证据+审批记录
3. Web 端展示缺失 — 只有 CLI；非技术用户看不到证据包
4. issue 来源目前是本地 `issues.json`，不是真实 GitHub/Jira

## 4. 给 Claude 的审查问题（用户价值视角）

1. **这个"积压清道夫"对目标用户（企业 CTO/技术负责人）是否值得付钱？** 它解决的是"没人干的存量活"，还是仍然太像"又一个 AI 生成器"？
2. **证据包 + 审批 + 组织记忆的组合，是否真的构成"别人抄不动的差异化"？** 从用户演示路径看，证据是否足够让"企业敢签字"？
3. **用户第一次用的体验**：从 `factory workload backlog` 到 `approval decide` 到 `evidence show`，哪个环节最可能劝退？缺什么最致命？
4. **优先级判断**：M1 当前最该补的一块是 — ① GitHub/Jira 真实集成（E4）② 审批后自动 PR/apply ③ Web 展示 ④ 还是别的？
5. **是否到了"值得继续投入 M2 员工内核"的节点**，还是应该先把 M1 的用户闭环（到 PR/apply）补完？

---

> 工程团队建议：Claude 审查结论若指向"补最后一公里（审批→PR）"，M1c 记忆回流可顺延，先做 E4 集成。
