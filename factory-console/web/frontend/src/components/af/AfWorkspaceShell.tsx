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
import { useEffect } from 'react';
import type { ParsedRoute } from '../../router';
import { AfHeader } from './AfHeader';
import { AfContextNav } from './AfContextNav';
import { AfConversationCenter } from './AfConversationCenter';
import { AfWorkspace } from './AfWorkspace';
import { useConversation } from './ConversationContext';
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
  /** S32-004B: URL ?project= 注入的项目 Context (Refresh 恢复用)。 */
  initialProjectId?: string | null;
}
export function AfWorkspaceShell({ route, initialProjectId }: AfWorkspaceShellProps): JSX.Element {
  const { t } = useI18n();
  const ctx = useConversation();
  const pageLabel = t(`nav.workspace.${route.page}`) || (WORKSPACE_PAGE_LABELS[route.page] ?? route.page);

  // S32-004B: URL ?project= 恢复项目 Context (挂载时注入一次)
  useEffect(() => {
    if (initialProjectId && initialProjectId.length > 0 && ctx.projectId !== initialProjectId) {
      ctx.setProjectId(initialProjectId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialProjectId]);

  const renderHeader = ({ collapsed, onToggleSidebar }: AfWorkspaceFrameHandlers) => (
    <AfHeader pageLabel={pageLabel} collapsed={collapsed} onToggleSidebar={onToggleSidebar} />
  );

  // K9 Human Workspace 三栏:
  // 左 = AfContextNav (Context), 中 = AfConversationCenter (唯一主入口), 右 = AfWorkspace (AI 工作现场)
  // S32-004B: 项目点击 → Context 选择 (setProjectId), 不离开 Workbench
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
          onSelectProject={(id) => {
            if (id) {
              ctx.setProjectId(id);
              navigate(`#/workspace?project=${encodeURIComponent(id)}`);
            } else {
              ctx.setProjectId(null);
              navigate('#/workspace');
            }
          }}
          onSelectConversation={() => navigate('#/workspace')}
        />
      )}
      main={<AfConversationCenter />}
      workspace={<AfWorkspace />}
    />
  );
}
