/**
 * pages/project/AfRuntimePage.tsx — Runtime Timeline 页面 (S10-015 Task 005b)。
 *
 * 真实数据流 (禁止 mock 冒充/前端自行生成状态):
 *   GET /api/projects/{id}/workflow + GET /api/projects/{id}/timeline 并行
 *   (Promise.all, 真实后端 8011 fetch + ApiError 语义)
 *   → toWorkflowPipeline + toRuntimeActivity (Domain Adapter, S10-015 Task 005 增强)
 *   → AfRuntimeTimeline (当前执行卡 8 项 + 事件流倒序 + 空态)
 *
 * 四态 (S10-015 §5.4 降级 + 用户 Task 005 要求):
 *   Loading → AfLoadingState ("正在加载运行状态…")
 *   Error   → AfErrorState (明确文案 + [重试] 重新拉取; 404/500/网络异常)
 *   Empty   → AfRuntimeTimeline 空态 (无 workflow + 无事件 → AfEmptyState)
 *   Success → AfRuntimeTimeline (真实失败/运行展示)
 *
 * projectName: 可选 (Shell 传入 → timeline 活动条目 projectName 投影 + 页面标题)。
 */

import { useState } from 'react';
import { toRuntimeActivity, toWorkflowPipeline } from '../../api/domain';
import { api } from '../../api/client';
import { AfRuntimeTimeline } from '../../components/af/AfRuntimeTimeline';
import { AfEmptyState, AfErrorState, AfLoadingState } from '../../components/af/AfState';
import { useAsync } from '../../hooks/useAsync';
import type { TimelineEventSummary, WorkflowDetail } from '../../models/types';

/** GET workflow + timeline 并行 (任一失败 → ApiError; 页面级真实数据源)。 */
export async function fetchRuntimeView(projectId: string): Promise<{
  workflow: WorkflowDetail;
  timeline: TimelineEventSummary[];
}> {
  const [workflow, timeline] = await Promise.all([
    api.projectWorkflow(projectId),
    api.projectTimeline(projectId, 200),
  ]);
  return { workflow, timeline };
}

export interface AfRuntimePageProps {
  /** 项目 id (路由解析; 真实 GET /api/projects/{id}/workflow + /timeline)。 */
  projectId: string;
  /** 项目名 (Shell 传入 → timeline 活动条目 projectName; 可选)。 */
  projectName?: string;
}

export function AfRuntimePage({ projectId, projectName }: AfRuntimePageProps): JSX.Element {
  const [retryTick, setRetryTick] = useState(0);

  const { data, error, loading } = useAsync(
    async () => {
      const view = await fetchRuntimeView(projectId);
      return {
        pipeline: toWorkflowPipeline(undefined, view.workflow),
        events: toRuntimeActivity(view.timeline, projectName),
      };
    },
    [projectId, projectName, retryTick],
  );

  if (loading) {
    return <AfLoadingState label="正在加载运行状态…" />;
  }
  if (error != null) {
    return (
      <AfErrorState
        message={`运行状态加载失败: ${error}`}
        onRetry={() => setRetryTick((t) => t + 1)}
      />
    );
  }
  // Success: 真实 pipeline + 事件流交给 AfRuntimeTimeline (空态由组件兜底, 禁空白)
  return (
    <div className="af-runtime-page" data-testid="af-runtime-page">
      {data != null ? (
        <AfRuntimeTimeline
          pipeline={data.pipeline}
          events={data.events}
          projectName={projectName}
        />
      ) : (
        <AfEmptyState
          message="暂无运行活动"
          hint="项目启动工作流后, 将在此展示 AI 正在做什么"
        />
      )}
    </div>
  );
}
