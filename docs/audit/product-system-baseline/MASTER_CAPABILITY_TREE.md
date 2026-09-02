# MASTER CAPABILITY TREE — STEP 9 (2026-09-02)
> 29 Atomic Capabilities (STEP 7 原样) × 状态树

```
状态图例: [CLOSED_LOOP]=M4 [PRODUCTION]=M3 [INTEGRATED]=M2 [IMPLEMENTED]=M1
          [ABSENT]=M0 [FUTURE] [UNKNOWN]

AI FACTORY
├── CORE 18
│   ├── Session Entry            [CLOSED_LOOP]
│   ├── Intent Capture           [CLOSED_LOOP]
│   ├── Requirement Persistence  [PRODUCTION]  ← 缺下游
│   ├── Requirement Traceability [ABSENT]
│   ├── Planning                 [CLOSED_LOOP]
│   ├── Task Management          [CLOSED_LOOP]
│   ├── Dependency Scheduling    [CLOSED_LOOP]
│   ├── Agent Selection          [PRODUCTION]
│   ├── Agent Execution          [PRODUCTION]
│   ├── LLM Invocation           [CLOSED_LOOP]
│   ├── Model Selection          [IMPLEMENTED]  ← LLMRouter 消费 0
│   ├── Orchestration(会话链)     [CLOSED_LOOP]
│   ├── Execution                [CLOSED_LOOP]
│   ├── Recovery                 [PRODUCTION]
│   ├── Cancellation             [CLOSED_LOOP]
│   ├── Verification             [INTEGRATED]  ← 无下游
│   ├── Audit                    [CLOSED_LOOP]
│   └── Governance/Approval      [PRODUCTION]
│
├── SUPPORTING 7
│   ├── Discovery/Clarification  [IMPLEMENTED]
│   ├── Tool Invocation          [PRODUCTION]
│   ├── Skill                    [IMPLEMENTED]
│   ├── Artifact Lifecycle       [INTEGRATED]  ← exec 域
│   ├── Project Management       [CLOSED_LOOP]
│   ├── WebUI                    [PRODUCTION]
│   └── CLI                      [PRODUCTION]
│
└── FUTURE 4
    ├── Experience               [IMPLEMENTED→FUTURE]
    ├── Learning                 [ABSENT→FUTURE]
    ├── Replanning               [ABSENT→FUTURE]
    └── Release                  [ABSENT→FUTURE]
