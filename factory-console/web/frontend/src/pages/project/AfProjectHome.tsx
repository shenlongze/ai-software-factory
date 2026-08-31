/**
 * pages/project/AfProjectHome.tsx — 项目首页 (K-7b, 敏捷项目管理)。
 *
 * ① 全生命周期条 (GET /lifecycle)  ② 任务 Todo (GET /backlog, 列表⇄泳道,
 *    编辑优先级/状态 PATCH, 完成标记)  ③ 运维摘要 (runtimes)
 * 原则: 简单 · 直接 · 高效 · 易用; 失败安全 (后端不可达 → 空态不崩)。
 */

import { useEffect, useState } from 'react';
import { renderInline } from '../../components/af/markdown';

interface LifecycleData {
  status?: string;
  completed_stages?: string[];
  current_stage?: { id?: string; name?: string } | null;
  next_actions?: string[];
}

interface WorkspaceData {
  name?: string;
  lifecycle_status?: string;
  root_path?: string;
  stages?: { id: string; label: string; done: boolean }[];
  done_stages?: string[];
  progress?: number;
  tasks?: { id: string; title: string; status: string; priority?: string | null }[];
  task_source?: string;
}

interface TaskItem {
  id: string;
  title?: string;
  priority?: string | null;
  status?: string;
}

// S35: 项目详情 API 返回 (统一数据源 — /api/projects/{id})
interface ProjectDetailData {
  project?: {
    id?: string;
    name?: string;
    status?: string;
    lifecycle_stage?: string;
    goal?: string;
    project_type?: string;
    framework?: string;
    repo_path?: string;
    created_at?: string;
    updated_at?: string;
  };
  counts?: { requirements?: number; plans?: number; tasks?: number; runs?: number };
  repository?: { enabled?: boolean; status?: string; path?: string; branch?: string; remote?: string };
  requirements?: { id?: string; title?: string; status?: string }[];
  plans?: { plan_id?: string; status?: string; goal?: string; approval_id?: string }[];
}

const STAGES = ['发现', '确认', 'PRD', '工程', '开发', '测试', '验收', '交付', '部署', '运维', '更新'];

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as T;
}

