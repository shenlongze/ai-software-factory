/**
 * pages/project/AfProjectHome.tsx — 项目首页 (K-7b, 敏捷项目管理)。
 *
 * ① 全生命周期条 (GET /lifecycle)  ② 任务 Todo (GET /backlog, 列表⇄泳道,
 *    编辑优先级/状态 PATCH, 完成标记)  ③ 运维摘要 (runtimes)
 * 原则: 简单 · 直接 · 高效 · 易用; 失败安全 (后端不可达 → 空态不崩)。
 */

import { useEffect, useMemo, useState } from 'react';

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
const TASK_STATUSES = ['todo', 'ready', 'in_progress', 'blocked', 'review', 'done'];
const PRIORITIES = ['P0', 'P1', 'P2'];

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
  const [view, setView] = useState<'list' | 'board'>('list');
  const [busy, setBusy] = useState<string>('');

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
    getJson<unknown[]>(`${base}/runtimes`)
      .then((list) => setRuntimeCount(Array.isArray(list) ? list.length : 0))
      .catch(() => setRuntimeCount(0));
  };

  // ③ 实时性: 打开拉取 + 手动刷新 + 可选自动轮询 (5/15/30/60s)
  const [pollMs, setPollMs] = useState<number>(0);
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

  const patchTask = (taskId: string, body: Record<string, unknown>) => {
    setBusy(taskId);
    fetch(`${base}/backlog/task/${encodeURIComponent(taskId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then((res) => {
        if (!res.ok) return res.json().then((e) => Promise.reject(new Error(e?.detail || 'HTTP ' + res.status)));
        loadAll();
      })
      .catch((err) => {
        // eslint-disable-next-line no-alert
        window.alert(`更新失败: ${String(err)}`);
      })
      .finally(() => setBusy(''));
  };

  const byStatus = useMemo(() => {
    const map: Record<string, TaskItem[]> = {};
    for (const st of TASK_STATUSES) map[st] = [];
    for (const t of tasks) {
      const st = t.status ?? 'todo';
      (map[st] ??= []).push(t);
    }
    return map;
  }, [tasks]);

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

  const todoList = (
    <div className="af-todo-list" data-testid="af-todo-list">
      {tasks.length === 0 && <p className="af-home-note">（暂无任务 — 在对话里说"加个功能"生成任务）</p>}
      {tasks.map((t) => (
        <div key={t.id} className="af-todo-row">
          <span className={`af-pri af-pri-${(t.priority ?? 'P2').toLowerCase()}`}>{t.priority || 'P2'}</span>
          <span className="af-todo-title">{t.title || t.id}</span>
          <select
            className="af-todo-pri"
            aria-label={`优先级 ${t.id}`}
            value={t.priority || 'P2'}
            disabled={busy === t.id}
            onChange={(e) => patchTask(t.id, { priority: e.target.value })}
          >
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <select
            className="af-todo-status"
            aria-label={`状态 ${t.id}`}
            value={t.status || 'todo'}
            disabled={busy === t.id}
            onChange={(e) => patchTask(t.id, { status: e.target.value })}
          >
            {TASK_STATUSES.map((st) => (
              <option key={st} value={st}>
                {st}
              </option>
            ))}
          </select>
          {t.status === 'done' ? (
            <span className="af-todo-archived" title="已完成 — 审计/溯源见执行记录">
              ⤓ 已归档
            </span>
          ) : null}
        </div>
      ))}
    </div>
  );

  const todoBoard = (
    <div className="af-todo-board" data-testid="af-todo-board">
      {TASK_STATUSES.filter((st) => st !== 'blocked' && st !== 'review').map((st) => (
        <div key={st} className="af-board-col" data-status={st}>
          <h4 className="af-board-col-title">{st}</h4>
          {(byStatus[st] ?? []).map((t) => (
            <div key={t.id} className="af-board-card">
              <span className={`af-pri af-pri-${(t.priority ?? 'P2').toLowerCase()}`}>{t.priority || 'P2'}</span>
              <span className="af-todo-title">{t.title || t.id}</span>
              <div className="af-board-actions">
                <button type="button" className="af-preview-btn" onClick={() => patchTask(t.id, { priority: 'P0' })}>
                  P0
                </button>
                {st !== 'done' ? (
                  <button
                    type="button"
                    className="af-preview-btn"
                    onClick={() =>
                      patchTask(t.id, { status: st === 'todo' ? 'ready' : st === 'ready' ? 'in_progress' : 'done' })
                    }
                  >
                    推进
                  </button>
                ) : (
                  <span className="af-todo-archived">已归档</span>
                )}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );

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
      <section className="af-home-card">
        <div className="af-home-card-head">
          <h3>📋 任务 Todo</h3>
          <div className="af-view-toggle">
            <button
              type="button"
              className={`af-preview-btn${view === 'list' ? ' active' : ''}`}
              onClick={() => setView('list')}
            >
              列表
            </button>
            <button
              type="button"
              className={`af-preview-btn${view === 'board' ? ' active' : ''}`}
              onClick={() => setView('board')}
            >
              泳道
            </button>
          </div>
        </div>
        {view === 'list' ? todoList : todoBoard}
      </section>
      <section className="af-home-card">
        <h3>🖥 运维 / 监控</h3>
        <p className="af-home-note">运行实例 {runtimeCount} 个 · 质量/成本/参与见右栏预览与后续面板</p>
      </section>
    </div>
  );
}
