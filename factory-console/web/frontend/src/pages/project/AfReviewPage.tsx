/**
 * AfReviewPage — S47-B Human Control Plane: Acceptance → Release → Delivery。
 *
 * 纯 Projection: 全部状态来自 canonical backend API (ACC 与 RELEASE 域);
 * 禁止本地维护验收/发布 truth; 按钮失败保持原状态 + 显示真实错误。
 */
import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api/client';
import type { AcceptanceReview, ReleaseTruth } from '../../models/domain';
import { StatusBadge } from '../../components/ds/StatusBadge';

interface Props {
  projectId: string;
}

interface Loaded {
  acceptances: AcceptanceReview[];
  releases: ReleaseTruth[];
}

function accStatusLabel(s: string): string {
  switch (s) {
    case 'APPROVED': return 'Approved';
    case 'CHANGE_REQUESTED': return 'Change Requested';
    case 'SUPERSEDED': return 'Superseded';
    default: return 'Pending Review';
  }
}

function relStatusLabel(s: string): string {
  const map: Record<string, string> = {
    CREATED: 'Created', CANDIDATE: 'Candidate', GATED: 'Gate Passed',
    RELEASED: 'Released', SUPERSEDED: 'Superseded', REJECTED: 'Rejected',
    REVOKED: 'Revoked',
  };
  return map[s] ?? s;
}

export function AfReviewPage({ projectId }: Props) {
  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState<string>('');
  const [busy, setBusy] = useState<string>('');
  const [changeComment, setChangeComment] = useState<Record<string, string>>({});
  const [changeOpen, setChangeOpen] = useState<string>('');

  const load = async () => {
    try {
      const [acceptances, releases] = await Promise.all([
        api.projectAcceptances(projectId),
        api.releasesTruth(),
      ]);
      // 项目归属 join: 本项目 ACC 的 run/artifact 关联的 canonical release
      const accRuns = new Set(acceptances.map((a) => a.source_run_id ?? ''));
      const mine = releases.filter((r) => accRuns.has(r.task_run_id ?? ''));
      setData({ acceptances, releases: mine });
      setError('');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const acceptances = useMemo(() => data?.acceptances ?? [], [data]);
  const releases = useMemo(() => data?.releases ?? [], [data]);

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    setError('');
    try {
      await fn();
      await load(); // backend 成功 → 重新读 canonical truth
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e)); // 失败保持原状态
    } finally {
      setBusy('');
    }
  };

  return (
    <div className="ai-review" data-testid="af-review-page">
      {error && (
        <div className="ai-review-error" role="alert" data-testid="af-review-error">
          {error}
        </div>
      )}

      <section className="ai-review-section" data-testid="af-review-acceptance">
        <h3>Review &amp; Acceptance</h3>
        {acceptances.length === 0 && <p className="ai-muted">还没有可验收的产物。</p>}
        {acceptances.map((a) => (
          <div className="ai-review-card" key={a.acceptance_id} data-testid={`acc-${a.acceptance_id}`}>
            <div className="ai-review-card-head">
              <strong>{accStatusLabel(a.status)}</strong>
              <StatusBadge status={a.status} />
              <span className="ai-muted">
                artifact {a.artifact_id.slice(0, 14)} · v{a.version} · ver{' '}
                {a.verification_id.slice(0, 10)} {a.verification_status ?? ''}
              </span>
            </div>
            {a.decision?.comment && (
              <p className="ai-review-comment">“{a.decision.comment}” — {a.decision.at ?? ''}</p>
            )}

            {a.status === 'PENDING' && (
              <div className="ai-review-actions">
                <button
                  type="button"
                  className="ai-btn ai-btn--approve"
                  disabled={busy !== ''}
                  data-testid={`approve-${a.acceptance_id}`}
                  onClick={() => void act('approve', () => api.approveAcceptance(a.acceptance_id))}
                >
                  {busy === 'approve' ? 'Approving…' : 'Approve'}
                </button>
                <button
                  type="button"
                  className="ai-btn"
                  disabled={busy !== ''}
                  onClick={() => setChangeOpen(changeOpen === a.acceptance_id ? '' : a.acceptance_id)}
                >
                  Request Changes
                </button>
              </div>
            )}
            {a.status === 'APPROVED' && (
              <button
                type="button"
                className="ai-btn"
                disabled={busy !== ''}
                data-testid={`request-change-${a.acceptance_id}`}
                onClick={() => setChangeOpen(changeOpen === a.acceptance_id ? '' : a.acceptance_id)}
              >
                Request Changes
              </button>
            )}

            {changeOpen === a.acceptance_id && (
              <div className="ai-review-change">
                <textarea
                  rows={3}
                  placeholder="请描述希望修改的内容（功能 / UI / 缺陷 …）"
                  value={changeComment[a.acceptance_id] ?? ''}
                  data-testid={`change-input-${a.acceptance_id}`}
                  onChange={(e) =>
                    setChangeComment((m) => ({ ...m, [a.acceptance_id]: e.target.value }))
                  }
                />
                <button
                  type="button"
                  className="ai-btn ai-btn--danger"
                  disabled={busy !== '' || !(changeComment[a.acceptance_id] ?? '').trim()}
                  onClick={() => {
                    const comment = (changeComment[a.acceptance_id] ?? '').trim();
                    void act('change', () => api.requestAcceptanceChange(a.acceptance_id, comment));
                  }}
                >
                  Submit Change Request
                </button>
              </div>
            )}
          </div>
        ))}
      </section>

      <section className="ai-review-section" data-testid="af-review-release">
        <h3>Release</h3>
        {releases.length === 0 && <p className="ai-muted">通过验收后即可创建 Release。</p>}
        {acceptances.some((a) => a.status === 'APPROVED') &&
          !releases.some((r) => r.status === 'RELEASED') && (
            <button
              type="button"
              className="ai-btn ai-btn--primary"
              disabled={busy !== ''}
              data-testid="af-create-release"
              onClick={() => {
                const acc = acceptances.find((a) => a.status === 'APPROVED');
                if (acc) void act('create-release', () => api.createReleaseFromAcceptance(acc.acceptance_id));
              }}
            >
              {busy === 'create-release' ? 'Creating…' : 'Create Release (Gate)'}
            </button>
          )}
        {releases.map((r) => (
          <div className="ai-review-card" key={r.release_id} data-testid={`rel-${r.release_id}`}>
            <div className="ai-review-card-head">
              <strong>{relStatusLabel(r.status)}</strong>
              <StatusBadge status={r.status} />
              <span className="ai-muted">{r.release_id}{r.version ? ` · v${r.version}` : ''}</span>
            </div>
            {r.gate && (
              <p className="ai-muted">
                Gate: {r.gate.allowed ? 'PASS' : 'BLOCKED'}
                {r.gate.missing && r.gate.missing.length > 0
                  ? ` — ${r.gate.missing.join(', ')}`
                  : ''}
              </p>
            )}
            {r.status !== 'RELEASED' && (
              <button
                type="button"
                className="ai-btn ai-btn--primary"
                disabled={busy !== ''}
                data-testid={`release-${r.release_id}`}
                onClick={() => void act('release', () => api.executeRelease(r.release_id))}
              >
                {busy === 'release' ? 'Releasing…' : 'Release'}
              </button>
            )}
            {r.status === 'RELEASED' && (
              <div className="ai-review-delivery" data-testid={`delivery-${r.release_id}`}>
                <strong>Delivered ✓</strong>
                <ul className="ai-muted">
                  {r.artifact_ids?.map((aid) => (
                    <li key={aid}>artifact {aid}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
      </section>
    </div>
  );
}
