# GAP PRINCIPLE MATRIX — STEP 6 (2026-09-02)

| GAP | Principle | Contract | Violation | 分类 | Confidence |
|-----|-----------|----------|-----------|------|-----------|
| G-TRUTH-01 三套 truth | P-DG-04 (SSOT) vs P-MOD-02 (模块独立数据+最终一致) | C-SSOT-01 | **域边界未定义**: 若三套属同一执行域 → 违反 P-DG-04; 若属不同模块数据域 (exec 独立产品) → P-MOD-02 允许 | CONTRACT_GAP (域契约缺失) | HIGH (冲突双方均有原则) |
| G-REQ-01 需求无下游 | P-REQ-01/02 (可追溯/变更受控) | C-TRACE-01 | 需求捕获真实但无版本/变更/下游引用 → 违反 P-REQ-01 | TRUE_GAP | HIGH |
| G-PRD-01 PRD 实体 | P-PRD-01 (审批门✅已实现) + P-PRD-02 (深度化 M3 🚧) | C-PRD-02 | 文档级 PRD+审批门有; domain entity+版本化属 M3 承诺未实现 | CONTRACT_GAP (M3 内未实现) | HIGH |
| G-ART-01 无 artifact 关联 | P-GOV-01 (审计) + P-DG-06 (evidence) | C-GOV-01 | 会话链执行证据 (artifacts) 未回写任务 → 审计链部分断裂 | TRUE_GAP (审计承诺内) | MEDIUM |
| G-LLM-01 LLMRouter 0 消费 | P-LLM-01/02 (分档路由) | C-LLM-01 | 模型路由承诺明确, 生产消费 0 | TRUE_GAP | HIGH |
| G-CORE-01 core 孤立 | P-MOD-01 (独立但统一) | C-MOD-01 | 无原则要求 console 必须 import core; 需契约测试纳入 (无证据) | DESIGN_CHOICE (意图独立) | MEDIUM |
| G-OS-01 非统一 OS | P-MOD-01/02 (独立但统一+最终一致) | — | 模块独立是设计原则; 但"统一设计/契约测试"无实施证据 | DESIGN_CHOICE (原则支撑) | MEDIUM |
| G-AGENT-01 | P-AGENT-01/02 (多 Agent 统一员工模型) | C-AGENT-01 | exec agents 真实; OS 级统一员工编排部分 UNKNOWN | PARTIAL MATCH | MEDIUM |
| G-EXP-01 Experience 写无读 | P-LEARN-01 (M4) + P-CONTROL-01 | C-LEARN-01 | M4 承诺 (产品自标 🚧📐); 当前 84 条写 = M4 前状态 | FUTURE_CAPABILITY (产品已标注) | HIGH |
| G-LEARN-01 Learning | P-LEARN-01 (M4) | C-LEARN-01 | M4 里程碑 | FUTURE_CAPABILITY | HIGH |
| G-REQ-02 分析不落盘 | P-REAL-01 (可审计) | C-GOV-01 | 产品智能分析结果不落盘 → 不可审计回看 | CONTRACT_GAP | MEDIUM |
| G-VER-01 验证无下游 | P-REAL-01 (能验证) | — | verify 存在于 ExecState/exec; 无独立验证 SSOT 下游 | UNPROVEN | MEDIUM |
