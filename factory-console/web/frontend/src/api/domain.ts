/**
 * api/domain.ts — Domain Adapter (S10-014-plan §2.5 + §6)。
 *
 * 职责 (S10-014 Task 007 实现):
 *   - 字段映射 (后端 snake_case → 前端 domain 字段)
 *   - 派生计算 (完成度/状态人话/风险计数 riskCount)
 *   - 聚合 (Todo Tree 从 backlog 投影 + 项目级降级树)
 *   - 降级 (§6.3: 后端字段缺失/接口未就绪 → domain 默认值, 不崩溃; 全部纯函数无副作用)
 *
 * 数据流: Component → Domain Hook → Domain Adapter → API Layer → FastAPI (8011)
 *
 * S10-014 Task 001 状态: 仅建签名 + 返回默认值 (占位); Task 007 替换为真实转换。
 * 输入为后端 JSON (models/types.ts 投影), 输出为 Frontend Domain Model (models/domain.ts)。
 */

import { lifecycleLabel, progressPercent, statusLabel } from '../components/af/afLabels';
import type {
  AgentStatus as DomainAgentStatus,
  AgentSummary as DomainAgentSummary,
  Activity,
  BacklogEpic,
  BacklogFeature,
  BacklogResponse,
  BacklogStory,
  BacklogTask,
  BlockedTask,
  DashboardViewModel,
  DomainStatus,
  ProjectLifecycleStage,
  QualityCheck,
  QualityCheckStatus,
  QualityDecision,
  QualityGateInfo,
  QualityGateViewModel,
  RuntimeActivity,
  RunningAgent,
  TaskDetail, TaskSessionRef,
  TodoTree,
  TreeNode,
  TreeNodeType,
  WorkflowPipeline,
  WorkflowStage,
  WorkspaceProject,
  WorkflowStatusItem,
} from '../models/domain';
import {
  artifactTypeLabel,
  type ApprovalSummary,
  type ConsoleDashboard,
  type CostSummary,
  type ExperienceSummaryModel,
  type ProjectSummary,
  type RuntimeSessionPayload,
  type StageRunSummary,
  type StageSummary,
  type TimelineEventSummary,
  type WorkflowDetail,
} from '../models/types';

// ------------------------------------------------------------------ 共享: 状态归一

/** 后端状态值 → DomainStatus 别名表 (大小写不敏感; 未知 → fallback)。 */
const STATUS_ALIASES: Record<string, DomainStatus> = {
  completed: 'completed',
  done: 'completed',
  success: 'completed',
  ok: 'completed',
  validated: 'completed',
  approved: 'completed',
  passed: 'completed',
  running: 'running',
  active: 'running',
  executing: 'running',
  in_progress: 'running',
  working: 'running',
  started: 'running',
  pending: 'pending',
  waiting: 'pending',
  ready: 'pending',
  queued: 'pending',
  created: 'pending',
  not_started: 'pending',
  idle: 'pending',
  paused: 'pending',
  todo: 'pending',
  blocked: 'blocked',
  failed: 'failed',
  error: 'failed',
  errored: 'failed',
  review: 'review',
  waiting_review: 'review',
  awaiting_approval: 'review',
  needs_approval: 'review',
};

/** 后端任意状态值 → DomainStatus (未知/缺失 → fallback, 默认 pending; §6.3 降级)。 */
export function toDomainStatus(
  status: string | null | undefined,
  fallback: DomainStatus = 'pending',
): DomainStatus {
  if (status == null || status.length === 0) return fallback;
  return STATUS_ALIASES[status.toLowerCase()] ?? fallback;
}

/** 值 → string (null/undefined → ''), 活动/历史条目宽松读取。 */
function str(value: unknown): string {
  if (value == null) return '';
  return String(value);
}

/** 值 → 非负整数 (非法/缺失 → 0), 计数派生用。 */
function toNonNegativeInt(value: unknown): number {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.round(n));
}

// ------------------------------------------------------------------ toWorkspaceProject

/** 后端生命周期/状态值 → ProjectLifecycleStage 语义别名 (未知 → draft 降级)。 */
const LIFECYCLE_ALIASES: Record<string, ProjectLifecycleStage> = {
  draft: 'draft',
  discovery: 'discovery',
  definition: 'definition',
  development: 'development',
  release: 'release',
  maintenance: 'maintenance',
  // 常见后端值 → 阶段语义
  idea: 'discovery',
  build: 'development',
  active: 'development',
  running: 'development',
  completed: 'release',
  done: 'release',
  success: 'release',
  failed: 'development',
  paused: 'draft',
  archived: 'maintenance',
};

/** GET /api/projects + /api/dashboard → WorkspaceProject。
 *
 * riskCount 派生: stage_counts.failed + stage_counts.blocked (§6.2 风险数)。
 * lifecycleStage: lifecycle_stage → 语义; 缺失 → status → 语义; 都缺/未知 → draft (§6.3)。
 */
export function toWorkspaceProject(raw?: ProjectSummary | null): WorkspaceProject {
  const source = raw ?? ({} as ProjectSummary);
  const lifecycleKey =
    source.lifecycle_stage != null && source.lifecycle_stage.length > 0
      ? source.lifecycle_stage
      : source.status;
  return {
    id: source.id ?? '',
    name: source.name ?? '',
    lifecycleStage: lifecycleKey ? (LIFECYCLE_ALIASES[lifecycleKey] ?? 'draft') : 'draft',
    lifecycleLabel: lifecycleLabel(source),
    progress: progressPercent(source.progress),
    pendingApprovals: toNonNegativeInt(source.pending_approvals),
    riskCount: riskCount(source.stage_counts),
  };
}

/** riskCount 派生: failed + blocked (缺字段 → 0)。 */
function riskCount(counts: Record<string, number> | undefined | null): number {
  if (counts == null) return 0;
  return toNonNegativeInt(counts.failed) + toNonNegativeInt(counts.blocked);
}

// ------------------------------------------------------------------ toTodoTree (S10-015 Task 002: BacklogResponse 真实结构重构)

/**
 * backlog (GET /api/projects/{id}/backlog) + projectName → TodoTree。
 *
 * 真实结构 (S10-015 §2.1 实测): 4 个平行数组 (epics/features/stories/tasks),
 * 层级仅靠自上而下的 `children` id 引用 (Epic→Feature→Story→Task);
 * Epic/Feature/Story 无 status/进度字段。
 *
 * 关联 (§3.3): id 反向索引自上而下组装; 悬空引用跳过 (不崩溃);
 *   孤儿 Epic (children=[]) 保留为空阶段。
 * 层级 (§3.2): Epic→phase / Feature→module / Story→task (状态/进度从子 Task
 *   聚合) / Task→task 子节点 (执行单元)。
 * 状态 (§3.4): Task 六态 (todo/ready→pending, in_progress→running,
 *   blocked→blocked, review→review, done→completed); Story 聚合 (全 done→completed;
 *   有 running→running; 有 blocked→blocked; 有 review→review; 否则 pending);
 *   Epic/Feature 由子节点聚合 (failed > blocked > running > review > completed > pending)。
 * 完成度 (§4.5): 叶子 Task 按 priority 加权 (P0=4/P1=3/P2=2/P3=1, 缺失=1);
 *   Story/Feature/Epic = 子节点加权均值; 无子 → 0。
 * 降级 (§3.5): 空 backlog (无 epics) → 单根 {id:'root', title: projectName || '项目',
 *   type:'phase', pending, 0%}。
 */
export function toTodoTree(
  backlog?: BacklogResponse | null,
  projectName?: string | null,
): TodoTree {
  const source = backlog ?? {};
  const featureIndex = buildIndex(source.features);
  const storyIndex = buildIndex(source.stories);
  const taskIndex = buildIndex(source.tasks);
  const weightedPhases = (source.epics ?? []).map((epic) =>
    toPhaseNode(epic, featureIndex, storyIndex, taskIndex),
  );
  const phases = weightedPhases.map((w) => w.node);
  if (phases.length === 0) {
    return { root: emptyRoot(projectName) };
  }
  const status = aggregateStatus(phases);
  return {
    root: {
      id: 'root',
      title: projectName ?? '项目',
      type: 'phase',
      status,
      statusLabel: statusLabel(status),
      progress: weightedProgress(weightedPhases),
      children: phases,
    },
  };
}

/** 加权节点: TreeNode + 叶子权重 (Task=priorityWeight, 上层=子权重和)。 */
interface WeightedNode {
  node: TreeNode;
  weight: number;
}

