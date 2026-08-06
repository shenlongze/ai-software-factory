import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import { useAsync } from '../hooks/useAsync';
import { useAppState } from '../state/AppState';
import { Card } from '../components/Card';
import { ScoreBar } from '../components/ScoreBar';
import { riskBadge, statusBadge } from '../components/Badge';
import { EvidenceChain } from '../components/EvidenceChain';
import { EmptyState, ErrorState, LoadingState } from '../components/State';
import { factorLabel } from '../models/types';

/**
 * Decisions — 决策视图: 候选/评分 (Capability/Cost/Performance/Experience)/
 * 推荐/原因 (11A DecisionSummary 只读投影)。
 * 列表来自 dashboard (最近决策); 点击 → /api/decisions/{id} 详情。
 */
export function DecisionsPage(): JSX.Element {
  const { mode, page } = useAppState();
  const initialId = page.name === 'decisions' ? (page.decisionId ?? null) : null;
  const [selectedId, setSelectedId] = useState<string | null>(initialId);

  const { data: dashboard, error: listError, loading: listLoading } = useAsync(
    useCallback(() => api.dashboard(), []),
    [],
  );

  const detail = useAsync(
    useCallback(() => (selectedId ? api.decision(selectedId) : Promise.resolve(null)), [selectedId]),
    [selectedId],
  );

  // 列表 → 自动选中第一条 (有列表时提升可用性)
  useEffect(() => {
    if (selectedId === null && dashboard && dashboard.decisions.length > 0) {
      setSelectedId(dashboard.decisions[0].id);
    }
  }, [dashboard, selectedId]);

  if (listLoading || (selectedId !== null && detail.loading)) {
    return <LoadingState label="加载决策…" />;
  }
  if (listError) {
    return <ErrorState message={listError} />;
  }

  const decisions = dashboard?.decisions ?? [];

  if (selectedId === null && decisions.length === 0) {
    return (
      <div className="page decisions-page">
        <h2>决策</h2>
        <EmptyState message="暂无 AI 决策" />
      </div>
    );
  }

  if (selectedId === null) {
    return (
      <div className="page decisions-page">
        <h2>决策</h2>
        <EmptyState message="请从列表选择一个决策" />
      </div>
    );
  }

  if (detail.error) {
    return <ErrorState message={detail.error} />;
  }
  const d = detail.data;
  if (!d) {
    return (
      <div className="page decisions-page">
        <h2>决策</h2>
        <EmptyState message="决策不存在或已归档" />
      </div>
    );
  }

  const recommended = d.options.find((o) => o.id === d.recommendation);

  return (
    <div className="page decisions-page">
      <h2>决策</h2>
      <p className="page-subtitle">
        {d.description || d.id} · {statusBadge(d.status)} · {riskBadge(d.risk_level)}
        {d.requires_approval ? ' · 需人工审批' : ''}
      </p>

      <div className="decision-selector">
        {decisions.map((dec) => (
          <button
            type="button"
            key={dec.id}
            className={`decision-tab${dec.id === selectedId ? ' active' : ''}`}
            onClick={() => setSelectedId(dec.id)}
          >
            {dec.description || dec.id}
          </button>
        ))}
      </div>

      <div className="decision-grid">
        <Card title="候选与评分" subtitle="Capability / Cost / Performance / Experience">
          {d.options.length === 0 ? (
            <EmptyState message="无候选" />
          ) : (
            <ul className="option-list">
              {d.options.map((o) => {
                const isRec = o.id === d.recommendation;
                return (
                  <li key={o.id} className={`option-item${isRec ? ' recommended' : ''}`}>
                    <div className="option-head">
                      <span className="option-name">
                        {o.name || o.id}
                        {isRec ? <span className="rec-tag">推荐</span> : null}
                      </span>
                      <ScoreBar label={o.id} value={o.score} max={1} />
                    </div>
                    {mode === 'expert' ? (
                      <div className="option-factors">
                        {Object.entries(o.factors ?? {}).map(([k, v]) => (
                          <ScoreBar key={k} label={factorLabel(k)} value={v} />
                        ))}
                      </div>
                    ) : null}
                    {o.reasoning && o.reasoning.length > 0 ? (
                      <p className="option-reasoning">{o.reasoning[0]}</p>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card title="AI 推荐" subtitle="为什么这样推荐">
          {recommended ? (
            <>
              <p className="recommendation-line">
                推荐 <strong>{recommended.name || recommended.id}</strong> (综合评分{' '}
                {(d.score * 100).toFixed(0)}%)
              </p>
              {d.reasoning.length === 0 ? (
                <EmptyState message="无推荐原因" />
              ) : (
                <ol className="reasoning-list">
                  {d.reasoning.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ol>
              )}
            </>
          ) : (
            <EmptyState message="未推荐 (等待人工判断)" />
          )}
          <div className="evidence-section">
            <EvidenceChain evidence={d.evidence} />
          </div>
        </Card>
      </div>
    </div>
  );
}
