/**
 * state/AppState.tsx — 应用级状态 (轻量, 无外部路由依赖)。
 *
 * - mode: 'simple' (普通模式, 默认) | 'expert' (专业模式)
 * - page: 当前页面 (Dashboard/Projects/Lifecycle/Approvals/Decisions/
 *   Intelligence/Providers — 状态导航, 无需 react-router)
 * - navigate: 页面切换 (仅前端路由状态, 不触发任何写请求)
 */

import { createContext, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

export type Mode = 'simple' | 'expert';

export type Page =
  | { name: 'dashboard' }
  | { name: 'projects' }
  | { name: 'lifecycle'; projectId: string }
  | { name: 'approvals' }
  | { name: 'decisions'; decisionId?: string }
  | { name: 'intelligence' }
  | { name: 'providers' };

export interface AppStateValue {
  mode: Mode;
  setMode: (mode: Mode) => void;
  page: Page;
  navigate: (page: Page) => void;
}

const AppStateContext = createContext<AppStateValue | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }): JSX.Element {
  const [mode, setMode] = useState<Mode>('simple');
  const [page, setPage] = useState<Page>({ name: 'dashboard' });

  const value = useMemo<AppStateValue>(
    () => ({ mode, setMode, page, navigate: setPage }),
    [mode, page],
  );

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState(): AppStateValue {
  const ctx = useContext(AppStateContext);
  if (ctx === null) {
    throw new Error('useAppState 必须在 <AppStateProvider> 内使用');
  }
  return ctx;
}