/** id → 条目 反向索引 (空 id 跳过; 重复 id 后者覆盖)。 */
function buildIndex<T extends { id?: string | null }>(
  items: T[] | null | undefined,
): Map<string, T> {
  const index = new Map<string, T>();
  for (const item of items ?? []) {
    if (item != null && item.id != null && item.id.length > 0) {
      index.set(item.id, item);
    }
  }
  return index;
}

/** Epic → phase 节点 (children id 反向索引 → Feature → module; 孤儿 → 空阶段)。 */
function toPhaseNode(
  epic: BacklogEpic,
  featureIndex: Map<string, BacklogFeature>,
  storyIndex: Map<string, BacklogStory>,
  taskIndex: Map<string, BacklogTask>,
): WeightedNode {
  const weighted = (epic.children ?? [])
    .map((id) => featureIndex.get(id))
    .filter((f): f is BacklogFeature => f != null)
    .map((feature) => toModuleNode(feature, storyIndex, taskIndex));
  return buildAggregateNode(epic.id, epic.name, 'phase', weighted);
}

/** Feature → module 节点 (children id → Story → task 节点)。 */
function toModuleNode(
  feature: BacklogFeature,
  storyIndex: Map<string, BacklogStory>,
  taskIndex: Map<string, BacklogTask>,
): WeightedNode {
  const weighted = (feature.children ?? [])
    .map((id) => storyIndex.get(id))
    .filter((s): s is BacklogStory => s != null)
    .map((story) => toStoryNode(story, taskIndex));
  const node = buildAggregateNode(feature.id, feature.name, 'module', weighted);
  // 想法→细化→待办链路: 模块成熟度透传 (idea → 💡 想法 / refined → 📦 正式)
  const maturity = String(feature.maturity ?? 'refined').trim().toLowerCase();
  if (maturity === 'idea') {
    node.node.maturity = 'idea';
  }
  return node;
}

/** Story → task 节点 (状态从子 Task 聚合, 规则 §3.4; children = Task 执行单元)。
 * 排序 (Founder 2026-08-26): 待办主树按优先级 P0→P3, 依赖未满足排后
 * (同后端 org.management.sort_tasks 语义 — 决策视图: 先做什么由重要性决定)。 */
function toStoryNode(
  story: BacklogStory,
  taskIndex: Map<string, BacklogTask>,
): WeightedNode {
  const statusById = new Map<string, string>();
  for (const task of taskIndex.values()) {
    if (task?.id != null) statusById.set(task.id, task.status ?? '');
  }
  const tasks = (story.children ?? [])
    .map((id) => taskIndex.get(id))
    .filter((t): t is BacklogTask => t != null)
    .sort((a, b) => compareTaskPriority(a, b, statusById));
  const weighted = tasks.map((task) => toTaskNode(task, taskIndex));
  const status = aggregateStoryStatus(weighted.map((w) => w.node));
  const priority = aggregatePriority(weighted);
  return {
    node: {
      id: story.id ?? '',
      title: story.name ?? '',
      type: 'task',
      status,
      statusLabel: statusLabel(status),
      progress: weightedProgress(weighted),
      ...(priority != null ? { priority } : {}),
      children: weighted.map((w) => w.node),
    },
    weight: sumWeights(weighted),
  };
}

/**
 * Task → task 节点。有子任务 (task.children, legacy 层级保留) → 聚合子节点:
 * 状态/进度从子任务派生 — 主任务子任务未全完成 → 不显示完成、不归档 (Founder 2026-08-27);
 * 无子任务 → 叶子 (完成 → 100%, 其余 → 0%; 权重 = priorityWeight)。
 */
function toTaskNode(task: BacklogTask, taskIndex: Map<string, BacklogTask>): WeightedNode {
  const childIds = task.children ?? [];
  if (childIds.length > 0) {
    const statusById = new Map<string, string>();
    for (const t of taskIndex.values()) {
      if (t?.id != null) statusById.set(t.id, t.status ?? '');
    }
    const children = childIds
      .map((id) => taskIndex.get(id))
      .filter((t): t is BacklogTask => t != null)
      .sort((a, b) => compareTaskPriority(a, b, statusById));
    const weighted = children.map((t) => toTaskNode(t, taskIndex));
    const status = aggregateStoryStatus(weighted.map((w) => w.node));
    const priority = aggregatePriority(weighted);
    return {
      node: {
        id: task.id ?? '',
        title: task.title ?? '',
        type: 'task',
        status,
        statusLabel: statusLabel(status),
        progress: weightedProgress(weighted),
        ...(priority != null ? { priority } : {}),
        children: weighted.map((w) => w.node),
        ...(task.created_at != null && task.created_at.length > 0
          ? { createdAt: task.created_at }
          : {}),
        ...(task.updated_at != null && task.updated_at.length > 0
          ? { updatedAt: task.updated_at }
          : {}),
      },
      weight: sumWeights(weighted),
    };
  }
  const status = toDomainStatus(task.status ?? null);
  const prio = normalizePriority(task.priority);
  const { startedAt, completedAt } = deriveTaskTimes(task);
  return {
    node: {
      id: task.id ?? '',
      title: task.title ?? '',
      type: 'task',
      status,
      statusLabel: statusLabel(status),
      progress: status === 'completed' ? 100 : 0,
      ...(prio != null ? { priority: prio } : {}),
      children: [],
      // Founder 2026-08-27: 任务时间 (创建/进行中/完成) — 树行显示 + 按更新时间排序
      ...(task.created_at != null && task.created_at.length > 0
        ? { createdAt: task.created_at }
        : {}),
      ...(task.updated_at != null && task.updated_at.length > 0
        ? { updatedAt: task.updated_at }
        : {}),
      ...(startedAt != null ? { startedAt } : {}),
      ...(completedAt != null ? { completedAt } : {}),
    },
    weight: priorityWeight(task.priority),
  };
}

/** 从 history 推导 开始/完成 时间 (进入 in_progress / done 的转换时间; 无 → undefined)。 */
function deriveTaskTimes(task: BacklogTask): { startedAt?: string; completedAt?: string } {
  let startedAt: string | undefined;
  let completedAt: string | undefined;
  for (const h of task.history ?? []) {
    const time = typeof h?.time === 'string' ? h.time : undefined;
    const result = String(h?.result ?? '');
    const action = String(h?.action ?? '');
    if (time == null) continue;
    if (startedAt == null && (result.includes('in_progress') || result.includes('toward in_progress'))) {
      startedAt = time;
    }
    if (completedAt == null && (result.includes('done') || result.includes('DONE'))) {
      completedAt = time;
    }
    if (completedAt == null && action === 'exec:completed') {
      completedAt = time;
    }
  }
  // done 且无 history 明确时间 → updated_at 兜底 (终态后不再变)
  if (completedAt == null && task.status === 'done' && task.updated_at != null && task.updated_at.length > 0) {
    completedAt = task.updated_at;
  }
  return { startedAt, completedAt };
}

/** 优先级排序键 (P0=0 … P3=3; 缺失/未知 → 99 排最后)。 */
const PRIORITY_RANK: Record<string, number> = { P0: 0, P1: 1, P2: 2, P3: 3 };

/** 规范化优先级 (P0-P3; 缺失/未知 → undefined, 诚实不臆造)。 */
function normalizePriority(priority: string | null | undefined): string | undefined {
  if (priority == null) return undefined;
  const key = String(priority).trim().toUpperCase();
  return key in PRIORITY_RANK ? key : undefined;
}

/** 聚合优先级 (史诗/模块/故事): 子节点最高优先级 P0 优先; 无 → undefined。 */
function aggregatePriority(weighted: WeightedNode[]): string | undefined {
  let best: string | undefined;
  for (const w of weighted) {
    const p = w.node.priority;
    if (p == null) continue;
    if (best == null || (PRIORITY_RANK[p] ?? 99) < (PRIORITY_RANK[best] ?? 99)) {
      best = p;
    }
  }
  return best;
}

function priorityRank(priority: string | null | undefined): number {
  if (priority == null) return 99;
  return PRIORITY_RANK[String(priority).trim().toUpperCase()] ?? 99;
}

/** 任务是否有未满足依赖 (依赖 id 不在表 / 状态非 done → 未满足)。 */
function hasUnsatisfiedDependency(
  task: BacklogTask,
  statusById: Map<string, string>,
): boolean {
  return (task.dependency ?? []).some((dep) => statusById.get(dep) !== 'done');
}

