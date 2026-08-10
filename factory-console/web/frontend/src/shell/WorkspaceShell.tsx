/**
 * shell/WorkspaceShell.tsx — S10-001 Workspace Shell (三栏布局框架)。
 *
 * ┌ Header (品牌/项目选择/LLM 状态/主题/用户菜单) ──────────────┐
 * ├ Explorer 220px ├ AI Workspace (flex) ├ Factory Panel 360px ┤
 *
 * - 消费 S10-000 Design System: <Layout> 三栏 (两侧可折叠) +
 *   ThemeToggle/Select/StatusBadge/Button + --ds-* 令牌
 * - 导航: 8 项 Explorer 导航 + Project Tree (mock) + Panel 4 Tab
 * - 不实现 Timeline/Browser/Artifact/Review 内容 (Empty State 占位)
 */

import { useEffect, useMemo, useState } from 'react';
import { Layout } from '../components/ds';
import { MOCK_PROJECTS } from '../mock/workspace';
import type { ExplorerViewId, PanelTabId } from '../mock/workspace';
import { api } from '../api/client';
import { ExplorerNav } from './ExplorerNav';
import { FactoryPanel } from './FactoryPanel';
import { ProjectTree, type TreeProject } from './ProjectTree';
import { WorkspaceHeader } from './WorkspaceHeader';
import { WorkspaceView } from './WorkspaceView';
import './workspace.css';

export function WorkspaceShell({
  initialProjectId = null,
  initialPanelTab = null,
  initialArtifactId = null,
}: {
  /** S10-003: hash 直链初始项目 (无 → 空态首页, 用户自行选择)。 */
  initialProjectId?: string | null;
  /** S10-005: hash 直链初始面板 Tab (截图入口 #/workspace?project=X&panel=artifact)。 */
  initialPanelTab?: PanelTabId | null;
  /** S10-005: hash 直链初始产物 (打开 Artifact Tab 并定位详情)。 */
  initialArtifactId?: string | null;
}): JSX.Element {
  const [view, setView] = useState<ExplorerViewId>('home');
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(initialProjectId);
  const [panelTab, setPanelTab] = useState<PanelTabId>(initialPanelTab ?? 'browser');
  // S10-006.5 P0: 真实项目列表 (GET /api/projects; 失败 → 空列表, 创建入口兜底)
  const [projects, setProjects] = useState<TreeProject[]>([]);
  useEffect(() => {
    let cancelled = false;
    api
      .projects()
      .then((list) => {
        if (!cancelled) {
          setProjects(
            list.map((project) => ({
              id: project.id,
              name: project.name,
              status: project.status ?? null,
            })),
          );
        }
      })
      .catch(() => {
        if (!cancelled) setProjects([]); // 后端不可达 → 空 (创建会诚实报错)
      });
    return () => {
      cancelled = true;
    };
  }, []);
  // S10-005 Timeline 联动: artifact 查看请求 (artifactId + 递增序号触发)
  const [artifactFocus, setArtifactFocus] = useState<{ artifactId: string; nonce: number } | null>(
    initialArtifactId != null ? { artifactId: initialArtifactId, nonce: 1 } : null,
  );

  const selectedProject = useMemo(
    () => MOCK_PROJECTS.find((project) => project.id === selectedProjectId) ?? null,
    [selectedProjectId],
  );

  /** S10-006.5: 创建项目 (POST /api/projects → 项目入树 + 选中)。 */
  const handleCreateProject = async (idea: string): Promise<void> => {
    const created = await api.createProject(idea);
    setProjects((prev) => {
      const next = prev.filter((project) => project.id !== created.project_id);
      return [...next, { id: created.project_id, name: created.name, status: created.status }];
    });
    setSelectedProjectId(created.project_id);
    window.location.hash = `#/workspace?project=${created.project_id}`;
  };

  /** Timeline artifact 查看 → 选中 Artifact Tab + 定位产物详情 (S10-005;
   * 复用 S10-004 onViewArtifact 管线, 目标由 Runtime 改为 Artifact Center)。 */
  const handleViewArtifact = (artifactId: string): void => {
    setArtifactFocus((prev) => ({ artifactId, nonce: (prev?.nonce ?? 0) + 1 }));
    setPanelTab('artifact');
  };

  return (
    <div className="ws-shell" data-testid="ws-shell">
      <WorkspaceHeader
        projectId={selectedProjectId}
        onSelectProject={setSelectedProjectId}
        onOpenSettings={() => setView('settings')}
      />
      <div className="ws-body">
        <Layout
          explorer={
            <>
              <ExplorerNav active={view} onSelect={setView} />
              {view === 'projects' || selectedProject != null ? (
                <ProjectTree
                  projects={projects}
                  selectedId={selectedProjectId}
                  onSelectProject={setSelectedProjectId}
                />
              ) : null}
            </>
          }
          workspace={
            <WorkspaceView
              view={view}
              project={selectedProject}
              onOpenProjects={() => setView('projects')}
              onViewArtifact={handleViewArtifact}
              onCreateProject={handleCreateProject}
            />
          }
          panel={
            <FactoryPanel
              activeTab={panelTab}
              onSelectTab={setPanelTab}
              projectId={selectedProjectId}
              focusArtifactId={artifactFocus?.artifactId ?? null}
              focusNonce={artifactFocus?.nonce ?? null}
              onFocusConsumed={() => setArtifactFocus(null)}
            />
          }
        />
      </div>
    </div>
  );
}
