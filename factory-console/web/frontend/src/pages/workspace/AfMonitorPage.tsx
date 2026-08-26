/**
 * pages/workspace/AfMonitorPage.tsx — 📊 监控 (M4, 设计文档 §8)。
 *
 * Founder 2026-08-27: 监控独立入口, 不进设置; 分两个 Tab:
 *   Tab 1 · 自身能力监控: 内部 AI 员工 / 技能 / 工具 / 执行中 / 系统
 *   Tab 2 · 外部能力监控: 外部执行器指标 (效率/效果/完成率/回修/验证) + 告警
 *
 * 真实数据流 (禁止 mock): /api/agents · /api/skills · /api/runtime-sessions?status=running
 *   · /api/monitor · /api/external-ai · /api/external-ai/monitor
 */

import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';
import { AfErrorState, AfLoadingState } from '../../components/af/AfState';

interface ExecutorMetric {
  executor_id: string; total: number; success: number; failed: number;
  success_rate: number; first_pass_rate: number; verify_pass_rate?: number | null;
  verified: number; avg_duration_ms?: number | null; rework_total: number;
  last_run_at?: string | null; last_result?: string | null; last_mode?: string | null;
  last_host_agent?: string | null; last_result_id?: string | null;
}
interface Alert { severity: string; executor_id?: string; type: string; detail: string }
interface Adapter { id: string; name: string; found: boolean; builtin: boolean; path?: string | null }

const SEV = { high: '🔴', medium: '🟠', info: 'ℹ️' } as Record<string, string>;

function pct(v: number | null | undefined): string {
  return v == null ? '—' : `${Math.round(v * 100)}%`;
}

function formatTime(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('zh-CN', { hour12: false });
}

