/**
 * components/af/AfWorkspaceFrame.tsx — AI OS 三栏壳 (K-7d 布局 v4, Founder 定稿)。
 *
 * A 列 OS 导航 (侧栏, 可收起 64px 图标轨) | B 列 数据工作区 (含预览标签页) |
 * C 列 AI 会话栏 (可收起/可常驻)。底部状态栏贯穿。
 *
 * 结构:
 *   header    — 顶栏 (调用方提供, 经 render props 拿 collapsed/toggle)
 *   sidebar   — A 列内容 (调用方提供, 接收 collapsed 态)
 *   main      — B 列页面内容; 预览标签页打开时替换为 AfPreviewWindow (并入 B)
 *   C 列      — AfConversationPanel (App 级 ConversationProvider 状态常驻)
 *   状态栏    — AfStatusBar (模型/作用域/上下文/版本)
 *
 * 快捷键 (VSCode 习惯): Cmd/Ctrl+B 切 A 列 · Cmd/Ctrl+J 切 C 列 · Cmd/Ctrl+K 新建会话。
 * 收起状态持久: 仅 af.sidebar.collapsed (localStorage)。
 * 预览 (Founder 2026-08-26 A 方案): 默认收起、不记住上次状态 — 每次进来
 * 中间显示页面, 预览只在点标签时打开 (纯内存态, 刷新即复位)。
 */

import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { AfPreviewWindow } from './AfPreviewWindow';
import { AfConversationPanel } from './AfConversationPanel';
import { AfStatusBar } from './AfStatusBar';
import { useConversation } from './ConversationContext';
import './af.css';

export const SIDEBAR_COLLAPSED_KEY = 'af.sidebar.collapsed';

function readFlag(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === '1';
  } catch {
    return false;
  }
}
function writeFlag(key: string, value: boolean): void {
  try {
    window.localStorage.setItem(key, value ? '1' : '0');
  } catch {
    /* 仅内存态 */
  }
}

export interface AfWorkspaceFrameHandlers {
  collapsed: boolean;
  onToggleSidebar: () => void;
}

export interface AfWorkspaceFrameProps {
  testId: string;
  pageLabel: string;
  projectId?: string | null;
  projectName?: string | null;
  header: (handlers: AfWorkspaceFrameHandlers) => ReactNode;
  sidebar: (collapsed: boolean) => ReactNode;
  main: ReactNode;
  scopeLabel: string;
}

export function AfWorkspaceFrame({
  testId,
  pageLabel,
  projectId,
  projectName,
  header,
  sidebar,
  main,
  scopeLabel,
}: AfWorkspaceFrameProps): JSX.Element {
  const [collapsed, setCollapsed] = useState<boolean>(() => readFlag(SIDEBAR_COLLAPSED_KEY));
  const [previewOpen, setPreviewOpen] = useState<boolean>(false); // 默认收起, 不持久
  const conversation = useConversation();

  // 清理历史持久化的预览状态 (旧版本 localStorage af.preview.open) — 一次复位
  useEffect(() => {
    try {
      window.localStorage.removeItem('af.preview.open');
    } catch {
      /* 无 localStorage → 忽略 */
    }
  }, []);

  const toggleSidebar = useCallback(() => {
    setCollapsed((prev) => {
      writeFlag(SIDEBAR_COLLAPSED_KEY, !prev);
      return !prev;
    });
  }, []);

  const togglePreview = useCallback(() => {
    setPreviewOpen((prev) => !prev);
  }, []);

  // 快捷键: Cmd/Ctrl+B 切侧栏 · J 切会话 · K 新建会话
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      const k = e.key.toLowerCase();
      if (k === 'b') {
        e.preventDefault();
        toggleSidebar();
      } else if (k === 'j') {
        e.preventDefault();
        conversation.toggleCollapsed();
      } else if (k === 'k') {
        e.preventDefault();
        void conversation.createSession();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [toggleSidebar, conversation.toggleCollapsed, conversation.createSession]);

  return (
    <div
      className={`af-shell af-workspace-shell${collapsed ? ' af-shell--sidebar-collapsed' : ''}`}
      data-testid={testId}
    >
      {header({ collapsed, onToggleSidebar: toggleSidebar })}
      <div className="af-shell-body">
        <aside className="af-col-a">{sidebar(collapsed)}</aside>
        <main className="af-main-content" data-testid="af-main-content">
          <div className="af-b-tabs" data-testid="af-b-tabs">
            <button
              type="button"
              className={`af-b-tab${!previewOpen ? ' af-b-tab--active' : ''}`}
              onClick={() => setPreviewOpen(false)}
              aria-label={`页面: ${pageLabel}`}
            >
              {pageLabel}
            </button>
            <button
              type="button"
              className={`af-b-tab${previewOpen ? ' af-b-tab--active' : ''}`}
              onClick={togglePreview}
              aria-label="预览"
            >
              👁 预览
            </button>
          </div>
          <div className="af-main-scroll" data-testid="af-main-scroll">
            {previewOpen ? <AfPreviewWindow projectId={projectId} defaultOpen /> : main}
          </div>
        </main>
        <aside className="af-col-c">
          <AfConversationPanel projectId={projectId} projectName={projectName} />
        </aside>
      </div>
      <AfStatusBar scopeLabel={scopeLabel} />
    </div>
  );
}
