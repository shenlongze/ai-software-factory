/**
 * pages/workspace/AfMonitorPage.tsx — 📊 监控中心 (M4.2, 设计文档 §8 扩展)。
 *
 * Founder 2026-08-27: 监控太简单, 维度不全 → 监控中心:
 * - 概览卡: 总执行/成功率/首次通过/验证通过/平均耗时/P90/回修/告警 (全部/自身/外部)
 * - 趋势图 (SVG 柱状: 近 N 天执行次数 + 成功率折线, 零依赖)
 * - 多维聚合: 按执行器 / host_agent / 项目 / 回修原因 / 验证方式
 * - 执行记录流 (最近 N 条, 点击钻取: 命令/验证/回修/错误)
 * - 告警区; 作用域切换 + 天数筛选 + 刷新
 *
 * 真实数据流: GET /api/external-ai/monitor?days=&recent= (内部+外部执行记录并轨)
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../../api/client';
import { AfErrorState, AfLoadingState } from '../../components/af/AfState';
import type { MonitorDetail, MonitorGroup, MonitorRecent, MonitorSummary } from '../../models/domain';

type Scope = 'all' | 'self' | 'external';
const SEV = { high: '🔴', medium: '🟠', info: 'ℹ️' } as Record<string, string>;

function pct(v: number | null | undefined): string {
  return v == null ? '—' : `${Math.round(v * 100)}%`;
}
function sec(ms?: number | null): string {
  return ms == null ? '—' : ms >= 60000 ? `${(ms / 60000).toFixed(1)}m` : `${Math.round(ms / 1000)}s`;
}
function fmt(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('zh-CN', { hour12: false });
}

function Card({ num, label, sub }: { num: string; label: string; sub?: string }) {
  return (
    <div className="af-monitor-card">
      <span className="af-monitor-card-num">{num}</span>
      <span>{label}</span>
      {sub ? <span className="af-monitor-card-sub">{sub}</span> : null}
    </div>
  );
}

function SummaryCards({ s }: { s: MonitorSummary }) {
  return (
    <div className="af-monitor-cards">
      <Card num={String(s.total)} label="执行次数" sub={`✓${s.success} · ✗${s.failed}`} />
      <Card num={pct(s.success_rate)} label="成功率" />
      <Card num={pct(s.first_pass_rate)} label="首次通过率" />
      <Card num={pct(s.verify_pass_rate)} label="验证通过率" sub={`已验证 ${s.verified}`} />
      <Card num={sec(s.avg_duration_ms)} label="平均耗时" sub={`P90 ${sec(s.p90_duration_ms)}`} />
      <Card num={s.cost_total_usd != null ? `$${s.cost_total_usd}` : '未知'} label="成本" sub={s.cost_known != null ? `已知 ${s.cost_known} · 未知 ${s.cost_unknown ?? 0}` : '宿主未报告'} />
      <Card num={String(s.total_rework)} label="回修总数" />
    </div>
  );
}

/** 对比视图: 内部 vs 外部 并排 (M4.3)。 */
function CompareView({ ext, internal }: { ext: MonitorSummary; internal: MonitorSummary }) {
  const row = (label: string, fmt: (s: MonitorSummary) => string) => (
    <tr key={label}>
      <td>{label}</td>
      <td>{fmt(ext)}</td>
      <td>{fmt(internal)}</td>
    </tr>
  );
  return (
    <div className="af-monitor-compare" data-testid="af-monitor-compare">
      <h3 className="af-settings-h3">内部 vs 外部 对比</h3>
      <table className="af-monitor-table">
        <thead><tr><th>维度</th><th>外部能力</th><th>自身能力</th></tr></thead>
        <tbody>
          {row('执行次数', (s) => String(s.total))}
          {row('成功率', (s) => pct(s.success_rate))}
          {row('首次通过率', (s) => pct(s.first_pass_rate))}
          {row('验证通过率', (s) => pct(s.verify_pass_rate))}
          {row('平均耗时', (s) => sec(s.avg_duration_ms))}
          {row('成本', (s) => (s.cost_total_usd != null ? `$${s.cost_total_usd}` : '未知'))}
          {row('回修', (s) => String(s.total_rework))}
        </tbody>
      </table>
    </div>
  );
}

/** 执行器对比: 简单分组条 (各执行器 成功/失败)。 */
function ExecutorBars({ rows }: { rows: MonitorGroup[] }) {
  if (!rows || rows.length === 0) return null;
  const max = Math.max(1, ...rows.map((r) => r.total));
  return (
    <div className="af-monitor-bars" data-testid="af-monitor-bars">
      <h3 className="af-settings-h3">执行器对比</h3>
      {rows.map((r) => (
        <div key={r.key} className="af-monitor-bar-row">
          <span className="af-monitor-bar-name">{r.key}</span>
          <div className="af-monitor-bar-track">
            <div className="af-monitor-bar-ok" style={{ width: `${(r.success / max) * 100}%` }} title={`成功 ${r.success}`} />
            <div className="af-monitor-bar-fail" style={{ width: `${(r.failed / max) * 100}%` }} title={`失败 ${r.failed}`} />
          </div>
          <span className="af-monitor-bar-num">{r.total}</span>
        </div>
      ))}
    </div>
  );
}

