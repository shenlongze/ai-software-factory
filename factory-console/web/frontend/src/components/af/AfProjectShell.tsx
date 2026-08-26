/**
 * components/af/AfProjectShell.tsx — AI OS 项目层壳 (S10-014 Task 005)。
 *
 * 依据 (唯一): S10-014-plan §3.1 (Project Shell 11 导航) + §2.3 (路由)
 * + AF-UI-Architecture §2.4 (布局骨架)。与 AfWorkspaceShell 同骨架 (af.css 复用)。
 *
 * 结构:
 *   Header  — ← 返回工作台 + 项目名 + lifecycle 徽标 (+ 进入 Human Console)
 *   Sidebar — 11 导航项 (Overview/Vision/Discovery/PRD/Roadmap/Backlog/Sprint/
 *             Todo Tree/Workflow/Runtime/Logs, 激活态主色左边框, 点击 → hash 路由)
 *   Main    — 页面分发: overview → 真实 Project Entity 详情 (GET /api/projects 定位,
 *             workflow_id 存在时补 GET /api/projects/{id}/workflow, 失败降级);
 *             其他 10 页 → 详情上下文 + AfModulePlaceholder (禁空白)
 *
 * 四态 (复用 State.tsx): LoadingState / 成功详情 / ErrorState (404 "项目不存在或已被删除"
 * 与 API 失败)。当前项目 id 从路由解析 (parseHash projectId), 不额外存储。
 * 导航: 点击 → hash 更新 → App.tsx hashchange 重渲染 → 新 route 传入 → 激活态/页面刷新。
 */

import { api } from '../../api/client';
import { lifecycleLabel } from './afLabels';
import { AfModulePlaceholder } from './AfModulePlaceholder';
import { AfProjectSidebar } from './AfProjectSidebar';
import { AfWorkspaceFrame, type AfWorkspaceFrameHandlers } from './AfWorkspaceFrame';
import { AfProjectHome } from '../../pages/project/AfProjectHome';
import { AfTodoTreePage } from '../../pages/project/AfTodoTreePage';
import { AfWorkflowPage } from '../../pages/project/AfWorkflowPage';
import { AfRuntimePage } from '../../pages/project/AfRuntimePage';
import { AfQualityGatePage } from '../../pages/project/AfQualityGatePage';
import { AfProjectDocs } from '../../pages/project/AfProjectDocs';
import { ErrorState, LoadingState } from '../State';
import { useAsync } from '../../hooks/useAsync';
import type { ProjectSummary, WorkflowDetail } from '../../models/types';
import type { ParsedRoute } from '../../router';
import './af.css';

/** Project 子页英文标签 (路由表 PROJECT_ROUTES 对齐; 导航/占位页共用)。 */
export const PROJECT_PAGE_LABELS: Record<string, string> = {
  overview: '概览',
  docs: '文档',
  todo: '任务',
  workflow: '执行',
  runtime: '运行时',
  quality: '质量',
};

/** 加载结果: 找到 (含可选 workflow 详情) 或 404。 */
interface ProjectView {
  kind: 'found';
  project: ProjectSummary;
  workflow: WorkflowDetail | null;
}
type LoadResult = { kind: 'notfound' } | ProjectView;

export interface AfProjectShellProps {
  route: ParsedRoute;
}

