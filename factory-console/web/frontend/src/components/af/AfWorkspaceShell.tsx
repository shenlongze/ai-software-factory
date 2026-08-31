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

import { useI18n } from '../../i18n';
import type { ParsedRoute } from '../../router';
import { AfHeader } from './AfHeader';
import { AfContextNav } from './AfContextNav';
import { AfConversationCenter } from './AfConversationCenter';
import { AfWorkspace } from './AfWorkspace';
import { AfWorkspaceFrame, type AfWorkspaceFrameHandlers } from './AfWorkspaceFrame';
import './af.css';

/** Workspace 子页人话标签 (K9: Header 子页标签用)。 */
const WORKSPACE_PAGE_LABELS: Record<string, string> = {
  dashboard: '我的公司',
  projects: '项目',
  monitor: '监控',
  settings: '设置',
  manage: '项目管理',
};

export interface AfWorkspaceShellProps {
  route: ParsedRoute;
}
export function AfWorkspaceShell({ route }: AfWorkspaceShellProps): JSX.Element {
  const { t } = useI18n();
  const pageLabel = t(`nav.workspace.${route.page}`) || (WORKSPACE_PAGE_LABELS[route.page] ?? route.page);

  const renderHeader = ({ collapsed, onToggleSidebar }: AfWorkspaceFrameHandlers) => (
    <AfHeader pageLabel={pageLabel} collapsed={collapsed} onToggleSidebar={onToggleSidebar} />
  );

  // K9 Human Workspace 三栏:
  // 左 = AfContextNav (Context), 中 = AfConversationCenter (唯一主入口), 右 = AfWorkspace (AI 工作现场)
  // S32-004A: 项目/会话点击 → hash 导航 (App.tsx hashchange → 真实页面)
  const navigate = (hash: string) => {
    window.location.hash = hash;
  };
  return (
    <AfWorkspaceFrame
      testId="af-workspace-entry"
      pageLabel={pageLabel}
      scopeLabel="公司 · AI Factory"
      header={renderHeader}
      sidebar={(collapsed) => (
        <AfContextNav
          collapsed={collapsed}
          onSelectProject={(id) => navigate(id ? `#/project/${encodeURIComponent(id)}` : '#/workspace')}
          onSelectConversation={() => navigate('#/workspace')}
        />
      )}
      main={<AfConversationCenter />}
      workspace={<AfWorkspace />}
    />
  );
}
