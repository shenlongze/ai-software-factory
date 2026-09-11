# 04 — ROUTING ARCHITECTURE (现状 vs 目标)

现状:
User → history 注入 → [guide? (正则漏则无)] → LLM FC (CORE 工具面=项目诊断
倾斜 + intent 软参考) → 工具 → S35 前端模板 (project_tasks→覆盖)

目标 (差异):
User → 语义理解 → Conversation State (topic/domain/pending_proposal/
constraints) → intent → domain → truth → capability/tool → answer → state

差距:
1. pending_proposal 需结构化 (非句尾正则文本猜) — proposal 在 assistant
   提议后由状态捕获, 下轮 confirm 直接指向
2. CORE 工具面需含域工具平衡 (产品/需求) 或按 state 动态
3. complaint/recovery 语义 (用户纠错 → 恢复 topic 而非诊断自证)
4. S35 前端模板需改为: project_tasks 统计仅作辅助卡片, 不整轮覆盖 AI 文本
