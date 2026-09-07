# 00 — S47-E4 REPORT: Conversation Refinement & Truth Retrieval (2026-09-07)

## Root Cause (验收暴露)
- Truth Read/Write 不对称: save_product_record 可写, agent 无通用读 →
  "继续/再具体/太模糊" 需读 REQ 正文时卡死 (轮4-6)
- "太模糊" 语义归 correction → 解释现状/抛问题, 非深化当前产出 (轮3)
- draft 内容无更新通道 → 深化只能重复新建

## Architecture Change
- Truth Retrieval: get_product_record 工具 (record_id / kind 最近 →
  完整 description) — canonical 读入口
- 迭代深化: product_truth.update_requirement + _update_content (仅
  draft/pending 草稿原地完善, 已批准拒绝→版本化); save_product_record
  支持 record_id → 同 id 更新 (幂等深化, 不重复建)
- Refinement 语义: governor relation + refinement (产出质量反馈) →
  guide 深化路径 (读产出→找不足→深化→update 同 draft)

## Real LLM E2E (P-b0adfaa6, 6 轮, 真实 API 链)
轮1 继续帮忙分析需求 → 读 REQ-5de88aef → 深化 (幂等)
轮2 有基础的想法么 → 读记录答已确定内容 (未跑任务统计)
轮3 太模糊了 → 读 REQ → 承认不足 → 主动钉死规格 (480×720/60fps/速度/
    血量/分值/Boss/公式) 标注"建议初值" + 聚焦确认
轮4 继续 → get_product_record + save_product_record(record_id)
    → REQ-5de88aef 更新为可开发规格 (状态机/数值/模块/验收点)
轮5 这个方向可以再具体一点 → 同 id 深化 (边界条件/异常/难度公式)
轮6 先看看确定什么 → get_product_record → 结构化 FACT 清单 (表格/公式/
    模块/范围边界)

## Acceptance
Truth Retrieval ✓ | Refinement → 深化 ✓ | 幂等 (同 id 更新) ✓
FACT/推断区分 (轮3 标注建议初值) ✓ | 无句子→工具硬编码 ✓

## Remaining Minor
- 轮1 措辞含"用户反复说太模糊了"(新会话历史无此前情 — LLM 轻微脑补,
  低危; 建议后续 grounding 检查)
- 轮1 project_scan 工具冗余调用 1 次 (未展开诊断, 引导已压制大部分)
- 深化数值为 AI 建议初值 (轮3 已标注待确认 — 规范行为)

## Git
1d5e7ef8 feat(conversation): refinement semantics and canonical record
retrieval | NO PUSH

## Verdict
缺陷 A (Truth Retrieval) + B (Refinement) 已修复并实证。Conversation 主链
「理解→工作→产出→读取→反馈→深化→再产出」闭环成立 — 接近可收口。

## Governance Items (记录, 不在此 Sprint 修)
1. FACT / INFERENCE / PROPOSAL / TO_CONFIRM 分层 — 产出与回答需显式区分
   用户确认事实 vs AI 推断/建议/待确认 (防推断渐变假需求); 建议在
   save_product_record 内容结构与回答模板层治理 (后续 PRD→Plan 前必做)
2. project_scan/project_status 冗余调用 — 归 Execution Optimization /
   Capability Router (工具面收敛), 非 Conversation 语义缺陷; 后续统一处理

## Status
S47-E4 收口 (Conversation 主线)。下一阶段: IDEA→Discovery→Requirement
→PRD→Plan 产品主链 全链路 Truth Read/Write/Refine/Continue 审计。