/** AI OS 项目层壳 (根节点保留 af-project-entry testid — 入口兼容)。 */
export function AfProjectShell({ route }: AfProjectShellProps): JSX.Element {
  const projectId = route.projectId ?? '';
  const pageLabel = PROJECT_PAGE_LABELS[route.page] ?? route.page;

  const { data, error, loading } = useAsync<LoadResult>(
    async () => {
      const projects = await api.projects();
      const found = projects.find((p) => p.id === projectId);
      if (found == null) return { kind: 'notfound' };
      let workflow: WorkflowDetail | null = null;
      if (found.workflow_id != null && found.workflow_id.length > 0) {
        try {
          workflow = await api.projectWorkflow(projectId);
        } catch {
          workflow = null; // 降级 (§6.3): 时间/阶段缺失不阻塞详情
        }
      }
      return { kind: 'found', project: found, workflow };
    },
    [projectId],
  );

  const project = data?.kind === 'found' ? data.project : null;

  const mainContent = loading ? (
    <LoadingState label="正在加载项目…" />
  ) : error != null ? (
    <ErrorState message={`项目加载失败: ${error}`} />
  ) : !loading && error == null && data?.kind === 'notfound' ? (
    <ErrorState message="项目不存在或已被删除" />
  ) : data?.kind === 'found' && route.page === 'overview' ? (
    <AfProjectHome projectId={projectId} projectName={project?.name ?? projectId} />
  ) : data?.kind === 'found' ? (
    <AfProjectSubPage page={route.page} projectId={projectId} projectName={project?.name ?? projectId} />
  ) : null;

  const renderHeader = ({ collapsed, onToggleSidebar }: AfWorkspaceFrameHandlers) => (
    <AfProjectHeader
      project={project}
      pageLabel={pageLabel}
      collapsed={collapsed}
      onToggleSidebar={onToggleSidebar}
    />
  );

  return (
    <AfWorkspaceFrame
      testId="af-project-entry"
      pageLabel={pageLabel}
      projectId={projectId}
      projectName={project?.name ?? projectId}
      scopeLabel={`项目 · ${project?.name ?? projectId}`}
      header={renderHeader}
      sidebar={() => <AfProjectSidebar projectId={projectId} activePage={route.page} />}
      main={mainContent}
    />
  );
}

export interface AfProjectHeaderProps {
  /** 已定位的项目 (加载中/404 → null, 显示子页标签兜底)。 */
  project: ProjectSummary | null;
  /** 当前子页英文标签 (未定位时的兜底显示)。 */
  pageLabel: string;
  /** A 列折叠态 (K-7d: 可选 — 折叠按钮)。 */
  collapsed?: boolean;
  /** 点击折叠按钮 → 切换侧栏折叠态。 */
  onToggleSidebar?: () => void;
}

/** Project Header: ← 返回工作台 + 项目名 + lifecycle 徽标 + 折叠按钮 (+ 进入 Human Console)。 */
export function AfProjectHeader({ project, pageLabel, collapsed, onToggleSidebar }: AfProjectHeaderProps): JSX.Element {
  return (
    <header className="af-header af-project-header" data-testid="af-project-header">
      <a className="af-back-link" href="#/workspace" data-testid="af-project-back-link">
        ← 返回工作台
      </a>
      {project != null ? (
        <>
          <span
            className="af-project-header-name"
            data-testid="af-project-header-name"
            title={project.id}
          >
            {project.name}
          </span>
          <span
            className="af-badge af-badge-blue af-project-header-lifecycle"
            data-testid="af-project-header-lifecycle"
          >
            {lifecycleLabel(project)}
          </span>
        </>
      ) : (
        <span className="af-subpage-label" data-testid="af-project-header-page">
          {pageLabel}
        </span>
      )}
      <span className="af-header-spacer" />
      {onToggleSidebar != null ? (
        <button
          type="button"
          className="af-collapse-btn"
          aria-label={collapsed ? '展开侧栏' : '折叠侧栏'}
          onClick={onToggleSidebar}
        >
          {collapsed ? '»' : '«'}
        </button>
      ) : null}
      <a className="af-console-link" href="#/" title="切换到 Human Console (只读控制台)">
        进入 Human Console
      </a>
    </header>
  );
}

/** 项目详情视图 (最少: name/lifecycle/status/时间/description/workflow 状态; 子页附加占位)。 */
function AfProjectSubPage({
  page,
  projectId,
  projectName,
}: {
  page: string;
  projectId?: string;
  projectName?: string;
}): JSX.Element {
  if (page === 'todo' && projectId != null) {
    return <AfTodoTreePage projectId={projectId} projectName={projectName ?? ''} />;
  }
  if (page === 'workflow' && projectId != null) {
    return <AfWorkflowPage projectId={projectId} projectName={projectName ?? ''} />;
  }
  if (page === 'runtime' && projectId != null) {
    return <AfRuntimePage projectId={projectId} projectName={projectName ?? ''} />;
  }
  if (page === 'quality' && projectId != null) {
    return <AfQualityGatePage projectId={projectId} />;
  }
  if (page === 'docs' && projectId != null) {
    return <AfProjectDocs projectId={projectId} projectName={projectName ?? ''} />;
  }
  return <AfModulePlaceholder pageLabel={page} />;
}