/** 待办主树排序 (Founder 2026-08-27): 依赖未满足排后, 组内按更新时间倒序 (最后更新最前)。 */
function compareTaskPriority(
  a: BacklogTask,
  b: BacklogTask,
  statusById: Map<string, string>,
): number {
  const aUnsatisfied = hasUnsatisfiedDependency(a, statusById) ? 1 : 0;
  const bUnsatisfied = hasUnsatisfiedDependency(b, statusById) ? 1 : 0;
  if (aUnsatisfied !== bUnsatisfied) return aUnsatisfied - bUnsatisfied;
  const ta = a.updated_at ?? '';
  const tb = b.updated_at ?? '';
  if (ta !== tb) return tb.localeCompare(ta); // 倒序: 最后更新最前
  return priorityRank(a.priority) - priorityRank(b.priority);
}

/** 通用聚合节点 (phase/module): 状态=子节点聚合, 进度=加权均值, 权重=子权重和。 */
function buildAggregateNode(
  id: string | null | undefined,
  title: string | null | undefined,
  type: TreeNodeType,
  weighted: WeightedNode[],
): WeightedNode {
  const children = weighted.map((w) => w.node);
  const status = aggregateStatus(children);
  const priority = aggregatePriority(weighted);
  return {
    node: {
      id: id ?? '',
      title: title ?? '',
      type,
      status,
      statusLabel: statusLabel(status),
      progress: weightedProgress(weighted),
      ...(priority != null ? { priority } : {}),
      children,
    },
    weight: sumWeights(weighted),
  };
}

/** 子节点权重和 (无子 → 0; 孤儿 Epic/空 Story 不贡献进度)。 */
function sumWeights(weighted: WeightedNode[]): number {
  return weighted.reduce((acc, w) => acc + w.weight, 0);
}

/** 加权进度: Σ(weight×progress) / Σ(weight) (叶子按 priority 权重; 无子 → 0)。 */
function weightedProgress(weighted: WeightedNode[]): number {
  const totalWeight = sumWeights(weighted);
  if (totalWeight === 0) return 0;
  const sum = weighted.reduce((acc, w) => acc + w.weight * w.node.progress, 0);
  return Math.round(sum / totalWeight);
}

/** Task 优先级 → 完成度权重 (P0=4/P1=3/P2=2/P3=1, 缺失/未知 → 1)。 */
const PRIORITY_WEIGHTS: Record<string, number> = { P0: 4, P1: 3, P2: 2, P3: 1 };

function priorityWeight(priority: string | null | undefined): number {
  if (priority == null) return 1;
  const key = String(priority).trim().toUpperCase();
  return PRIORITY_WEIGHTS[key] ?? 1;
}

/** Story 状态聚合 (子 Task 派生, S10-015 §3.4): 全 done→completed;
 * 有 running→running; 有 blocked→blocked; 有 review→review; 否则 pending。 */
function aggregateStoryStatus(tasks: TreeNode[]): DomainStatus {
  if (tasks.length === 0) return 'pending';
  if (tasks.every((t) => t.status === 'completed')) return 'completed';
  if (tasks.some((t) => t.status === 'running')) return 'running';
  if (tasks.some((t) => t.status === 'blocked')) return 'blocked';
  if (tasks.some((t) => t.status === 'review')) return 'review';
  return 'pending';
}

/** 聚合状态 (Epic/Feature/root 用): failed > blocked > running > review > completed > pending。 */
function aggregateStatus(nodes: TreeNode[]): DomainStatus {
  const priority: DomainStatus[] = [
    'failed',
    'blocked',
    'running',
    'review',
    'completed',
    'pending',
  ];
  for (const p of priority) {
    if (nodes.some((n) => n.status === p)) return p;
  }
  return 'pending';
}

/** 空 backlog 降级根 (单根, phase, pending, 0%; §3.5 空降级)。 */
function emptyRoot(projectName?: string | null): TreeNode {
  return {
    id: 'root',
    title: projectName ?? '项目',
    type: 'phase',
    status: 'pending',
    statusLabel: statusLabel('pending'),
    progress: 0,
    children: [],
  };
}

// ------------------------------------------------------------------ toWorkflowPipeline

/** 阶段名 → 人话 (未知 → 原样; §6.3)。 */
const STAGE_NAME_LABELS: Record<string, string> = {
  idea: '需求分析',
  pm: '需求分析',
  product: '产品设计',
  ux_ui: 'UI/UX 设计',
  design: '架构设计',
  architecture: '架构设计',
  development: '开发',
  testing: '测试',
  test: '测试',
  release: '发布',
};

/** role_id → 角色人话 (未知 → 原样)。 */
const ROLE_LABELS: Record<string, string> = {
  'product-manager': '产品经理',
  pm: '产品经理',
  planner: '产品经理',
  'ui-designer': 'UI 设计师',
  designer: 'UI 设计师',
  architect: '架构师',
  developer: '开发工程师',
  'backend-dev': '开发工程师',
  'full-stack-dev': '开发工程师',
  tester: '测试工程师',
  'qa-engineer': '测试工程师',
  devops: '发布工程师',
};

/** 流水线阶段输入: WorkflowDetail.stages (StageSummary) 或 /workflows/{id}/stages (StageRunSummary)。 */
type StageInput = StageSummary | StageRunSummary;

/** GET /api/projects/{id}/workflow + stages → WorkflowPipeline (S10-015 Task 004 增强)。
 *
 * 真实实例结构 (S10-015 §2.2 实测 + 用户 Task 004 约束):
 *   - isMock: workflowDetail.is_mock 透传 (true → 前端降级标注"演示数据", 不冒充真实)
 *   - status: workflow.status → DomainStatus (active→running/completed→completed/failed→failed)
 *   - startedAt/completedAt: 实例起止时间 (缺失 → undefined)
 *   - failedReason: workflow.failed_reason (工作流级失败原因, 缺失 → undefined)
 *   - stages: 阶段映射 (名称/角色人话 Agent 名/5 状态映射含 waiting_review→review/
 *     blocked 阶段 blockedReason = depends_on 前置阶段人话)
 * 降级 (§6.3): 无 workflow → templateName='未启动', stages=[] (不崩溃)。
 */
export function toWorkflowPipeline(
  project?: ProjectSummary | null,
  workflowDetail?: WorkflowDetail | null,
  stages?: StageRunSummary[] | null,
): WorkflowPipeline {
  const source = project ?? ({} as ProjectSummary);
  const detail = workflowDetail ?? null;
  const stageInputs: StageInput[] = stages ?? detail?.stages ?? [];
  // stageId → role_id 反向索引 (blockedReason 把 depends_on 阶段 id 翻译成人话前置阶段)
  const roleByStageId = new Map<string, string>();
  for (const s of stageInputs) {
    if (s?.id != null && s.id.length > 0 && s.role_id != null && s.role_id.length > 0) {
      roleByStageId.set(s.id, s.role_id);
    }
  }
  const failedReason =
    detail?.failed_reason != null && detail.failed_reason.length > 0
      ? detail.failed_reason
      : undefined;
  return {
    templateId: detail?.id ?? source.workflow_id ?? '',
    templateName: detail?.name ?? source.workflow_name ?? '未启动',
    isMock: detail?.is_mock ?? false,
    status: toDomainStatus(detail?.status ?? source.workflow_status ?? null),
    startedAt: detail?.started_at ?? undefined,
    completedAt: detail?.completed_at ?? undefined,
    ...(failedReason != null ? { failedReason } : {}),
    stages: stageInputs.map((s, index) => toWorkflowStage(s, index, roleByStageId)),
  };
}

/** 单阶段映射 (order/名称/角色/Agent/状态/耗时/产物; 缺失 → 可选字段 undefined)。 */
function toWorkflowStage(
  s: StageInput,
  index: number,
  roleByStageId: Map<string, string>,
): WorkflowStage {
  const pendingApproval = (s as StageSummary).pending_approval;
  const status: DomainStatus =
    pendingApproval != null && pendingApproval.status === 'pending'
      ? 'review'
      : toDomainStatus(s.status);
  const roleId = s.role_id ?? '';
  const blockedReason = blockedReasonOf(s, status, roleByStageId);
  return {
    order: s.order ?? index + 1,
    name: STAGE_NAME_LABELS[s.name] ?? s.name,
    ...(roleId.length > 0 ? { roleId } : {}),
    agentName: agentNameOf(s, roleId),
    status,
    statusLabel: statusLabel(status),
    ...(blockedReason != null ? { blockedReason } : {}),
    currentTask: currentTaskOf(s),
    duration: (s as StageRunSummary).duration_s ?? undefined,
    artifact: artifactRefOf(s),
  };
}