export function AfMonitorPage(): JSX.Element {
  const [tab, setTab] = useState<'self' | 'external'>('self');
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [refreshTick, setRefreshTick] = useState(0);

  // 自身能力数据
  const [agents, setAgents] = useState<Array<{ id?: string; name?: string; role?: string; status?: string; source?: string }>>([]);
  const [skillsCount, setSkillsCount] = useState(0);
  const [running, setRunning] = useState<Array<{ id?: string; agent_id?: string; task_id?: string; status?: string }>>([]);
  const [sysMon, setSysMon] = useState<Record<string, unknown> | null>(null);
  // 外部能力数据
  const [adapters, setAdapters] = useState<Adapter[]>([]);
  const [executors, setExecutors] = useState<ExecutorMetric[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [ag, sk, run, mon, ext, extMon] = await Promise.all([
        api.agents(),
        api.skills(),
        api.runtimeSessions('running'),
        api.monitor(5, 0),
        api.externalAi(),
        api.externalAiMonitor(),
      ]);
      setAgents(ag as Array<{ id?: string; name?: string; role?: string; status?: string; source?: string }>);
      setSkillsCount((sk as { skills?: unknown[] }).skills?.length ?? 0);
      setRunning(run as Array<{ id?: string; agent_id?: string; task_id?: string; status?: string }>);
      setSysMon(mon as Record<string, unknown>);
      setAdapters(ext.adapters ?? []);
      setExecutors(extMon.executors ?? []);
      setAlerts(extMon.alerts ?? []);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load, refreshTick]);

  const internalCount = agents.filter((a) => !(a.source && a.source !== '')).length;

  return (
    <div className="af-monitor" data-testid="af-monitor">
      <h2 className="af-detail-name">📊 监控</h2>
      <div className="af-settings-tabs" role="tablist" aria-label="监控分类">
        <button type="button" role="tab" aria-selected={tab === 'self'} className={`af-settings-tab${tab === 'self' ? ' active' : ''}`} onClick={() => setTab('self')}>自身能力</button>
        <button type="button" role="tab" aria-selected={tab === 'external'} className={`af-settings-tab${tab === 'external' ? ' active' : ''}`} onClick={() => setTab('external')}>外部能力</button>
      </div>
      <div className="af-monitor-actions">
        <button type="button" className="af-settings-action" onClick={() => setRefreshTick((t) => t + 1)}>⟳ 刷新</button>
      </div>
      {error ? <AfErrorState message={`监控加载失败: ${error}`} onRetry={() => setRefreshTick((t) => t + 1)} /> : null}
      {loading && !error ? <AfLoadingState label="正在加载监控…" /> : null}
      {!loading && !error ? (
        tab === 'self' ? (
          <div className="af-monitor-self" data-testid="af-monitor-self">
            <div className="af-monitor-cards">
              <div className="af-monitor-card"><span className="af-monitor-card-num">{agents.length}</span><span>AI 员工（内部 {internalCount}）</span></div>
              <div className="af-monitor-card"><span className="af-monitor-card-num">{skillsCount}</span><span>技能</span></div>
              <div className="af-monitor-card"><span className="af-monitor-card-num">{running.length}</span><span>执行中任务</span></div>
              <div className="af-monitor-card"><span className="af-monitor-card-num">{alerts.filter((a) => a.severity === 'high').length}</span><span>告警</span></div>
            </div>
            <h3 className="af-settings-h3">AI 员工</h3>
            <div className="af-settings-list">
              {agents.map((a) => (
                <div key={a.id ?? ''} className="af-settings-list-row">
                  <span className="af-settings-list-name">{a.name ?? a.id}{a.source ? ` ⚡${a.source}` : ''}</span>
                  <span className="af-settings-list-meta">{a.role ?? '—'}</span>
                </div>
              ))}
            </div>
            <h3 className="af-settings-h3">执行中任务</h3>
            {running.length === 0 ? <p className="af-home-note">暂无执行中任务</p> : (
              <div className="af-settings-list">
                {running.map((r) => (
                  <div key={r.id ?? ''} className="af-settings-list-row">
                    <span className="af-settings-list-name">agent: {r.agent_id ?? '—'}</span>
                    <span className="af-settings-list-meta">task: {r.task_id ?? '—'} · {r.status ?? ''}</span>
                  </div>
                ))}
              </div>
            )}
            <h3 className="af-settings-h3">系统</h3>
            {sysMon ? (
              <p className="af-home-note">
                version={String((sysMon as Record<string, unknown>).version ?? '—')} ·
                frontend={(sysMon as Record<string, unknown>).frontend ? '运行中' : '未运行'} ·
                backend={(sysMon as Record<string, unknown>).backend ? '运行中' : '未运行'}
              </p>
            ) : null}
          </div>
        ) : (
          <div className="af-monitor-external" data-testid="af-monitor-external">
            <h3 className="af-settings-h3">外部执行器（{adapters.length}）</h3>
            <div className="af-settings-list">
              {adapters.map((a) => (
                <div key={a.id} className="af-settings-list-row">
                  <span className="af-settings-list-name">{a.name} <code>{a.id}</code>{a.builtin ? ' 内置' : ' 自定义'}</span>
                  <span className="af-settings-list-meta">{a.found ? `✅ ${a.path}` : '⚠️ 未发现'}</span>
                </div>
              ))}
            </div>
            <h3 className="af-settings-h3">指标（EXS 执行记录）</h3>
            {executors.length === 0 ? <p className="af-home-note">暂无委派记录（有委派后自动出现；黑盒层如实标注）</p> : (
              <table className="af-monitor-table" data-testid="af-monitor-table">
                <thead><tr><th>执行器</th><th>次数</th><th>成功率</th><th>首次通过</th><th>验证通过</th><th>平均耗时</th><th>回修</th><th>最近</th></tr></thead>
                <tbody>
                  {executors.map((m) => (
                    <tr key={m.executor_id} data-testid={`af-monitor-exec-${m.executor_id}`}>
                      <td>{m.executor_id}{m.last_host_agent ? ` · ${m.last_host_agent}` : ''}</td>
                      <td>{m.total}</td>
                      <td>{pct(m.success_rate)}</td>
                      <td>{pct(m.first_pass_rate)}</td>
                      <td>{pct(m.verify_pass_rate)}</td>
                      <td>{m.avg_duration_ms != null ? `${Math.round(m.avg_duration_ms / 1000)}s` : '—'}</td>
                      <td>{m.rework_total}</td>
                      <td>{formatTime(m.last_run_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <h3 className="af-settings-h3">告警</h3>
            {alerts.length === 0 ? <p className="af-home-note">暂无告警</p> : (
              <div className="af-settings-list">
                {alerts.map((a, i) => (
                  <div key={i} className="af-settings-list-row">
                    <span className="af-settings-list-name">{SEV[a.severity] ?? '•'} {a.executor_id ?? a.type}</span>
                    <span className="af-settings-list-meta">{a.detail}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      ) : null}
    </div>
  );
}
