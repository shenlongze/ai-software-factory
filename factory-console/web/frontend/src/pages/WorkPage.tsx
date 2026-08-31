/**
 * pages/WorkPage.tsx — K6 Work (Projects/Sprints/Tasks + Approval)。
 *
 * - 项目列表 (/api/projects-os)
 * - Project → Sprint → Task 视图 (/api/projects-os/:id/status)
 * - Task Detail: 状态/why/run/evidence (真实投影)
 * - Approval: [批准]/[拒绝] (经 governance, 不直接执行)
 */
import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { OsProjectSummary, OsProjectStatus } from '../models/types';

const STATE_ICON: Record<string, string> = {
  RUNNING: '🟢', WAITING: '🟡', BLOCKED: '🔴', FAILED: '❌',
  COMPLETED: '✅', IDLE: '⚪', RECOVERING: '🔧', PLANNED: '📋', READY: '🔵',
};

export function WorkPage(): JSX.Element {
  const [projects, setProjects] = useState<OsProjectSummary[]>([]);
  const [activeId, setActiveId] = useState('');
  const [status, setStatus] = useState<OsProjectStatus | null>(null);
  const [error, setError] = useState('');
  const [approvalMsg, setApprovalMsg] = useState('');

  useEffect(() => { void loadProjects(); }, []);

  const loadProjects = async () => {
    try {
      setProjects(await api.osProjects());
    } catch (e) {
      setError(String(e));
    }
  };

  const loadStatus = async (id: string) => {
    setActiveId(id);
    try {
      setStatus(await api.osProjectStatus(id));
    } catch (e) {
      setError(String(e));
    }
  };

  const requestApproval = async (taskId: string) => {
    try {
      const a = await api.osApproveTask(taskId);
      setApprovalMsg(`审批请求已创建: ${a.approval_id.slice(0, 14)} (PENDING) — 用户决定后任务可继续`);
    } catch (e) {
      setApprovalMsg('审批请求失败: ' + String(e));
    }
  };

  return (
    <div style={{ display: 'flex', height: '100%', gap: 12 }}>
      {/* 项目列表 */}
      <aside style={{ width: 240, borderRight: '1px solid rgba(255,255,255,0.1)', paddingRight: 12, overflowY: 'auto' }}>
        <h3 style={{ margin: '4px 0 10px', fontSize: 14 }}>项目</h3>
        {projects.map((p) => (
          <div
            key={p.id}
            onClick={() => void loadStatus(p.id)}
            style={{ padding: '8px 10px', borderRadius: 8, cursor: 'pointer', marginBottom: 4,
                     background: p.id === activeId ? 'rgba(0,113,227,0.25)' : 'rgba(255,255,255,0.04)',
                     border: '1px solid rgba(255,255,255,0.06)' }}
          >
            <div style={{ fontSize: 13, fontWeight: 600 }}>{p.title}</div>
            <div style={{ fontSize: 11, opacity: 0.6 }}>{p.status ?? 'ACTIVE'}</div>
          </div>
        ))}
        {projects.length === 0 && <div style={{ fontSize: 12, opacity: 0.6 }}>暂无项目 (从 Conversation 创建)</div>}
      </aside>

      {/* Project → Sprint → Task */}
      <main style={{ flex: 1, overflowY: 'auto', minWidth: 0 }}>
        {error && <div style={{ color: '#ff453a', fontSize: 12 }}>{error}</div>}
        {approvalMsg && <div style={{ fontSize: 12, marginBottom: 6, opacity: 0.8 }}>{approvalMsg}</div>}

        {status ? (
          <>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 8 }}>
              <h2 style={{ margin: 0, fontSize: 18 }}>{status.title}</h2>
              <span style={{ fontSize: 12, opacity: 0.7 }}>{status.status}</span>
              <span style={{ fontSize: 12, opacity: 0.7 }}>
                进度 {status.progress.percentage}% ({status.progress.completed}/{status.progress.total})
              </span>
            </div>

            {status.sprints.map((s) => (
              <section key={s.sprint_id} style={{ marginBottom: 14, padding: 10, borderRadius: 12,
                                                  background: 'rgba(255,255,255,0.04)' }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>📋 {s.title}</span>
                  <span style={{ fontSize: 11, opacity: 0.6 }}>
                    {s.progress.percentage}% ({s.progress.completed}/{s.progress.total})
                  </span>
                </div>
                {s.tasks.map((t) => (
                  <div key={t.id} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '4px 6px',
                                           fontSize: 13, borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                    <span>{STATE_ICON[t.status] ?? '•'}</span>
                    <span style={{ flex: 1 }}>{t.title.slice(0, 44)}</span>
                    <span style={{ opacity: 0.6, fontSize: 11 }}>{t.status}</span>
                    {t.production_run_id && (
                      <span style={{ opacity: 0.4, fontSize: 10 }}>{t.production_run_id.slice(0, 14)}</span>
                    )}
                    <button
                      onClick={() => void requestApproval(t.id)}
                      title="高风险任务需审批"
                      style={{ fontSize: 10, padding: '2px 8px', borderRadius: 6, cursor: 'pointer',
                               background: 'rgba(255,179,0,0.2)', border: '1px solid rgba(255,179,0,0.4)' }}
                    >
                      审批
                    </button>
                  </div>
                ))}
              </section>
            ))}
          </>
        ) : (
          <div style={{ opacity: 0.6, textAlign: 'center', marginTop: 80 }}>
            <div style={{ fontSize: 20, marginBottom: 8 }}>📋</div>
            <div>选择一个项目查看 Sprint / Task</div>
          </div>
        )}
      </main>
    </div>
  );
}
