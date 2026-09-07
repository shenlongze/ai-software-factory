# 06 Target Architecture (本任务范围)
HUMAN → CONVERSATION (intent adapter) → CURRENT NODE → NodeRun →
LLM Loop (context: input+history+tool results+checkpoint+truth) →
[Tool|AskUser|Done] → Verify → COMPLETE → Truth Write → Next Node
Phase1: node_runtime + WAITING_FOR_USER + Decision Event + checkpoint/resume
        + REPAIRING 状态机修正 (不动既有 TASK execution)
Phase2: requirement-analysis Node (executor prompt 分析 Loop: 理解→读上下文→
        维度分析→findings→ask user(WAIT)→resume→verify 收敛→complete→
        REQ truth 写 (经决策确认))
Phase3: conversation adapter: 意图→定位/创建 NodeRun→注入 user input→
        resume→呈现; governor/resolver 中执行指导职责旁路 (保留 intent/
        安全)
Phase4: E2E (飞机大战需求分析 多轮: create→ask→resume→continue→complete)
