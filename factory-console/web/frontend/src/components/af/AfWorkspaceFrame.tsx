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

import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { AfConversationPanel } from './AfConversationPanel';
import { AfStatusBar } from './AfStatusBar';
import { useConversation } from './ConversationContext';
import './af.css';

export const SIDEBAR_COLLAPSED_KEY = 'af.sidebar.collapsed';
export const SIDEBAR_WIDTH_KEY = 'af.sidebar.width';
export const CHAT_WIDTH_KEY = 'af.chat.width';
/** 拖拽宽度范围 (px) — 中间大小可调 (Founder 2026-08-26)。 */
export const SIDEBAR_WIDTH_MIN = 150;
export const SIDEBAR_WIDTH_MAX = 420;
export const CHAT_WIDTH_MIN = 240;
export const CHAT_WIDTH_MAX = 560;
export const SIDEBAR_WIDTH_DEFAULT = 260;
export const CHAT_WIDTH_DEFAULT = 520;

function readNum(key: string, fallback: number): number {
  try {
    const n = Number(window.localStorage.getItem(key));
    return Number.isFinite(n) && n > 0 ? n : fallback;
  } catch {
    return fallback;
  }
}
function writeNum(key: string, value: number): void {
  try {
    window.localStorage.setItem(key, String(Math.round(value)));
  } catch {
    /* 仅内存态 */
  }
}

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v));
}

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
  /** K9 Human Workspace: 右栏 Workbench (缺省时回退 AfConversationPanel)。 */
  workspace?: ReactNode;
  scopeLabel: string;
}

export function AfWorkspaceFrame({
  testId,
  projectId,
  projectName,
  header,
  sidebar,
  scopeLabel,
  main,
  workspace,
}: AfWorkspaceFrameProps): JSX.Element {
  const [collapsed, setCollapsed] = useState<boolean>(() => readFlag(SIDEBAR_COLLAPSED_KEY));
  const [sidebarWidth, setSidebarWidth] = useState<number>(() =>
    readNum(SIDEBAR_WIDTH_KEY, SIDEBAR_WIDTH_DEFAULT),
  );
  const [chatWidth, setChatWidth] = useState<number>(() =>
    readNum(CHAT_WIDTH_KEY, CHAT_WIDTH_DEFAULT),
  );
  const conversation = useConversation();

  // 拖拽分隔条调整 A/C 列宽 (B 列中间 flex:1 自适应 — Founder: 中间可调整大小)
  const dragRef = useRef<{ side: 'left' | 'right'; startX: number; startW: number } | null>(null);
  const widthRef = useRef({ sidebar: sidebarWidth, chat: chatWidth });
  widthRef.current = { sidebar: sidebarWidth, chat: chatWidth };

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const drag = dragRef.current;
      if (drag == null) return;
      const delta = e.clientX - drag.startX;
      if (drag.side === 'left') {
        setSidebarWidth(clamp(drag.startW + delta, SIDEBAR_WIDTH_MIN, SIDEBAR_WIDTH_MAX));
      } else {
        setChatWidth(clamp(drag.startW - delta, CHAT_WIDTH_MIN, CHAT_WIDTH_MAX));
      }
    };
    const onUp = () => {
      const side = dragRef.current?.side;
      dragRef.current = null;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      if (side === 'left') writeNum(SIDEBAR_WIDTH_KEY, widthRef.current.sidebar);
      if (side === 'right') writeNum(CHAT_WIDTH_KEY, widthRef.current.chat);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  const startDrag = (side: 'left' | 'right') => (e: React.MouseEvent) => {
    e.preventDefault();
    dragRef.current = {
      side,
      startX: e.clientX,
      startW: side === 'left' ? sidebarWidth : chatWidth,
    };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

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
        <aside className="af-col-a" style={{ width: collapsed ? undefined : sidebarWidth }}>
          {sidebar(collapsed)}
        </aside>
        {!collapsed ? (
          <div
            className="af-resizer af-resizer--left"
            data-testid="af-resizer-left"
            role="separator"
            aria-label="调整侧栏宽度"
            onMouseDown={startDrag('left')}
            onDoubleClick={() => {
              setSidebarWidth(SIDEBAR_WIDTH_DEFAULT);
              writeNum(SIDEBAR_WIDTH_KEY, SIDEBAR_WIDTH_DEFAULT);
            }}
          />
        ) : null}
        <main className="af-main-content" data-testid="af-main-content">
          {/* K9 Human Workspace: B 列 = 中栏 (ConversationCenter — 唯一主入口) */}
          <div className="af-main-scroll af-main-scroll--ws" data-testid="af-main-scroll">
            {main}
          </div>
        </main>
        <div
          className="af-resizer af-resizer--right"
          data-testid="af-resizer-right"
          role="separator"
          aria-label="调整工作台宽度"
          onMouseDown={startDrag('right')}
          onDoubleClick={() => {
            setChatWidth(CHAT_WIDTH_DEFAULT);
            writeNum(CHAT_WIDTH_KEY, CHAT_WIDTH_DEFAULT);
          }}
        />
        <aside className="af-col-c" style={{ width: collapsed ? undefined : chatWidth }}>
          {/* K9 Human Workspace: C 列 = 右栏 (Workspace — AI 工作现场) */}
          {workspace ?? <AfConversationPanel projectId={projectId} projectName={projectName} />}
        </aside>
      </div>
      <AfStatusBar scopeLabel={scopeLabel} />
    </div>
  );
}
