/**
 * pages/project/AfQualityGatePage.tsx — Quality Gate 页面 (S10-015 Task 007)。
 *
 * 真实数据流 (禁止 mock 冒充/编造质量结果):
 *   GET /api/approvals (全局审批门) + GET /api/projects/{id}/workflow (阶段状态)
 *   + GET /api/projects/{id}/timeline (质量事件) 并行
 *   (单端点失败 → null 诚实降级, 不阻塞整页 — 与 AfDashboard loadPerProject 同策略)
 *   → toQualityGateViewModel (Domain Adapter, 组合真实数据)
 *   → AfQualityGate (5 模块: Current Gate / Required Checks / Quality Decision /
 *     Human Approval / Decision History)
 *
 * 四态: Loading → AfLoadingState; Error → AfErrorState (重试); 其余 → AfQualityGate
 * (viewModel 内部诚实降级: 无审批 → Unavailable/Not available, 不编造)。
 */

import { useState } from 'react';
import { api } from '../../api/client';
import { toQualityGateViewModel } from '../../api/domain';
import { AfQualityGate } from '../../components/af/AfQualityGate';
import { AfEmptyState, AfErrorState, AfLoadingState } from '../../components/af/AfState';
import { useAsync } from '../../hooks/useAsync';
import type { QualityGateViewModel } from '../../models/domain';

/** 真实数据聚合: approvals + workflow + timeline → QualityGateViewModel。
 * 单端点失败 → null (诚实降级; 例如无 workflow 的项目 → 阶段检查 unavailable)。 */
export async function fetchQualityGateView(projectId: string): Promise<QualityGateViewModel> {
  const [approvals, workflow, timeline] = await Promise.all([
    api.approvals().catch(() => null),
    api.projectWorkflow(projectId).catch(() => null),
    api.projectTimeline(projectId, 200).catch(() => null),
  ]);
  return toQualityGateViewModel({ approvals, workflow, timeline });
}

export interface AfQualityGatePageProps {
  /** 项目 id (路由解析; 真实 GET /api/projects/{id}/workflow + /timeline)。 */
  projectId: string;
}

export function AfQualityGatePage({ projectId }: AfQualityGatePageProps): JSX.Element {
  const [retryTick, setRetryTick] = useState(0);

  const { data, error, loading } = useAsync(
    () => fetchQualityGateView(projectId),
    [projectId, retryTick],
  );

  if (loading) {
    return <AfLoadingState label="正在加载质量门…" />;
  }
  if (error != null) {
    return (
      <AfErrorState message={`质量门加载失败: ${error}`} onRetry={() => setRetryTick((t) => t + 1)} />
    );
  }
  if (data == null) {
    return <AfEmptyState message="质量门数据不可用" />;
  }
  return (
    <div className="af-quality-page" data-testid="af-quality-page">
      <AfQualityGate viewModel={data} />
    </div>
  );
}