/** agent 名: agent_id/role_id → ROLE_LABELS 人话 (未知原样; org 角色即执行者, agent_id=role_id)。 */
function agentNameOf(s: StageInput, roleId: string): string | undefined {
  const agentId = (s as StageRunSummary).agent_id;
  const rawId = agentId != null && agentId.length > 0 ? agentId : roleId;
  if (rawId == null || rawId.length === 0) return undefined;
  return ROLE_LABELS[rawId] ?? rawId;
}

/** 阻塞原因: blocked 阶段 depends_on 前置阶段 id → 人话角色 (无依赖 → 通用, 不臆造)。 */
function blockedReasonOf(
  s: StageInput,
  status: DomainStatus,
  roleByStageId: Map<string, string>,
): string | undefined {
  if (status !== 'blocked') return undefined;
  const dependsOn = (s as StageSummary).depends_on ?? [];
  const labels = dependsOn
    .map((id) => roleByStageId.get(id))
    .filter((r): r is string => r != null && r.length > 0)
    .map((roleId) => ROLE_LABELS[roleId] ?? roleId);
  if (labels.length > 0) return `等待前置阶段完成: ${labels.join('、')}`;
  if (dependsOn.length > 0) return '等待前置阶段完成';
  return '依赖未就绪';
}

/** 当前任务: 阶段产物 type 人话 (无 → undefined, 诚实降级)。 */
function currentTaskOf(s: StageInput): string | undefined {
  const artifact = (s as StageSummary).artifact;
  if (artifact?.type) return artifactTypeLabel(artifact.type);
  return undefined;
}

/** 产物引用: 阶段 artifact.ref (无 → undefined)。 */
function artifactRefOf(s: StageInput): string | undefined {
  const artifact = (s as StageSummary).artifact;
  return artifact?.ref ?? undefined;
}

// ------------------------------------------------------------------ toTaskDetail

/** 任务详情宽松输入 (后端 task 结构 + history 投影; 缺字段 → 降级)。 */
export interface TaskDetailInput {
  id?: string | null;
  title?: string | null;
  name?: string | null;
  status?: string | null;
  agent?: string | null;
  owner?: string | null;
  assignee?: string | null;
  priority?: string | null;
  description?: string | null;
  dependency?: string[] | null;
  started_at?: string | null;
  startedAt?: string | null;
  completed_at?: string | null;
  completedAt?: string | null;
  next_action?: string | null;
  nextAction?: string | null;
  blocked_reason?: string | null;
  blockedReason?: string | null;
  history?: Array<Record<string, unknown>> | null;
  artifacts?: string[] | null;
  epic_name?: string | null;
  feature_name?: string | null;
  story_name?: string | null;
  /** 关联会话 (T-4 双向追溯; 后端任务详情返回)。 */
  sessions?: Array<{ id?: string | null; title?: string | null; updated_at?: string | null; project_id?: string | null }> | null;
}

/** 空 TaskDetail 降级 (Task 未定位/输入缺失; §6.3 不崩溃)。 */
function emptyTaskDetail(): TaskDetail {
  return {
    id: '',
    title: '',
    status: 'pending',
    statusLabel: statusLabel('pending'),
    history: [],
    artifacts: [],
  };
}

/** 负责人归一: null/空串 → undefined (真实 assignee='' 不显示空负责人)。 */
function normalizeOwner(value: string | null | undefined): string | undefined {
  if (value == null || value.length === 0) return undefined;
  return value;
}

/** 下一步动作派生 (后端无 next_action 字段时; 从真实 status 推导人话, 非伪造状态)。 */
function deriveNextAction(status: DomainStatus): string | undefined {
  switch (status) {
    case 'running':
      return '正在执行 — 等待当前工作完成';
    case 'blocked':
      return '解除阻塞后继续执行';
    case 'review':
      return '等待人工审核';
    case 'failed':
      return '修复失败原因后重试';
    case 'completed':
      return '已完成 — 无后续动作';
    default:
      return '等待开始执行';
  }
}

/**
 * 任务详情统一 Adapter (S10-015 Task 005 双模式):
 *   ① backlog 定位模式: toTaskDetail(backlog, taskId) — 从 GET /api/projects/{id}/backlog
 *      定位 Task + 自上而下 children 反向关联 Epic/Feature/Story (为什么存在);
 *      agent = assignee → ROLE_LABELS 人话 (哪个 Agent); nextAction = 后端字段 ?: status 派生
 *   ② 任务实体模式: toTaskDetail(taskRaw) — 兼容 S10-014 单对象输入 (字段直映,
 *      缺失 → undefined, 不派生)
 * 输入检测: 含 epics/features/stories/tasks 数组 → backlog 模式; 否则 → 实体模式。
 */
export function toTaskDetail(
  backlogOrTask?: BacklogResponse | TaskDetailInput | null,
  taskId?: string | null,
): TaskDetail {
  if (isBacklogResponse(backlogOrTask)) {
    return toTaskDetailFromBacklog(backlogOrTask, taskId);
  }
  return toTaskDetailFromInput(backlogOrTask as TaskDetailInput | null | undefined);
}

/** 输入是否 BacklogResponse (4 平行数组中任一存在 → backlog 模式)。 */
function isBacklogResponse(value: unknown): value is BacklogResponse {
  const v = (value ?? {}) as Record<string, unknown>;
  return (
    Array.isArray(v.epics) ||
    Array.isArray(v.features) ||
    Array.isArray(v.stories) ||
    Array.isArray(v.tasks)
  );
}

/** backlog 定位模式: taskId → Task + Epic/Feature/Story 反向关联 (缺失 → 降级)。 */
function toTaskDetailFromBacklog(
  backlog: BacklogResponse | null | undefined,
  taskId: string | null | undefined,
): TaskDetail {
  const source = backlog ?? {};
  const tasks = source.tasks ?? [];
  const task = taskId != null ? tasks.find((t) => t?.id === taskId) : undefined;
  if (task == null) return emptyTaskDetail();
  const story = (source.stories ?? []).find((s) => (s?.children ?? []).includes(taskId ?? ''));
  const feature =
    story != null
      ? (source.features ?? []).find((f) => (f?.children ?? []).includes(story.id ?? ''))
      : undefined;
  const epic =
    feature != null
      ? (source.epics ?? []).find((e) => (e?.children ?? []).includes(feature.id ?? ''))
      : undefined;
  const status = toDomainStatus(task.status ?? null);
  const assignee = normalizeOwner(task.assignee);
  return {
    id: task.id ?? '',
    title: task.title ?? '',
    status,
    statusLabel: statusLabel(status),
    ...(assignee != null
      ? { owner: assignee, agent: ROLE_LABELS[assignee] ?? assignee }
      : {}),
    ...(task.priority != null && task.priority.length > 0 ? { priority: task.priority } : {}),
    ...(task.description != null && task.description.length > 0
      ? { description: task.description }
      : {}),
    ...(Array.isArray(task.dependency) ? { dependency: task.dependency } : {}),
    ...(task.created_at != null && task.created_at.length > 0
      ? { startedAt: task.created_at }
      : {}),
    rawStatus: task.status ?? '',
    ...(task.exec_ref != null && task.exec_ref.length > 0 ? { execRef: task.exec_ref } : {}),
    ...(task.exec_result != null && task.exec_result.length > 0
      ? { execResult: task.exec_result }
      : {}),
    nextAction: deriveNextAction(status),
    ...(epic != null && epic.name != null && epic.name.length > 0 ? { epicName: epic.name } : {}),
    ...(feature != null && feature.name != null && feature.name.length > 0
      ? { featureName: feature.name }
      : {}),
    ...(story != null && story.name != null && story.name.length > 0 ? { storyName: story.name } : {}),
    history: (task.history ?? []).map(toActivity),
    artifacts: [],
  };
}

