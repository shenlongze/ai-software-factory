# REQUIREMENT GAPS — STEP 5
- G-REQ-01 CRITICAL: 需求捕获真实 (requirements.json 7 VALIDATED) 但无任何 downstream 引用
  (无 plan_id/task_id 字段, 无代码 reader 之外消费者) → 需求→执行链断裂
- G-REQ-02 MEDIUM: 需求分析 (product_intelligence) 结果不落盘 (actions.py:2864-2893)
- G-REQ-03 MEDIUM: requirements.json 无 version/change/status 演进字段 (仅 VALIDATED)
- 证据: requirements.json 结构 + agent_loop.py:795 + fastapi:1501
