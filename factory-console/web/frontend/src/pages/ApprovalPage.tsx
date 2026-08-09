import { useCallback, useState } from 'react';
import { api } from '../api/client';
import { useAsync } from '../hooks/useAsync';
import { useAppState } from '../state/AppState';
import { Card } from '../components/Card';
import { ScoreBar } from '../components/ScoreBar';
import { riskBadge, statusBadge } from '../components/Badge';
import { EvidenceChain } from '../components/EvidenceChain';
import { EmptyState, ErrorState, LoadingState, Modal } from '../components/State';
import type { ApprovalGateSummary, ApprovalSummary } from '../models/types';

/**
 * Approval Center — 审批中心。
 * 上半区: 组织级审批门 (S9-001 org ApprovalGate) — 可 approve/reject (Console 唯一写路径)。
 * 下半区: Core 9c 审批 (只读投影, 保持既有语义)。
 */
export function ApprovalPage(): JSX.Element {
  const { mode } = useAppState();
  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  // 组织级审批门 (S9-001)
  const gates = useAsync(useCallback(() => api.approvalGates(), [refreshKey]), [refreshKey]);
  // Core 审批 (只读)
  const core = useAsync(useCallback(() => api.approvals(), [refreshKey]), [refreshKey]);

  const [deciding, setDeciding] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [coreTarget, setCoreTarget] = useState<ApprovalSummary | null>(null);

  const decide = async (gate: ApprovalGateSummary, action: 'approve' | 'reject') => {
    setDeciding(gate.id);
    setDecisionError(null);
    try {
      if (action === 'approve') {
        await api.approveApproval(gate.id);
      } else {
        await api.rejectApproval(gate.id);
      }
      refresh();
    } catch (e: unknown) {
      setDecisionError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeciding(null);
    }
  };

  const pendingGates = (gates.data ?? []).filter((g) => g.status === 'pending');

  return (
    <div className="page approval-page">
      <h2>审批中心</h2>

      <section className="card" style={{ marginBottom: 16 }}>
        <h3>组织级审批门 (AI Factory Workflow)</h3>
        <p className="page-subtitle">
          当前 {pendingGates.length} 个待处理门 (共 {(gates.data ?? []).length} 个)。
          批准/驳回 将推进或终止 Workflow (source=console 审计)。
        </p>
        {decisionError ? <ErrorState message={decisionError} /> : null}
        {gates.loading ? <LoadingState label="加载审批门…" /> : null}
        {gates.error ? <ErrorState message={gates.error} /> : null}
        {(gates.data ?? []).length === 0 && !gates.loading && !gates.error ? (
          <EmptyState message="暂无组织级审批门" />
        ) : (
          <div className="approval-grid">
            {(gates.data ?? []).map((g) => (
              <Card key={g.id} title={`门 ${g.stage_id}`} subtitle={g.workflow_id}>
                <div className="approval-meta">
                  {statusBadge(g.status)}
                  {g.reviewer ? <span className="muted">by {g.reviewer}</span> : null}
                </div>
                {g.comment ? <p className="approval-comment">备注: {g.comment}</p> : null}
                {g.status === 'pending' ? (
                  <div className="approval-actions">
                    <button
                      type="button"
                      className="btn-approve"
                      disabled={deciding === g.id}
                      onClick={() => decide(g, 'approve')}
                    >
                      {deciding === g.id ? '处理中…' : 'Approve'}
                    </button>
                    <button
                      type="button"
                      className="btn-reject"
                      disabled={deciding === g.id}
                      onClick={() => decide(g, 'reject')}
                    >
                      {deciding === g.id ? '处理中…' : 'Reject'}
                    </button>
                  </div>
                ) : null}
              </Card>
            ))}
          </div>
        )}
      </section>

      <section>
        <h3>Core 审批 (只读)</h3>
        {core.loading ? <LoadingState label="加载审批…" /> : null}
        {core.error ? <ErrorState message={core.error} /> : null}
        {(core.data ?? []).length === 0 && !core.loading && !core.error ? (
          <EmptyState message="暂无 Core 审批请求" />
        ) : (
          <div className="approval-grid">
            {(core.data ?? []).map((a) => (
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
              </Card>
            ))}
          </div>
        )}
      </section>

      {coreTarget ? (
        <Modal title={`Core 审批 ${coreTarget.id}`} onClose={() => setCoreTarget(null)}>
          <p className="muted">
            Core 9c 审批保持只读投影；决定请使用上方的组织级审批门或 CLI (factory approval
            approve/reject)。
          </p>
        </Modal>
      ) : null}
    </div>
  );
}
