import { useCallback } from 'react';
import { api } from '../api/client';
import { useAsync } from '../hooks/useAsync';
import { useAppState } from '../state/AppState';
import { Table } from '../components/Table';
import type { Column } from '../components/Table';
import { statusBadge } from '../components/Badge';
import { ErrorState, LoadingState } from '../components/State';
import type { ProjectSummary } from '../models/types';

/** Projects — 项目清单 (点击进入项目工作区 = LifecyclePage)。 */
export function ProjectsPage(): JSX.Element {
  const { navigate } = useAppState();
  const { data, error, loading } = useAsync(useCallback(() => api.projects(), []), []);

  if (loading) {
    return <LoadingState label="加载项目…" />;
  }
  if (error) {
    return <ErrorState message={error} />;
  }
  const projects = data ?? [];

  const columns: Column<ProjectSummary>[] = [
    {
      key: 'name',
      header: '项目',
      render: (p) => (
        <span className="project-name">
          {p.name || p.id}
          {p.language ? <span className="muted"> · {p.language}</span> : null}
        </span>
      ),
    },
    { key: 'stage', header: '生命周期阶段', render: (p) => p.lifecycle_stage ?? '—' },
    { key: 'status', header: '状态', render: (p) => statusBadge(p.status) },
    {
      key: 'pending',
      header: '待审批',
      render: (p) => (p.pending_approvals > 0 ? <strong>{p.pending_approvals}</strong> : '0'),
    },
    { key: 'last_activity', header: '最近活动', render: (p) => p.last_activity ?? '—' },
  ];

  return (
    <div className="page projects-page">
      <h2>项目</h2>
      <p className="page-subtitle">点击项目查看其 AI 工作区 (生命周期 / 当前状态 / 下一步)。</p>
      <Table
        columns={columns}
        rows={projects}
        rowKey={(p) => p.id}
        empty="暂无项目 — 通过 CLI 创建: factory workspace init / idea new"
        onRowClick={(p) => navigate({ name: 'lifecycle', projectId: p.id })}
      />
    </div>
  );
}
