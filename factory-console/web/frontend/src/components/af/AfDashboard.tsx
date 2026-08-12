/**
 * components/af/AfDashboard.tsx — AI 软件公司 Control Center (S10-015 Task 006)。
 *
 * 依据 (唯一): docs/design/AF-UI-Architecture.md §7 (Dashboard 设计) + 用户 Task 006
 * 设计约束 (Control Center, 非项目管理统计页)。
 *
 * 6 模块 (用户指定, 全部真实数据驱动):
 *   ① Active Projects        复用 AfProjectCard (真实项目 + workflow 状态); 无 → 空态引导
 *   ② Running AI Employees   Agent 卡 (名称/当前任务/Workflow Stage/状态); 无 → 暂无执行中 AI 员工
 *   ③ Workflow Status        真实 workflow 实例阶段链 (项目名 + 状态 + 当前阶段 + 阶段链);
 *                             无实例 → 暂无工作流运行 (不编造)
 *   ④ Blocked Tasks          任务名/阻塞原因/负责人 Agent/下一步; 无 → 暂无阻塞任务
 *   ⑤ Recent Runtime Events  复用 AfTimeline (最近 N 条, 倒序); 无 → 暂无活动
 *   ⑥ Quality Summary        Tests/Quality Gate/Build (cost/approvals/experience);
 *                             后端无数据 → Unavailable (不编造)
 *
 * 数据流 (禁止 mock 冒充):
 *   GET /api/dashboard (七域) + 每项目 GET /api/projects/{id}/workflow|timeline|backlog
 *   (Promise.allSettled 风格, 单项目失败 → null 诚实降级, 不阻塞整页)
 *   → toDashboardViewModel (Dashboard Adapter — UI 不直接依赖 API DTO)
 *   → 6 模块渲染。
 *
 * 诚实降级 (§6.3): 任何数据缺失 → 空态/Unavailable; 点击项目/工作流/阻塞任务 → 跳转现有路由。
 */

import { useState } from 'react';
import { api } from '../../api/client';
import { toDashboardViewModel, toDomainStatus } from '../../api/domain';
import type { ConsoleDashboard, ProjectSummary, TimelineEventSummary, WorkflowDetail } from '../../models/types';
import type { BacklogResponse, DashboardViewModel, RuntimeActivity } from '../../models/domain';
import { useAsync } from '../../hooks/useAsync';
import { fetchProjectBacklog } from '../../pages/project/AfTodoTreePage';
import { AfProjectCard } from './AfProjectCard';
import { AfStatusBadge } from './AfStatusBadge';
import { AfTimeline, type AfTimelineItem } from './AfTimeline';
import { AfEmptyState, AfErrorState, AfLoadingState } from './AfState';
import './af.css';

interface DashboardData {
  /** 原始 dashboard (模块① AfProjectCard 需要 ProjectSummary 契约: workflow 状态/阶段/芯片)。 */
  raw: ConsoleDashboard;
  /** Adapter 视图模型 (模块②-⑥)。 */
  viewModel: DashboardViewModel;
}

/** 每项目加载器: 单项目失败 → null (诚实降级, 不阻塞整页)。 */
async function loadPerProject<T>(
  projects: ProjectSummary[],
  loader: (project: ProjectSummary) => Promise<T>,
): Promise<Record<string, T | null>> {
  const entries = await Promise.all(
    projects.map(async (project) => {
      const value = await loader(project).catch(() => null);
      return [project.id, value] as const;
    }),
  );
  return Object.fromEntries(entries);
}

/** 真实数据聚合: dashboard 七域 + 每项目 workflow/timeline/backlog → Adapter。 */
async function loadDashboard(): Promise<DashboardData> {
  const raw = await api.dashboard();
  const projects = raw.projects ?? [];
  const [workflows, timelines, backlogs] = await Promise.all([
    loadPerProject(projects, (project) =>
      project.workflow_id != null && project.workflow_id.length > 0
        ? api.projectWorkflow(project.id)
        : Promise.resolve(null),
    ),
    loadPerProject(projects, (project) => api.projectTimeline(project.id, 50)),
    loadPerProject(projects, (project) => fetchProjectBacklog(project.id)),
  ]);
  const viewModel = toDashboardViewModel(raw, {
    workflows: workflows as Record<string, WorkflowDetail | null>,
    timelines: timelines as Record<string, TimelineEventSummary[] | null>,
    backlogs: backlogs as Record<string, BacklogResponse | null>,
  });
  return { raw, viewModel };
}

