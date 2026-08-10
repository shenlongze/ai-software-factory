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

import { useMemo, useState } from 'react';
import { Layout } from '../components/ds';
import { MOCK_PROJECTS } from '../mock/workspace';
import type { ExplorerViewId, PanelTabId } from '../mock/workspace';
import { ExplorerNav } from './ExplorerNav';
import { FactoryPanel } from './FactoryPanel';
import { ProjectTree } from './ProjectTree';
import { WorkspaceHeader } from './WorkspaceHeader';
import { WorkspaceView } from './WorkspaceView';
import './workspace.css';

export function WorkspaceShell({
  initialProjectId = null,
}: {
  /** S10-003: hash 直链初始项目 (无 → 空态首页, 用户自行选择)。 */
  initialProjectId?: string | null;
}): JSX.Element {
  const [view, setView] = useState<ExplorerViewId>('home');
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(initialProjectId);
  const [panelTab, setPanelTab] = useState<PanelTabId>('browser');

  const selectedProject = useMemo(
    () => MOCK_PROJECTS.find((project) => project.id === selectedProjectId) ?? null,
    [selectedProjectId],
  );

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
                <ProjectTree project={selectedProject} onSelectProject={setSelectedProjectId} />
              ) : null}
            </>
          }
          workspace={<WorkspaceView view={view} project={selectedProject} onOpenProjects={() => setView('projects')} />}
          panel={<FactoryPanel activeTab={panelTab} onSelectTab={setPanelTab} />}
        />
      </div>
    </div>
  );
}
