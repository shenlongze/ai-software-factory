/**
 * pages/project/AfWorkflowPage.tsx — Workflow Viewer 页面 (S10-015 Task 004)。
 *
 * 真实数据流 (禁止 mock 冒充):
 *   GET /api/projects/{id}/workflow + GET /api/projects/{id}/timeline 并行
 *   (Promise.all, 真实后端 8011 fetch 直连 + ApiError 语义)
 *   → toWorkflowPipeline + toRuntimeActivity (Domain Adapter, S10-015 Task 004 增强)
 *   → AfWorkflowViewer (Instance/Template/Timeline 三层 + 5 问回答 + isMock 降级)
 *
 * 四态 (S10-015 §4.5 降级 + 用户 Task 004 要求):
 *   Loading → AfLoadingState ("正在加载流程…")
 *   Error   → AfErrorState (明确文案 + [重试] 重新拉取; 404/500/网络异常)
 *   Empty   → AfEmptyState ("暂无流程运行" — stages 为空 / 未启动)
 *   Success → AfWorkflowViewer (真实流水线; is_mock=true 时 Viewer 顶部降级警告)
 *
 * projectName: 可选 (Shell 传入 → timeline 活动条目 projectName 投影)。
 */

import { useState } from 'react';
import { toRuntimeActivity, toWorkflowPipeline } from '../../api/domain';
import { ApiError } from '../../api/client';
import { AfWorkflowViewer } from '../../components/af/AfWorkflowViewer';
import { AfEmptyState, AfErrorState, AfLoadingState } from '../../components/af/AfState';
import { useAsync } from '../../hooks/useAsync';
import type { TimelineEventSummary, WorkflowDetail } from '../../models/types';

/** GET workflow + timeline 并行 (任一失败 → ApiError; 页面级真实数据源)。 */
export async function fetchWorkflowView(projectId: string): Promise<{
  workflow: WorkflowDetail;
  timeline: TimelineEventSummary[];
}> {
  const base = `/api/projects/${encodeURIComponent(projectId)}`;
  const headers = { Accept: 'application/json' };
  const [workflowRes, timelineRes] = await Promise.all([
    fetch(`${base}/workflow`, { headers }),
    fetch(`${base}/timeline?limit=200`, { headers }),
  ]);
  if (!workflowRes.ok) throw new ApiError(`${base}/workflow`, workflowRes.status);
  if (!timelineRes.ok) throw new ApiError(`${base}/timeline`, timelineRes.status);
  const [workflow, timelineRaw] = await Promise.all([
    workflowRes.json() as Promise<WorkflowDetail>,
    timelineRes.json() as Promise<{ items?: TimelineEventSummary[] } | TimelineEventSummary[]>,
  ]);
  // API 规范 v1: 集合 {items, count}
  const timeline = Array.isArray(timelineRaw) ? timelineRaw : (timelineRaw.items ?? []);
  return { workflow, timeline };
}

export interface AfWorkflowPageProps {
  /** 项目 id (路由解析; 真实 GET /api/projects/{id}/workflow + /timeline)。 */
  projectId: string;
  /** 项目名 (Shell 传入 → timeline 活动条目 projectName; 可选)。 */
  projectName?: string;
}

export function AfWorkflowPage({ projectId, projectName }: AfWorkflowPageProps): JSX.Element {
  const [retryTick, setRetryTick] = useState(0);

  const { data, error, loading } = useAsync(
    async () => {
      const view = await fetchWorkflowView(projectId);
      return {
        pipeline: toWorkflowPipeline(undefined, view.workflow),
        timeline: toRuntimeActivity(view.timeline, projectName),
      };
    },
    [projectId, projectName, retryTick],
  );

  if (loading) {
    return <AfLoadingState label="正在加载流程…" />;
  }
  if (error != null) {
    return (
      <AfErrorState message={`流程加载失败: ${error}`} onRetry={() => setRetryTick((t) => t + 1)} />
    );
  }
  // Empty: 无阶段 (未启动/后端无流程) → 诚实空态
  if (data == null || data.pipeline.stages.length === 0) {
    return (
      <AfEmptyState
        message="暂无流程运行"
        hint="项目启动工作流后, 将在此展示真实流水线 (运行流程/设计流程/历史)"
      />
    );
  }
  // Success: 真实流水线交给 Viewer (isMock 降级/三层/5 问由 Viewer 负责)
  return (
    <div className="af-workflow-page" data-testid="af-workflow-page">
      <AfWorkflowViewer pipeline={data.pipeline} timeline={data.timeline} />
    </div>
  );
}