/** SVG 趋势图: 柱 = 执行次数, 折线 = 成功率 (零依赖)。 */
function TrendChart({ trend }: { trend: Array<{ date: string; count: number; success: number; failed: number }> }) {
  if (!trend || trend.length === 0) return <p className="af-home-note">暂无趋势数据（有执行后自动出现）</p>;
  const w = 760, h = 160, pad = 24;
  const max = Math.max(1, ...trend.map((t) => t.count));
  const bw = (w - pad * 2) / trend.length;
  const barH = (c: number) => (c / max) * (h - pad * 2);
  const line = trend
    .map((t, i) => {
      const rate = t.count ? t.success / t.count : 0;
      const x = pad + bw * i + bw / 2;
      const y = h - pad - rate * (h - pad * 2);
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <div className="af-monitor-chart">
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} role="img" aria-label="执行趋势">
        {[0.25, 0.5, 0.75, 1].map((g) => (
          <line key={g} x1={pad} x2={w - pad} y1={h - pad - g * (h - pad * 2)} y2={h - pad - g * (h - pad * 2)} stroke="var(--c-border)" strokeDasharray="4 4" />
        ))}
        {trend.map((t, i) => (
          <g key={t.date}>
            <rect x={pad + bw * i + bw * 0.2} y={h - pad - barH(t.count)} width={bw * 0.6} height={barH(t.count)} fill="#4c8dff" opacity={0.7} rx={2} />
            <title>{`${t.date}: ${t.count} 次 (成功 ${t.success})`}</title>
          </g>
        ))}
        <path d={line} fill="none" stroke="#22c55e" strokeWidth={2} />
      </svg>
      <div className="af-monitor-chart-labels">
        {trend.map((t) => (
          <span key={t.date}>{t.date.slice(5)}</span>
        ))}
      </div>
    </div>
  );
}

function TrendChartHourly({ trend }: { trend: Array<{ hour: string; count: number; success: number; failed: number }> }) {
  if (!trend || trend.length === 0) return <p className="af-home-note">暂无小时趋势</p>;
  const w = 760, h = 120, pad = 24;
  const max = Math.max(1, ...trend.map((t) => t.count));
  const bw = (w - pad * 2) / trend.length;
  return (
    <div className="af-monitor-chart">
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} role="img" aria-label="小时趋势">
        {trend.map((t, i) => (
          <g key={t.hour}>
            <rect x={pad + bw * i + bw * 0.25} y={h - pad - (t.count / max) * (h - pad)} width={bw * 0.5} height={(t.count / max) * (h - pad)} fill="#4c8dff" opacity={0.7} rx={2} />
            <title>{`${t.hour}: ${t.count} 次 (成功 ${t.success})`}</title>
          </g>
        ))}
      </svg>
      <div className="af-monitor-chart-labels">
        {trend.filter((_, i) => i % 4 === 0).map((t) => <span key={t.hour}>{t.hour.slice(6)}</span>)}
      </div>
    </div>
  );
}