/** 任务实体模式: 单对象直映 (S10-014 兼容; 缺失 → undefined, 不派生)。 */
function toTaskDetailFromInput(taskRaw?: TaskDetailInput | null): TaskDetail {
  const t = taskRaw ?? {};
  const status = toDomainStatus(t.status ?? null);
  const owner = normalizeOwner(t.owner ?? t.assignee);
  return {
    id: t.id ?? '',
    title: t.title ?? t.name ?? '',
    status,
    statusLabel: statusLabel(status),
    ...(t.agent != null && t.agent.length > 0 ? { agent: t.agent } : {}),
    ...(owner != null ? { owner } : {}),
    ...(t.priority != null && t.priority.length > 0 ? { priority: t.priority } : {}),
    ...(t.description != null && t.description.length > 0 ? { description: t.description } : {}),
    ...(Array.isArray(t.dependency) && t.dependency.length > 0
      ? { dependency: t.dependency }
      : {}),
    ...(t.started_at != null && t.started_at.length > 0
      ? { startedAt: t.started_at }
      : t.startedAt != null && t.startedAt.length > 0
        ? { startedAt: t.startedAt }
        : {}),
    ...(t.completed_at != null && t.completed_at.length > 0
      ? { completedAt: t.completed_at }
      : t.completedAt != null && t.completedAt.length > 0
        ? { completedAt: t.completedAt }
        : {}),
    ...(t.next_action != null && t.next_action.length > 0
      ? { nextAction: t.next_action }
      : t.nextAction != null && t.nextAction.length > 0
        ? { nextAction: t.nextAction }
        : {}),
    ...(t.blocked_reason != null && t.blocked_reason.length > 0
      ? { blockedReason: t.blocked_reason }
      : t.blockedReason != null && t.blockedReason.length > 0
        ? { blockedReason: t.blockedReason }
        : {}),
    ...(t.epic_name != null && t.epic_name.length > 0 ? { epicName: t.epic_name } : {}),
    ...(t.feature_name != null && t.feature_name.length > 0 ? { featureName: t.feature_name } : {}),
    ...(t.story_name != null && t.story_name.length > 0 ? { storyName: t.story_name } : {}),
    ...(normalizeTaskSessions(t.sessions).length > 0
      ? { sessions: normalizeTaskSessions(t.sessions) }
      : {}),
    history: (t.history ?? []).map(toActivity),
    artifacts: Array.isArray(t.artifacts) ? t.artifacts : [],
  };
}

/** 关联会话归一 (T-4): 空/非法 → [] (面板不渲染该区)。 */
function normalizeTaskSessions(
  sessions: TaskDetailInput['sessions'],
): TaskSessionRef[] {
  return (sessions ?? [])
    .filter((s) => s != null && s.id != null && String(s.id).length > 0)
    .map((s) => ({
      id: String(s.id),
      title: String(s.title ?? '未命名'),
      ...(s.updated_at != null && s.updated_at.length > 0 ? { updated_at: s.updated_at } : {}),
      ...(s.project_id != null && s.project_id.length > 0 ? { project_id: s.project_id } : {}),
    }));
}

/** 历史/事件条目 → Activity (宽松读取: created_at/time/timestamp, message/action/event_type)。 */
function toActivity(ev: Record<string, unknown>): Activity {
  return {
    time: str(ev.created_at ?? ev.time ?? ev.timestamp),
    actor: str(ev.actor ?? ev.agent_id ?? ev.source),
    action: str(ev.action ?? ev.message ?? ev.event_type),
    result: str(ev.result ?? ev.status),
  };
}

// ------------------------------------------------------------------ toRuntimeActivity

/** 事件类型 → 人话动作 (未知/缺失 → 原样; message 优先于映射)。 */
const EVENT_ACTION_LABELS: Record<string, string> = {
  'org.workflow.created': '创建工作流',
  'org.workflow.started': '启动工作流',
  'org.workflow.stage_ready': '阶段就绪',
  'org.workflow.stage_started': '阶段开始',
  'org.workflow.stage_completed': '阶段完成',
  'org.workflow.stage_failed': '阶段失败',
  'org.workflow.completed': '工作流完成',
  'org.workflow.failed': '工作流失败',
  'org.artifact.created': '生成产物',
  'org.artifact.updated': '更新产物',
  'org.artifact.validated': '验证产物',
  'org.artifact.consumed': '消费产物',
  'approval.required': '等待审批',
  'approval.completed': '审批完成',
  // S10-015 Task 007: org.approval.* 受控事件 (S10-015 评审 §5.3 补齐; message 优先于映射)
  'org.approval.created': '审批待处理',
  'org.approval.approved': '审批通过',
  'org.approval.rejected': '审批驳回',
  'stage.started': '阶段开始',
  'stage.completed': '阶段完成',
  'task.started': '开始任务',
  'task.completed': '完成任务',
  // S10-018 Task 001: Tool Runtime 事件 (AI Employee 调用工具)
  'tool_requested': '工具请求',
  'tool_started': '工具执行中',
  'tool_completed': '工具完成',
  'tool_failed': '工具失败',
  // S10-019 Task 001: Skill 事件 (AI Employee 职业能力加载/选择)
  'skill_loaded': '技能加载',
  'skill_selected': '技能选择',
  // S10-020 Task 001: MCP 事件 (外部 MCP 服务连接/工具发现/注册)
  'mcp_connected': 'MCP 已连接',
  'mcp_tool_discovered': 'MCP 工具发现',
  'mcp_tool_registered': 'MCP 工具注册',
  error: '发生错误',
};

/** 事件结果/状态 → result 人话 (S10-015 Task 005: OK→通过; 未知 → 原样, §6.3)。 */
const RESULT_LABELS: Record<string, string> = {
  OK: '通过',
  ok: '通过',
  success: '成功',
  completed: '完成',
  done: '完成',
  validated: '验证通过',
  ready: '就绪',
  running: '执行中',
  failed: '失败',
  error: '失败',
  FAIL: '失败',
  pending: '待处理',
  approved: '已通过',
  rejected: '已驳回',
};

/** 后端 role/agent id → 人话 Agent 名 (ROLE_LABELS 命中 → '产品经理 Agent'; 未知 → 原样)。 */
function agentLabel(id: string): string {
  if (id == null || id.length === 0) return '';
  return ROLE_LABELS[id] != null ? `${ROLE_LABELS[id]} Agent` : id;
}

/** timeline + events/stream → RuntimeActivity[] (事件 → 活动条目; 空/非数组 → [])。
 *
 * 输入兼容 TimelineEventSummary (created_at/message/status/agent_id/stage_id/event_type)
 * 与 EventSummary (timestamp/source/action/result)。projectName 可选 (全局流)。
 * S10-015 Task 005 增强:
 *   - actor: agent_id → ROLE_LABELS 人话 + 'Agent' 后缀 (未知 role 原样, 不臆造);
 *     无 agent_id → source/actor 原样; 全无 → '系统'
 *   - result: 已知状态值 → 人话 (OK → 通过; completed → 完成; …); 未知 → 原样
 *   - stageId/eventType 透传 (Runtime Timeline 阶段/事件定位)
 */
export function toRuntimeActivity(
  events?: unknown[] | null,
  projectName?: string | null,
): RuntimeActivity[] {
  if (!Array.isArray(events)) return [];
  return events.map((ev) => {
    const raw = (ev ?? {}) as Record<string, unknown>;
    const eventType = str(raw.event_type);
    const message = str(raw.message);
    const action =
      message ||
      (eventType ? (EVENT_ACTION_LABELS[eventType] ?? eventType) : str(raw.action));
    const agentId = str(raw.agent_id);
    const sourceActor = str(raw.source ?? raw.actor);
    const actor =
      agentId.length > 0 ? agentLabel(agentId) : sourceActor.length > 0 ? sourceActor : '系统';
    const rawResult = str(raw.result ?? raw.status);
    const result = rawResult.length > 0 ? (RESULT_LABELS[rawResult] ?? rawResult) : '';
    const stageId = str(raw.stage_id);
    return {
      time: str(raw.created_at ?? raw.timestamp ?? raw.time),
      actor,
      action,
      result,
      ...(stageId.length > 0 ? { stageId } : {}),
      ...(eventType.length > 0 ? { eventType } : {}),
      ...(projectName != null && projectName.length > 0 ? { projectName } : {}),
    };
  });
}

// ------------------------------------------------------------------ toRuntimeSession (S10-016)

/** S10-016: Runtime Session 状态 → result 人话 (未知 → 原样, §6.3)。 */
const SESSION_RESULT_LABELS: Record<string, string> = {
  pending: '待处理',
  running: '执行中',
  success: '成功',
  failed: '失败',
  cancelled: '已取消',
};

