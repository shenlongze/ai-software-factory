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
  /** 模块锚点 (想法→细化→待办链路): 会话细化该模块 (create_task 自动绑定)。 */
  featureId: string | null;
  /** 模块锚点名 (作用域指示器显示, 人话)。 */
  featureName: string | null;
  sessions: SessionSummary[];
  activeId: string | null;
  messages: ChatMessage[];
  loadingSessions: boolean;
  sending: boolean;
  uiPrefs: { show_thinking: boolean; show_execution: boolean; show_timing: boolean };
  setUiPrefs: (p: { show_thinking?: boolean; show_execution?: boolean; show_timing?: boolean }) => void;
  collapsed: boolean;
  pinned: boolean;
  setScope: (scope: SessionScope) => void;
  setProjectId: (pid: string | null) => void;
  setFeatureId: (fid: string | null, name?: string) => void;
  toggleCollapsed: () => void;
  togglePinned: () => void;
  openPanel: () => void;
  createSession: (title?: string, featureId?: string | null) => Promise<SessionSummary | null>;
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
  featureId: null,
  featureName: null,
  sessions: [],
  activeId: null,
  messages: [],
  loadingSessions: false,
  sending: false,
  uiPrefs: { show_thinking: true, show_execution: true, show_timing: true },
  setUiPrefs: () => {},
  collapsed: false,
  pinned: false,
  setScope: () => {},
  setProjectId: () => {},
  setFeatureId: () => {},
  toggleCollapsed: () => {},
  togglePinned: () => {},
  openPanel: () => {},
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
  const [featureId, setFeatureIdState] = useState<string | null>(null);
  const [featureName, setFeatureNameState] = useState<string | null>(null);
  // A 方案 (Founder 2026-08-26): 作用域自动跟随当前视图 — 有项目 → project, 否则 company
  const setProjectId = useCallback((pid: string | null) => {
    setProjectIdState(pid);
    // 模块锚点属于项目 — 切换项目/回公司时清空 (避免串作用域)
    setFeatureIdState(null);
    setFeatureNameState(null);
    const next: SessionScope = pid ? 'project' : 'company';
    setScopeState((prev) => (prev !== next ? next : prev));
  }, []);
  const setFeatureId = useCallback((fid: string | null, name?: string) => {
    setFeatureIdState(fid);
    setFeatureNameState(fid ? (name ?? null) : null);
  }, []);
  const openPanel = useCallback(() => {
    setCollapsed(false);
  }, []);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<SessionMessage[]>([]);
  const [loadingSessions, setLoadingSessions] = useState<boolean>(true);
  const [sending, setSending] = useState<boolean>(false);
  const [uiPrefs, setUiPrefsState] = useState({ show_thinking: true, show_execution: true, show_timing: true });

  // U3: 加载 UI 显示偏好 (失败默认全开)
  useEffect(() => {
    void api
      .getUiPrefs()
      .then((p) => setUiPrefsState({ ...p }))
      .catch(() => {
        /* 默认 */
      });
  }, []);

  const setUiPrefs = useCallback((p: { show_thinking?: boolean; show_execution?: boolean; show_timing?: boolean }) => {
    setUiPrefsState((prev) => {
      const next = { ...prev, ...p };
      void api.setUiPrefs(next).catch(() => {});
      return next;
    });
  }, []);
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
    async (title?: string, fid?: string | null): Promise<SessionSummary | null> => {
      try {
        const created = await api.createSession({
          scope,
          project_id: scope === 'project' ? projectId : null,
          title,
          feature_id: fid !== undefined ? fid : featureId,
        });
        await refresh();
        setActiveId(created.id);
        return created;
      } catch {
        return null;
      }
    },
    [scope, projectId, featureId, refresh],
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
        // S10-127 P1.4: 优先流式 (工具调用实时展示); 失败/不支持 → 回退同步
        const assistantId = `tmp-ai-${Date.now()}`;
        setMessages((prev) => [
          ...prev,
          {
            id: assistantId,
            session_id: target as string,
            role: 'assistant',
            content: '（思考中…）',
            created_at: new Date().toISOString(),
            meta: { tool_calls: [], thinking_steps: [] },
          },
        ]);
        let streamed = false;
        const ok = await api.sessionSendStream(target as string, text, (e) => {
          if (e.type === 'thinking') {
            // T3: 思考链可视化 — 存独立 thinking_steps 数组 (含 round), 不污染 content
            const detail = (e as { detail?: string }).detail;
            const round = (e as { round?: number }).round ?? 0;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      content: '（思考中…）',
                      meta: {
                        ...(m.meta ?? {}),
                        thinking_steps: [
                          ...(m.meta?.thinking_steps ?? []),
                          { round, detail: detail ?? '' },
                        ],
                      },
                    }
                  : m,
              ),
            );
          } else if (e.type === 'tool') {
            // U2: 执行过程 — 徽章带耗时
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      content: '（执行中…）',
                      meta: {
                        tool_calls: [
                          ...(m.meta?.tool_calls ?? []),
                          {
                            tool: e.tool ?? '',
                            ok: e.ok ?? false,
                            duration_ms: e.duration_ms ?? 0,
                            // S8-4: bash 写操作批准 — 需批准时带命令/审批ID
                            need_approval: e.need_approval ?? false,
                            approval_id: e.approval_id ?? '',
                            command: e.command ?? '',
                            error: e.error ?? '',
                            // T4: 全息展示 — 参数预览 + 结果截断
                            params: e.params ?? '',
                            output: e.output ?? '',
                          },
                        ],
                      },
                    }
                  : m,
              ),
            );
          } else if (e.type === 'done' && e.result) {
            streamed = true;
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? (e.result?.assistant ?? m) : m)),
            );
          }
        });
        if (!ok || !streamed) {
          // 回退同步
          setMessages((prev) => prev.filter((m) => m.id !== assistantId));
          const result = await api.sendSessionMessage(target as string, text);
          setMessages((prev) => [
            ...prev.filter((m) => !m.id.startsWith('tmp-')),
            result.user,
            { ...result.assistant, target: result.meta?.target ?? null },
          ]);
        }
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
      featureId,
      featureName,
      sessions,
      activeId,
      messages,
      loadingSessions,
      sending,
      uiPrefs,
      setUiPrefs,
      collapsed,
      pinned,
      setScope,
      setProjectId,
      setFeatureId,
      toggleCollapsed,
      togglePinned,
      openPanel,
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
      featureId,
      featureName,
      sessions,
      activeId,
      messages,
      loadingSessions,
      sending,
      collapsed,
      pinned,
      setScope,
      setProjectId,
      setFeatureId,
      setFeatureNameState,
      toggleCollapsed,
      togglePinned,
      openPanel,
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
