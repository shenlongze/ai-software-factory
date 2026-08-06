import { useCallback } from 'react';
import { api } from '../api/client';
import { useAsync } from '../hooks/useAsync';
import { useAppState } from '../state/AppState';
import { Card } from '../components/Card';
import { ScoreBar } from '../components/ScoreBar';
import { statusBadge } from '../components/Badge';
import { EvidenceChain } from '../components/EvidenceChain';
import { EmptyState, ErrorState, LoadingState } from '../components/State';

/**
 * Intelligence — 经验成长 / Provider 表现 / Agent 能力 / 推荐准确度
 * (聚合自 /api/experience + /api/providers + /api/recommendations + dashboard agents)。
 */
export function IntelligencePage(): JSX.Element {
  const { mode } = useAppState();
  const { data: experience, error: expError, loading: expLoading } = useAsync(
    useCallback(() => api.experience(20), []),
    [],
  );
  const { data: providers, error: provError, loading: provLoading } = useAsync(
    useCallback(() => api.providers(), []),
    [],
  );
  const { data: recommendations, error: recError, loading: recLoading } = useAsync(
    useCallback(() => api.recommendations(20), []),
    [],
  );
  const { data: dashboard, loading: dashLoading } = useAsync(
    useCallback(() => api.dashboard(), []),
    [],
  );

  if (expLoading || provLoading || recLoading || dashLoading) {
    return <LoadingState label="加载智能视图…" />;
  }
  if (expError || provError || recError) {
    return <ErrorState message={expError ?? provError ?? recError ?? '加载失败'} />;
  }

  const successCount = (experience ?? []).filter((e) => e.result === 'success').length;
  const successRate = (experience ?? []).length > 0
    ? (successCount / (experience ?? []).length) * 100
    : 0;
  const agents = dashboard?.agents ?? [];

  return (
    <div className="page intelligence-page">
      <h2>智能视图</h2>
      <p className="page-subtitle">经验在增长 — 系统从每一次执行中学习 (只读统计)。</p>

      <div className="intelligence-grid">
        <Card title="Experience Growth" subtitle="经验记录 (六域)">
          {(experience ?? []).length === 0 ? (
            <EmptyState message="暂无经验记录" />
          ) : (
            <>
              <p>
                共 {(experience ?? []).length} 条 · 成功率 {successRate.toFixed(0)}%
              </p>
              <ul className="experience-list">
                {(experience ?? []).slice(0, 8).map((e) => (
                  <li key={e.id} className="experience-item">
                    <span className="experience-subject">{e.subject}</span>
                    {statusBadge(e.result)}
                    <ScoreBar label="score" value={e.score} />
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>

        <Card title="Provider Performance" subtitle="成本 / 性能 / 经验 聚合">
          {(providers ?? []).length === 0 ? (
            <EmptyState message="暂无 Provider 数据" />
          ) : (
            <ul className="provider-list">
              {(providers ?? []).map((p) => (
                <li key={p.id} className="provider-item">
                  <span className="provider-name">{p.name || p.id}</span>
                  <ScoreBar label="cost" value={p.cost} />
                  <ScoreBar label="performance" value={p.performance} />
                  <ScoreBar label="experience" value={p.experience} />
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Agent Capability" subtitle="Agent 技能清单">
          {agents.length === 0 ? (
            <EmptyState message="暂无 Agent" />
          ) : (
            <ul className="agent-capability-list">
              {agents.slice(0, 10).map((a) => (
                <li key={a.id}>
                  <span className="agent-name">
                    {a.name} <span className="muted">({a.role})</span>
                  </span>
                  <div className="skill-tags">
                    {a.skills.map((s) => (
                      <span key={s} className="skill-tag">
                        {s}
                      </span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Recommendation Accuracy" subtitle="推荐产物 + 证据链">
          {(recommendations ?? []).length === 0 ? (
            <EmptyState message="暂无推荐记录" />
          ) : (
            <ul className="recommendation-list">
              {(recommendations ?? []).slice(0, 8).map((r) => (
                <li key={r.id} className="recommendation-item">
                  <div className="recommendation-head">
                    <span className="recommendation-candidate">{r.candidate}</span>
                    <ScoreBar label="score" value={r.score} />
                  </div>
                  {r.explanation.length > 0 ? (
                    <p className="recommendation-explanation">{r.explanation[0]}</p>
                  ) : null}
                  {mode === 'expert' ? <EvidenceChain evidence={r.evidence} /> : null}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