/** Runtime Session → RuntimeActivity (S10-016 — AI Employee 执行会话活动条目)。

 * 后端 RuntimeSession (GET/POST /api/runtime-sessions/*) → 前端实时活动流
 * 兼容结构 (S10-015 RuntimeActivity — Dashboard 最近活动/运行时时间线数据源):
 *   - time: started_at ?? created_at (会话开始/创建时间; 缺失 → '')
 *   - actor: agent_id → ROLE_LABELS 人话 + 'Agent' 后缀 (未知原样, 同
 *     toRuntimeActivity agentLabel 口径; 空 → '系统')
 *   - action: 执行任务 <task_id> (含 workflow_id → 追加 (工作流 id);
 *     全缺 → 'Agent 执行会话')
 *   - result: 五态状态人话 (pending→待处理/running→执行中/success→成功/
 *     failed→失败/cancelled→已取消; 未知 → 原样)
 *   - eventType: runtime_session.<status> (Runtime Timeline 会话定位; 缺状态
 *     → undefined)
 * 降级 (§6.3): null/undefined 输入 → 空活动条目 (time/actor/action 空,
 * result 空, 不崩溃)。
 */
export function toRuntimeSession(
  session?: RuntimeSessionPayload | null,
): RuntimeActivity {
  const source = session ?? ({} as RuntimeSessionPayload);
  const status = str(source.status);
  const task = str(source.task_id).trim();
  const workflow = str(source.workflow_id).trim();
  const action =
    task.length > 0
      ? workflow.length > 0
        ? `执行任务 ${task} (${workflow})`
        : `执行任务 ${task}`
      : workflow.length > 0
        ? `执行工作流 ${workflow}`
        : 'Agent 执行会话';
  const actor =
    str(source.agent_id).length > 0 ? agentLabel(str(source.agent_id)) : '系统';
  return {
    time: str(source.started_at ?? source.created_at),
    actor,
    action,
    result: status.length > 0 ? (SESSION_RESULT_LABELS[status] ?? status) : '',
    ...(status.length > 0 ? { eventType: `runtime_session.${status}` } : {}),
  };
}

// ------------------------------------------------------------------ toAgentSummary

/** Agent 实体宽松输入 (后端 AgentSummary: id/name/role/status/skills/current_task)。 */
export interface AgentSummaryInput {
  id?: string | null;
  name?: string | null;
  role?: string | null;
  status?: string | null;
  skills?: string[] | null;
  version?: string | null;
  current_task?: string | null;
  success_rate?: number | null;
  avg_duration?: number | null;
}

/** 后端 agent 状态 → 卡片状态 (工作中/忙碌 → available; 未知 → available 降级)。 */
const AGENT_STATUS_ALIASES: Record<string, DomainAgentStatus> = {
  available: 'available',
  idle: 'available',
  online: 'available',
  working: 'available',
  busy: 'available',
  active: 'available',
  disabled: 'disabled',
  offline: 'disabled',
  error: 'disabled',
  retired: 'retired',
};

/** workflows/agents + registry 门面 → AgentSummary (实体 → 卡片字段; 缺失 → 默认)。 */
export function toAgentSummary(agentRaw?: AgentSummaryInput | null): DomainAgentSummary {
  const a = agentRaw ?? {};
  const rawStatus = str(a.status).toLowerCase();
  return {
    id: a.id ?? '',
    name: a.name ?? '',
    role: a.role ?? '',
    status: AGENT_STATUS_ALIASES[rawStatus] ?? 'available',
    skills: Array.isArray(a.skills) ? a.skills : [],
    version: a.version ?? '',
    ...(typeof a.success_rate === 'number' ? { successRate: a.success_rate } : {}),
    ...(typeof a.avg_duration === 'number' ? { avgDuration: a.avg_duration } : {}),
  };
}

// ------------------------------------------------------------------ toDashboardViewModel (S10-015 Task 006)

/**
 * Dashboard 聚合附加输入 (每项目真实数据; 缺失 → 降级, 不崩溃)。
 * 页面数据流 (AfDashboard): api.dashboard() + 每项目 projectWorkflow / projectTimeline /
 * fetchProjectBacklog → DashboardExtras (Promise.allSettled, 单项目失败 → null)。
 */
export interface DashboardExtras {
  /** projectId → workflow 实例 (GET /api/projects/{id}/workflow; 缺失 → null)。 */
  workflows?: Record<string, WorkflowDetail | null | undefined> | null;
  /** projectId → timeline 事件 (GET /api/projects/{id}/timeline; 缺失 → null)。 */
  timelines?: Record<string, TimelineEventSummary[] | null | undefined> | null;
  /** projectId → backlog (GET /api/projects/{id}/backlog; 缺失 → null)。 */
  backlogs?: Record<string, BacklogResponse | null | undefined> | null;
}

/** 最近活动条数上限 (Recent Runtime Events 模块)。 */
export const RECENT_EVENTS_LIMIT = 10;

/** 审批门 gate → 人话 (未知 → 原样)。 */
const GATE_LABELS: Record<string, string> = {
  prd: 'PRD',
  product: 'PRD',
  design: '设计',
  ux_ui: 'UX/UI',
  ui: 'UX/UI',
  architecture: '架构',
  code: '代码',
  test: '测试',
  release: '发布',
};

/** 时间戳排序键 (ISO → epoch; 非法 → 0, 不崩溃)。 */
function timeKey(time: string): number {
  const t = Date.parse(time);
  return Number.isNaN(t) ? 0 : t;
}

/** 比率 (0..1) → 百分比人话 ('13%'; 非法 → '0%')。 */
function percentLabel(rate: number | null | undefined): string {
  const raw = Number(rate ?? 0);
  if (!Number.isFinite(raw)) return '0%';
  return `${Math.round(raw * 100)}%`;
}

/**
 * Dashboard 视图模型聚合 (S10-015 Task 006 — AI 软件公司 Control Center 数据源)。
 *
 * 输入: GET /api/dashboard 七域 + 每项目 workflow/timeline/backlog (DashboardExtras)。
 * 输出: DashboardViewModel 6 域 (UI 不直接依赖 API DTO — Adapter Layer):
 *   - projects:       dashboard.projects → toWorkspaceProject (复用, 无 → [])
 *   - runningAgents:  agents toDomainStatus=running (RUNNING/EXECUTING/WORKING/ACTIVE…)
 *                     → {agentName, currentTask, workflowStage, status}; workflowStage =
 *                     运行中阶段 role 匹配人话名 (无 → null, 不编造); 无 → []
 *   - workflowStatus: 有真实 workflow 实例的项目 → 阶段链 (toWorkflowPipeline 复用,
 *                     status 从实例; currentStage = project.current_stage);
 *                     无实例项目不编造 (其 workflow 状态已由项目卡展示); 无 → []
 *   - blockedTasks:   backlog tasks status=blocked → {taskName, reason (dependency
 *                     依赖任务标题), ownerAgent (assignee→ROLE_LABELS 人话), nextAction,
 *                     projectId}; 无 → []
 *   - recentEvents:   每项目 timeline + dashboard activity → toRuntimeActivity 合并,
 *                     按时间倒序, 上限 RECENT_EVENTS_LIMIT; 无 → []
 *   - qualitySummary: cost.calls>0 → tests; approvals pending → qualityGate;
 *                     experience.total>0 → buildStatus; 无数据 → undefined (UI Unavailable)
 * 降级 (§6.3): 任何输入缺失/非法 → 空数组/undefined, 不崩溃; 全部纯函数无副作用。
 */
export function toDashboardViewModel(
  dashboard?: ConsoleDashboard | null,
  extras?: DashboardExtras | null,
): DashboardViewModel {
  const dash = dashboard ?? null;
  const projects = dash?.projects ?? [];
  const workflows = extras?.workflows ?? {};
  const runningStages = collectRunningStages(projects, workflows);

  return {
    projects: projects.map(toWorkspaceProject),
    runningAgents: (dash?.agents ?? [])
      .filter((a) => toDomainStatus(a?.status ?? null) === 'running')
      .map((a) => toRunningAgent(a, runningStages)),
    workflowStatus: workflowStatusItems(projects, workflows),
    blockedTasks: collectBlockedTasks(projects, backlogsOf(extras)),
    recentEvents: collectRecentEvents(projects, timelinesOf(extras), dash?.activity),
    qualitySummary: {
      tests: qualityTests(dash?.cost),
      qualityGate: qualityGate(dash?.approvals),
      buildStatus: qualityBuild(dash?.experience),
    },
  };
}

function backlogsOf(extras: DashboardExtras | null | undefined) {
  return extras?.backlogs ?? {};
}

function timelinesOf(extras: DashboardExtras | null | undefined) {
  return extras?.timelines ?? {};
}

