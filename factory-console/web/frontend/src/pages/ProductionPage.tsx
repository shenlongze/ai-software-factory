// pages/ProductionPage.tsx — S18 Production Control Tower
// 真实 API 投影 (无第二业务逻辑): ProductionRuns + Release + Approval
import { useEffect, useState, useCallback } from 'react';

interface Run { run_id: string; workflow_id: string; state: string; created_at?: string; artifacts?: string[]; }
interface Release { release_id: string; state: string; production_run_id: string; artifact_ids: string[]; evidence: unknown[]; failure_reason?: string; history?: { to: string; note?: string }[]; }
interface Approval { approval_id: string; decision: string; production_run_id: string; requested_by: string; artifact_ids: string[]; }
interface Gate { allowed: boolean; reason?: string; missing?: string[]; }
interface ReleaseView { releases: Release[]; gate: Gate; }

const api = async <T,>(path: string, init?: RequestInit): Promise<T> => {
  const res = await fetch(`/api${path}`, { headers: { 'Content-Type': 'application/json' }, ...init });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
};

const Badge = ({ state }: { state: string }) => (
  <span className={`badge badge-${String(state).toLowerCase().replace('_', '-')}`}>{state}</span>
);

export default function ProductionPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [selected, setSelected] = useState<string>('');
  const [view, setView] = useState<ReleaseView | null>(null);
  const [err, setErr] = useState('');

  const refresh = useCallback(async () => {
    try {
      setRuns(await api<{ items: Run[] }>('/production-runs').then(r => r.items ?? []));
      setApprovals(await api<{ items: Approval[] }>('/approval-requests').then(r => r.items ?? []));
    } catch (e) { setErr(String(e)); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const loadRun = async (runId: string) => {
    setSelected(runId);
    try { setView(await api<ReleaseView>(`/production-runs/${runId}/release`)); setErr(''); }
    catch (e) { setErr(String(e)); }
  };

  const doApproval = async (id: string, decision: 'approve' | 'reject') => {
    try {
      await api(`/approval-requests/${id}/${decision}`, { method: 'POST', body: JSON.stringify({ decided_by: 'human', reason: 'console' }) });
      await refresh();
      if (selected) loadRun(selected);
    } catch (e) { setErr(String(e)); }
  };

  const doRelease = async (relId: string) => {
    try {
      const r = await api<{ release: Release; blocked?: boolean; reason?: string }>(`/releases/${relId}/execute`, { method: 'POST' });
      if (r.blocked) setErr(`Release BLOCKED: ${r.reason}`);
      await refresh();
      if (selected) loadRun(selected);
    } catch (e) { setErr(String(e)); }
  };

  return (
    <div className="production-page">
      <h2>Production Control Tower</h2>
      {err && <div className="err-box">{err}</div>}
      <section>
        <h3>Production Runs</h3>
        <table>
          <thead><tr><th>Run</th><th>Workflow</th><th>State</th><th>Artifacts</th></tr></thead>
          <tbody>
            {runs.map(r => (
              <tr key={r.run_id} onClick={() => loadRun(r.run_id)} className={selected === r.run_id ? 'sel' : ''}>
                <td>{r.run_id}</td><td>{r.workflow_id}</td><td><Badge state={r.state} /></td>
                <td>{(r.artifacts || []).length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {selected && (
        <section>
          <h3>Release Panel — {selected}</h3>
          {view && (
            <>
              <p><strong>Gate:</strong> {view.gate.allowed ? 'ALLOWED' : 'BLOCKED'}
                {view.gate.reason && <span> — {view.gate.reason}</span>}
                {view.gate.missing && view.gate.missing.length > 0 && <span> (missing: {view.gate.missing.join(', ')})</span>}
              </p>
              {view.releases.map(rel => (
                <div key={rel.release_id} className="release-card">
                  <span>{rel.release_id} <Badge state={rel.state} /></span>
                  {rel.failure_reason && <div className="err-box">{rel.failure_reason}</div>}
                  {rel.history && <small>{rel.history.map(h => h.to).join(' → ')}</small>}
                  {rel.state === 'PENDING' || rel.state === 'GATED' || rel.state === 'APPROVED' ? (
                    <button onClick={() => doRelease(rel.release_id)}>Execute Release</button>
                  ) : null}
                </div>
              ))}
              {view.releases.length === 0 && (
                <button onClick={async () => { await api(`/production-runs/${selected}/releases`, { method: 'POST' }); loadRun(selected); }}>
                  Create Release
                </button>
              )}
            </>
          )}
        </section>
      )}

      <section>
        <h3>Approval Center</h3>
        <table>
          <thead><tr><th>Approval</th><th>Run</th><th>Decision</th><th>Requested By</th><th>Actions</th></tr></thead>
          <tbody>
            {approvals.filter(a => a.decision === 'PENDING').map(a => (
              <tr key={a.approval_id}>
                <td>{a.approval_id}</td><td>{a.production_run_id}</td><td><Badge state={a.decision} /></td>
                <td>{a.requested_by}</td>
                <td>
                  <button onClick={() => doApproval(a.approval_id, 'approve')}>Approve</button>
                  <button className="danger" onClick={() => doApproval(a.approval_id, 'reject')}>Reject</button>
                </td>
              </tr>
            ))}
            {approvals.filter(a => a.decision === 'PENDING').length === 0 && <tr><td colSpan={5}>No pending approvals</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  );
}
