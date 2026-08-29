# S10 Architecture Assessment — Professional Workflow Assembly

> 日期: 2026-08-29 | HEAD: cc75bbc3 (v1.1.315) | 状态: 实现前审查

## 1. 已存在能力 (复用)
| 能力 | 位置 | 状态 |
|------|------|------|
| AgentEntity/AgentRegistry | session/agent_entity.py + agent_registry.py | REAL |
| AgentRun + Agent Loop + Handoff | agent_kernel.py | REAL (S9) |
| ProductionRun/NodeRun/Artifact/Verification/Repair/Recovery | S1-S8 | REAL |
| LLM Gateway (complete) | session/llm_gateway.py | REAL |
| LLM key/provider/model 解析 | workflow_runner.load_llm_key + get_config().get_llm() | REAL |
| 真实 executor (codex) | external_executor | REAL |
| CLI/API production | S6/S8 | REAL |

## 2. 缺失 (S10 新增)
| 缺口 | 最小实现 |
|------|---------|
| 4 个专业 Agent 定义 | AgentEntity 预置 (PM/Architect/Developer/QA) |
| Professional Workflow | professional_workflow.py 编排器 (AgentRun 链 + Handoff) |
| LLM Decision Layer | agent_executor: system_prompt → llm_gateway → 结构化 artifact |
| 专业验收标准 | 每 Agent 的 verify 函数 (PRD 段存在/code 语法/pytest) |

## 3. 数据流
```
Idea → PM AgentRun → PRD Artifact → Handoff → Architect AgentRun
→ Architecture Artifact → Handoff → Developer AgentRun → Code Artifact
→ Handoff → QA AgentRun → Test Artifact → pytest → PASS → Lifecycle → Apply → Workspace
```

## 4. 关系
- AgentRun ↔ ProductionRun: 每 Agent 一个 AgentRun, 各包一个 ProductionRun (S9 模式)
- 专业 workflow = 编排多个 AgentRun 串行 (非 monolithic)
- LLM Decision: agent 的 executor 用 system_prompt + input_artifacts → llm_gateway.complete → 文本 → Artifact

## 5. 严禁触碰
- S1-S8 Production Kernel / agent_kernel / llm_gateway 核心
- legacy workflow_runner (BYPASS)
- 不建第二套 Artifact/Verification/Recovery

## 6. 实施范围
professional_workflow.py + 4 Agent 预置 + LLM 接入 + CLI workflow list + 测试 + 真实 E2E
