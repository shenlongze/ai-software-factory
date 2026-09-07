import { useCallback, useEffect, useState } from 'react';

interface PendingDecision {
  decision_id: string;
  question: string;
  options: string[];
}

interface RunStatus {
  run_id: string;
  state: string;
  node_id: string;
  iteration: number;
  completed_dimensions: string[];
  pending_decisions: PendingDecision[];
}

/** Phase 3.5: NodeRun Human Decision 卡 — 真实用户点击 → canonical API (actor=human)。 */
export function AfNodeRunDecision({ projectId }: { projectId: string }): JSX.Element | null {
  const [run, setRun] = useState<RunStatus | null>(null);
  const [busy, setBusy] = useState<string>('');

  const load = useCallback(async () => {
    try {
      const r = await fetch(
        `/api/projects/${encodeURIComponent(projectId)}/requirement-analysis`);
      const d = await r.json();
      setRun(d?.run ?? null);
    } catch {
      setRun(null);
    }
  }, [projectId]);

  useEffect(() => {
    load();
    const t = window.setInterval(load, 4000);
    return () => window.clearInterval(t);
  }, [load]);

  const decide = async (decisionId: string, chosen: string) => {
    setBusy(decisionId);
    try {
      await fetch(
        `/api/projects/${encodeURIComponent(projectId)}/requirement-analysis/decisions`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decision_id: decisionId, chosen }) });
    } finally {
      setBusy('');
      load();
    }
  };

  if (!run || run.state !== 'WAITING_FOR_USER' || run.pending_decisions.length === 0) {
    return null;
  }
  const dims = run.completed_dimensions?.length ?? 0;
  return (
    <section className="af-home-card" data-testid="af-node-run-decision"
             style={{ border: '1px solid #d97706', background: '#fffbeb' }}>
      <h3>🧭 需求分析 · 等待你的决策 (NodeRun {run.run_id.slice(-8)})</h3>
      <p style={{ fontSize: 12, opacity: 0.7 }}>
        已覆盖维度 {dims}/7 · 迭代 {run.iteration} — 选择后分析自动继续
      </p>
      {run.pending_decisions.map((pd) => (
        <div key={pd.decision_id} style={{ margin: '8px 0' }}>
          <strong>{pd.question}</strong>
          <div style={{ display: 'flex', gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
            {pd.options.map((opt) => (
              <button key={opt} disabled={busy === pd.decision_id}
                      className="af-btn"
                      style={{ padding: '6px 12px', borderRadius: 8,
                               border: '1px solid #d97706', background: '#fff',
                               cursor: 'pointer' }}
                      onClick={() => decide(pd.decision_id, opt)}>
                {opt}
              </button>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
