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
import { useConversation } from '../../components/af/ConversationContext';
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

/** 战役任务链 (Founder 2026-08-27): 同一任务链 = S/T/U/V/X 系列, 非按 P0 优先级。 */
export const CAMPAIGN_CHAINS: readonly string[] = ['S', 'T', 'U', 'V', 'X'];

/** 任务链进度摘要 (Founder 2026-08-27): 按系列逐链展示同一任务链上的任务。
 *  每行 = 一条任务链 (S/T/U/V/X) 自己的 done ✅ + 剩余, 不混其他分类 (C/D/E/F/G/H/I/J/L/W), 也不按 P0 筛。 */
export function buildChainLines(backlog: BacklogResponse | null | undefined): string[] {
  const tasks = backlog?.tasks ?? [];
  const label = (t: BacklogTask) => {
    const m = /\[([A-Z]-\d+)\]/.exec(t.description ?? '');
    return m ? m[1] : '';
  };
  const groups = new Map<string, { total: number; done: string[]; remain: string[] }>();
  for (const t of tasks) {
    const id = label(t);
    if (id.length === 0) continue;
    const chain = id[0];
    if (!CAMPAIGN_CHAINS.includes(chain)) continue;
    const g = groups.get(chain) ?? { total: 0, done: [], remain: [] };
    g.total += 1;
    ((t.status ?? '') === 'done' ? g.done : g.remain).push(id);
    groups.set(chain, g);
  }
  if (groups.size === 0) return [];
  const byNum = (a: string, b: string) => {
    const na = Number(a.split('-')[1] ?? 0);
    const nb = Number(b.split('-')[1] ?? 0);
    return na - nb;
  };
  return CAMPAIGN_CHAINS.filter((c) => groups.has(c)).map((chain) => {
    const g = groups.get(chain)!;
    g.done.sort(byNum);
    g.remain.sort(byNum);
    const doneStr = g.done.length > 0 ? g.done.map((x) => `${x}✅`).join(' ') : '';
    const remainStr =
      g.remain.length > 0
        ? `剩 ${g.remain.slice(0, 8).join('·')}${g.remain.length > 8 ? ` 等${g.remain.length}个` : ''}`
        : '全部完成 🎉';
    return `${chain} 链 ${g.done.length}/${g.total}: ${[doneStr, remainStr].filter(Boolean).join(' → ')}`;
  });
}

/** 兼容旧签名: 多行拼接 (组件改用 buildChainLines 逐行渲染)。 */
export function buildChainProgress(backlog: BacklogResponse | null | undefined): string {
  return buildChainLines(backlog).join('\n');
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
  const chat = useConversation();

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

  /** 想法→细化→待办链路: 新建想法模块 (maturity=idea, 挂第一个 Epic; 无 Epic → 提示)。 */
  async function handleCreateFeature(): Promise<void> {
    const name = window.prompt('新建模块 (想法): 输入模块名', '');
    const title = (name ?? '').trim();
    if (title.length === 0) return;
    const backlogData = data?.backlog;
    const firstEpic = backlogData?.epics?.[0];
    try {
      await api.createBacklogFeature(projectId, {
        name: title,
        ...(firstEpic?.id != null ? { epic_id: firstEpic.id } : {}),
        maturity: 'idea',
      });
      setRetryTick((tick) => tick + 1);
    } catch (err) {
      window.alert(`新建模块失败: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  /** 想法→细化→待办链路: 点「和 AI 讨论」→ 会话锚定该模块 (打开会话栏 + 建锚定会话)。 */
  function handleDiscussFeature(featureId: string, featureName: string): void {
    chat.setProjectId(projectId);
    chat.setFeatureId(featureId, featureName);
    chat.openPanel();
    void chat.createSession(`细化: ${featureName}`, featureId);
  }

  /** 想法→细化→待办链路: 想法模块「转为正式」(maturity idea→refined)。 */
  async function handleRefineFeature(featureId: string): Promise<void> {
    try {
      await api.updateBacklogFeature(projectId, featureId, { maturity: 'refined' });
      setRetryTick((tick) => tick + 1);
    } catch (err) {
      window.alert(`转为正式失败: ${err instanceof Error ? err.message : String(err)}`);
    }
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
              onCreateFeature={handleCreateFeature}
              onDiscussFeature={handleDiscussFeature}
              onRefineFeature={handleRefineFeature}
              chainProgress={buildChainLines(data.backlog)}
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
