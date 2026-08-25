/**
 * components/af/AfWorkspaceShell.tsx — AI OS Workspace 三栏壳 (S10-014 Task 004)。
 *
 * 依据 (唯一): S10-014-plan §3.1 (Workspace 级 7 导航) + §4 (Design System)
 * + AF-UI-Architecture §2.4 (三栏: Sidebar 240px 可折叠 / Main flex /
 * Context Panel 320px 可隐藏)。
 *
 * 结构:
 *   Header   — ◆ AI Factory 品牌 + 子页标签 + LLM 状态点 + [进入 Human Console] + 折叠按钮
 *   Sidebar  — 7 导航项 (图标+文字, 激活态主色左边框 3px), 240px 可折叠 64px (localStorage 持久)
 *   Main     — 页面分发: dashboard/projects → 真实项目列表 (GET /api/dashboard, 四态);
 *              team/workflows/runtime/audit/settings → AfModulePlaceholder (禁空白)
 *   Context  — 右侧情境面板 (320px, 预留 — Task 005+ 接入)
 *
 * 导航: 点击导航项 → hash 更新 → App.tsx hashchange 重渲染 → 新 route 传入 → 激活态/页面刷新。
 * 折叠: 状态持久 localStorage (af.sidebar.collapsed), 环境无 localStorage 时退化为内存态。
 */

import { useState } from 'react';
import { api } from '../../api/client';
import { useAsync } from '../../hooks/useAsync';
import type { ParsedRoute } from '../../router';
import { AfProjectCard } from './AfProjectCard';
import { AfDashboard } from './AfDashboard';
import { AfEmptyState, AfErrorState, AfLoadingState } from './AfState';
import { AfModulePlaceholder } from './AfModulePlaceholder';
import { AfHeader } from './AfHeader';
import { AfSidebar, WORKSPACE_NAV_ITEMS } from './AfSidebar';
import { AfPreviewWindow } from './AfPreviewWindow';
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
};

/** 侧栏折叠持久化 key。 */
export const SIDEBAR_COLLAPSED_KEY = 'af.sidebar.collapsed';

function readSidebarCollapsed(): boolean {
  try {
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1';
  } catch {
    return false; // jsdom/隐私模式无 localStorage → 内存态
  }
}

function writeSidebarCollapsed(collapsed: boolean): void {
  try {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? '1' : '0');
  } catch {
    // 仅内存态, 不阻塞 UI
  }
}

/**
 * Dashboard/Projects 页: 真实项目列表 (GET /api/dashboard → 项目卡网格)。
 * 四态复用 AfState (AI OS 深色): AfLoadingState / AfErrorState / AfEmptyState。
 * 点击项目卡 → #/project/{id} (hash 路由)。
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

/** Main 页面分发 (S10-015 Task 006): dashboard → Control Center (AfDashboard 6 模块);
 * projects → 项目列表 (保留); 其余 5 页 → AfModulePlaceholder (禁空白)。 */
import { AfProjectManage } from '../../pages/workspace/AfProjectManage';

function WorkspacePage({ route }: { route: ParsedRoute }): JSX.Element {
  if (route.page === 'dashboard') {
    return <AfDashboard />;
  }
  if (route.page === 'projects') {
    return <AfProjectListView />;
  }
  if (route.page === 'manage') {
    return <AfProjectManage />;
  }
  const navItem = WORKSPACE_NAV_ITEMS.find((item) => item.page === route.page);
  return <AfModulePlaceholder pageLabel={navItem?.label ?? route.page} />;
}

export interface AfWorkspaceShellProps {
  route: ParsedRoute;
}

/** AI OS Workspace 三栏壳 (根节点保留 af-workspace-entry testid — 入口兼容)。 */
export function AfWorkspaceShell({ route }: AfWorkspaceShellProps): JSX.Element {
  const [collapsed, setCollapsed] = useState<boolean>(readSidebarCollapsed);
  const [composerText, setComposerText] = useState<string>('');

  const toggleSidebar = () => {
    setCollapsed((prev) => {
      writeSidebarCollapsed(!prev);
      return !prev;
    });
  };

  const pageLabel = WORKSPACE_PAGE_LABELS[route.page] ?? route.page;

  const [composerMsg, setComposerMsg] = useState<string>('');
  const [creating, setCreating] = useState<boolean>(false);

  const submitComposer = () => {
    const text = composerText.trim();
    if (!text) return;
    // K-7b 分域: workspace = 全局。创建意图 → 真实创建项目; 通用对话 → 诚实占位。
    const creationHint = /(做|创建|开发|我想|给我做个)/.test(text);
    if (creationHint) {
      setCreating(true);
      setComposerMsg('');
      api
        .createProject(text)
        .then((created) => {
          setComposerText('');
          window.location.hash = `#/project/${created.project_id}`;
        })
        .catch((err) => {
          setComposerMsg(`创建失败: ${String(err)}`);
        })
        .finally(() => setCreating(false));
      return;
    }
    setComposerMsg('（全局对话：输入产品想法即可创建项目；通用 AI 会话后端待接）');
    setComposerText('');
  };

  return (
    <div
      className={`af-shell af-workspace-shell${collapsed ? ' af-shell--sidebar-collapsed' : ''}`}
      data-testid="af-workspace-entry"
    >
      <AfHeader pageLabel={pageLabel} collapsed={collapsed} onToggleSidebar={toggleSidebar} />
      <div className="af-shell-body">
        <AfSidebar activePage={route.page} collapsed={collapsed} />
        <main className="af-main-content" data-testid="af-main-content">
          <WorkspacePage route={route} />
        </main>
        {/* K-7b: 右栏 = 预览窗口 (类浏览器, 独立收起/展开, 默认展开) */}
        <AfPreviewWindow />
      </div>
      <footer className="af-composer" data-testid="af-composer">
        <span className="af-composer-scope" data-testid="af-composer-scope">
          全局（我的公司）
        </span>
        <input
          className="af-composer-input"
          placeholder="我想做一个记账App / 继续聊…"
          aria-label="对话输入"
          value={composerText}
          onChange={(e) => setComposerText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submitComposer();
          }}
        />
        <button type="button" className="af-composer-send" onClick={submitComposer} disabled={creating}>
          {creating ? '创建中…' : '发送'}
        </button>
        {composerMsg ? <span className="af-composer-msg">{composerMsg}</span> : null}
      </footer>
    </div>
  );
}
