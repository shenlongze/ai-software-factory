# 09 — WebUI Truth Audit
- useState 扫描: projects/open/input/runs/selection — 均为 UI/投影态,
  业务真相来自 API (S35 模板降级已做) — 无独立业务真相 (健康)
- 风险点: 审批/进度卡由后端 SSE 事件驱动 (projection), ACC/APR 经 API —
  Human Control Plane 成立
- 结论: 前端健康; 无 P0
