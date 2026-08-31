/**
 * pages/ControlTowerPage.tsx — K6 Control Tower (实时 Operations View)。
 *
 * 回答: "现在公司正在干什么?"
 * - Global Overview: Projects/Workforce/Activity (真实 /api/ops/overview)
 * - 谁在工作: agent 级状态 + Idle 原因 (真实 /api/ops/who-working)
 * - Project drill-down: /api/ops/drill/:project → task→run→evidence
 * - 状态全来自 Operational State 投影 (UI 不维护业务状态)
 */
import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { OpsOverview, OpsWhoWorking, OpsDrill, OsProjectSummary } from '../models/types';

const STATE_ICON: Record<string, string> = {
  RUNNING: '🟢', WAITING: '🟡', BLOCKED: '🔴', FAILED: '❌',
  COMPLETED: '✅', IDLE: '⚪', RECOVERING: '🔧',
};

export function ControlTowerPage(): JSX.Element {
  const [overview, setOverview] = useState<OpsOverview | null>(null);
  const [who, setWho] = useState<OpsWhoWorking | null>(null);
  const [projects, setProjects] = useState<OsProjectSummary[]>([]);
  const [drill, setDrill] = useState<OpsDrill | null>(null);
  const [error, setError] = useState('');
  const [auto, setAuto] = useState(true);

  const loadAll = async () => {
    try {
      const [ov, w, ps] = await Promise.all([api.opsOverview(), api.opsWhoWorking(), api.osProjects()]);
      setOverview(ov);
      setWho(w);
      setProjects(ps);
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    void loadAll();
    if (!auto) return;
    const t = window.setInterval(() => void loadAll(), 5000); // polling fallback
    return () => window.clearInterval(t);
  }, [auto]);

  const loadDrill = async (projectId: string) => {
    try {
      setDrill(await api.opsDrill(projectId));
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>🛰 Control Tower</h2>
        <label style={{ fontSize: 12, opacity: 0.7, display: 'flex', gap: 6, alignItems: 'center' }}>
          <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
          自动刷新 (5s)
        </label>
      </div>

      {error && <div style={{ color: '#ff453a', fontSize: 12 }}>{error}</div>}

      {/* Global Overview */}
      {overview && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
          {[
            ['项目', overview.projects.total],
            ['运行中', overview.projects.running],
            ['等待', overview.projects.waiting],
            ['阻塞', overview.projects.blocked],
            ['待审批', overview.projects.approval],
            ['失败', overview.projects.failed],
          ].map(([k, v]) => (
            <div key={String(k)} style={{ padding: 12, borderRadius: 12, background: 'rgba(255,255,255,0.05)',
                                          border: '1px solid rgba(255,255,255,0.08)' }}>
              <div style={{ fontSize: 11, opacity: 0.7 }}>{k}</div>
              <div style={{ fontSize: 26, fontWeight: 700 }}>{v}</div>
            </div>
          ))}
        </div>
      )}

      {/* 谁在工作 */}
      {who && (
        <section>
          <h3 style={{ margin: '8px 0', fontSize: 14 }}>谁在工作</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ opacity: 0.6, textAlign: 'left' }}>
                <th style={{ padding: 6 }}>Agent</th>
                <th style={{ padding: 6 }}>状态</th>
                <th style={{ padding: 6 }}>当前工作</th>
                <th style={{ padding: 6 }}>说明</th>
              </tr>
            </thead>
            <tbody>
              {who.agents.map((a) => (
                <tr key={a.agent} style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                  <td style={{ padding: 6 }}>{a.agent.slice(0, 20)}</td>
                  <td style={{ padding: 6 }}>
                    <span style={{ marginRight: 4 }}>{STATE_ICON[a.state] ?? '•'}</span>
                    {a.state}
                  </td>
                  <td style={{ padding: 6 }}>{a.current_work ?? '-'}</td>
                  <td style={{ padding: 6, opacity: 0.6, fontSize: 11 }}>
                    {a.idle_reason ?? a.blocking_reason ?? `${a.tasks} tasks`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Projects + drill-down */}
      <section>
        <h3 style={{ margin: '8px 0', fontSize: 14 }}>项目</h3>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => void loadDrill(p.id)}
              style={{ padding: '10px 14px', borderRadius: 10, cursor: 'pointer',
                       background: drill?.project.id === p.id ? 'rgba(0,113,227,0.3)' : 'rgba(255,255,255,0.06)',
                       border: '1px solid rgba(255,255,255,0.1)' }}
            >
              {p.title}
              <div style={{ fontSize: 10, opacity: 0.6 }}>{p.status}</div>
            </button>
          ))}
        </div>

        {drill && (
          <div style={{ marginTop: 10, padding: 12, borderRadius: 12, background: 'rgba(255,255,255,0.04)' }}>
            <div style={{ fontSize: 14, fontWeight: 600 }}>
              {drill.project.title} · {drill.project.progress.percentage}%
              <span style={{ marginLeft: 8, fontSize: 11, opacity: 0.6 }}>
                {drill.project.progress.completed}/{drill.project.progress.total} 完成
              </span>
            </div>
            {drill.sprints.map((s) => (
              <div key={s.sprint.id} style={{ marginTop: 8 }}>
                <div style={{ fontSize: 12, opacity: 0.7 }}>
                  {s.sprint.title} · {s.sprint.progress.percentage}%
                </div>
                {s.tasks.map((t) => (
                  <div key={t.id} style={{ display: 'flex', gap: 8, fontSize: 12, padding: '3px 6px', alignItems: 'center' }}>
                    <span>{STATE_ICON[t.operational_state] ?? '•'}</span>
                    <span>{t.title.slice(0, 32)}</span>
                    <span style={{ opacity: 0.6, fontSize: 10 }}>{t.status}</span>
                    {t.why && <span style={{ opacity: 0.5, fontSize: 10, marginLeft: 'auto' }}>{t.why.slice(0, 40)}</span>}
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
