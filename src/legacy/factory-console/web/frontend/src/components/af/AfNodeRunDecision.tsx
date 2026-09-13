import { useCallback, useEffect, useState } from 'react';

interface Decision { decision_id: string; question: string; options: string[] }
interface Resolved { question?: string; chosen?: string }
interface RunStatus {
  run_id: string; state: string; node_id: string; iteration: number;
  completed_dimensions: string[];
  last_dimension?: string; last_summary?: string;
  open_question_count?: number;
  resolved_decisions?: Resolved[];
  pending_decisions: Decision[];
}

const DIM_LABELS = ['范围与目标', '功能与流程', '交互与操作', '边界与异常',
                    '非功能', '体验与内容', '验收与依赖'];

/** NodeRun 过程面板 — 真实执行过程可见 (Hermes 式): 维度推进/每回合
 *  摘要/已确认决策/待决策点击。轮询 API (canonical NodeRun 数据源)。 */
export function AfNodeRunDecision({ projectId }: { projectId?: string | null }): JSX.Element | null {
  const [run, setRun] = useState<RunStatus | null>(null);
  const [busy, setBusy] = useState<string>('');

  const load = useCallback(async () => {
    if (!projectId) { setRun(null); return; }
    try {
      const r = await fetch(`/api/projects/${encodeURIComponent(String(projectId))}/requirement-analysis`);
      const d = await r.json();
      setRun(d?.run ?? null);
    } catch { setRun(null); }
  }, [projectId]);

  useEffect(() => { load(); const t = window.setInterval(load, 3000);
    return () => window.clearInterval(t); }, [load]);

  const decide = async (decisionId: string, chosen: string) => {
    setBusy(decisionId);
    try {
      await fetch(`/api/projects/${encodeURIComponent(String(projectId))}/requirement-analysis/decisions`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decision_id: decisionId, chosen }) });
    } finally { setBusy(''); load(); }
  };

  const delegate = async () => {
    setBusy('delegate');
    try {
      await fetch(`/api/projects/${encodeURIComponent(String(projectId))}/requirement-analysis/auto-delegate`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ authorization: 'user-delegated' }) });
    } finally { setBusy(''); load(); }
  };

  if (!run) return null;
  const pend = run.pending_decisions ?? [];
  const resolved = run.resolved_decisions ?? [];
  const dims = run.completed_dimensions ?? [];
  const waiting = run.state === 'WAITING_FOR_USER';
  const done = run.state === 'COMPLETED';
  return (
    <section className="af-home-card" data-testid="af-node-run-decision"
             style={{ border: `1px solid ${done ? '#15803d' : waiting ? '#d97706' : '#2563eb'}`,
                      background: done ? '#f0fdf4' : waiting ? '#fffbeb' : '#eff6ff' }}>
      <h3>{done ? '✅' : waiting ? '🧭' : '⏳'} 需求分析 NodeRun {run.run_id.slice(-8)}
        <span style={{ marginLeft: 8, fontSize: 12, opacity: .7 }}>{run.state} · 迭代 {run.iteration}</span>
      </h3>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', margin: '6px 0', fontSize: 12 }}>
        {DIM_LABELS.map((l) => {
          const i = DIM_LABELS.indexOf(l);
          const covered = dims.includes(l) || i < dims.length;
          return <span key={l} style={{ padding: '2px 6px', borderRadius: 6,
            background: covered ? '#bbf7d0' : '#e5e7eb' }}>{covered ? '✓' : '○'} {l}</span>;
        })}
      </div>
      {run.last_dimension && run.last_summary ? (
        <p style={{ fontSize: 13, margin: '4px 0' }}>
          <strong>[{run.last_dimension}]</strong> {run.last_summary}
        </p>
      ) : null}
      {resolved.length > 0 ? (
        <div style={{ fontSize: 12, margin: '4px 0', opacity: .9 }}>
          <strong>已确认 {resolved.length} 项:</strong>
          <ul style={{ margin: '4px 0', paddingLeft: 18 }}>
            {resolved.slice(-5).map((r, i) => (
              <li key={i}>{String(r.question || '').slice(0, 40)}… → <b>{r.chosen}</b></li>
            ))}
          </ul>
        </div>
      ) : null}
      {waiting && pend.length > 0 ? pend.map((pd) => (
        <div key={pd.decision_id} style={{ margin: '8px 0' }}>
          <strong>{pd.question}</strong>
          <div style={{ display: 'flex', gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
            {pd.options.map((opt) => (
              <button key={opt} disabled={busy === pd.decision_id}
                      style={{ padding: '6px 12px', borderRadius: 8,
                               border: '1px solid #d97706', background: '#fff', cursor: 'pointer' }}
                      onClick={() => decide(pd.decision_id, opt)}>{opt}</button>
            ))}
          </div>
        </div>
      )) : null}
      {!done && (
        <button disabled={busy === 'delegate'} style={{ marginTop: 6, padding: '5px 12px',
          borderRadius: 8, border: '1px solid #2563eb', background: '#dbeafe', cursor: 'pointer' }}
          onClick={delegate}>⚡ 按推荐自动完成剩余</button>
      )}
      {done ? <p style={{ fontSize: 13, color: '#15803d' }}>需求分析完成 — 决策/建议已整理为需求记录</p> : null}
    </section>
  );
}