/** 单 Agent → RunningAgent (缺失字段诚实降级; workflowStage 从运行中阶段 role 匹配)。 */
function toRunningAgent(
  a: ConsoleDashboard['agents'][number] | null | undefined,
  runningStages: Map<string, string>,
): RunningAgent {
  return {
    agentName: a?.name ?? a?.id ?? '',
    currentTask:
      a?.current_task != null && a.current_task.length > 0 ? a.current_task : null,
    workflowStage: runningStages.get(a?.role ?? '') ?? null,
    status: 'running',
  };
}

/** 运行中阶段索引: role_id → 阶段人话名 (只取真实 running 阶段; 无 → 空 Map)。 */
function collectRunningStages(
  projects: ProjectSummary[],
  workflows: Record<string, WorkflowDetail | null | undefined>,
): Map<string, string> {
  const map = new Map<string, string>();
  for (const project of projects) {
    for (const stage of workflows[project.id]?.stages ?? []) {
      if (toDomainStatus(stage?.status ?? null) !== 'running') continue;
      const role = stage?.role_id;
      if (role == null || role.length === 0) continue;
      const label = STAGE_NAME_LABELS[stage.name] ?? stage.name;
      if (!map.has(role)) map.set(role, label);
    }
  }
  return map;
}

/** workflowStatus: 有真实 workflow 实例的项目 → 阶段链 (无实例 → 不编造)。 */
function workflowStatusItems(
  projects: ProjectSummary[],
  workflows: Record<string, WorkflowDetail | null | undefined>,
): WorkflowStatusItem[] {
  const items: WorkflowStatusItem[] = [];
  for (const project of projects) {
    const detail = workflows[project.id];
    if (detail == null) continue;
    const pipeline = toWorkflowPipeline(project, detail);
    const status = pipeline.status ?? 'pending';
    items.push({
      projectId: project.id,
      projectName: project.name ?? '',
      status,
      statusLabel: statusLabel(status),
      ...(project.current_stage != null && project.current_stage.length > 0
        ? { currentStage: project.current_stage }
        : {}),
      stages: pipeline.stages,
    });
  }
  return items;
}

/** blockedTasks: 各项目 backlog blocked Task → 任务名/原因/负责人/下一步 (无 → [])。 */
function collectBlockedTasks(
  projects: ProjectSummary[],
  backlogs: Record<string, BacklogResponse | null | undefined>,
): BlockedTask[] {
  const tasks: BlockedTask[] = [];
  for (const project of projects) {
    const backlog = backlogs[project.id];
    if (backlog == null) continue;
    const taskIndex = buildIndex(backlog.tasks);
    for (const task of backlog.tasks ?? []) {
      if (toDomainStatus(task?.status ?? null) !== 'blocked') continue;
      const depTitles = (task?.dependency ?? [])
        .map((id) => taskIndex.get(id)?.title)
        .filter((t): t is string => t != null && t.length > 0);
      tasks.push({
        taskName: task?.title ?? '',
        ...(depTitles.length > 0 ? { reason: `等待: ${depTitles.join('、')}` } : {}),
        ...(task?.assignee != null && task.assignee.length > 0
          ? { ownerAgent: ROLE_LABELS[task.assignee] ?? task.assignee }
          : {}),
        nextAction: deriveNextAction('blocked') ?? '解除阻塞后继续执行',
        projectId: project.id,
      });
    }
  }
  return tasks;
}

/** recentEvents: timeline + activity 合并 → RuntimeActivity, 时间倒序, 上限 N (无 → [])。 */
function collectRecentEvents(
  projects: ProjectSummary[],
  timelines: Record<string, TimelineEventSummary[] | null | undefined>,
  activity: ConsoleDashboard['activity'] | null | undefined,
): RuntimeActivity[] {
  const all: RuntimeActivity[] = [];
  for (const project of projects) {
    const events = timelines[project.id];
    if (!Array.isArray(events) || events.length === 0) continue;
    all.push(...toRuntimeActivity(events, project.name));
  }
  if (Array.isArray(activity) && activity.length > 0) {
    all.push(...toRuntimeActivity(activity));
  }
  return all
    .sort((a, b) => timeKey(b.time) - timeKey(a.time))
    .slice(0, RECENT_EVENTS_LIMIT);
}

/** qualitySummary.tests: cost.calls > 0 → '执行 N 次 · 成功率 P%' (无数据 → undefined)。 */
function qualityTests(cost: CostSummary | null | undefined): string | undefined {
  if (cost == null) return undefined;
  const calls = toNonNegativeInt(cost.calls);
  if (calls === 0) return undefined;
  return `执行 ${calls} 次 · 成功率 ${percentLabel(cost.success_rate)}`;
}

/** qualitySummary.qualityGate: pending 审批门 → '待审批 N 项 (gate 人话)' (无 → undefined)。 */
function qualityGate(approvals: ApprovalSummary[] | null | undefined): string | undefined {
  if (!Array.isArray(approvals)) return undefined;
  const pending = approvals.filter((a) => toDomainStatus(a?.status ?? null) === 'pending');
  if (pending.length === 0) return undefined;
  const gates = pending
    .map((a) => a?.gate)
    .filter((g): g is string => g != null && g.length > 0)
    .map((g) => GATE_LABELS[g] ?? g);
  const suffix = gates.length > 0 ? ` (${gates.join('、')})` : '';
  return `待审批 ${pending.length} 项${suffix}`;
}

/** qualitySummary.buildStatus: experience.total > 0 → '经验 N 条 · 成功率 P%' (无 → undefined)。 */
function qualityBuild(
  experience: ExperienceSummaryModel | null | undefined,
): string | undefined {
  if (experience == null) return undefined;
  const total = toNonNegativeInt(experience.total);
  if (total === 0) return undefined;
  return `经验 ${total} 条 · 成功率 ${percentLabel(experience.success_rate)}`;
}

// ------------------------------------------------------------------ toQualityGateViewModel (S10-015 Task 007)

/**
 * Quality Gate 输入 (组合真实数据; 全部可选, 缺失 → 降级, 不崩溃):
 *   approvals — GET /api/approvals (全局审批门; 主数据源)
 *   workflow  — GET /api/projects/{id}/workflow (阶段状态 → 架构/测试/构建检查)
 *   timeline  — GET /api/projects/{id}/timeline (org.approval./org.artifact. 事件 → 历史)
 */
export interface QualityGateInput {
  approvals?: ApprovalSummary[] | null;
  workflow?: WorkflowDetail | null;
  timeline?: TimelineEventSummary[] | null;
}

/** approval.status → QualityCheckStatus (未知/缺失 → unavailable, 不臆造)。 */
function approvalCheckStatus(status: string | null | undefined): QualityCheckStatus {
  const s = str(status).toLowerCase();
  if (s === 'approved' || s === 'passed' || s === 'completed' || s === 'done') return 'passed';
  if (s === 'rejected' || s === 'failed' || s === 'error') return 'failed';
  if (s === 'pending' || s === 'requested' || s === 'waiting') return 'pending';
  return 'unavailable';
}

/** 主审批门: 优先 pending, 同组按 requested_at 倒序取最新 (无 → null)。 */
function primaryApproval(approvals: ApprovalSummary[]): ApprovalSummary | null {
  if (approvals.length === 0) return null;
  const pending = approvals.filter((a) => str(a?.status).toLowerCase() === 'pending');
  const pool = pending.length > 0 ? pending : approvals;
  return (
    [...pool].sort(
      (a, b) => timeKey(str(b?.requested_at)) - timeKey(str(a?.requested_at)),
    )[0] ?? null
  );
}

/** PRD 审批: artifact_type=prd|product (product 也视为 PRD; 无 → null)。 */
function prdApprovalOf(approvals: ApprovalSummary[]): ApprovalSummary | null {
  return (
    approvals.find((a) => {
      const t = str(a?.artifact_type).toLowerCase();
      return t === 'prd' || t === 'product';
    }) ?? null
  );
}

/** workflow 阶段按 role_id/stage name 定位 (无匹配阶段 → undefined — 诚实 unavailable)。 */
function stageByRoleOrName(
  workflow: WorkflowDetail | null | undefined,
  roleIds: readonly string[],
  stageNames: readonly string[],
): StageSummary | undefined {
  for (const stage of workflow?.stages ?? []) {
    const role = str(stage?.role_id).toLowerCase();
    const name = str(stage?.name).toLowerCase();
    if (roleIds.includes(role) || stageNames.includes(name)) return stage;
  }
  return undefined;
}

