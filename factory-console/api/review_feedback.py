"""factory-console/api/review_feedback.py — S10-006 审核反馈路由函数。

Feedback Loop (workspace-architecture.md §3 Panel Review + api-data-model.md
§1 ReviewComment): Reject 决定 → 前端同时 POST /api/review-feedback 保存
结构化反馈 {reviewer, artifact_id, comment, round} — 作为下一轮 Agent
重生成输入的数据源 (gate.comment 由 S9-001 决定端点负责审计落库, 本模块
只补 Loop 数据流, 不重设计审批 API)。

- POST /api/review-feedback   {reviewer, artifact_id, gate_id, comment}
  → 保存反馈记录 (round 按产物递增; 空意见不落库 → None (HTTP 层 400);
  缺 store → None (HTTP 层 503 — 失败安全: 审批决定不受反馈保存失败影响))
- GET  /api/review-feedback   ?artifact_id=&gate_id= (均可选, 无过滤 → 全库)
  → 反馈历史 (round 升序, 下轮输入按序消费; 缺 store → [] 失败安全)
"""

from __future__ import annotations

from typing import Any

from ..events import record_console_viewed
from ..models import ReviewFeedback


def save_review_feedback(
    service: Any,
    *,
    reviewer: str,
    artifact_id: str,
    gate_id: str,
    comment: str,
) -> ReviewFeedback | None:
    """POST /api/review-feedback — 保存一条审核反馈记录。

    空意见 → None (HTTP 层 400 — 无反馈不落库, 诚实边界); store 缺失 →
    None (HTTP 层 503 — 失败安全: Console 冷启动/未装配 review_feedback
    照常工作, 审批决定不受影响)。
    """
    return service.save_review_feedback(
        gate_id=gate_id,
        artifact_id=artifact_id,
        reviewer=reviewer,
        comment=comment,
    )


def list_review_feedback(
    service: Any,
    artifact_id: str | None = None,
    *,
    gate_id: str | None = None,
    logger: Any = None,
) -> list[ReviewFeedback]:
    """GET /api/review-feedback — 反馈历史 (按 artifact/gate 过滤, round 升序)。

    无过滤 → 全部记录; 无匹配 → [] (诚实空态); store 缺失 → [] (失败
    安全, 读命令永不因数据缺失失败)。logger 存在时发 console.viewed
    (view="review_feedback") 只读审计。
    """
    records = service.list_review_feedback(artifact_id, gate_id=gate_id)
    if logger is not None:
        record_console_viewed(
            logger,
            view="review_feedback",
            count=len(records),
            extra={"artifact_id": artifact_id, "gate_id": gate_id},
        )
    return records
