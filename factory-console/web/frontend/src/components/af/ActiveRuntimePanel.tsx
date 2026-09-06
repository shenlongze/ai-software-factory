/**
 * ActiveRuntimePanel — S47-C1 实时运行卡 (Human Control Plane)。
 *
 * 纯投影: runs/当前状态来自父层真实 snapshot (projectRuns + workflow),
 * 事件增量来自 useRuntimeProjection (SSE)。不生成生产状态。
 */
import { useRuntimeProjection, type ConnectionState } from '../../hooks/useRuntimeProjection';

interface RunSummary {
  run_id: string;
  status: string;
  updated_at?: string;
  totals?: Record<string, number>;
}

interface Props {
  projectId: string;
  runs: RunSummary[];
  workflowStages?: { name: string; status: string }[];
  loading?: boolean;
}

function connectionLabel(c: ConnectionState): { text: string; cls: string } {
  switch (c) {
    case 'connected': return { text: '● LIVE', cls: 'live' };
    case 'connecting': return { text: '● CONNECTING', cls: 'busy' };
    case 'reconnecting': return { text: '↻ RECONNECTING', cls: 'busy' };
    case 'mock': return { text: '○ DEMO (event store unavailable)', cls: 'mock' };
    default: return { text: '○ OFFLINE', cls: 'off' };
  }
}

function eventLabel(name: string): string {
  switch (name) {
    case 'stage.started': return 'Stage Started';
    case 'stage.completed': return 'Stage Completed';
    case 'artifact.created': return 'Artifact Created';
    case 'approval.required': return 'Approval Required';
    case 'approval.completed': return 'Approval Completed';
    case 'runtime.created': return 'Runtime Created';
    case 'runtime.status.changed': return 'Runtime Status Changed';
    default: return name;
  }
}

export function ActiveRuntimePanel({ projectId, runs, workflowStages = [], loading }: Props) {
  const live = useRuntimeProjection(projectId);
  const conn = connectionLabel(live.connection);
  const activeRun = runs.find((r) => /running|in_progress/i.test(r.status)) ?? null;

  return (
    <section className="af-live-panel" data-testid="active-runtime-panel">
      <div className="af-live-head">
        <h3>Live Production</h3>
        <span className={`af-live-badge af-live-badge--${conn.cls}`} data-testid="af-conn-state">
          {conn.text}
        </span>
      </div>

      <div className="af-live-body" data-testid="af-active-run">
        {loading ? (
          <p className="ai-muted">Loading…</p>
        ) : activeRun != null ? (
          <dl className="af-live-run">
            <dt>Active Run</dt>
            <dd data-testid="af-active-run-id">{activeRun.run_id}</dd>
            <dt>Status</dt>
            <dd>{activeRun.status}</dd>
            {live.currentStage && (
              <>
                <dt>Current Stage</dt>
                <dd data-testid="af-current-stage">{live.currentStage}</dd>
              </>
            )}
            {live.lastStageCompleted && (
              <>
                <dt>Last Completed</dt>
                <dd>{live.lastStageCompleted}</dd>
              </>
            )}
            {live.lastError && (
              <>
                <dt className="af-error">Error</dt>
                <dd className="af-error" data-testid="af-last-error">{live.lastError}</dd>
              </>
            )}
          </dl>
        ) : (
          <p className="ai-muted">No active run.</p>
        )}

        {workflowStages.length > 0 && (
          <div className="af-live-stages" data-testid="af-stage-progress">
            {workflowStages.map((s) => (
              <span
                key={`${s.name}`}
                className={`af-stage-chip ${/complete|pass/i.test(s.status) ? 'done' : /running|in_progress/i.test(s.status) ? 'run' : ''}`}
              >
                {s.name}
              </span>
            ))}
          </div>
        )}

        {live.recentEvents.length > 0 && (
          <ul className="af-live-events" data-testid="af-live-events">
            {live.recentEvents.slice(-12).map((ev, i) => (
              <li key={`${ev.seq}-${i}`} className="af-live-event">
                <span className="ai-muted">
                  {ev.at.slice(11, 19)} · {eventLabel(ev.name)}
                  {ev.name === 'stage.completed' && ev.data.name ? ` — ${String(ev.data.name)}` : ''}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
