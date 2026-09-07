# 05 Tool Boundary
- tool_schemas+handler 全在 agent_loop (35) — Tool Registry 无
- 但本重构主线 = Node Loop; Tool 注册层排在 Node 化后 (先不大规模拆)
- requirement-analysis 期间 LLM 需工具: 项目上下文读 (project_status/
  project_lifecycle/get_product_record) — 复用既有, 不新建专用分析工具
  (分析能力 = Node executor prompt 结构, 非新 tool)
