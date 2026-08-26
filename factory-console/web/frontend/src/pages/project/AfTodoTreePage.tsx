/**
 * pages/project/AfTodoTreePage.tsx — Todo Tree 页面 (S10-015 Task 003)。
 *
 * 真实数据流 (禁止 mock 冒充):
 *   GET /api/projects/{id}/backlog (真实后端 8011, fetch 直连 + ApiError 语义)
 *   → toTodoTree(backlog, projectName) (Domain Adapter, S10-015 Task 002 重构)
 *   → AfTodoTree (阶段 → 模块 → 任务树 + 6 态徽标 + 优先级 + 折叠/过滤)
 *
 * 四态 (S10-015 §3.5 降级 + 任务要求):
 *   Loading  → AfLoadingState ("正在加载任务树…")
 *   Error    → AfErrorState (明确文案 + [重试] 重新拉取; 404/500/网络异常)
 *   Empty    → AfEmptyState ("暂无任务 — AI 正在规划"; backlog 无任务节点)
 *   Success  → AfTodoTree (真实树)
 *
 * taskMeta: backlog.tasks 真实字段投影 {id → {priority, owner}} — Adapter
 *   (S10-015 Task 002) 未映射 priority/assignee 到 TreeNode, 页面级补充供
 *   树节点渲染优先级标签与负责人; 全部来自真实响应, 无 mock。
 *
 * projectName: 可选 (Shell 传入项目名 → 树根标题); 缺省 '项目' 兜底 (§6.3)。
 */

import { useState } from 'react';
import { ApiError, api } from '../../api/client';
import { AfTodoTree, type TaskMeta } from '../../components/af/AfTodoTree';
import { AfTaskDetailPanel, type TaskPatch } from '../../components/af/AfTaskDetailPanel';
import { toTaskDetail, toTodoTree } from '../../api/domain';
import { AfEmptyState, AfErrorState, AfLoadingState } from '../../components/af/AfState';
import { useAsync } from '../../hooks/useAsync';
import type { BacklogResponse, BacklogTask } from '../../models/domain';

/** GET /api/projects/{id}/backlog (真实 fetch; 失败 → ApiError, 与 client 同语义)。 */
export async function fetchProjectBacklog(projectId: string): Promise<BacklogResponse> {
  const path = `/api/projects/${encodeURIComponent(projectId)}/backlog`;
  const res = await fetch(path, { headers: { Accept: 'application/json' } });
  if (!res.ok) {
    throw new ApiError(path, res.status);
  }
  return (await res.json()) as BacklogResponse;
}

/** backlog.tasks → {id → {priority, owner}} (assignee 空串 → owner undefined, 诚实降级)。 */
export function buildTaskMeta(tasks: BacklogTask[] | null | undefined): Record<string, TaskMeta> {
  const meta: Record<string, TaskMeta> = {};
  for (const task of tasks ?? []) {
    if (task?.id == null || task.id.length === 0) continue;
    meta[task.id] = {
      priority: task.priority != null && task.priority.length > 0 ? task.priority : undefined,
      owner: task.assignee != null && task.assignee.length > 0 ? task.assignee : undefined,
    };
  }
  return meta;
}

export interface AfTodoTreePageProps {
  /** 项目 id (路由解析; 真实 GET /api/projects/{id}/backlog)。 */
  projectId: string;
  /** 项目名 (Shell 传入 → 树根标题; 缺省 '项目')。 */
  projectName?: string;
}

export function AfTodoTreePage({ projectId, projectName }: AfTodoTreePageProps): JSX.Element {
  const [retryTick, setRetryTick] = useState(0);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  const { data, error, loading } = useAsync(
    async () => {
      const backlog = await fetchProjectBacklog(projectId);
      return {
        backlog,
        tree: toTodoTree(backlog, projectName),
        meta: buildTaskMeta(backlog.tasks),
      };
    },
    [projectId, projectName, retryTick],
  );

  /** W-3: 任务更新 (PATCH 真实后端 + 刷新; statusPath 按受控状态机逐布 PATCH)。
   *  失败 → 抛错 (面板展示诚实错误; 状态机拒绝/依赖未满足 → 后端 400/409)。 */
  async function handleUpdateTask(changes: TaskPatch, taskId: string): Promise<void> {
    const { statusPath, ...patch } = changes;
    if (statusPath != null && statusPath.length > 0) {
      for (const status of statusPath) {
        await api.updateBacklogTask(projectId, taskId, { status });
      }
    } else if (Object.keys(patch).length > 0) {
      await api.updateBacklogTask(projectId, taskId, patch);
    }
    setRetryTick((tick) => tick + 1);
  }

  if (loading) {
    return <AfLoadingState label="正在加载任务树…" />;
  }
  if (error != null) {
    return <AfErrorState message={`任务树加载失败: ${error}`} onRetry={() => setRetryTick((t) => t + 1)} />;
  }
  // Success: 树交给 AfTodoTree (空树由组件内 AfEmptyState 兜底, 禁空白);
  // 点击任务 → toTaskDetail (真实 backlog 定位 + Epic/Feature/Story 关联) → AfTaskDetailPanel (闭环)
  const backlog = data?.backlog ?? null;
  const selectedDetail =
    backlog != null && selectedTaskId != null ? toTaskDetail(backlog, selectedTaskId) : null;
  return (
    <div className="af-todo-tree-page" data-testid="af-todo-tree-page">
      {data != null ? (
        <div className="af-todo-tree-layout">
          <div className="af-todo-tree-main">
            <AfTodoTree
              tree={data.tree}
              taskMeta={data.meta}
              onSelectTask={setSelectedTaskId}
            />
          </div>
          {selectedDetail != null ? (
            <aside className="af-context-panel" data-testid="af-todo-tree-detail">
              <AfTaskDetailPanel
                task={selectedDetail}
                onClose={() => setSelectedTaskId(null)}
                onUpdate={handleUpdateTask}
              />
            </aside>
          ) : null}
        </div>
      ) : (
        <AfEmptyState message="暂无任务 — AI 正在规划" />
      )}
    </div>
  );
}