export function AfProjectHome({
  projectId,
  projectName,
}: {
  projectId: string;
  projectName: string;
}): JSX.Element {
  const [lifecycle, setLifecycle] = useState<LifecycleData | null>(null);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [runtimeCount, setRuntimeCount] = useState<number>(0);
  const [failedCount, setFailedCount] = useState<number>(0);
  const [qualityScore, setQualityScore] = useState<number | null>(null);
  const [qualityNote, setQualityNote] = useState<string>('');
  // S32-004: 项目真实 Run 列表
  const [runs, setRuns] = useState<Array<{ run_id: string; status: string; updated_at?: string; totals?: Record<string, number> }>>([]);

  const base = `/api/projects/${encodeURIComponent(projectId)}`;

  const [wsData, setWsData] = useState<WorkspaceData | null>(null);
  // S35: 项目详情 (统一数据源)
  const [detail, setDetail] = useState<ProjectDetailData | null>(null);

  const loadAll = () => {
    // S35: 项目详情 — Identity/Git/Requirement/Plan 摘要 (统一后端)
    getJson<ProjectDetailData>(`${base}`)
      .then(setDetail)
      .catch(() => setDetail(null));
    // 真实数据优先: workspace 资产汇总 (Founder 2026-08-26); org 端点回退
    getJson<WorkspaceData>(`${base}/workspace`)
      .then((w) => {
        setWsData(w);
        if (w.lifecycle_status) setLifecycle({ status: w.lifecycle_status });
        setTasks(w.tasks ?? []);
      })
      .catch(() => {
        setWsData(null);
        getJson<LifecycleData>(`${base}/lifecycle`).then(setLifecycle).catch(() => setLifecycle(null));
        getJson<{ tasks?: TaskItem[] }>(`${base}/backlog`)
          .then((b) => setTasks(b.tasks ?? []))
          .catch(() => setTasks([]));
      });
    // 健康信号统一读 Monitor (单一数据源, v1.1.134)
    getJson<{ project?: { runtimes?: number; failed?: number; quality?: number | null } }>(`${base}/monitor`)
      .then((m) => {
        const pj = m.project ?? {};
        setRuntimeCount(pj.runtimes ?? 0);
        setFailedCount(pj.failed ?? 0);
        setQualityScore(typeof pj.quality === 'number' ? pj.quality : null);
        setQualityNote(typeof pj.quality === 'number' ? '' : '未生成');
      })
      .catch(() => {
        setRuntimeCount(0);
        setFailedCount(0);
        setQualityScore(null);
        setQualityNote('未评测');
      });
    // S32-004: 真实 Run 列表
    getJson<{ runs?: Array<{ run_id: string; status: string; updated_at?: string; totals?: Record<string, number> }> }>(`${base}/runs`)
      .then((d) => setRuns(d.runs ?? []))
      .catch(() => setRuns([]));
  };

  // ③ 实时性: 打开拉取 + 默认 15s 自动轮询 (Founder: todo 要实时) + 手动刷新
  const [pollMs, setPollMs] = useState<number>(15000);
  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);
  useEffect(() => {
    if (pollMs <= 0) return;
    const t = window.setInterval(loadAll, pollMs);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pollMs, projectId]);

  const doneCount = wsData ? (wsData.done_stages?.length ?? 0) : (lifecycle?.completed_stages?.length ?? 0);
  const stageLabels = wsData?.stages?.map((st) => st.label) ?? STAGES;
  const pct = wsData?.progress ?? Math.round((doneCount / stageLabels.length) * 100);
  const currentStage = lifecycle?.current_stage?.name ?? (wsData ? stageLabels[doneCount] ?? '' : '');

  const lifecycleBar = (() => {
    const segs = stageLabels.map((label, i) => {
      const done = i < doneCount;
      const current = i === doneCount;
      return (
        <span
          key={label}
          className={`af-lc-stage${done ? ' done' : ''}${current ? ' current' : ''}`}
          title={current ? `当前: ${label}` : label}
        >
          {done ? '✓' : current ? '●' : '○'}
          {label}
        </span>
      );
    });
    return (
      <section className="af-home-card" data-testid="af-home-lifecycle">
        <h3>🌱 全生命周期</h3>
        <div className="af-lc-bar">
          <div className="af-lc-fill" style={{ width: `${pct}%` }} />
        </div>
        <div className="af-lc-stages">{segs}</div>
        <p className="af-home-note">
          {doneCount}/{STAGES.length} · 当前: {currentStage || '—'}
        </p>
      </section>
    );
  })();

  const pendingTasks = tasks.filter((t) => t.status !== 'done');
  const doneTasks = tasks.filter((t) => t.status === 'done');

  return (
    <div className="af-project-home" data-testid="af-project-home">
      <div className="af-home-head">
        <h2 className="af-detail-name">{projectName}</h2>
        <div className="af-home-controls">
          <select
            className="af-todo-pri"
            aria-label="自动刷新间隔"
            value={String(pollMs)}
            onChange={(e) => setPollMs(Number(e.target.value))}
          >
            <option value="0">不自动</option>
            <option value="5000">5s</option>
            <option value="15000">15s</option>
            <option value="30000">30s</option>
            <option value="60000">60s</option>
          </select>
          <button type="button" className="af-preview-btn" onClick={loadAll} aria-label="刷新数据">
            ⟳ 刷新
          </button>
        </div>
      </div>
      {lifecycleBar}
      <section className="af-home-card" data-testid="af-home-health">
        <div className="af-health-row">
          <span className="af-health-title">⚡ 健康信号</span>
          <a className="af-health-chip" href={`#/project/${projectId}/runtime`}>
            🖥 运行 {runtimeCount}
          </a>
          <a className="af-health-chip" href={`#/project/${projectId}/quality`}>
            ✅ 质量 {qualityScore != null ? qualityScore.toFixed(2) : qualityNote || '未评测'}
          </a>
          <a className="af-health-chip" href={`#/project/${projectId}/workflow`}>
            ⚠️ 失败 {failedCount}
          </a>
        </div>
      </section>
      {/* S35: 项目信息卡 — Identity/Workspace/Git/Requirement/Plan (统一后端数据) */}
      <section className="af-home-card" data-testid="af-home-detail">
        <div className="af-home-card-head">
          <h3>📁 项目管理</h3>
        </div>
        <div className="af-detail-grid">
          <div className="af-detail-col">
            <div className="af-detail-row">
              <span className="af-detail-label">项目 ID</span>
              <code className="af-detail-value">{detail?.project?.id ?? projectId}</code>
            </div>
            <div className="af-detail-row">
              <span className="af-detail-label">状态 / 阶段</span>
              <span className="af-detail-value">
                {detail?.project?.status ?? '—'} / {detail?.project?.lifecycle_stage ?? '—'}
              </span>
            </div>
            <div className="af-detail-row">
              <span className="af-detail-label">类型 / 框架</span>
              <span className="af-detail-value">
                {detail?.project?.project_type || '未指定'} / {detail?.project?.framework || '—'}
              </span>
            </div>
            <div className="af-detail-row">
              <span className="af-detail-label">创建时间</span>
              <span className="af-detail-value">{detail?.project?.created_at ?? '—'}</span>
            </div>
            {detail?.project?.goal ? (
              <div className="af-detail-row">
                <span className="af-detail-label">目标</span>
                <span className="af-detail-value">{String(detail.project.goal).slice(0, 60)}</span>
              </div>
            ) : null}
          </div>
          <div className="af-detail-col">
            <div className="af-detail-row">
              <span className="af-detail-label">Workspace</span>
              <code className="af-detail-value af-detail-path">{wsData?.root_path ?? '—'}</code>
            </div>
            <div className="af-detail-row">
              <span className="af-detail-label">Git</span>
              <span className="af-detail-value">
                {detail?.repository?.enabled ? '已启用' : '未初始化'}
                {detail?.repository?.branch ? ` · ${detail.repository.branch}` : ''}
              </span>
            </div>
            {detail?.repository?.remote ? (
              <div className="af-detail-row">
                <span className="af-detail-label">Remote</span>
                <code className="af-detail-value af-detail-path">{detail.repository.remote}</code>
              </div>
            ) : null}
            <div className="af-detail-row">
              <span className="af-detail-label">Requirement</span>
              <span className="af-detail-value">{detail?.counts?.requirements ?? 0} 条</span>
            </div>
            <div className="af-detail-row">
              <span className="af-detail-label">Plan</span>
              <span className="af-detail-value">{detail?.counts?.plans ?? 0} 份</span>
            </div>
          </div>
        </div>
        {detail && detail.requirements && detail.requirements.length > 0 ? (
          <div className="af-detail-sub">
            <span className="af-detail-label">最近需求</span>
            <ul className="af-detail-list">
              {detail.requirements.slice(0, 3).map((rq) => (
                <li key={rq.id ?? rq.title}>
                  <code className="af-run-code">{rq.id ?? ''}</code>{' '}
                  <span>{String(rq.title ?? '').slice(0, 40)}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>
      {/* S32-004: 真实 Run 列表 (来自 /api/projects/{id}/runs, 非前端模拟) */}
      <section className="af-home-card" data-testid="af-home-runs">
        <div className="af-home-card-head">
          <h3>▶ 执行记录（{runs.length}）</h3>
        </div>
        {runs.length === 0 ? (
          <p className="af-home-note">暂无执行 — AI Factory 开始工作时会显示真实 Run。</p>
        ) : (
          <div className="af-runs-list">
            {runs.map((r) => (
              <div key={r.run_id} className="af-run-row">
                <span className={`af-run-dot af-run-dot--${r.status}`}>
                  {r.status === 'running' ? '●' : r.status === 'completed' ? '✓' : '✗'}
                </span>
                <code className="af-run-code">{r.run_id}</code>
                <span className="af-run-state">{r.status}</span>
                {r.totals && r.totals.total_tokens != null && (
                  <span className="af-run-tokens">tokens {r.totals.total_tokens}</span>
                )}
                {r.updated_at && (
                  <span className="af-run-time">{new Date(r.updated_at).toLocaleTimeString()}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
            <section className="af-home-card" data-testid="af-home-todo-summary">
        <div className="af-home-card-head">
          <h3>📋 任务 Todo（未完成 {pendingTasks.length}）</h3>
          <a className="af-preview-btn af-todo-more" href={`#/project/${projectId}/todo`}>
            查看全部 →
          </a>
        </div>
        {pendingTasks.length === 0 ? (
          <p className="af-home-note">（暂无未完成任务 — 在对话里说"加个功能"生成任务）</p>
        ) : (
          <div className="af-todo-list">
            {pendingTasks.slice(0, 5).map((t) => (
              <div key={t.id} className="af-todo-row af-todo-row--summary">
                <span className={`af-pri af-pri-${(t.priority ?? 'P2').toLowerCase()}`}>{t.priority || 'P2'}</span>
                <span className="af-todo-title">{renderInline(t.title || t.id)}</span>
              </div>
            ))}
          </div>
        )}
        <p className="af-home-note">✅ 已完成 {doneTasks.length} · 全部任务/详情/审计见「任务」页</p>
      </section>
    </div>
  );
}
