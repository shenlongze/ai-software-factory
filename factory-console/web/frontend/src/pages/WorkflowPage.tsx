import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import { useAsync } from '../hooks/useAsync';
import { useAppState } from '../state/AppState';
import { Table } from '../components/Table';
import type { Column } from '../components/Table';
import { statusBadge } from '../components/Badge';
import { ErrorState, LoadingState } from '../components/State';
import type { WorkflowSummary, WorkflowDetail, StageSummary } from '../models/types';

/** Workflow — 组织级工作流视图 (8 阶段链: 每阶段 status/role/artifact)。 */
export function WorkflowPage(): JSX.Element {
  const { page, navigate } = useAppState();
  const [selected, setSelected] = useState<string | null>(page.name === 'workflow' ? page.workflowId : null);
  const [detail, setDetail] = useState<WorkflowDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  const { data, error, loading } = useAsync(
    useCallback(() => api.workflows(page.name === 'workflow' ? page.projectId : undefined), [page]),
    [page],
  );

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    let alive = true;
    api
      .workflow(selected)
      .then((d) => {
        if (alive) {
          setDetail(d);
          setDetailError(null);
        }
      })
      .catch((e: unknown) => {
        if (alive) {
          setDetail(null);
          setDetailError(e instanceof Error ? e.message : String(e));
        }
      });
    return () => {
      alive = false;
    };
  }, [selected]);

  if (loading) return <LoadingState label="加载工作流…" />;
  if (error) return <ErrorState message={error} />;
  const workflows = data ?? [];

  const columns: Column<WorkflowSummary>[] = [
    {
      key: 'name',
      header: '工作流',
      render: (w) => (
        <button
          type="button"
          className="link-like"
          onClick={() => {
            setSelected(w.id);
            navigate({ name: 'workflow', workflowId: w.id, projectId: w.project_id });
          }}
        >
          {w.name || w.id}
        </button>
      ),
    },
    { key: 'project_id', header: '项目', render: (w) => w.project_name || w.project_id },
    { key: 'status', header: '状态', render: (w) => statusBadge(w.status) },
    { key: 'progress', header: '进度', render: (w) => `${Math.round(w.progress * 100)}%` },
  ];

  const stageColumns: Column<StageSummary>[] = [
    { key: 'name', header: '阶段', render: (s) => s.name },
    { key: 'role_id', header: '角色', render: (s) => s.role_id },
    { key: 'status', header: '状态', render: (s) => statusBadge(s.status) },
    {
      key: 'artifact',
      header: '产物',
      render: (s) => (s.artifact ? `${s.artifact.type} (${s.artifact.status})` : '—'),
    },
  ];

  return (
    <div className="page">
      <h2>工作流</h2>
      <Table columns={columns} rows={workflows} rowKey={(w) => w.id} />
      {detailError ? <ErrorState message={detailError} /> : null}
      {detail ? (
        <section className="card" style={{ marginTop: 16 }}>
          <h3>
            {detail.name || detail.id} — {statusBadge(detail.status)}
          </h3>
          <Table columns={stageColumns} rows={detail.stages} rowKey={(s) => s.id} />
        </section>
      ) : null}
    </div>
  );
}
