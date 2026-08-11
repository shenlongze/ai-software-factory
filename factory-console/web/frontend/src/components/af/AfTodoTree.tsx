/**
 * components/af/AfTodoTree.tsx — AI Factory Todo Tree 组件 (S10-015 Task 003)。
 *
 * 依据 (唯一): S10-015-architecture-review §3 + AF-UI-Architecture §4 (Todo Tree 核心设计 ⭐)。
 *
 * 渲染 (Project → Phase → Module → Task, 树深 ≤4):
 *   - 项目头 (root): 标题 + AfProgressBar + AfStatusBadge (整体完成度/状态)
 *   - 阶段节点 (phase): 📁 + 标题 + 状态徽标 + 完成度% + 展开/折叠箭头
 *   - 模块节点 (module): 📦 + 标题 + 状态徽标 + 完成度%
 *   - 任务节点 (task): 📄 + 标题 + AfStatusBadge (6 态色点+人话) + 优先级标签
 *     (P0 红/P1 橙/P2 蓝/P3 灰) + 负责人/Agent (若字段有) + 叶子额外: 开始时间/下一步/阻塞原因
 *   - 缩进层级线 + 展开动画 120ms + 执行中节点焦点高亮 (af-tree-node--focus)
 *
 * 交互 (§4.6):
 *   - 展开/折叠: 单击箭头 (aria-expanded); 工具栏 [全展开][全折叠]
 *   - 过滤: [全部][执行中][阻塞][待审核][失败] — 只显示匹配任务及其祖先
 *   - 点击任务节点 → onSelectTask(taskId) (Context Panel 联动, Task 006)
 *
 * 数据:
 *   - tree: TodoTree (domain, 由页面 toTodoTree(backlog) 得到 — 真实数据驱动)
 *   - taskMeta: 可选 {id → {priority, owner}} — backlog.tasks 真实字段投影
 *     (Adapter 未映射 priority/assignee, 页面级补充; 缺 → 标签/负责人不渲染)
 *   - 空树 (root 无子) → AfEmptyState "暂无任务 — AI 正在规划" (禁空白)
 * 纯展示组件: 不 fetch, 数据由父层传入。
 */

import { useState } from 'react';
import type { DomainStatus, TodoTree, TreeNode, TreeNodeType } from '../../models/domain';
import { formatTime } from './afLabels';
import { AfEmptyState } from './AfState';
import { AfProgressBar } from './AfProgressBar';
import { AfStatusBadge } from './AfStatusBadge';
import './af.css';

/** 任务补充元数据 (priority/owner 来自真实 backlog.tasks 字段投影)。 */
export interface TaskMeta {
  priority?: string;
  owner?: string;
}

export interface AfTodoTreeProps {
  /** 进度树 (domain; 由 toTodoTree(backlog) 真实转换)。 */
  tree: TodoTree;
  /** 任务补充元数据: taskId → {priority, owner} (可选; 缺 → 不渲染对应标签)。 */
  taskMeta?: Record<string, TaskMeta>;
  /** 点击任务节点回调 (taskId; Context Panel 联动, Task 006)。 */
  onSelectTask?: (taskId: string) => void;
}

/** 过滤选项 (§4.6: [全部][执行中][阻塞][待审核][失败] — 待办/完成不进过滤, 全量可见)。 */
export const TREE_FILTERS: readonly { key: 'all' | DomainStatus; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'running', label: '执行中' },
  { key: 'blocked', label: '阻塞' },
  { key: 'review', label: '待审核' },
  { key: 'failed', label: '失败' },
] as const;

/** 节点类型图标 (阶段 📁 / 模块 📦 / 任务 📄)。 */
const TYPE_ICONS: Record<TreeNodeType, string> = {
  phase: '📁',
  module: '📦',
  task: '📄',
};

/** 树节点 (含子) id 集合 (全折叠用)。 */
function collectBranchIds(node: TreeNode): string[] {
  const ids: string[] = [];
  for (const child of node.children) {
    if (child.children.length > 0) ids.push(child.id);
    ids.push(...collectBranchIds(child));
  }
  return ids;
}

/** 过滤可见性: 任务节点按状态匹配; 阶段/模块/故事 = 有匹配后代才可见 (祖先保留)。 */
function visibleUnderFilter(node: TreeNode, filter: 'all' | DomainStatus): boolean {
  if (filter === 'all') return true;
  if (node.type === 'task' && node.status === filter) return true;
  return node.children.some((child) => visibleUnderFilter(child, filter));
}

/** 树中是否还有任务节点 (页面/组件空态判定)。 */
export function hasTaskNodes(node: TreeNode): boolean {
  if (node.type === 'task') return true;
  return node.children.some(hasTaskNodes);
}

