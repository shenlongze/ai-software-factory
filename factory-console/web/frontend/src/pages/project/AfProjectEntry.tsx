/**
 * pages/project/AfProjectEntry.tsx — AI Factory 项目真实入口 (S10-014 Task 002b)。
 *
 * #/project/:id[/subpage] 读取真实 Project Entity:
 *   Browser → Router → api.projects (GET /api/projects) → 按 id 定位 → 详情
 *   (+ workflow_id 存在时 GET /api/projects/{id}/workflow 补创建时间, 失败降级)。
 *
 * 四态 (复用 State.tsx): LoadingState / 成功详情 / ErrorState (404 "项目不存在或已被删除"
 * 与 API 失败)。子页未实现 → 明确 placeholder ("{Page} module loading — 开发中")。
 */

import { api } from '../../api/client';
import {
  formatTime,
  lifecycleLabel,
  progressPercent,
  stageCountChips,
  statusLabel,
  workflowLabel,
} from '../../components/af/afLabels';
import { AfBrandHeader } from '../../components/af/AfBrandHeader';
import { AfModulePlaceholder } from '../../components/af/AfModulePlaceholder';
import { ErrorState, LoadingState } from '../../components/State';
import { useAsync } from '../../hooks/useAsync';
import type { ProjectSummary, WorkflowDetail } from '../../models/types';
import type { ParsedRoute } from '../../router';
import '../../components/af/af.css';

/** Project 子页人话标签 (路由表 PROJECT_ROUTES 对齐; 未实现子页 placeholder 用)。 */
export const PROJECT_PAGE_LABELS: Record<string, string> = {
  overview: 'Overview',
  vision: 'Vision',
  discovery: 'Discovery',
  prd: 'PRD',
  roadmap: 'Roadmap',
  backlog: 'Backlog',
  sprint: 'Sprint',
  todo: 'Todo Tree',
  workflow: 'Workflow',
  runtime: 'Runtime',
  logs: 'Logs',
};

/** 加载结果: 找到 (含可选 workflow 详情) 或 404。 */
interface ProjectView {
  kind: 'found';
  project: ProjectSummary;
  workflow: WorkflowDetail | null;
}
type LoadResult = { kind: 'notfound' } | ProjectView;

export function AfProjectEntry({ route }: { route: ParsedRoute }): JSX.Element {
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

  return (
    <div className="af-shell" data-testid="af-project-entry">
      <AfBrandHeader
        contextLabel={`项目 · ${pageLabel}`}
        trailing={
          <a className="af-back-link" href="#/workspace">
            ← 返回工作台
          </a>
        }
      />
      <main className="af-main">
        {loading ? <LoadingState label="正在加载项目…" /> : null}
        {error != null ? <ErrorState message={`项目加载失败: ${error}`} /> : null}
        {!loading && error == null && data?.kind === 'notfound' ? (
          <ErrorState message="项目不存在或已被删除" />
        ) : null}
        {!loading && error == null && data?.kind === 'found' ? (
          <ProjectDetailView
            view={data}
            pageLabel={pageLabel}
            isOverview={route.page === 'overview'}
          />
        ) : null}
      </main>
    </div>
  );
}

/** 项目详情视图 (最少: name/lifecycle/status/时间/description/workflow 状态)。 */
function ProjectDetailView({
  view,
  pageLabel,
  isOverview,
}: {
  view: ProjectView;
  pageLabel: string;
  isOverview: boolean;
}): JSX.Element {
  const { project, workflow } = view;
  const pct = progressPercent(project.progress);
  const chips = stageCountChips(project.stage_counts);
  const createdTime = workflow?.created_at ?? null;
  const lastActivity = project.last_activity ?? null;

  return (
    <div className="af-project-detail" data-testid="af-project-detail">
      <div className="af-detail-head">
        <h2 className="af-detail-name">{project.name}</h2>
        <span className="af-detail-id">{project.id}</span>
      </div>
      <div className="af-detail-badges">
        <span className="af-badge af-badge-blue">{lifecycleLabel(project)}</span>
        <span className="af-badge af-badge-gray">{statusLabel(project.status)}</span>
      </div>
      {project.description != null && project.description.length > 0 ? (
        <p className="af-detail-desc">{project.description}</p>
      ) : null}
      <div className="af-detail-grid">
        <div className="af-detail-field">
          <span className="af-detail-label">工作流</span>
          <span className="af-detail-value">{workflowLabel(project.workflow_status)}</span>
          {project.workflow_name != null && project.workflow_name.length > 0 ? (
            <span className="af-detail-sub">{project.workflow_name}</span>
          ) : null}
        </div>
        <div className="af-detail-field">
          <span className="af-detail-label">当前阶段</span>
          <span className="af-detail-value">{project.current_stage ?? '—'}</span>
          {project.current_stage_status != null && project.current_stage_status.length > 0 ? (
            <span className="af-detail-sub">状态: {statusLabel(project.current_stage_status)}</span>
          ) : null}
        </div>
        <div className="af-detail-field">
          <span className="af-detail-label">进度</span>
          <span className="af-detail-value">{pct}%</span>
        </div>
        {chips.length > 0 ? (
          <div className="af-detail-field">
            <span className="af-detail-label">阶段统计</span>
            <span className="af-detail-value">
              {chips.map((chip) => `${chip.label} ${chip.count}`).join(' · ')}
            </span>
          </div>
        ) : null}
        {createdTime != null ? (
          <div className="af-detail-field">
            <span className="af-detail-label">创建时间</span>
            <span className="af-detail-value">{formatTime(createdTime)}</span>
          </div>
        ) : null}
        {lastActivity != null ? (
          <div className="af-detail-field">
            <span className="af-detail-label">最后活动</span>
            <span className="af-detail-value">{formatTime(lastActivity)}</span>
          </div>
        ) : null}
      </div>
      <div className="af-detail-progress">
        <div className="af-progress-track">
          <div className="af-progress-fill" style={{ width: `${pct}%` }} />
        </div>
      </div>
      {isOverview ? null : <AfModulePlaceholder pageLabel={pageLabel} />}
    </div>
  );
}
