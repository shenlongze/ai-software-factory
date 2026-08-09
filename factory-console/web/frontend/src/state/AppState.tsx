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
  | { name: 'providers' }
  // S9-002: 组织级 Workflow / Artifact 视图
  | { name: 'workflow'; workflowId: string; projectId?: string }
  | { name: 'artifacts'; projectId?: string; workflowId?: string }
  // S9-003: 单产物评审页 (从 Artifacts 列表进入; 详情 + approve/reject/comment)
  | { name: 'review'; artifactId: string }
  // S10-001: Workspace Shell (三栏 AI 工作台, 全屏独立于 Human Console)
  | { name: 'workspace' };

export interface AppStateValue {
  mode: Mode;
  setMode: (mode: Mode) => void;
  page: Page;
  navigate: (page: Page) => void;
}

const AppStateContext = createContext<AppStateValue | null>(null);

/** 直接入口 (URL hash): `#/workspace` → Workspace Shell。S10-001 状态导航入口。 */
export function pageFromHash(hash: string): Page | null {
  if (hash === '#/workspace') return { name: 'workspace' };
  return null;
}

function initialPage(): Page {
  try {
    return pageFromHash(window.location.hash) ?? { name: 'dashboard' };
  } catch {
    return { name: 'dashboard' };
  }
}

export function AppStateProvider({ children }: { children: ReactNode }): JSX.Element {
  const [mode, setMode] = useState<Mode>('simple');
  const [page, setPage] = useState<Page>(initialPage);

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