export function AfTodoTree({ tree, taskMeta = {}, onSelectTask }: AfTodoTreeProps): JSX.Element {
  const root = tree.root;
  // 空树 → AfEmptyState (禁空白; 用户刚建项目, AI 正在规划)
  if (root.children.length === 0 || !hasTaskNodes(root)) {
    return (
      <AfEmptyState message="暂无任务 — AI 正在规划" hint="Backlog 生成后将在此展示阶段 → 模块 → 任务进度树" />
    );
  }

  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());
  const [filter, setFilter] = useState<'all' | DomainStatus>('all');

  const toggle = (id: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const expandAll = () => setCollapsed(new Set());
  const collapseAll = () => setCollapsed(new Set(collectBranchIds(root)));

  const visiblePhases = root.children.filter((phase) => visibleUnderFilter(phase, filter));

  return (
    <div className="af-todo-tree" data-testid="af-todo-tree">
      <div className="af-tree-toolbar" data-testid="af-tree-toolbar">
        <button type="button" className="af-btn af-tree-btn" onClick={expandAll}>
          全展开
        </button>
        <button type="button" className="af-btn af-tree-btn" onClick={collapseAll}>
          全折叠
        </button>
        <div className="af-tree-filters" role="group" aria-label="状态过滤">
          {TREE_FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              className={`af-filter-chip${filter === f.key ? ' af-filter-chip--active' : ''}`}
              aria-pressed={filter === f.key}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* 项目头 (root): 整体完成度 + 状态 */}
      <div className="af-tree-root" data-testid="af-tree-root">
        <span className="af-tree-icon" aria-hidden="true">
          🗂
        </span>
        <span className="af-tree-root-title">{root.title}</span>
        <AfStatusBadge status={root.status} label={root.statusLabel} />
        <div className="af-tree-root-progress">
          <AfProgressBar value={root.progress} status={root.status} />
        </div>
      </div>

      <div className="af-tree-body" data-testid="af-tree-body">
        {visiblePhases.length === 0 ? (
          <AfEmptyState message="没有匹配的任务" hint="试试切换其他过滤条件" />
        ) : (
          visiblePhases.map((phase) => (
            <TreeNodeRow
              key={phase.id}
              node={phase}
              collapsed={collapsed}
              filter={filter}
              taskMeta={taskMeta}
              onSelectTask={onSelectTask}
              onToggle={toggle}
            />
          ))
        )}
      </div>
    </div>
  );
}

interface TreeNodeRowProps {
  node: TreeNode;
  collapsed: Set<string>;
  filter: 'all' | DomainStatus;
  taskMeta: Record<string, TaskMeta>;
  onSelectTask?: (taskId: string) => void;
  onToggle: (id: string) => void;
}

function TreeNodeRow({
  node,
  collapsed,
  filter,
  taskMeta,
  onSelectTask,
  onToggle,
}: TreeNodeRowProps): JSX.Element | null {
  if (!visibleUnderFilter(node, filter)) return null;

  const hasChildren = node.children.length > 0;
  const isExpanded = !collapsed.has(node.id);
  const isTask = node.type === 'task';
  const meta = taskMeta[node.id];
  const priority = meta?.priority;
  const owner = node.owner ?? node.agent ?? meta?.owner;
  const isFocus = node.status === 'running'; // 当前焦点: 执行中节点高亮 (§4.6)

  const rowClass = [
    'af-tree-node',
    `af-tree-node--${node.type}`,
    isTask ? 'af-tree-node--clickable' : '',
    isFocus ? 'af-tree-node--focus' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <>
      <div
        className={rowClass}
        data-testid={`af-tree-node-${node.id}`}
        data-node-id={node.id}
        data-node-type={node.type}
        data-node-status={node.status}
        role={isTask ? 'button' : undefined}
        tabIndex={isTask ? 0 : undefined}
        aria-label={isTask ? `任务: ${node.title}` : undefined}
        onClick={isTask ? () => onSelectTask?.(node.id) : undefined}
        onKeyDown={
          isTask
            ? (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onSelectTask?.(node.id);
                }
              }
            : undefined
        }
      >
        {hasChildren ? (
          <button
            type="button"
            className="af-tree-toggle"
            aria-expanded={isExpanded}
            aria-label={`${isExpanded ? '折叠' : '展开'} ${node.title}`}
            onClick={(e) => {
              e.stopPropagation();
              onToggle(node.id);
            }}
          >
            {isExpanded ? '▾' : '▸'}
          </button>
        ) : (
          <span className="af-tree-toggle af-tree-toggle--spacer" aria-hidden="true" />
        )}
        <span className="af-tree-icon" aria-hidden="true">
          {TYPE_ICONS[node.type]}
        </span>
        <span className="af-tree-title">{node.title}</span>
        <AfStatusBadge status={node.status} label={node.statusLabel} />
        {isTask && priority != null && priority.length > 0 ? (
          <span className={`af-priority af-priority--${priority.toUpperCase()}`} data-testid="af-priority">
            {priority.toUpperCase()}
          </span>
        ) : null}
        {isTask && owner != null && owner.length > 0 ? (
          <span className="af-tree-owner" title="负责人 / Agent">
            {owner}
          </span>
        ) : null}
        {isTask && node.startedAt != null ? (
          <span className="af-tree-meta">开始 {formatTime(node.startedAt)}</span>
        ) : null}
        {isTask && node.nextAction != null && node.nextAction.length > 0 ? (
          <span className="af-tree-meta">下一步: {node.nextAction}</span>
        ) : null}
        {isTask && node.blockedReason != null && node.blockedReason.length > 0 ? (
          <span className="af-tree-meta af-tree-meta--blocked">阻塞: {node.blockedReason}</span>
        ) : null}
        <span className="af-tree-progress">{node.progress}%</span>
      </div>
      {hasChildren && isExpanded ? (
        <div className="af-tree-children" data-testid={`af-tree-children-${node.id}`}>
          {node.children
            .filter((child) => visibleUnderFilter(child, filter))
            .map((child) => (
              <TreeNodeRow
                key={child.id}
                node={child}
                collapsed={collapsed}
                filter={filter}
                taskMeta={taskMeta}
                onSelectTask={onSelectTask}
                onToggle={onToggle}
              />
            ))}
        </div>
      ) : null}
    </>
  );
}
