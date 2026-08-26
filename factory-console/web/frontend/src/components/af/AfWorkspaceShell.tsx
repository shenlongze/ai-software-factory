/**
 * components/af/AfWorkspaceShell.tsx — AI OS Workspace 三栏壳 (K-7d 布局 v4)。
 *
 * 结构 (AfWorkspaceFrame 三栏, Founder 定稿 A|B|C):
 *   A 列   — AfSidebar (OS 层级树, 可收起 64px 图标轨)
 *   B 列   — WorkspacePage (公司首页/项目列表/设置/管理) + 预览标签页 (并入 B)
 *   C 列   — AfConversationPanel (AI 会话栏, 可收起/可常驻, App 级状态常驻)
 *   底部   — AfStatusBar (模型/作用域/上下文/版本)
 *
 * 导航: 点击导航项 → hash 更新 → App.tsx hashchange 重渲染 → 新 route 传入。
 */

import { api } from '../../api/client';
import { useAsync } from '../../hooks/useAsync';
import type { ParsedRoute } from '../../router';
import { AfProjectCard } from './AfProjectCard';
import { AfCompanyHome } from '../../pages/workspace/AfCompanyHome';
import { AfEmptyState, AfErrorState, AfLoadingState } from './AfState';
import { AfModulePlaceholder } from './AfModulePlaceholder';
import { AfHeader } from './AfHeader';
import { AfSidebar, WORKSPACE_NAV_ITEMS } from './AfSidebar';
import { AfWorkspaceFrame, type AfWorkspaceFrameHandlers } from './AfWorkspaceFrame';
import './af.css';

/** Workspace 子页人话标签 (对齐 WORKSPACE_ROUTES; Header 子页标签用)。 */
const WORKSPACE_PAGE_LABELS: Record<string, string> = {
  dashboard: '工作台',
  projects: '项目',
  team: 'AI 团队',
  workflows: '工作流中心',
  runtime: '运行时',
  audit: '审计',
  settings: '设置',
  manage: '项目管理',
};

/**
 * 项目列表页 (GET /api/dashboard → 项目卡网格)。
 * 四态复用 AfState (AI OS 深色): AfLoadingState / AfErrorState / AfEmptyState。
 */
function AfProjectListView(): JSX.Element {
  const { data, error, loading } = useAsync(() => api.dashboard(), []);
  const projects = data?.projects ?? [];
  const showList = !loading && error == null && data != null && projects.length > 0;
  const showEmpty = !loading && error == null && data != null && projects.length === 0;

  const openProject = (id: string) => {
    window.location.hash = `#/project/${encodeURIComponent(id)}`;
  };

  return (
    <section>
      <h2 className="af-section-title">项目列表</h2>
      {loading ? <AfLoadingState label="正在加载工作台数据…" /> : null}
      {error != null ? <AfErrorState message={`工作台数据加载失败: ${error}`} /> : null}
      {showEmpty ? <AfEmptyState message="暂无项目 — 输入想法创建一个" /> : null}
      {showList ? (
        <div className="af-project-grid">
          {projects.map((project) => (
            <AfProjectCard key={project.id} project={project} onOpen={openProject} />
          ))}
        </div>
      ) : null}
    </section>
  );
}

import { AfProjectManage } from '../../pages/workspace/AfProjectManage';
import { AfSettings } from '../../pages/workspace/AfSettings';

function WorkspacePage({ route }: { route: ParsedRoute }): JSX.Element {
  if (route.page === 'dashboard') {
    return <AfCompanyHome />;
  }
  if (route.page === 'projects') {
    return <AfProjectListView />;
  }
  if (route.page === 'manage') {
    return <AfProjectManage />;
  }
  if (route.page === 'settings') {
    return <AfSettings />;
  }
  const navItem = WORKSPACE_NAV_ITEMS.find((item) => item.page === route.page);
  return <AfModulePlaceholder pageLabel={navItem?.label ?? route.page} />;
}

export interface AfWorkspaceShellProps {
  route: ParsedRoute;
}

/** AI OS Workspace 三栏壳 (根节点保留 af-workspace-entry testid — 入口兼容)。 */
export function AfWorkspaceShell({ route }: AfWorkspaceShellProps): JSX.Element {
  const pageLabel = WORKSPACE_PAGE_LABELS[route.page] ?? route.page;

  const renderHeader = ({ collapsed, onToggleSidebar }: AfWorkspaceFrameHandlers) => (
    <AfHeader pageLabel={pageLabel} collapsed={collapsed} onToggleSidebar={onToggleSidebar} />
  );

  return (
    <AfWorkspaceFrame
      testId="af-workspace-entry"
      pageLabel={pageLabel}
      scopeLabel="公司 · 我的公司"
      header={renderHeader}
      sidebar={(collapsed) => <AfSidebar activePage={route.page} collapsed={collapsed} />}
      main={<WorkspacePage route={route} />}
    />
  );
}
