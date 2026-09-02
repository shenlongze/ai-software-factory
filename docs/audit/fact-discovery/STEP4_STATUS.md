# STEP 4 STATUS — (2026-09-02)

## 完成项
- Relation graph (E01-E19) / Data lineage (含断点) / Agent control / LLM control
- Capability registry (30 项) / Isolated modules / Execution relation / Module integration
- PRD forensic (ABSENT) / Requirement lineage (capture PROVEN, downstream ABSENT)

## 1. 已证明关系 (PROVEN)
- User→Session→Requirement→requirements.json (agent_loop.py:795)
- Session→Plan→Task (plan_id) → ExecState → Run (会话链, E2E)
- Agent Selection→Execution (gateway router→execution_records 100)
- Execution→Audit (5160) / Artifact→Task (exec ART-* task=T00x)
- console→org (69) / console→exec (79)

## 2. 部分关系 (PARTIAL)
- Execution→Experience (写入 84, consumer 未证明)
- Discovery (conversation 集成, 运行时 UNKNOWN)
- Verification (exec test_result 存在; 会话链 verify 在 ExecState)

## 3. 缺失关系 (ABSENT)
- Requirement→Plan / Requirement→Task (requirements.json 无引用)
- Requirement→PRD (PRD 实体不存在)
- 会话链 Task→Artifact (backlog 无 artifact_ref)
- console→core / console→runtime (0)

## 4. UNKNOWN
- factory-core 内部消费者 (外部 0; 测试如何引用未验证)
- Experience/Learning/Release 消费者
- exec 角色 Agent (developer 等) 的独立生产入口
- factory.db 用途

## 5. REAL capabilities
Session / Intent / Requirement(capture) / Planning / Task / Agent / Agent Selection /
LLM(调用) / Tool / Skill / Execution / Recovery / Audit / Project Mgmt / WebUI / CLI

## 6. PARTIAL capabilities
Requirement(无下游) / Discovery / Orchestration(会话链动态,M3 侧 UNKNOWN) /
Verification / Artifact(exec 域) / Governance / Experience(写无读)

## 7. ISOLATED capabilities/modules
factory-core / LLMRouter / factory-runtime / Learning / Release / PRD(ABSENT)

## 8. 关键断点
- Requirement 无 plan/task 下游引用
- PRD 实体缺失
- 会话链 Task 无 Artifact 关联
- 三套 task/execution truth (backlog TASK-* / execution_plan T-* / exec T00x)
- LLMRouter 未接入 (模型选择无动态层)

## 9. 下一阶段输入材料
- 上述断点即 GAP/SEVERITY 输入
- CAPABILITY_REGISTRY + ISOLATED_MODULES = 孤立能力清单
- EXECUTION_RELATION = 三套 truth 证据
