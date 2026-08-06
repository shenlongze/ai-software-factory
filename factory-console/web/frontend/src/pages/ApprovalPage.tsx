import { useCallback, useState } from 'react';
import { api } from '../api/client';
import { useAsync } from '../hooks/useAsync';
import { useAppState } from '../state/AppState';
import { Card } from '../components/Card';
import { ScoreBar } from '../components/ScoreBar';
import { riskBadge, statusBadge } from '../components/Badge';
import { EvidenceChain } from '../components/EvidenceChain';
import { EmptyState, ErrorState, LoadingState, Modal } from '../components/State';
import type { ApprovalSummary } from '../models/types';

const DECISION_GUIDANCE =
  'Human Console 只读 — 审批决定由 9c Approval 状态机处理 (CLI: factory approval decide)。' +
  '本界面只提供查看与理解，不提供写路径 (Permission Boundary: 决策权永远在人工一侧)。';

/**
 * Approval Center — 审批中心 (PRD v3 / Confidence / Risk / Evidence +
 * Approve / Request Change / Reject 交互; 全部只读, 决定经 9c 状态机)。
 */
export function ApprovalPage(): JSX.Element {
  const { mode } = useAppState();
  const { data, error, loading } = useAsync(useCallback(() => api.approvals(), []), []);
  const [actionTarget, setActionTarget] = useState<ApprovalSummary | null>(null);
  const [actionName, setActionName] = useState('');

  if (loading) {
    return <LoadingState label="加载审批中心…" />;
  }
  if (error) {
    return <ErrorState message={error} />;
  }
  const approvals = data ?? [];
  const pending = approvals.filter((a) => a.status === 'pending');

  const requestAction = (approval: ApprovalSummary, action: string) => {
    // 只读语义: 不发起任何写请求 — 仅展示决定通道指引
    setActionTarget(approval);
    setActionName(action);
  };

  return (
    <div className="page approval-page">
      <h2>审批中心</h2>
      <p className="page-subtitle">
        当前 {pending.length} 个待处理请求 (共 {approvals.length} 个)。
        Console 只读 — 批准/驳回/要求修改 由 9c 状态机处理。
      </p>

      {approvals.length === 0 ? (
        <EmptyState message="暂无审批请求" />
      ) : (
        <div className="approval-grid">
          {approvals.map((a) => (
            <Card
              key={a.id}
              title={`${a.artifact_type || 'artifact'} · v${a.artifact_version ?? '?'}`}
              subtitle={`门 ${a.gate} · ${a.id}`}
            >
              <div className="approval-meta">
                {statusBadge(a.status)}
                {a.risk ? riskBadge(a.risk) : null}
                {mode === 'expert' ? <span className="muted">by {a.by}</span> : null}
              </div>
              <ScoreBar label="Confidence" value={a.confidence} />
              <div className="evidence-section">
                <EvidenceChain evidence={a.evidence} />
              </div>
              {a.comment ? <p className="approval-comment">备注: {a.comment}</p> : null}
              {a.status === 'pending' ? (
                <div className="approval-actions">
                  <button
                    type="button"
                    className="btn-approve"
                    onClick={() => requestAction(a, 'Approve')}
                  >
                    Approve
                  </button>
                  <button type="button" onClick={() => requestAction(a, 'Request Change')}>
                    Request Change
                  </button>
                  <button type="button" className="btn-reject" onClick={() => requestAction(a, 'Reject')}>
                    Reject
                  </button>
                </div>
              ) : null}
            </Card>
          ))}
        </div>
      )}

      {actionTarget ? (
        <Modal
          title={`${actionName} — ${actionTarget.artifact_type || 'artifact'} ${actionTarget.id}`}
          onClose={() => setActionTarget(null)}
        >
          <p>{DECISION_GUIDANCE}</p>
          <p className="muted">
            你选择了 <strong>{actionName}</strong>。本操作不向系统写入任何状态 (只读控制台)；
            实际决定请通过 CLI 状态机完成，以保留完整审计链。
          </p>
        </Modal>
      ) : null}
    </div>
  );
}
