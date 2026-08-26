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

  const base = `/api/projects/${encodeURIComponent(projectId)}`;

  const [wsData, setWsData] = useState<WorkspaceData | null>(null);

  const loadAll = () => {
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
    getJson<{ items?: { status?: string }[] }>(`${base}/runtimes`)
      .then((d) => {
        const items = d.items ?? [];
        setRuntimeCount(items.length);
        setFailedCount(items.filter((r) => r.status === 'failed').length);
      })
      .catch(() => {
        setRuntimeCount(0);
        setFailedCount(0);
      });
    // 质量分: 读 quality.json (真实; 未生成 → 诚实"未评测")
    getJson<{ content?: string | null; note?: string | null }>(`${base}/docs/quality.json`)
      .then((q) => {
        if (q.content) {
          try {
            const parsed = JSON.parse(q.content) as { score?: number };
            setQualityScore(typeof parsed.score === 'number' ? parsed.score : null);
            setQualityNote(parsed.score != null ? '' : '（无评分）');
          } catch {
            setQualityScore(null);
            setQualityNote('（格式异常）');
          }
        } else {
          setQualityScore(null);
          setQualityNote(q.note ?? '未评测');
        }
      })
      .catch(() => {
        setQualityScore(null);
        setQualityNote('未评测');
      });
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
