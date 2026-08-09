import { useCallback, useState } from 'react';
import { api } from '../api/client';
import { useAsync } from '../hooks/useAsync';
import { useAppState } from '../state/AppState';
import { Table } from '../components/Table';
import type { Column } from '../components/Table';
import { statusBadge } from '../components/Badge';
import { ErrorState, LoadingState } from '../components/State';
import type { ArtifactSummary } from '../models/types';

const ARTIFACT_TYPES = ['', 'product', 'ux_ui', 'design', 'code', 'test', 'release'] as const;

/** Artifacts — Artifact 查看器 (6 类型, 按 project/workflow/type 过滤; S9-003 评审入口)。 */
export function ArtifactsPage(): JSX.Element {
  const { page, navigate } = useAppState();
  const [type, setType] = useState<string>('');
  const { data, error, loading } = useAsync(
    useCallback(
      () =>
        api.artifacts({
          projectId: page.name === 'artifacts' ? page.projectId : undefined,
          workflowId: page.name === 'artifacts' ? page.workflowId : undefined,
          type: type || undefined,
        }),
      [page, type],
    ),
    [page, type],
  );

  const columns: Column<ArtifactSummary>[] = [
    { key: 'id', header: 'ID', render: (a) => a.id },
    { key: 'type', header: '类型', render: (a) => a.type },
    { key: 'status', header: '状态', render: (a) => statusBadge(a.status) },
    { key: 'stage_id', header: '阶段', render: (a) => a.stage_id },
    { key: 'producer_role', header: '产出角色', render: (a) => a.producer_role },
    {
      key: 'location',
      header: '内容',
      render: (a) => (a.location ? `${a.location} (v${a.version ?? '?'})` : '—'),
    },
    {
      key: 'review',
      header: '评审',
      render: (a) => (
        <button
          type="button"
          className="review-entry"
          onClick={() => navigate({ name: 'review', artifactId: a.id })}
        >
          评审
        </button>
      ),
    },
  ];

  if (loading) return <LoadingState label="加载产物…" />;
  if (error) return <ErrorState message={error} />;
  const artifacts = data ?? [];

  return (
    <div className="page">
      <h2>产物</h2>
      <div className="toolbar">
        <label>
          类型
          <select value={type} onChange={(e) => setType(e.target.value)}>
            {ARTIFACT_TYPES.map((t) => (
              <option key={t} value={t}>
                {t || '全部'}
              </option>
            ))}
          </select>
        </label>
      </div>
      <Table columns={columns} rows={artifacts} rowKey={(a) => a.id} />
    </div>
  );
}