/** RuntimeActivity → AfTimelineItem (状态点色: result → DomainStatus 语义)。 */
function toTimelineItems(events: RuntimeActivity[]): AfTimelineItem[] {
  return events.map((ev) => ({
    time: ev.time,
    actor: ev.actor,
    action: ev.action,
    result: ev.result,
    status: toDomainStatus(ev.result),
  }));
}

export function AfDashboard(): JSX.Element {
  const [retryTick, setRetryTick] = useState(0);
  const { data, error, loading } = useAsync(() => loadDashboard(), [retryTick]);

  if (loading) {
    return <AfLoadingState label="正在加载控制中心…" />;
  }
  if (error != null) {
    return (
      <AfErrorState
        message={`控制中心加载失败: ${error}`}
        onRetry={() => setRetryTick((tick) => tick + 1)}
      />
    );
  }
  if (data == null) {
    return <AfErrorState message="控制中心数据不可用" onRetry={() => setRetryTick((tick) => tick + 1)} />;
  }

  const { raw, viewModel } = data;
  const openProject = (id: string) => {
    window.location.hash = `#/project/${encodeURIComponent(id)}`;
  };
  const openWorkflow = (id: string) => {
    window.location.hash = `#/project/${encodeURIComponent(id)}/workflow`;
  };
  const openTodo = (id: string) => {
    if (id == null || id.length === 0) return;
    window.location.hash = `#/project/${encodeURIComponent(id)}/todo`;
  };

  return (
    <div className="af-dashboard" data-testid="af-dashboard">
      <header className="af-dashboard-head">
        <h2 className="af-section-title">AI 软件公司控制中心</h2>
        <p className="af-dashboard-sub">我的 AI 软件公司现在怎么样? — 全部来自真实后端数据</p>
      </header>
      <div className="af-dashboard-grid">
        {/* ① Active Projects — 复用 AfProjectCard (真实 ProjectSummary: workflow 状态/阶段/芯片) */}
        <section className="af-dash-module" data-testid="af-dash-active-projects">
          <h3 className="af-dash-module-title">
            Active Projects <span className="af-dash-module-sub">我的项目</span>
          </h3>
          {raw.projects.length === 0 ? (
            <AfEmptyState message="暂无项目 — 输入想法创建一个" />
          ) : (
            <div className="af-project-grid">
              {raw.projects.map((project) => (
                <AfProjectCard key={project.id} project={project} onOpen={openProject} />
              ))}
            </div>
          )}
        </section>

        {/* ② Running AI Employees — Agent 卡 (名称/当前任务/Workflow Stage/状态) */}
        <section className="af-dash-module" data-testid="af-dash-running-agents">
          <h3 className="af-dash-module-title">
            Running AI Employees <span className="af-dash-module-sub">当前执行</span>
          </h3>
          {viewModel.runningAgents.length === 0 ? (
            <div className="af-dash-empty" data-testid="af-dash-running-empty">
              暂无执行中 AI 员工
            </div>
          ) : (
            <ul className="af-dash-agent-list">
              {viewModel.runningAgents.map((agent, idx) => (
                <li key={`${agent.agentName}-${idx}`} className="af-dash-agent" data-testid="af-dash-agent">
                  <span className="af-dash-agent-name">🤖 {agent.agentName}</span>
                  <span className="af-dash-agent-task">任务: {agent.currentTask ?? '—'}</span>
                  <span className="af-dash-agent-stage">
                    Workflow Stage: {agent.workflowStage ?? '—'}
                  </span>
                  <AfStatusBadge status={agent.status} />
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* ③ Workflow Status — 真实 workflow 实例阶段链 */}
        <section className="af-dash-module" data-testid="af-dash-workflow-status">
          <h3 className="af-dash-module-title">
            Workflow Status <span className="af-dash-module-sub">工作流状态</span>
          </h3>
          {viewModel.workflowStatus.length === 0 ? (
            <div className="af-dash-empty" data-testid="af-dash-wf-empty">
              暂无工作流运行
            </div>
          ) : (
            <ul className="af-dash-wf-list">
              {viewModel.workflowStatus.map((item) => (
                <li key={item.projectId}>
                  <button
                    type="button"
                    className="af-dash-wf-item"
                    data-testid="af-dash-wf-item"
                    onClick={() => openWorkflow(item.projectId)}
                  >
                    <div className="af-dash-wf-head">
                      <span className="af-dash-wf-name">{item.projectName}</span>
                      <AfStatusBadge status={item.status} />
                    </div>
                    {item.currentStage != null && item.currentStage.length > 0 ? (
                      <div className="af-dash-wf-stage">当前阶段: {item.currentStage}</div>
                    ) : null}
                    <ol className="af-dash-wf-chain">
                      {item.stages.map((stage, idx) => (
                        <li
                          key={stage.order}
                          className={`af-dash-wf-step${stage.status === 'running' ? ' af-dash-wf-step--active' : ''}`}
                          data-testid="af-dash-wf-step"
                        >
                          {idx > 0 ? <span className="af-dash-wf-arrow">→</span> : null}
                          <span className="af-dash-wf-step-name">{stage.name}</span>
                          <AfStatusBadge status={stage.status} />
                        </li>
                      ))}
                    </ol>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* ④ Blocked Tasks — 任务名/原因/负责人/下一步 */}
        <section className="af-dash-module" data-testid="af-dash-blocked-tasks">
          <h3 className="af-dash-module-title">
            Blocked Tasks <span className="af-dash-module-sub">阻塞任务</span>
          </h3>
          {viewModel.blockedTasks.length === 0 ? (
            <div className="af-dash-empty" data-testid="af-dash-blocked-empty">
              暂无阻塞任务
            </div>
          ) : (
            <ul className="af-dash-blocked-list">
              {viewModel.blockedTasks.map((task, idx) => (
                <li key={`${task.taskName}-${idx}`}>
                  <button
                    type="button"
                    className="af-dash-blocked-item"
                    data-testid="af-dash-blocked-item"
                    onClick={() => openTodo(task.projectId ?? '')}
                  >
                    <span className="af-dash-blocked-name">⛔ {task.taskName}</span>
                    <span className="af-dash-blocked-reason">原因: {task.reason ?? '—'}</span>
                    <span className="af-dash-blocked-owner">负责人: {task.ownerAgent ?? '—'}</span>
                    <span className="af-dash-blocked-next">下一步: {task.nextAction}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* ⑤ Recent Runtime Events — 复用 AfTimeline (最近 N 条, 倒序; 空 → 暂无活动) */}
        <section className="af-dash-module" data-testid="af-dash-recent-events">
          <h3 className="af-dash-module-title">
            Recent Runtime Events <span className="af-dash-module-sub">最近活动</span>
          </h3>
          <AfTimeline items={toTimelineItems(viewModel.recentEvents)} />
        </section>

        {/* ⑥ Quality Summary — Tests/Quality Gate/Build; 后端无数据 → Unavailable (不编造) */}
        <section className="af-dash-module" data-testid="af-dash-quality">
          <h3 className="af-dash-module-title">
            Quality Summary <span className="af-dash-module-sub">质量摘要</span>
          </h3>
          <dl className="af-dash-quality">
            <div className="af-dash-quality-row">
              <dt>Tests</dt>
              <dd data-testid="af-dash-quality-tests">
                {viewModel.qualitySummary.tests ?? 'Unavailable'}
              </dd>
            </div>
            <div className="af-dash-quality-row">
              <dt>Quality Gate</dt>
              <dd data-testid="af-dash-quality-gate">
                {viewModel.qualitySummary.qualityGate ?? 'Unavailable'}
              </dd>
            </div>
            <div className="af-dash-quality-row">
              <dt>Build</dt>
              <dd data-testid="af-dash-quality-build">
                {viewModel.qualitySummary.buildStatus ?? 'Unavailable'}
              </dd>
            </div>
          </dl>
        </section>
      </div>
    </div>
  );
}
