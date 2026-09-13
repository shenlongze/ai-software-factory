/**
 * AfRunDetail — S47-C2 Run / Stage / Call / Repair Drill-down (纯投影)。
 *
 * 数据源: GET /api/projects/{id}/runs/{run_id} (progress+report 真实只读)。
 * 展示真实执行事实: stages (含 repair/retest) / calls usage metadata /
 * errors / totals。SECRET 规则: 只展示 usage metadata, 绝不渲染
 * key/secret/环境变量/content 正文 (progress calls 无 key; content 跳过)。
 */
import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { RunDetail, RunStageDetail } from '../../models/domain';

interface Props {
  projectId: string;
  runId: string;
  onClose?: () => void;
}

const STAGE_LABEL: Record<string, string> = {
  product: '产品设计', ux_ui: 'UI/UX 设计', design: '架构设计',
  architecture: '架构设计', development: '开发', testing: '测试',
  test: '测试', release: '发布',
};

const ROLE_LABEL: Record<string, string> = {
  'product-manager': '产品经理', 'ui-designer': 'UI 设计师', architect: '架构师',
  developer: '开发工程师', tester: '测试工程师', devops: '发布工程师',
};

function stageLabel(stage: string): string {
  if (/repair/i.test(stage)) return '问题修复 (AI Repair)';
  if (/retest/i.test(stage)) return '复测 (Retest)';
  return STAGE_LABEL[stage] ?? stage;
}

function roleLabel(role?: string): string {
  return ROLE_LABEL[role ?? ''] ?? role ?? '';
}

function stageIcon(status?: string): string {
  const s = (status ?? '').toUpperCase();
  if (s === 'COMPLETED' || s === 'PASS') return '✓';
  if (s === 'RUNNING' || s === 'IN_PROGRESS' || s === 'PENDING') return '●';
  if (s === 'FAILED' || s === 'ERROR') return '✗';
  return '○';
}

function isRepair(stage: string): boolean {
  return /repair|retest/i.test(stage);
}

/** Stage 展开行: 状态 + role/cost/latency; repair 阶段人话提示。 */
function StageRow({ stage, open, onToggle }: {
  stage: RunStageDetail; open: boolean; onToggle: () => void;
}): JSX.Element {
  const s = (stage.status ?? '').toUpperCase();
  const cls = s === 'COMPLETED' || s === 'PASS' ? 'done'
    : s === 'FAILED' || s === 'ERROR' ? 'fail'
      : s === 'RUNNING' || s === 'IN_PROGRESS' ? 'run' : 'wait';
  return (
    <li className={`af-run-stage af-run-stage--${cls}`}>
      <button type="button" className="af-run-stage-head" onClick={onToggle}>
        <span className="af-run-stage-icon">{stageIcon(stage.status)}</span>
        <span className="af-run-stage-name">{stageLabel(stage.stage)}</span>
        {isRepair(stage.stage) && <span className="af-badge-repair">AI 修复</span>}
        <span className="af-muted">
          {roleLabel(stage.role)}
          {stage.latency_s != null ? ` · ${stage.latency_s.toFixed(1)}s` : ''}
          {stage.cost_usd_est != null ? ` · $${stage.cost_usd_est.toFixed(4)}` : ''}
        </span>
      </button>
      {open && (
        <div className="af-run-stage-detail">
          <dl>
            <dt>Stage</dt><dd>{stage.stage}</dd>
            {stage.workflow && <><dt>Workflow</dt><dd>{stage.workflow}</dd></>}
            <dt>Status</dt><dd>{stage.status ?? ''}</dd>
            {stage.note && <><dt>Note</dt><dd>{stage.note}</dd></>}
          </dl>
        </div>
      )}
    </li>
  );
}

export function AfRunDetail({ projectId, runId, onClose }: Props): JSX.Element {
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [error, setError] = useState('');
  const [openStages, setOpenStages] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    setError('');
    api.projectRunDetail(projectId, runId)
      .then((d) => { if (!cancelled) setDetail(d); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, [projectId, runId]);

  if (error) {
    return <div className="ai-review-error" role="alert">{error}</div>;
  }
  if (detail == null) {
    return <p className="ai-muted">加载 Run 详情…</p>;
  }

  const totals = detail.totals ?? {};
  const toggle = (name: string) => setOpenStages((prev) => {
    const next = new Set(prev);
    if (next.has(name)) next.delete(name); else next.add(name);
    return next;
  });

  return (
    <div className="af-run-detail" data-testid="af-run-detail">
      <div className="af-run-detail-head">
        <h3>Run {detail.run_id}</h3>
        <span className="ai-muted">status: {detail.status ?? ''}</span>
        {onClose && <button type="button" onClick={onClose} className="ai-btn">关闭</button>}
      </div>

      {totals.calls != null && (
        <div className="af-run-totals" data-testid="af-run-totals">
          <span>{totals.calls} LLM calls</span>
          <span>{totals.total_tokens ?? 0} tokens</span>
          {totals.cost_usd_est != null && <span>${totals.cost_usd_est.toFixed(4)}</span>}
          {totals.wall_s != null && <span>{totals.wall_s.toFixed(0)}s</span>}
        </div>
      )}

      {detail.errors.length > 0 && (
        <div className="af-run-errors" data-testid="af-run-errors">
          {detail.errors.map((e, i) => (
            <p key={i} className="af-error">✗ {e.where}: {e.message}</p>
          ))}
        </div>
      )}

      <ul className="af-run-stages" data-testid="af-run-stages">
        {detail.stages.map((st) => (
          <StageRow
            key={`${st.workflow}-${st.stage}`}
            stage={st}
            open={openStages.has(st.stage)}
            onToggle={() => toggle(st.stage)}
          />
        ))}
      </ul>

      {detail.calls.length > 0 && (
        <div className="af-run-calls" data-testid="af-run-calls">
          <h4>LLM Calls (usage metadata — 无 secret)</h4>
          <table className="af-table">
            <thead>
              <tr><th>model</th><th>status</th><th>tokens</th><th>latency</th></tr>
            </thead>
            <tbody>
              {detail.calls.map((c, i) => (
                <tr key={i}>
                  <td>{c.model ?? '—'}</td>
                  <td>{c.ok ? 'ok' : c.error ?? '—'}</td>
                  <td>{c.usage?.total_tokens ?? '—'}</td>
                  <td>{c.latency_s != null ? `${c.latency_s.toFixed(1)}s` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
