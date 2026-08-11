/**
 * pages/workspace/AfWorkspaceEntry.tsx — AI Factory 工作台真实入口 (S10-014 Task 002b)。
 *
 * #/workspace (dashboard) 与 #/workspace/* 打开后渲染真实 Workspace 数据:
 *   Browser → Router → Frontend API Adapter (api.dashboard) → Backend GET /api/dashboard
 *   → 真实项目列表 → 项目卡 (name/lifecycle/workflow/progress/stage_counts)。
 *
 * 四态 (复用 State.tsx): LoadingState / 成功列表 / EmptyState / ErrorState。
 * 点击项目卡 → #/project/{id} (真实路由, hash 导航)。
 */

import { api } from '../../api/client';
import { AfBrandHeader } from '../../components/af/AfBrandHeader';
import { AfProjectCard } from '../../components/af/AfProjectCard';
import { ErrorState, EmptyState, LoadingState } from '../../components/State';
import { useAsync } from '../../hooks/useAsync';
import type { ParsedRoute } from '../../router';
import '../../components/af/af.css';

/** Workspace 子页人话标签 (路由表 WORKSPACE_ROUTES 对齐)。 */
const WORKSPACE_PAGE_LABELS: Record<string, string> = {
  dashboard: '工作台',
  projects: '项目',
  team: 'AI 团队',
  workflows: '工作流中心',
  runtime: '运行时',
  audit: '审计',
  settings: '设置',
};

export function AfWorkspaceEntry({ route }: { route: ParsedRoute }): JSX.Element {
  const { data, error, loading } = useAsync(() => api.dashboard(), []);
  const subpageLabel = WORKSPACE_PAGE_LABELS[route.page] ?? route.page;

  const openProject = (id: string) => {
    // hash 路由跳转 (App.tsx hashchange 监听 → 重渲染 → 项目入口)
    window.location.hash = `#/project/${encodeURIComponent(id)}`;
  };

  const projects = data?.projects ?? [];
  const showList = !loading && error == null && data != null && projects.length > 0;
  const showEmpty = !loading && error == null && data != null && projects.length === 0;

  return (
    <div className="af-shell" data-testid="af-workspace-entry">
      <AfBrandHeader contextLabel={subpageLabel} />
      <main className="af-main">
        <h2 className="af-section-title">项目列表</h2>
        {loading ? <LoadingState label="正在加载工作台数据…" /> : null}
        {error != null ? <ErrorState message={`工作台数据加载失败: ${error}`} /> : null}
        {showEmpty ? <EmptyState message="暂无项目 — 输入想法创建一个" /> : null}
        {showList ? (
          <div className="af-project-grid">
            {projects.map((project) => (
              <AfProjectCard key={project.id} project={project} onOpen={openProject} />
            ))}
          </div>
        ) : null}
      </main>
    </div>
  );
}
