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
  DomainStatus,
  ProjectLifecycleStage,
  RuntimeActivity,
  TaskDetail,
  TodoTree,
  TreeNode,
  TreeNodeType,
  WorkflowPipeline,
  WorkflowStage,
  WorkspaceProject,
} from '../models/domain';
import {
  artifactTypeLabel,
  type ProjectSummary,
  type StageRunSummary,
  type StageSummary,
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
  return buildAggregateNode(feature.id, feature.name, 'module', weighted);
}

/** Story → task 节点 (状态从子 Task 聚合, 规则 §3.4; children = Task 执行单元)。 */
function toStoryNode(
  story: BacklogStory,
  taskIndex: Map<string, BacklogTask>,
): WeightedNode {
  const weighted = (story.children ?? [])
    .map((id) => taskIndex.get(id))
    .filter((t): t is BacklogTask => t != null)
    .map((task) => toTaskNode(task));
  const status = aggregateStoryStatus(weighted.map((w) => w.node));
  return {
    node: {
      id: story.id ?? '',
      title: story.name ?? '',
      type: 'task',
      status,
      statusLabel: statusLabel(status),
      progress: weightedProgress(weighted),
      children: weighted.map((w) => w.node),
    },
    weight: sumWeights(weighted),
  };
}

/** Task → task 叶子节点 (完成 → 100%, 其余 → 0%; 权重 = priorityWeight)。 */
function toTaskNode(task: BacklogTask): WeightedNode {
  const status = toDomainStatus(task.status ?? null);
  return {
    node: {
      id: task.id ?? '',
      title: task.title ?? '',
      type: 'task',
      status,
      statusLabel: statusLabel(status),
      progress: status === 'completed' ? 100 : 0,
      children: [],
    },
    weight: priorityWeight(task.priority),
  };
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
  return {
    node: {
      id: id ?? '',
      title: title ?? '',
      type,
      status,
      statusLabel: statusLabel(status),
      progress: weightedProgress(weighted),
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
}

/** backlog/task/{id} + timeline → TaskDetail (字段映射 + history 投影; 缺失 → undefined/[])。 */
export function toTaskDetail(taskRaw?: TaskDetailInput | null): TaskDetail {
  const t = taskRaw ?? {};
  const status = toDomainStatus(t.status ?? null);
  return {
    id: t.id ?? '',
    title: t.title ?? t.name ?? '',
    status,
    statusLabel: statusLabel(status),
    agent: t.agent ?? undefined,
    owner: t.owner ?? t.assignee ?? undefined,
    startedAt: t.started_at ?? t.startedAt ?? undefined,
    completedAt: t.completed_at ?? t.completedAt ?? undefined,
    nextAction: t.next_action ?? t.nextAction ?? undefined,
    blockedReason: t.blocked_reason ?? t.blockedReason ?? undefined,
    history: (t.history ?? []).map(toActivity),
    artifacts: Array.isArray(t.artifacts) ? t.artifacts : [],
  };
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
  'stage.started': '阶段开始',
  'stage.completed': '阶段完成',
  'task.started': '开始任务',
  'task.completed': '完成任务',
  error: '发生错误',
};

/** timeline + events/stream → RuntimeActivity[] (事件 → 活动条目; 空/非数组 → [])。
 *
 * 输入兼容 TimelineEventSummary (created_at/message/status/agent_id) 与
 * EventSummary (timestamp/source/action/result)。projectName 可选 (全局流)。
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
    return {
      time: str(raw.created_at ?? raw.timestamp ?? raw.time),
      actor: str(raw.agent_id ?? raw.source ?? raw.actor),
      action,
      result: str(raw.result ?? raw.status),
      ...(projectName != null && projectName.length > 0 ? { projectName } : {}),
    };
  });
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
