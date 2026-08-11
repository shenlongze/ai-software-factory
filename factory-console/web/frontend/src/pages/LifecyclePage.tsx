import { useCallback } from 'react';
import { api } from '../api/client';
import { useAsync } from '../hooks/useAsync';
import { useAppState } from '../state/AppState';
import { Card } from '../components/Card';
import { Badge, riskBadge } from '../components/Badge';
import { EmptyState, ErrorState, LoadingState } from '../components/State';

/** 404 = 项目无生命周期记录 (后端 None → HTTP 404) → 空态而非错误。 */
function isNotFound(error: string | null): boolean {
  return error != null && error.includes('HTTP 404');
}

/**
 * Lifecycle — 项目工作区 (Notion+Linear 风格):
 * 项目名 / 生命周期阶段 / 当前 AI 状态 / 下一步 (只读快照)。
 *
 * S10-015 修复: 404 (旧项目/未关联 idea → 无生命周期记录) 视为
 * "暂无记录" 空态, 不向用户暴露 HTTP 状态码。
 */
export function LifecyclePage(): JSX.Element {
  const { page, navigate } = useAppState();
  const projectId = page.name === 'lifecycle' ? page.projectId : '';
  const { data, error, loading } = useAsync(
    useCallback(() => api.lifecycle(projectId), [projectId]),
    [projectId],
  );

  if (loading) {
    return <LoadingState label="加载项目工作区…" />;
  }
  if (error && !isNotFound(error)) {
    return <ErrorState message={error} />;
  }
  if (!data) {
    return (
      <div className="page lifecycle-page">
        <h2>项目工作区</h2>
        <EmptyState message="该项目暂无生命周期记录 (idea 尚未创建或未关联该项目)。" />
      </div>
    );
  }

  const stage = data.current_stage ?? null;
  const stageName = (stage?.name as string | undefined) ?? '—';
  const stageStatus = (stage?.status as string | undefined) ?? data.status;

  return (
    <div className="page lifecycle-page">
      <div className="lifecycle-header">
        <div>
          <button type="button" className="back-link" onClick={() => navigate({ name: 'projects' })}>
            ← 返回项目
          </button>
          <h2>{projectId}</h2>
          <p className="page-subtitle">
            生命周期 <code>{data.lifecycle_id ?? '—'}</code> · 模板 {data.template_name || '—'}
          </p>
        </div>
        <div className="lifecycle-status">
          <Badge text={data.status || 'idle'} tone={data.status === 'running' ? 'warn' : 'neutral'} />
        </div>
      </div>

      <div className="lifecycle-grid">
        <Card title="当前阶段" subtitle="AI 当前状态">
          <div className="stage-name">{stageName}</div>
          <p className="stage-status">状态: {statusBadgeText(stageStatus)}</p>
          {stage ? (
            <dl className="stage-details">
              {Object.entries(stage)
                .filter(([k]) => !['name', 'status'].includes(k))
                .slice(0, 6)
                .map(([k, v]) => (
                  <div key={k} className="stage-detail">
                    <dt>{k}</dt>
                    <dd>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</dd>
                  </div>
                ))}
            </dl>
          ) : null}
        </Card>

        <Card title="下一步" subtitle="引擎建议 (只读, 不执行)">
          {data.next_actions.length === 0 ? (
            <EmptyState message="暂无下一步建议" />
          ) : (
            <ol className="next-actions">
              {data.next_actions.map((action) => (
                <li key={action}>{action}</li>
              ))}
            </ol>
          )}
        </Card>

        <Card title="已完成的阶段">
          {data.completed_stages.length === 0 ? (
            <EmptyState message="暂无已完成阶段" />
          ) : (
            <ul className="completed-stages">
              {data.completed_stages.map((s) => (
                <li key={s}>
                  <Badge text={s} tone="ok" />
                </li>
              ))}
            </ul>
          )}
        </Card>

        {data.pending_approval ? (
          <Card title="待人工审批" subtitle="需要你的决定">
            <p>
              {data.pending_approval.artifact_type || 'artifact'} · 门 {data.pending_approval.gate}{' '}
              · 置信度 {(data.pending_approval.confidence * 100).toFixed(0)}%
            </p>
            <p>风险: {riskBadge(data.pending_approval.risk)}</p>
            <button type="button" onClick={() => navigate({ name: 'approvals' })}>
              去审批中心处理
            </button>
          </Card>
        ) : null}
      </div>
    </div>
  );
}

function statusBadgeText(status: string): JSX.Element {
  const tone = status === 'running' ? 'warn' : status === 'completed' ? 'ok' : 'neutral';
  return <Badge text={status} tone={tone} />;
}
