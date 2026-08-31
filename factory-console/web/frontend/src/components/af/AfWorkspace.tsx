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
  const [error] = useState('');

  return (
    <div className="af-ws-panel">
      <div className="af-ws-section-title">代码</div>
      <div className="af-ws-empty">
        {error || 'Agent 生成的代码会在这里显示。去对话中开始一个开发任务。'}
      </div>
    </div>
  );
}

function PreviewPanel(): JSX.Element {
  return (
    <div className="af-ws-panel">
      <div className="af-ws-section-title">预览</div>
      <div className="af-ws-empty">产物预览会在这里显示。完成开发后可在此查看真实 Web App。</div>
    </div>
  );
}

function DiffPanel(): JSX.Element {
  return (
    <div className="af-ws-panel">
      <div className="af-ws-section-title">Diff</div>
      <div className="af-ws-empty">代码变更对比会在这里显示。</div>
    </div>
  );
}

function EvidencePanel(): JSX.Element {
  return (
    <div className="af-ws-panel">
      <div className="af-ws-section-title">证据</div>
      <div className="af-ws-empty">验证结果与 Evidence 会在这里显示。</div>
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
