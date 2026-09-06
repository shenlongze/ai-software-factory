# 03 — Semantic Routing
User → Governor LLM → relation/domain/needs_tool → 引导:
- complaint/correction/clarify → recovery (禁 project 诊断自证)
- confirm → 执行 pending; modify → 约束优先; decline → 不执行
- continue/reference → 保持 topic/domain
- question → 域工具提示 (product_lifecycle→project_lifecycle;
  task→project_tasks; 非本域不用统计)
- opinion/unknown → needs_tool=false → 工具克制 (无万能诊断 fallback)
