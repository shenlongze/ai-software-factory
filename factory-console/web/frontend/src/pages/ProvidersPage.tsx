import { useCallback } from 'react';
import { api } from '../api/client';
import { useAsync } from '../hooks/useAsync';
import { Table } from '../components/Table';
import type { Column } from '../components/Table';
import { statusBadge } from '../components/Badge';
import { ErrorState, LoadingState } from '../components/State';
import type { ProviderSummary } from '../models/types';

/**
 * Providers — Provider 目录 (专业模式页面: Expert 专属)。
 * capability/cost/performance/experience/usage_calls (无数据 → '—', 不臆造)。
 */
export function ProvidersPage(): JSX.Element {
  const { data, error, loading } = useAsync(useCallback(() => api.providers(), []), []);

  if (loading) {
    return <LoadingState label="加载 Provider 目录…" />;
  }
  if (error) {
    return <ErrorState message={error} />;
  }
  const providers = data ?? [];

  const columns: Column<ProviderSummary>[] = [
    { key: 'id', header: 'ID', render: (p) => <strong>{p.id}</strong> },
    { key: 'name', header: '名称', render: (p) => p.name || '—' },
    { key: 'type', header: '类型', render: (p) => p.type },
    { key: 'status', header: '状态', render: (p) => statusBadge(p.status) },
    {
      key: 'capabilities',
      header: '能力',
      render: (p) => (p.capabilities.length ? p.capabilities.join(', ') : '—'),
    },
    { key: 'cost', header: '成本', render: (p) => fmt(p.cost) },
    { key: 'performance', header: '性能', render: (p) => fmt(p.performance) },
    { key: 'experience', header: '经验', render: (p) => fmt(p.experience) },
    { key: 'usage_calls', header: '调用数', render: (p) => String(p.usage_calls) },
  ];

  return (
    <div className="page providers-page">
      <h2>Provider 目录</h2>
      <p className="page-subtitle">
        专业模式 — 能力 / 成本 / 性能 / 经验 聚合 (无数据 → '—'，冷启动不臆造)。
      </p>
      <Table columns={columns} rows={providers} rowKey={(p) => p.id} empty="暂无 Provider" />
    </div>
  );
}

function fmt(value: number | null): string {
  return value === null ? '—' : `${(value * 100).toFixed(0)}%`;
}
