import { useCallback, useState } from 'react';
import { api } from '../api/client';
import { useAsync } from '../hooks/useAsync';
import { useAppState } from '../state/AppState';
import { Card } from '../components/Card';
import { ScoreBar } from '../components/ScoreBar';
import { statusBadge } from '../components/Badge';
import { EmptyState, ErrorState, LoadingState, Modal } from '../components/State';

/**
 * Dashboard — 普通模式默认页 (human-console-model.md §普通模式):
 * "项目 → AI 当前状态 → 需要我决定什么 → 为什么这样推荐"。
 */
export function DashboardPage(): JSX.Element {
  const { mode, navigate } = useAppState();
  const { data, error, loading } = useAsync(useCallback(() => api.dashboard(), []), []);
  const [showIdeaNotice, setShowIdeaNotice] = useState(false);

  if (loading) {
    return <LoadingState label="加载控制台…" />;
  }
  if (error) {
    return <ErrorState message={error} />;
  }
  if (!data) {
    return <EmptyState message="暂无数据" />;
  }

  const activeProjects = data.projects.filter((p) => p.status === 'active');
  const pendingApprovals = data.approvals.filter((a) => a.status === 'pending');

  return (
    <div className="page dashboard-page">
      <div className="dashboard-hero">
        <h2>正在管理 {activeProjects.length} 个项目</h2>
        <p>
          {pendingApprovals.length > 0 ? (
            <>
              当前 <strong>{pendingApprovals.length}</strong> 个需要你的决定
            </>
          ) : (
            '当前没有待处理的决定'
          )}
        </p>
        <div className="hero-actions">
          <button type="button" onClick={() => navigate({ name: 'projects' })}>
            查看项目
          </button>
          <button type="button" onClick={() => navigate({ name: 'approvals' })}>
            处理审批
          </button>
          <button type="button" onClick={() => setShowIdeaNotice(true)}>
            创建新想法
          </button>
        </div>
      </div>

      <div className="dashboard-grid">
        <Card title="最近 AI 决策" subtitle="只读推荐产物">
          {data.decisions.length === 0 ? (
            <EmptyState message="暂无 AI 决策" />
          ) : (
            <ul className="decision-list">
              {data.decisions.slice(0, 5).map((d) => (
                <li key={d.id} className="decision-item">
                  <button
                    type="button"
                    className="decision-link"
                    onClick={() => navigate({ name: 'decisions', decisionId: d.id })}
                  >
                    <span className="decision-desc">{d.description || d.id}</span>
                    <span className="decision-reason">{d.reasoning[0] ?? '无原因'}</span>
                  </button>
                  {statusBadge(d.status)}
                </li>
              ))}
            </ul>
          )}
        </Card>

        {mode === 'expert' ? (
          <>
            <Card title="成本汇总" subtitle="估算计量 (非真实计费)">
              <ScoreBar label="成功率" value={data.cost.success_rate} />
              <p>
                总成本 ${data.cost.total_cost.toFixed(4)} · {data.cost.calls} 次调用 ·{' '}
                {data.cost.total_tokens} tokens
              </p>
            </Card>
            <Card title="运行中 Agent">
              {data.agents.filter((a) => a.status === 'WORKING').length === 0 ? (
                <EmptyState message="无运行中 Agent" />
              ) : (
                <ul className="agent-list">
                  {data.agents
                    .filter((a) => a.status === 'WORKING')
                    .map((a) => (
                      <li key={a.id}>
                        {a.name} <span className="muted">({a.role})</span>
                      </li>
                    ))}
                </ul>
              )}
            </Card>
            <Card title="最近活动" subtitle="事件审计流 (Expert)">
              {data.activity.length === 0 ? (
                <EmptyState message="暂无活动" />
              ) : (
                <ul className="activity-list">
                  {data.activity.slice(0, 8).map((e) => (
                    <li key={e.seq} className="activity-item">
                      <span className="activity-type">{e.type}</span>
                      <span className="activity-action">{e.action ?? ''}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </>
        ) : null}
      </div>

      {showIdeaNotice ? (
        <Modal title="创建新想法" onClose={() => setShowIdeaNotice(false)}>
          <p>
            Human Console 只读 — 新想法请通过 CLI 创建：<code>factory idea new</code>。
          </p>
          <p>本界面不提供写路径 (Permission Boundary)，执行权永远保留在人工一侧。</p>
        </Modal>
      ) : null}
    </div>
  );
}
