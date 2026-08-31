/**
 * components/af/AfWorkspace.tsx — K9 Human Workspace 右栏 (Workbench)。
 *
 * "AI 正在做什么" 的可视化现场。由中栏 Conversation 联动驱动
 * (ConversationContext.workspaceTab), 用户可手动切 Tab。
 *
 * Tab 集合 (PRD §3.3): Task / Code / Preview / Diff / Evidence
 * 数据全来自 OS API (task-trees / projects-os / ops / artifacts), UI 零业务状态。
 */

import { useEffect, useState } from 'react';
import { useConversation } from './ConversationContext';
import { api } from '../../api/client';
import type { OsProjectStatus } from '../../models/types';
import './af.css';

export const WORKSPACE_TABS = [
  { id: 'task', label: '📊 任务', icon: '📊' },
  { id: 'code', label: '💻 代码', icon: '💻' },
  { id: 'preview', label: '🌐 预览', icon: '🌐' },
  { id: 'diff', label: '📝 Diff', icon: '📝' },
  { id: 'evidence', label: '✅ 证据', icon: '✅' },
] as const;

export type WorkspaceTabId = (typeof WORKSPACE_TABS)[number]['id'];

/** 联动规则 (PRD §5): 消息 Intent → 右栏 Tab。 */
export function tabForIntent(intent: string): WorkspaceTabId {
  switch (intent) {
    case 'EXECUTE':
    case 'APPROVE':
      return 'task';
    case 'ASK_STATUS':
      return 'task';
    case 'DECIDE':
      return 'code';
    case 'CLARIFY':
      return 'code';
    case 'DISCUSS':
    default:
      return 'preview';
  }
}