/** 阶段检查 (Architecture/Tests/Build): 真实阶段状态 → 检查状态 (无阶段 → unavailable)。 */
function stageCheck(
  workflow: WorkflowDetail | null | undefined,
  roleIds: readonly string[],
  stageNames: readonly string[],
  labels: { unavailable: string; passed: string; failed: string; pending: string; running: string },
  name: string,
): QualityCheck {
  const stage = stageByRoleOrName(workflow, roleIds, stageNames);
  if (stage == null) return { name, status: 'unavailable', detail: labels.unavailable };
  const status = toDomainStatus(stage.status ?? null);
  switch (status) {
    case 'completed':
      return { name, status: 'passed', detail: labels.passed };
    case 'failed':
      return { name, status: 'failed', detail: labels.failed };
    case 'running':
      return { name, status: 'pending', detail: labels.running };
    case 'review':
      return { name, status: 'pending', detail: '等待人工评审' };
    case 'blocked':
      return { name, status: 'pending', detail: '前置依赖未就绪' };
    default:
      return { name, status: 'pending', detail: labels.pending };
  }
}

/** PRD Exists 检查: 从 PRD 审批真实状态推导 (无审批 → unavailable, 不编造 passed)。 */
function prdCheck(approval: ApprovalSummary | null): QualityCheck {
  if (approval == null) {
    return { name: 'PRD Exists', status: 'unavailable', detail: '无 PRD 审批记录' };
  }
  const status = approvalCheckStatus(approval.status);
  const version =
    approval.artifact_version != null ? ` v${approval.artifact_version}` : '';
  if (status === 'passed') return { name: 'PRD Exists', status, detail: `PRD${version} 已通过` };
  if (status === 'failed') return { name: 'PRD Exists', status, detail: `PRD${version} 未通过` };
  return { name: 'PRD Exists', status: 'pending', detail: `PRD${version} 已生成, 待审批` };
}

/** Human Approval 检查: 主审批门真实状态 (无审批 → unavailable)。 */
function approvalCheck(approval: ApprovalSummary | null): QualityCheck {
  if (approval == null) return { name: 'Human Approval', status: 'unavailable', detail: '无审批数据' };
  const status = approvalCheckStatus(approval.status);
  const by = str(approval.by);
  const suffix = by.length > 0 ? ` (by ${by})` : '';
  if (status === 'passed') return { name: 'Human Approval', status, detail: `已通过${suffix}` };
  if (status === 'failed') return { name: 'Human Approval', status, detail: `未通过${suffix}` };
  return { name: 'Human Approval', status: 'pending', detail: '等待人工审核' };
}

/** 当前质量 Gate 卡 (主审批门投影; 无 → null → UI Unavailable)。 */
function toCurrentGate(approval: ApprovalSummary | null): QualityGateInfo | null {
  if (approval == null) return null;
  const gate = str(approval.gate);
  return {
    name: gate.length > 0 ? (GATE_LABELS[gate] ?? gate) : '质量门',
    status: approvalCheckStatus(approval.status),
    ...(str(approval.artifact_type).length > 0 ? { artifactType: str(approval.artifact_type) } : {}),
    ...(approval.artifact_version != null ? { artifactVersion: approval.artifact_version } : {}),
    ...(typeof approval.confidence === 'number' ? { confidence: approval.confidence } : {}),
    ...(str(approval.risk).length > 0 ? { risk: str(approval.risk) } : {}),
    ...(str(approval.requested_at).length > 0 ? { requestedAt: str(approval.requested_at) } : {}),
  };
}

/** 质量决策 (pending → WAITING_FOR_REVIEW / approved → APPROVED / rejected → FAILED / 无 → UNKNOWN)。 */
function qualityDecision(approval: ApprovalSummary | null): QualityDecision {
  if (approval == null) return { status: 'UNKNOWN', label: '无法评估' };
  const s = str(approval.status).toLowerCase();
  const reason =
    approval.comment != null && approval.comment.length > 0 ? approval.comment : undefined;
  if (s === 'pending' || s === 'requested' || s === 'waiting') {
    return { status: 'WAITING_FOR_REVIEW', label: '等待人工审核', ...(reason != null ? { reason } : {}) };
  }
  if (s === 'approved' || s === 'passed' || s === 'completed' || s === 'done') {
    return { status: 'APPROVED', label: '已通过' };
  }
  if (s === 'rejected' || s === 'failed' || s === 'error') {
    return { status: 'FAILED', label: '未通过', ...(reason != null ? { reason } : {}) };
  }
  return { status: 'UNKNOWN', label: '无法评估' };
}

/** Human Approval 视图 (主审批门投影; 无 → null → UI Not available)。 */
function toApprovalView(approval: ApprovalSummary | null): QualityGateViewModel['approval'] {
  if (approval == null) return null;
  const status = approvalCheckStatus(approval.status);
  return {
    status: status === 'passed' ? 'approved' : status === 'failed' ? 'rejected' : 'pending',
    ...(str(approval.by).length > 0 ? { by: str(approval.by) } : {}),
    ...(str(approval.comment).length > 0 ? { comment: str(approval.comment) } : {}),
    ...(str(approval.requested_at).length > 0 ? { requestedAt: str(approval.requested_at) } : {}),
  };
}

/** Decision History: timeline org.approval./org.artifact. 事件 → 条目 (倒序; 无 → [])。 */
function qualityHistory(timeline: TimelineEventSummary[]): QualityGateViewModel['history'] {
  const relevant = timeline.filter((ev) => {
    const type = str(ev?.event_type);
    return type.startsWith('org.approval.') || type.startsWith('org.artifact.');
  });
  return toRuntimeActivity(relevant)
    .map((a) => ({ time: a.time, actor: a.actor, action: a.action, result: a.result }))
    .sort((a, b) => timeKey(b.time) - timeKey(a.time));
}

/**
 * Quality Gate 视图模型聚合 (S10-015 Task 007 — AI 生产交付标准界面)。
 *
 * 输入: approvals (GET /api/approvals) + workflow 实例 (GET /api/projects/{id}/workflow)
 *   + timeline (GET /api/projects/{id}/timeline) — 组合真实数据, 禁止 mock 冒充。
 * 输出: QualityGateViewModel 5 域 (UI 不直接依赖 API DTO — Adapter Layer):
 *   - currentGate: 主审批门 (pending 优先, requested_at 倒序) → 卡 (name/status/artifact/
 *     confidence/risk/requestedAt); 无审批 → null
 *   - checks: 5 项 Required Checks (PRD Exists ← PRD 审批; Architecture/Tests/Build ←
 *     workflow 阶段真实状态; Human Approval ← 主审批门); 无对应数据 → unavailable
 *   - decision: pending → WAITING_FOR_REVIEW / approved → APPROVED / rejected → FAILED /
 *     无审批 → UNKNOWN (UI Unavailable, 不编造质量结果)
 *   - approval: 主审批门 → {status, by?, comment?, requestedAt?}; 无 → null
 *   - history: timeline org.approval./org.artifact. 事件 → 倒序条目; 无 → []
 * 降级 (§6.3): 任何输入缺失/非法 → null/[]/UNKNOWN/unavailable, 不崩溃; 纯函数无副作用。
 */
export function toQualityGateViewModel(input?: QualityGateInput | null): QualityGateViewModel {
  const src = input ?? {};
  const approvals = Array.isArray(src.approvals) ? src.approvals : [];
  const workflow = src.workflow ?? null;
  const timeline = Array.isArray(src.timeline) ? src.timeline : [];
  const primary = primaryApproval(approvals);

  return {
    currentGate: toCurrentGate(primary),
    checks: [
      prdCheck(prdApprovalOf(approvals)),
      stageCheck(workflow, ['architect'], ['design', 'architecture'], {
        unavailable: '无架构阶段记录',
        passed: '架构阶段已完成',
        failed: '架构阶段失败',
        pending: '架构评审待进行',
        running: '架构评审进行中',
      }, 'Architecture Review'),
      stageCheck(workflow, ['tester', 'qa-engineer'], ['testing', 'test'], {
        unavailable: '无测试阶段记录',
        passed: '测试阶段已完成',
        failed: '测试阶段失败',
        pending: '测试待进行',
        running: '测试进行中',
      }, 'Tests Passed'),
      stageCheck(workflow, ['devops'], ['release'], {
        unavailable: '无发布阶段记录',
        passed: '发布阶段已完成',
        failed: '发布阶段失败',
        pending: '发布待进行',
        running: '发布进行中',
      }, 'Build Available'),
      approvalCheck(primary),
    ],
    decision: qualityDecision(primary),
    approval: toApprovalView(primary),
    history: qualityHistory(timeline),
  };
}
