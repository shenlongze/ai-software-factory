import { useCallback, useState } from 'react';
import { api } from '../api/client';
import { useAsync } from '../hooks/useAsync';
import { Card } from '../components/Card';
import { EmptyState, ErrorState, LoadingState } from '../components/State';

/**
 * AuditPage — T8 审计视图 (只读): 事件列表 + 类型计数 + 过滤 + 导出 CSV。
 * 数据源: GET /api/audit (audit_events.json, 失败安全空态)。
 */
interface AuditEvent {
  event_type?: string;
  action?: string;
  timestamp?: string;
  trace_id?: string;
  project_id?: string;
  decision?: string;
  result?: { ok?: boolean } | null;
  evidence?: unknown[];
}

function fmtTime(iso?: string): string {
  if (!iso) return '';
  return iso.replace('T', ' ').slice(0, 19);
}

export function AuditPage(): JSX.Element {
  const [eventType, setEventType] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);

  const { data, error, loading } = useAsync(
    useCallback(() => {
      const params = new URLSearchParams();
      if (eventType) params.set('event_type', eventType);
      if (sessionId) params.set('session_id', sessionId);
      params.set('limit', '200');
      return api.audit(params.toString());
    }, [eventType, sessionId, refreshKey]),
    [eventType, sessionId, refreshKey],
  );

  const events: AuditEvent[] = data?.items ?? [];
  const counts = data?.counts ?? {};

  const exportCsv = () => {
    const header = 'timestamp,event_type,action,trace_id,project_id,decision,ok';
    const rows = events.map((e) =>
      [
        e.timestamp ?? '',
        e.event_type ?? '',
        (e.action ?? '').replace(/,/g, ';'),
        e.trace_id ?? '',
        e.project_id ?? '',
        e.decision ?? '',
        e.result?.ok ? 'true' : 'false',
      ]
        .map((v) => `"${String(v).replace(/"/g, '""')}"`)
        .join(','),
    );
    const blob = new Blob([[header, ...rows].join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `audit-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="af-audit" data-testid="audit-page">
      <h2 className="af-audit-title">审计视图</h2>
      <div className="af-audit-toolbar">
        <input
          className="af-audit-input"
          placeholder="按事件类型过滤 (如 TOOL_CALL)"
          value={eventType}
          onChange={(e) => setEventType(e.target.value)}
          aria-label="事件类型过滤"
        />
        <input
          className="af-audit-input"
          placeholder="按会话 ID 过滤"
          value={sessionId}
          onChange={(e) => setSessionId(e.target.value)}
          aria-label="会话过滤"
        />
        <button type="button" className="af-audit-btn" onClick={() => setRefreshKey((k) => k + 1)}>
          ⟳ 刷新
        </button>
        <button type="button" className="af-audit-btn" onClick={exportCsv} disabled={events.length === 0}>
          ⬇ 导出 CSV
        </button>
      </div>
      {Object.keys(counts).length > 0 ? (
        <div className="af-audit-counts" data-testid="audit-counts">
          {Object.entries(counts).map(([t, n]) => (
            <span key={t} className="af-audit-count-chip">
              {t}: {String(n)}
            </span>
          ))}
        </div>
      ) : null}
      <Card title="审计事件">
        {loading ? (
          <LoadingState label="加载审计事件…" />
        ) : error ? (
          <ErrorState message={String(error)} />
        ) : events.length === 0 ? (
          <EmptyState message="暂无审计事件 — 运行会话触发工具调用后自动记录" />
        ) : (
          <table className="af-audit-table" data-testid="audit-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>类型</th>
                <th>动作</th>
                <th>会话</th>
                <th>项目</th>
                <th>决策</th>
                <th>结果</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e, i) => (
                <tr key={i} data-testid={`audit-row-${i}`}>
                  <td className="af-audit-td-time">{fmtTime(e.timestamp)}</td>
                  <td>
                    <span className={`af-audit-type af-audit-type--${String(e.event_type).toLowerCase()}`}>
                      {e.event_type ?? '—'}
                    </span>
                  </td>
                  <td className="af-audit-td-action">{e.action ?? '—'}</td>
                  <td className="af-audit-td-id">{e.trace_id ? e.trace_id.slice(0, 12) : '—'}</td>
                  <td className="af-audit-td-id">{e.project_id ? e.project_id.slice(0, 12) : '—'}</td>
                  <td>{e.decision ?? '—'}</td>
                  <td>{e.result?.ok ? '✅' : e.result?.ok === false ? '❌' : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
