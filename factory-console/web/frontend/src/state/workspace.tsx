/**
 * state/workspace.tsx — Workspace/Project 选中状态 (Domain Store, S10-014-plan §2.4)。
 *
 * 域状态层: 当前项目上下文 (currentProjectId → Project 级各页面共享)。
 * 原则 (§2.4): 不引入 Redux/MobX; 轻量 Context + hook。
 *
 * S10-014 Task 001: 类型 + Provider 空壳 (默认 null); Task 005 Project Shell 接入。
 */

import { createContext, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { WorkspaceProject } from '../models/domain';

/** Workspace 域状态: 当前选中项目 (id + 完整投影) 与切换入口。 */
export interface WorkspaceContext {
  currentProjectId: string | null;
  currentProject: WorkspaceProject | null;
  setProject: (project: WorkspaceProject | null) => void;
}

const WorkspaceReactContext = createContext<WorkspaceContext | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }): JSX.Element {
  const [currentProject, setCurrentProject] = useState<WorkspaceProject | null>(null);

  const value = useMemo<WorkspaceContext>(
    () => ({
      currentProjectId: currentProject?.id ?? null,
      currentProject,
      setProject: setCurrentProject,
    }),
    [currentProject],
  );

  return <WorkspaceReactContext.Provider value={value}>{children}</WorkspaceReactContext.Provider>;
}

export function useWorkspace(): WorkspaceContext {
  const ctx = useContext(WorkspaceReactContext);
  if (ctx === null) {
    throw new Error('useWorkspace 必须在 <WorkspaceProvider> 内使用');
  }
  return ctx;
}