function GroupTable({ title, rows }: { title: string; rows: MonitorGroup[] }) {
  if (!rows || rows.length === 0) return null;
  return (
    <>
      <h3 className="af-settings-h3">{title}</h3>
      <table className="af-monitor-table">
        <thead><tr><th>维度</th><th>次数</th><th>成功率</th><th>首次通过</th><th>验证通过</th><th>平均耗时</th><th>成本</th><th>回修</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <td>{r.key}</td><td>{r.total}</td>
              <td>{pct(r.success_rate)}</td><td>{pct(r.first_pass_rate)}</td>
              <td>{pct(r.verify_pass_rate)}</td><td>{sec(r.avg_duration_ms)}</td>
              <td>{r.cost_total_usd != null ? `$${r.cost_total_usd}` : '—'}</td>
              <td>{r.total_rework}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function RecentStream({ items }: { items: MonitorRecent[] }) {
  const [openId, setOpenId] = useState<string | null>(null);
  if (!items || items.length === 0) return <p className="af-home-note">暂无执行记录</p>;
  return (
    <div className="af-monitor-recent">
      {items.map((r) => {
        const rid = r.result_id ?? '';
        const ok = r.result === 'success';
        const open = openId === rid;
        return (
          <div key={rid || `${r.timestamp}-${Math.random()}`} className={`af-monitor-recent-row${open ? ' open' : ''}`} data-testid={`af-monitor-recent-${rid || 'x'}`}>
            <button type="button" className="af-monitor-recent-head" onClick={() => setOpenId(open ? null : rid)}>
              <span className={`af-monitor-dot ${ok ? 'ok' : 'fail'}`} />
              <span className="af-monitor-recent-who">{r.executor_id ?? ''}{r.host_agent ? `·${r.host_agent}` : ''}{r.agent && !r.executor_id ? `·${r.agent}` : ''}</span>
              <span className="af-monitor-recent-task">{r.task}</span>
              <span className="af-monitor-recent-meta">{sec(r.duration_ms)} · {fmt(r.timestamp)}</span>
              <span className={`af-monitor-recent-result ${ok ? 'ok' : 'fail'}`}>{ok ? '成功' : '失败'}</span>
            </button>
            {open ? (
              <div className="af-monitor-recent-detail">
                {r.verify && r.verify.result ? <p>✅ 验证: {r.verify.method ?? '—'} · {r.verify.result}{r.verify.score != null ? ` · ${r.verify.score}` : ''}</p> : null}
                {r.rework && r.rework.count ? <p>🔄 回修 {r.rework.count} 次{r.rework.reasons?.length ? `: ${r.rework.reasons.join('、')}` : ''}</p> : null}
                {r.command ? <p className="af-monitor-code">{r.command}</p> : null}
                {r.error ? <p className="af-monitor-error">{r.error}</p> : null}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

/** M6: 路由测试 + 自动闭环 (选谁 + 理由 + 候选; 一键委派)。 */
function RouteTest(): JSX.Element {
  const [task, setTask] = useState('');
  const [explicit, setExplicit] = useState('');
  const [route, setRoute] = useState<{ pick?: string | null; work_type: string; reason: string; alternatives: string[]; degraded?: boolean } | null>(null);
  const [exec, setExec] = useState<{ exit_code?: number; output?: string; result_id?: string; note?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  const doRoute = useCallback(async () => {
    if (!task.trim()) { setMsg('请输入任务描述'); return; }
    setBusy(true); setExec(null); setMsg('');
    try {
      const r = await api.routeExternalAi(task, explicit.trim());
      setRoute(r);
      setMsg(r.pick ? `选: ${r.pick} — ${r.reason}` : `无候选: ${r.reason}`);
    } catch (err) {
      setMsg(`路由失败: ${String(err)}`);
    } finally { setBusy(false); }
  }, [task, explicit]);

  const doAuto = useCallback(async () => {
    if (!task.trim()) { setMsg('请输入任务描述'); return; }
    setBusy(true); setMsg('');
    try {
      const r = await api.autoExternalAi(task, '', explicit.trim());
      setRoute(r.route);
      setExec(r.execution ?? { note: r.note ?? '无执行' });
    } catch (err) {
      setMsg(`自动闭环失败: ${String(err)}`);
    } finally { setBusy(false); }
  }, [task, explicit]);

  return (
    <div className="af-monitor-route" data-testid="af-monitor-route">
      <h3 className="af-settings-h3">🧭 路由测试（专业的人做专业的事）</h3>
      <div className="af-settings-form">
        <input className="af-settings-input af-settings-input--wide" placeholder="输入任务描述，如: 帮忙审查系统架构" aria-label="路由任务" value={task} onChange={(e) => setTask(e.target.value)} />
        <input className="af-settings-input" placeholder="显式指定 agent (可选)" aria-label="路由显式agent" value={explicit} onChange={(e) => setExplicit(e.target.value)} />
        <button type="button" className="af-settings-action af-settings-action--primary" onClick={() => void doRoute()} disabled={busy}>🧭 路由</button>
        <button type="button" className="af-settings-action" onClick={() => void doAuto()} disabled={busy}>🚀 路由+委派</button>
      </div>
      {msg ? <p className="af-composer-msg">{msg}</p> : null}
      {route ? (
        <div className="af-monitor-route-result" data-testid="af-monitor-route-result">
          <p><strong>🎯 选: {route.pick ?? '无'}</strong>（{route.work_type} · {route.reason}{route.degraded ? ' ⚠️已降级' : ''}）</p>
          {route.alternatives.length > 0 ? <p className="af-home-note">候选: {route.alternatives.slice(0, 6).join(' · ')}</p> : null}
        </div>
      ) : null}
      {exec ? (
        <div className="af-monitor-route-exec" data-testid="af-monitor-route-exec">
          {exec.note ? <p>⚠️ {exec.note}</p> : (
            <>
              <p>🚀 委派完成: exit={exec.exit_code} · result_id={exec.result_id}</p>
              {exec.output ? <p className="af-monitor-code">{exec.output.slice(0, 500)}</p> : null}
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}

export function AfMonitorPage(): JSX.Element {
  const [scope, setScope] = useState<Scope>('all');
  const [days, setDays] = useState(14);
  const [granularity, setGranularity] = useState<'day' | 'hour'>('day');
  const [data, setData] = useState<MonitorDetail | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setData(await api.externalAiMonitor(days, 30));
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { void load(); }, [load]);

  const scopeFilter = useCallback(
    (rows: MonitorGroup[] | undefined) => {
      if (!rows) return [];
      if (scope === 'self') return rows.filter((r) => !r.key.includes('.'));
      if (scope === 'external') return rows.filter((r) => r.key.includes('.') || ['codex', 'claude', 'hermes'].includes(r.key));
      return rows;
    },
    [scope],
  );

  const recent = useMemo(() => {
    if (!data) return [];
    if (scope === 'self') return data.recent.filter((r) => !r.executor_id);
    if (scope === 'external') return data.recent.filter((r) => r.executor_id);
    return data.recent;
  }, [data, scope]);

  const summary = data?.summary[scope === 'self' ? 'internal' : scope === 'external' ? 'external' : 'combined'] ?? null;
  const alerts = scope === 'self' ? [] : (data?.alerts ?? []);

  return (
    <div className="af-monitor" data-testid="af-monitor">
      <h2 className="af-detail-name">📊 监控</h2>
      <div className="af-monitor-toolbar">
        <div className="af-settings-tabs" role="tablist" aria-label="监控作用域">
          {(['all', 'self', 'external'] as Scope[]).map((s) => (
            <button key={s} type="button" role="tab" aria-selected={scope === s}
              className={`af-settings-tab${scope === s ? ' active' : ''}`} onClick={() => setScope(s)}>
              {s === 'all' ? '全部' : s === 'self' ? '自身能力' : '外部能力'}
            </button>
          ))}
        </div>
        <div className="af-monitor-actions">
          <select className="af-settings-input" aria-label="趋势天数" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>近 7 天</option><option value={14}>近 14 天</option><option value={30}>近 30 天</option>
          </select>
          <button type="button" className="af-settings-action" onClick={() => void load()}>⟳ 刷新</button>
        </div>
      </div>
      {error ? <AfErrorState message={`监控加载失败: ${error}`} onRetry={() => void load()} /> : null}
      {loading && !error ? <AfLoadingState label="正在加载监控…" /> : null}
      {!loading && !error && data ? (
        <div className="af-monitor-body">
          {summary ? <SummaryCards s={summary} /> : null}
          <CompareView ext={data.summary.external} internal={data.summary.internal} />
          <div className="af-monitor-granularity">
            <h3 className="af-settings-h3">执行趋势（{scope === 'all' ? '全部' : scope === 'self' ? '自身' : '外部'}）</h3>
            <div className="af-settings-tabs" role="tablist" aria-label="趋势粒度">
              <button type="button" role="tab" aria-selected={granularity === 'day'} className={`af-settings-tab${granularity === 'day' ? ' active' : ''}`} onClick={() => setGranularity('day')}>按天</button>
              <button type="button" role="tab" aria-selected={granularity === 'hour'} className={`af-settings-tab${granularity === 'hour' ? ' active' : ''}`} onClick={() => setGranularity('hour')}>按小时(近24h)</button>
            </div>
          </div>
          {granularity === 'day'
            ? <TrendChart trend={data.trend} />
            : <TrendChartHourly trend={data.trend_hourly} />}
          <ExecutorBars rows={scope === 'self' ? [] : data.by_executor} />
          <GroupTable title="按执行器" rows={scope === 'self' ? [] : data.by_executor} />
          <GroupTable title="按 Agent / Skill" rows={scopeFilter(data.by_agent)} />
          {scope !== 'self' ? <GroupTable title="按项目目录" rows={data.by_project} /> : null}
          {scope !== 'self' ? <RouteTest /> : null}
          {scope !== 'self' ? (
            <>
              <h3 className="af-settings-h3">回修原因 / 验证方式</h3>
              <div className="af-monitor-chips">
                {data.rework_reasons.map((r) => <span key={r.reason} className="af-settings-badge">🔄 {r.reason} ×{r.count}</span>)}
                {data.verify_methods.map((m) => <span key={m.method} className="af-settings-badge">✅ {m.method} ×{m.count}</span>)}
                {data.rework_reasons.length === 0 && data.verify_methods.length === 0 ? <span className="af-home-note">暂无（有验证/回修后出现）</span> : null}
              </div>
            </>
          ) : null}
          <h3 className="af-settings-h3">执行记录流（最近 {recent.length}）</h3>
          <RecentStream items={recent} />
          {scope !== 'self' ? (
            <>
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
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
