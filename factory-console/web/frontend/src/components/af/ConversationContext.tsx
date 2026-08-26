/**
 * components/af/ConversationContext.tsx — K-7e AI 会话栏状态 (App 级常驻)。
 *
 * 会话数据跨导航持久 (App 级 Provider 包裹, Shell 切换不丢):
 * - scope: company|project (作用域); projectId: 项目级当前项目
 * - sessions: 当前作用域会话列表 (多线程); messages: 当前会话消息
 * - collapsed/pinned: 面板收起/常驻 (localStorage 持久)
 * 数据: 真实 API (GET/POST /api/sessions + messages), 失败安全空态。
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { api } from '../../api/client';
import type { SessionMessage, SessionSummary } from '../../models/types';

/** 前端会话消息 (assistant 可带跳转 target — 来自后端 meta.target)。 */
export type ChatMessage = SessionMessage & { target?: { url: string; label: string } | null };

export type SessionScope = 'company' | 'project';

const COLLAPSED_KEY = 'af.chat.collapsed';
const PINNED_KEY = 'af.chat.pinned';
const SCOPE_KEY = 'af.chat.scope';

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

export interface ConversationContextValue {
  scope: SessionScope;
  projectId: string | null;
  sessions: SessionSummary[];
  activeId: string | null;
  messages: ChatMessage[];
  loadingSessions: boolean;
  sending: boolean;
  collapsed: boolean;
  pinned: boolean;
  setScope: (scope: SessionScope) => void;
  setProjectId: (pid: string | null) => void;
  toggleCollapsed: () => void;
  togglePinned: () => void;
  createSession: (title?: string) => Promise<SessionSummary | null>;
  selectSession: (id: string) => void;
  renameSession: (id: string, title: string) => void;
  archiveSession: (id: string) => void;
  send: (content: string) => Promise<void>;
  refresh: () => void;
}

/** 默认上下文 (无 Provider 时兜底 — 组件不崩溃, 空态/无操作)。 */
const DEFAULT_CONTEXT: ConversationContextValue = {
  scope: 'company',
  projectId: null,
  sessions: [],
  activeId: null,
  messages: [],
  loadingSessions: false,
  sending: false,
  collapsed: false,
  pinned: false,
  setScope: () => {},
  setProjectId: () => {},
  toggleCollapsed: () => {},
  togglePinned: () => {},
  createSession: async () => null,
  selectSession: () => {},
  renameSession: () => {},
  archiveSession: () => {},
  send: async () => {},
  refresh: () => {},
};

const ConversationContext = createContext<ConversationContextValue>(DEFAULT_CONTEXT);

