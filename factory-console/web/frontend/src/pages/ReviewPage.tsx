/**
 * pages/ReviewPage.tsx — 单产物评审页 (S9-003 UX/UI Review Interface)。
 *
 * 数据流:
 *   GET  /api/artifacts/{id}          → ArtifactDetail (metadata 契约载荷 + review 门)
 *   POST /api/approvals/{id}/approve|reject body {reviewer, comment}
 *                                    → 决定 + comment 落库 (gate.comment 持久化;
 *                                      驳回意见 = 下轮重生成反馈输入, 数据流见 S9-003 报告)
 *
 * - 头部: 产物 ID/类型/版本/产出角色 + review 门状态 (status/reviewer/comment)
 * - pending 门 → approve/reject/comment 表单 (决定后自动刷新详情)
 * - 终态门 → 只读展示决定结果 (不可撤销 — 审计铁律)
 * - 内容分派: product → ProductReview (6 节) / ux_ui → UXUIReview (7 节 +
 *   wireframe ASCII 预览) / 其他 → GenericReview
 * - 空 metadata / API 错误 → 空态 / ErrorState (失败安全)
 */
import { useCallback, useState } from 'react';
import { api } from '../api/client';
import { useAsync } from '../hooks/useAsync';
import { useAppState } from '../state/AppState';
import { statusBadge } from '../components/Badge';
import { ErrorState, LoadingState } from '../components/State';
import { artifactTypeLabel } from '../models/types';
import type { ArtifactDetail } from '../models/types';
import { GenericReview, ProductReview, UXUIReview } from './ReviewSections';

/** 产物类型 → 评审内容组件分派 (product/ux_ui 特殊节渲染; 其余通用)。 */
function reviewBody(detail: ArtifactDetail): JSX.Element {
  const type = detail.type.toLowerCase();
  if (type === 'product' || type === 'prd') {
    return <ProductReview detail={detail} />;
  }
  if (type === 'ux_ui' || type === 'design') {
    return <UXUIReview detail={detail} />;
  }
  return <GenericReview detail={detail} />;
}

export function ReviewPage(): JSX.Element {
  const { page, navigate } = useAppState();
  const artifactId = page.name === 'review' ? page.artifactId : '';

  const [refreshKey, setRefreshKey] = useState(0);
  const { data: detail, error, loading } = useAsync(
    useCallback(() => api.artifact(artifactId), [artifactId, refreshKey]),
    [artifactId, refreshKey],
  );

  // 决定表单状态 (approve/reject + comment)
  const [comment, setComment] = useState('');
  const [deciding, setDeciding] = useState<'approve' | 'reject' | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionDone, setActionDone] = useState<string | null>(null);

  const decide = async (action: 'approve' | 'reject') => {
    if (!detail?.review) return;
    setDeciding(action);
    setActionError(null);
    setActionDone(null);
    try {
      const trimmed = comment.trim();
      if (action === 'approve') {
        await api.approveApproval(detail.review.id, trimmed);
      } else {
        await api.rejectApproval(detail.review.id, trimmed);
      }
      setActionDone(action === 'approve' ? '已批准 — 意见已持久化到审批门' : '已驳回 — 意见为下轮重生成反馈输入');
      setComment('');
      setRefreshKey((k) => k + 1); // 刷新详情 → 门状态更新
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeciding(null);
    }
  };

  if (loading) return <LoadingState label="加载产物详情…" />;
  if (error) return <ErrorState message={error} />;
  if (!detail) return <ErrorState message="产物详情为空" />;

  const review = detail.review;
  const pending = review !== null && review.status === 'pending';

  return (
    <div className="page review-page">
      <div className="review-header">
        <button type="button" className="back-link" onClick={() => navigate({ name: 'artifacts' })}>
          ← 返回产物
        </button>
        <h2>评审 · {artifactTypeLabel(detail.type)}</h2>
        <div className="approval-meta review-meta">
          {statusBadge(detail.status)}
          <span className="muted">
            {detail.id} · v{detail.version ?? '?'}
          </span>
          <span className="muted">产出: {detail.producer_role}</span>
          <span className="muted">阶段: {detail.stage_id}</span>
        </div>
      </div>

      {review ? (
        <div className="review-gate">
          <p className="review-gate-title">
            审批门 {review.stage_id} — {review.id}
          </p>
          <div className="approval-meta">
            {statusBadge(review.status)}
            {review.reviewer ? <span className="muted">by {review.reviewer}</span> : null}
          </div>
          {review.comment ? <p className="approval-comment">评审意见: {review.comment}</p> : null}
          {!pending ? <p className="muted">该门已决定, 不可撤销 (审计铁律)。</p> : null}
        </div>
      ) : (
        <div className="review-gate">
          <p className="muted">该产物暂无绑定审批门 (只读浏览, 无法决定)。</p>
        </div>
      )}

      {pending ? (
        <div className="review-decide">
          <label className="muted" htmlFor="review-comment">
            评审意见 (持久化为 gate.comment; 驳回意见将作为下轮重生成反馈输入)
          </label>
          <textarea
            id="review-comment"
            aria-label="评审意见"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="例如: MVP 范围过大, 请移除月度报表…"
            rows={3}
          />
          {actionError ? <ErrorState message={actionError} /> : null}
          {actionDone ? <p className="review-done">✅ {actionDone}</p> : null}
          <div className="approval-actions">
            <button
              type="button"
              className="btn-approve"
              disabled={deciding !== null}
              onClick={() => decide('approve')}
            >
              {deciding === 'approve' ? '处理中…' : 'Approve'}
            </button>
            <button
              type="button"
              className="btn-reject"
              disabled={deciding !== null}
              onClick={() => decide('reject')}
            >
              {deciding === 'reject' ? '处理中…' : 'Reject'}
            </button>
          </div>
        </div>
      ) : null}

      {reviewBody(detail)}
    </div>
  );
}