function TaskPanel(): JSX.Element {
  const [projects, setProjects] = useState<Array<{ id: string; title: string }>>([]);
  const [status, setStatus] = useState<OsProjectStatus | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    api
      .osProjects()
      .then((list) => {
        if (!cancelled) setProjects(list.slice(0, 5));
        if (!cancelled && list.length > 0) {
          return api.osProjectStatus(list[0].id).then((s) => {
            if (!cancelled) setStatus(s);
          });
        }
        return undefined;
      })
      .catch(() => {
        if (!cancelled) setError('任务数据加载失败');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <div className="af-ws-empty">{error}</div>;
  if (!status && projects.length === 0) return <div className="af-ws-empty">暂无任务 — 在对话中开始一个工作</div>;

  return (
    <div className="af-ws-panel">
      <div className="af-ws-section-title">项目进度</div>
      {projects.map((p) => (
        <div key={p.id} className="af-ws-row">
          <span>{p.title}</span>
          <span className="af-ws-muted">{p.id.slice(0, 12)}</span>
        </div>
      ))}
      {status && (
        <>
          <div className="af-ws-section-title">Sprint 进度</div>
          {status.sprints.map((s) => (
            <div key={s.sprint_id} className="af-ws-card">
              <div className="af-ws-row">
                <span>{s.title}</span>
                <span>{s.progress.percentage}%</span>
              </div>
              <div className="af-ws-bar">
                <div className="af-ws-bar-fill" style={{ width: `${s.progress.percentage}%` }} />
              </div>
              {s.tasks.map((t) => (
                <div key={t.id} className="af-ws-row af-ws-task">
                  <span>{t.title}</span>
                  <span className={`af-ws-state af-ws-state--${t.status.toLowerCase()}`}>{t.status}</span>
                </div>
              ))}
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function CodePanel(): JSX.Element {
  const [artifacts, setArtifacts] = useState<Array<{ id: string; type?: string; ref?: string; status?: string }>>([]);
  const [selected, setSelected] = useState<string>('');
  const [content, setContent] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    api
      .artifacts({})
      .then((list) => {
        if (cancelled) return;
        setArtifacts(list.slice(0, 10));
        if (list.length > 0) {
          setSelected(list[0].id);
          return api.artifactContent(list[0].id).then((c) => {
            if (!cancelled) setContent(c.content ?? '');
          });
        }
        return undefined;
      })
      .catch(() => {
        if (!cancelled) setError('产物加载失败');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const open = async (id: string) => {
    setSelected(id);
    try {
      const c = await api.artifactContent(id);
      setContent(c.content ?? '');
    } catch {
      setContent('');
    }
  };

  if (error) return <div className="af-ws-empty">{error}</div>;

  return (
    <div className="af-ws-panel">
      <div className="af-ws-section-title">代码产物 (真实 /api/artifacts)</div>
      {artifacts.length === 0 && <div className="af-ws-empty">暂无产物 — 去对话中开始一个开发任务</div>}
      {artifacts.map((a) => (
        <button
          key={a.id}
          type="button"
          className={`af-ws-file${selected === a.id ? ' af-ws-file--active' : ''}`}
          onClick={() => void open(a.id)}
        >
          <span>{a.ref ?? a.type ?? a.id}</span>
          <span className="af-ws-muted">{a.status ?? ''}</span>
        </button>
      ))}
      {content && (
        <pre className="af-ws-code" data-testid="af-ws-code">
          {content.slice(0, 4000)}
        </pre>
      )}
    </div>
  );
}

function PreviewPanel(): JSX.Element {
  const [previews, setPreviews] = useState<Array<{ id: string; type?: string; ref?: string }>>([]);
  const [selected, setSelected] = useState<string>('');
  const [content, setContent] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    api
      .artifacts({})
      .then((list) => {
        if (cancelled) return;
        // 可预览产物: web/markdown/html/doc
        const p = list.filter((a) => /web|markdown|html|doc|artifact/i.test(String(a.type ?? ''))).slice(0, 5);
        setPreviews(p);
        if (p.length > 0) {
          setSelected(p[0].id);
          return api.artifactContent(p[0].id).then((c) => {
            if (!cancelled) setContent(c.content ?? '');
          });
        }
        return undefined;
      })
      .catch(() => {
        if (!cancelled) setError('预览加载失败');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <div className="af-ws-empty">{error}</div>;

  return (
    <div className="af-ws-panel">
      <div className="af-ws-section-title">预览 (真实产物)</div>
      {previews.length === 0 && <div className="af-ws-empty">暂无可预览产物 — 完成开发后产物会出现在这里</div>}
      {previews.map((p) => (
        <button
          key={p.id}
          type="button"
          className={`af-ws-file${selected === p.id ? ' af-ws-file--active' : ''}`}
          onClick={() => {
            setSelected(p.id);
            void api.artifactContent(p.id).then((c) => setContent(c.content ?? ''));
          }}
        >
          <span>{p.ref ?? p.type ?? p.id}</span>
        </button>
      ))}
      {content && <pre className="af-ws-code af-ws-code--preview">{content.slice(0, 3000)}</pre>}
    </div>
  );
}

function DiffPanel(): JSX.Element {
  const [diffs, setDiffs] = useState<Array<{ id: string; type?: string; ref?: string; status?: string }>>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    api
      .artifacts({})
      .then((list) => {
        if (!cancelled) setDiffs(list.filter((a) => /diff|code|patch/i.test(String(a.type ?? ''))).slice(0, 10));
      })
      .catch(() => {
        if (!cancelled) setError('变更记录加载失败');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <div className="af-ws-empty">{error}</div>;

  return (
    <div className="af-ws-panel">
      <div className="af-ws-section-title">代码变更 (真实产物)</div>
      {diffs.length === 0 && <div className="af-ws-empty">暂无变更记录</div>}
      {diffs.map((d) => (
        <div key={d.id} className="af-ws-row af-ws-task">
          <span>{d.ref ?? d.type ?? d.id}</span>
          <span className={`af-ws-state af-ws-state--${String(d.status ?? '').toLowerCase()}`}>{d.status ?? ''}</span>
        </div>
      ))}
    </div>
  );
}

function EvidencePanel(): JSX.Element {
  const [tasks, setTasks] = useState<Array<{ id: string; title: string; status: string }>>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    api
      .osProjects()
      .then((list) => {
        if (cancelled || list.length === 0) return;
        return api.opsDrill(list[0].id).then((drill) => {
          if (cancelled) return;
          const t = drill.sprints?.flatMap((s) => s.tasks ?? []) ?? [];
          setTasks(t.map((x) => ({ id: x.id, title: x.title ?? x.id, status: x.status ?? x.operational_state ?? '' })).slice(0, 10));
        });
      })
      .catch(() => {
        if (!cancelled) setError('验证记录加载失败');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <div className="af-ws-empty">{error}</div>;

  return (
    <div className="af-ws-panel">
      <div className="af-ws-section-title">验证结果 (真实 task 状态)</div>
      {tasks.length === 0 && <div className="af-ws-empty">暂无验证记录 — 工作开始后这里显示验证结果</div>}
      {tasks.map((t) => (
        <div key={t.id} className="af-ws-row af-ws-task">
          <span>{t.title}</span>
          <span className={`af-ws-state af-ws-state--${t.status.toLowerCase()}`}>{t.status}</span>
        </div>
      ))}
    </div>
  );
}

export function AfWorkspace(): JSX.Element {
  const { workspaceTab, setWorkspaceTab } = useConversation();
  const active = (WORKSPACE_TABS.find((t) => t.id === workspaceTab) ?? WORKSPACE_TABS[0]).id as WorkspaceTabId;

  return (
    <div className="af-workspace" data-testid="af-workspace">
      <div className="af-ws-tabs" role="tablist" aria-label="Workspace 工具">
        {WORKSPACE_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={active === t.id}
            className={`af-ws-tab${active === t.id ? ' af-ws-tab--active' : ''}`}
            onClick={() => setWorkspaceTab(t.id)}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>
      <div className="af-ws-body">
        {active === 'task' && <TaskPanel />}
        {active === 'code' && <CodePanel />}
        {active === 'preview' && <PreviewPanel />}
        {active === 'diff' && <DiffPanel />}
        {active === 'evidence' && <EvidencePanel />}
      </div>
    </div>
  );
}