export function ConversationProvider({ children }: { children: ReactNode }): JSX.Element {
  const [scope, setScopeState] = useState<SessionScope>(() => {
    try {
      return window.localStorage.getItem(SCOPE_KEY) === 'project' ? 'project' : 'company';
    } catch {
      return 'company';
    }
  });
  const [projectId, setProjectIdState] = useState<string | null>(null);
  // A 方案 (Founder 2026-08-26): 作用域自动跟随当前视图 — 有项目 → project, 否则 company
  const setProjectId = useCallback((pid: string | null) => {
    setProjectIdState(pid);
    const next: SessionScope = pid ? 'project' : 'company';
    setScopeState((prev) => (prev !== next ? next : prev));
  }, []);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<SessionMessage[]>([]);
  const [loadingSessions, setLoadingSessions] = useState<boolean>(true);
  const [sending, setSending] = useState<boolean>(false);
  const [collapsed, setCollapsed] = useState<boolean>(() => readFlag(COLLAPSED_KEY));
  const [pinned, setPinned] = useState<boolean>(() => readFlag(PINNED_KEY));

  const setScope = useCallback((s: SessionScope) => {
    setScopeState(s);
    writeFlag(SCOPE_KEY, s === 'project');
    setActiveId(null);
    setMessages([]);
  }, []);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((prev) => {
      writeFlag(COLLAPSED_KEY, !prev);
      return !prev;
    });
  }, []);
  const togglePinned = useCallback(() => {
    setPinned((prev) => {
      writeFlag(PINNED_KEY, !prev);
      return !prev;
    });
  }, []);

  const refresh = useCallback(() => {
    setLoadingSessions(true);
    api
      .sessions(scope, scope === 'project' ? projectId ?? undefined : undefined)
      .then((list) => {
        setSessions(list);
        setActiveId((prev) => {
          if (prev != null && list.some((s) => s.id === prev)) return prev;
          const first = list.find((s) => s.status === 'active') ?? list[0];
          return first ? first.id : null;
        });
      })
      .catch(() => setSessions([]))
      .finally(() => setLoadingSessions(false));
  }, [scope, projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // 作用域切换 (跟随视图) → 清空当前会话/消息, 加载新作用域列表
  useEffect(() => {
    setActiveId(null);
    setMessages([]);
  }, [scope]);

  // 当前会话消息加载
  useEffect(() => {
    if (activeId == null) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    api
      .sessionMessages(activeId)
      .then((msgs) => {
        if (!cancelled) setMessages(msgs);
      })
      .catch(() => {
        if (!cancelled) setMessages([]);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  const selectSession = useCallback((id: string) => {
    setActiveId(id);
  }, []);

  const createSession = useCallback(
    async (title?: string): Promise<SessionSummary | null> => {
      try {
        const created = await api.createSession({
          scope,
          project_id: scope === 'project' ? projectId : null,
          title,
        });
        await refresh();
        setActiveId(created.id);
        return created;
      } catch {
        return null;
      }
    },
    [scope, projectId, refresh],
  );

  const renameSession = useCallback(
    (id: string, title: string) => {
      void api
        .updateSession(id, { title })
        .then(() => refresh())
        .catch(() => {
          /* 失败保持原样 */
        });
    },
    [refresh],
  );

  const archiveSession = useCallback(
    (id: string) => {
      void api
        .updateSession(id, { status: 'archived' })
        .then(() => refresh())
        .catch(() => {
          /* 失败保持原样 */
        });
    },
    [refresh],
  );

  const send = useCallback(
    async (content: string): Promise<void> => {
      const text = content.trim();
      if (!text || sending) return;
      let target = activeId;
      if (target == null) {
        const created = await createSession();
        if (created == null) return;
        target = created.id;
      }
      setSending(true);
      // 乐观追加用户消息
      setMessages((prev) => [
        ...prev,
        {
          id: `tmp-${Date.now()}`,
          session_id: target as string,
          role: 'user',
          content: text,
          created_at: new Date().toISOString(),
        },
      ]);
      try {
        const result = await api.sendSessionMessage(target as string, text);
        setMessages((prev) => [
          ...prev.filter((m) => !m.id.startsWith('tmp-')),
          result.user,
          { ...result.assistant, target: result.meta?.target ?? null },
        ]);
        await refresh();
      } catch {
        // 失败 → 保留用户消息, 追加诚实提示
        setMessages((prev) => [
          ...prev,
          {
            id: `err-${Date.now()}`,
            session_id: target as string,
            role: 'assistant',
            content: '（发送失败 — 后端不可达，请稍后重试）',
            created_at: new Date().toISOString(),
          },
        ]);
      } finally {
        setSending(false);
      }
    },
    [activeId, sending, createSession, refresh],
  );

  const value = useMemo<ConversationContextValue>(
    () => ({
      scope,
      projectId,
      sessions,
      activeId,
      messages,
      loadingSessions,
      sending,
      collapsed,
      pinned,
      setScope,
      setProjectId,
      toggleCollapsed,
      togglePinned,
      createSession,
      selectSession,
      renameSession,
      archiveSession,
      send,
      refresh,
    }),
    [
      scope,
      projectId,
      sessions,
      activeId,
      messages,
      loadingSessions,
      sending,
      collapsed,
      pinned,
      setScope,
      setProjectId,
      toggleCollapsed,
      togglePinned,
      createSession,
      selectSession,
      renameSession,
      archiveSession,
      send,
      refresh,
    ],
  );

  return <ConversationContext.Provider value={value}>{children}</ConversationContext.Provider>;
}

export function useConversation(): ConversationContextValue {
  return useContext(ConversationContext);
}
