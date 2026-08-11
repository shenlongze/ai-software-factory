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
  DomainStatus,
  ProjectLifecycleStage,
  RuntimeActivity,
  TaskDetail,
  TodoTree,
  TreeNode,
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
  blocked: 'blocked',
  failed: 'failed',
  error: 'failed',
  errored: 'failed',
  review: 'review',
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

// ------------------------------------------------------------------ toTodoTree

/** backlog 节点宽松输入 (后端无专用 backlog 结构时的前端投影; 缺字段 → 降级)。 */
export interface BacklogNodeInput {
  id?: string | null;
  title?: string | null;
  name?: string | null;
  type?: string | null;
  status?: string | null;
  progress?: number | null;
  agent?: string | null;
  owner?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  next_action?: string | null;
  blocked_reason?: string | null;
  features?: BacklogNodeInput[];
  items?: BacklogNodeInput[];
  children?: BacklogNodeInput[];
}

/** backlog 聚合输入: { epics: [...] } 或裸数组 (视为 epics)。 */
export interface BacklogInput {
  epics?: BacklogNodeInput[];
}

/** 项目级降级树阶段 (从 lifecycle 派生: 产品/开发/测试发布)。 */
const FALLBACK_PHASES: ReadonlyArray<{ id: string; title: string }> = [
  { id: 'product', title: '产品设计' },
  { id: 'development', title: '开发' },
  { id: 'release', title: '测试发布' },
];

/** backlog + runtime 投影 → TodoTree。
 *
 * 聚合: epic → phase, feature → module, task → task (三层)。
 * 降级: 无 backlog / 结构不匹配 → 项目级降级树 (单根 = 项目名, 阶段从 lifecycle
 *       + workflow 信号 (failed/blocked/stage_counts) 派生), 不崩溃 (§6.3)。
 */
export function toTodoTree(
  project?: ProjectSummary | null,
  backlog?: BacklogInput | BacklogNodeInput[] | null,
  _runtime?: unknown,
): TodoTree {
  const source = project ?? ({} as ProjectSummary);
  const rootTitle = source.name ?? '';
  const epics = extractEpics(backlog);
  if (epics.length > 0) {
    const phases = epics.map((epic) => toPhaseNode(epic));
    return { root: aggregateRoot(source, rootTitle, phases) };
  }
  return { root: fallbackRoot(source, rootTitle) };
}

/** backlog 输入 → epics 数组 (数组 → 视为 epics; 缺 → [])。 */
function extractEpics(
  backlog: BacklogInput | BacklogNodeInput[] | null | undefined,
): BacklogNodeInput[] {
  if (Array.isArray(backlog)) return backlog;
  const epics = backlog?.epics;
  return Array.isArray(epics) ? epics : [];
}

/** epic → phase 节点 (feature → module → task)。 */
function toPhaseNode(epic: BacklogNodeInput): TreeNode {
  const children = (epic.features ?? []).map((feature) => toModuleNode(feature));
  return {
    id: epic.id ?? '',
    title: epic.title ?? epic.name ?? '',
    type: 'phase',
    status: toDomainStatus(epic.status ?? null),
    statusLabel: statusLabel(epic.status ?? null),
    progress: nodeProgress(epic, children),
    agent: epic.agent ?? undefined,
    owner: epic.owner ?? undefined,
    startedAt: epic.started_at ?? undefined,
    completedAt: epic.completed_at ?? undefined,
    nextAction: epic.next_action ?? undefined,
    blockedReason: epic.blocked_reason ?? undefined,
    children,
  };
}

/** feature → module 节点 (items/children → task 节点)。 */
function toModuleNode(feature: BacklogNodeInput): TreeNode {
  const children = (feature.items ?? feature.children ?? []).map((item) => toTaskNode(item));
  return {
    id: feature.id ?? '',
    title: feature.title ?? feature.name ?? '',
    type: 'module',
    status: toDomainStatus(feature.status ?? null),
    statusLabel: statusLabel(feature.status ?? null),
    progress: nodeProgress(feature, children),
    agent: feature.agent ?? undefined,
    owner: feature.owner ?? undefined,
    startedAt: feature.started_at ?? undefined,
    completedAt: feature.completed_at ?? undefined,
    nextAction: feature.next_action ?? undefined,
    blockedReason: feature.blocked_reason ?? undefined,
    children,
  };
}

/** item → task 节点 (叶子)。 */
function toTaskNode(item: BacklogNodeInput): TreeNode {
  return {
    id: item.id ?? '',
    title: item.title ?? item.name ?? '',
    type: 'task',
    status: toDomainStatus(item.status ?? null),
    statusLabel: statusLabel(item.status ?? null),
    progress: nodeProgress(item, []),
    agent: item.agent ?? undefined,
    owner: item.owner ?? undefined,
    startedAt: item.started_at ?? undefined,
    completedAt: item.completed_at ?? undefined,
    nextAction: item.next_action ?? undefined,
    blockedReason: item.blocked_reason ?? undefined,
    children: [],
  };
}

/** 节点进度: 显式 progress (0..1) → 0..100; 否则子节点均值 (无子 → 0)。 */
function nodeProgress(node: BacklogNodeInput, children: TreeNode[]): number {
  if (typeof node.progress === 'number' && Number.isFinite(node.progress)) {
    return progressPercent(node.progress);
  }
  return aggregateProgress(children);
}

/** 聚合根节点 (backlog 路径): 状态/进度从子阶段派生。 */
function aggregateRoot(source: ProjectSummary, title: string, phases: TreeNode[]): TreeNode {
  const status = aggregateStatus(phases);
  return {
    id: source.id ?? '',
    title,
    type: 'phase',
    status,
    statusLabel: statusLabel(status),
    progress: aggregateProgress(phases),
    children: phases,
  };
}

/** 聚合状态: failed > blocked > running > review > completed > pending。 */
function aggregateStatus(nodes: TreeNode[]): DomainStatus {
  const priority: DomainStatus[] = ['failed', 'blocked', 'running', 'review', 'completed', 'pending'];
  for (const p of priority) {
    if (nodes.some((n) => n.status === p)) return p;
  }
  return 'pending';
}

/** 聚合进度: 子节点均值 (空 → 0)。 */
function aggregateProgress(nodes: TreeNode[]): number {
  if (nodes.length === 0) return 0;
  const sum = nodes.reduce((acc, n) => acc + n.progress, 0);
  return Math.round(sum / nodes.length);
}

/** 项目级降级树 (无 backlog): 单根 = 项目名, 3 阶段从 lifecycle/workflow 信号派生。 */
function fallbackRoot(source: ProjectSummary, title: string): TreeNode {
  const phases = deriveFallbackPhases(source).map(({ phase, status }) => ({
    id: `${source.id ?? 'project'}:phase:${phase.id}`,
    title: phase.title,
    type: 'phase' as const,
    status,
    statusLabel: statusLabel(status),
    progress: phaseProgress(status),
    children: [],
  }));
  return aggregateRoot(source, title, phases);
}

/** 降级阶段进度: completed → 100, running/review → 50, 其余 → 0。 */
function phaseProgress(status: DomainStatus): number {
  switch (status) {
    case 'completed':
      return 100;
    case 'running':
    case 'review':
      return 50;
    default:
      return 0;
  }
}

/** 降级阶段状态派生 (顺序): lifecycle/status 基础 → 完成信号 → failed → blocked → running 增强。 */
function deriveFallbackPhases(
  source: ProjectSummary,
): Array<{ phase: { id: string; title: string }; status: DomainStatus }> {
  const statuses = ['pending', 'pending', 'pending'] as DomainStatus[];
  const lifecycleKey = source.lifecycle_stage ?? source.status ?? '';
  switch (lifecycleKey) {
    case 'draft':
    case 'idea':
      break; // 全 pending
    case 'discovery':
    case 'definition':
      statuses[0] = 'running';
      break;
    case 'development':
    case 'build':
    case 'active':
    case 'running':
      statuses[0] = 'completed';
      statuses[1] = 'running';
      break;
    case 'release':
      statuses[0] = 'completed';
      statuses[1] = 'completed';
      statuses[2] = 'running';
      break;
    case 'maintenance':
    case 'completed':
    case 'done':
    case 'success':
    case 'archived':
      statuses[0] = 'completed';
      statuses[1] = 'completed';
      statuses[2] = 'completed';
      break;
    case 'failed':
      statuses[0] = 'completed';
      statuses[1] = 'failed';
      break;
    case 'paused':
      statuses[0] = 'completed';
      break;
    default:
      break; // 未知 → 全 pending
  }

  const counts = source.stage_counts ?? {};
  // workflow 完成信号: 3+ 阶段完成 → 全部 completed
  if (toNonNegativeInt(counts.completed) >= 3) {
    return FALLBACK_PHASES.map((phase) => ({ phase, status: 'completed' as DomainStatus }));
  }
  // failed 信号 → 第一个未完成阶段 failed
  const failedSignal =
    source.workflow_status === 'failed' ||
    source.current_stage_status === 'failed' ||
    toNonNegativeInt(counts.failed) > 0;
  if (failedSignal) {
    const idx = statuses.findIndex((s) => s !== 'completed');
    if (idx >= 0) statuses[idx] = 'failed';
  }
  // blocked 信号 → 第一个未完成且未失败阶段 blocked (不覆盖 failed)
  const blockedSignal =
    source.current_stage_status === 'blocked' || toNonNegativeInt(counts.blocked) > 0;
  if (blockedSignal) {
    const idx = statuses.findIndex((s) => s !== 'completed' && s !== 'failed');
    if (idx >= 0) statuses[idx] = 'blocked';
  }
  // running 增强: 无 lifecycle 派生状态时, 用 stage_counts 推进阶段 (completed N 个 → 第 N+1 运行中)
  if (
    toNonNegativeInt(counts.running) > 0 &&
    toNonNegativeInt(counts.completed) > 0 &&
    statuses.every((s): boolean => s === 'pending')
  ) {
    const done = Math.min(toNonNegativeInt(counts.completed), 2);
    for (let i = 0; i < done; i += 1) statuses[i] = 'completed';
    statuses[Math.min(done, 2)] = 'running';
  }

  return FALLBACK_PHASES.map((phase, i) => ({ phase, status: statuses[i] }));
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
};

/** 流水线阶段输入: WorkflowDetail.stages (StageSummary) 或 /workflows/{id}/stages (StageRunSummary)。 */
type StageInput = StageSummary | StageRunSummary;

/** GET /api/projects/{id}/workflow + stages → WorkflowPipeline。
 *
 * 阶段: 名称/角色人话映射, pending_approval → review; 降级: 无 workflow →
 * templateName='未启动', stages=[] (§6.3 不崩溃)。
 */
export function toWorkflowPipeline(
  project?: ProjectSummary | null,
  workflowDetail?: WorkflowDetail | null,
  stages?: StageRunSummary[] | null,
): WorkflowPipeline {
  const source = project ?? ({} as ProjectSummary);
  const detail = workflowDetail ?? null;
  const stageInputs: StageInput[] = stages ?? detail?.stages ?? [];
  return {
    templateId: detail?.id ?? source.workflow_id ?? '',
    templateName: detail?.name ?? source.workflow_name ?? '未启动',
    stages: stageInputs.map((s, index) => toWorkflowStage(s, index)),
  };
}

/** 单阶段映射 (order/名称/角色/状态/耗时/产物; 缺失 → 可选字段 undefined)。 */
function toWorkflowStage(s: StageInput, index: number): WorkflowStage {
  const pendingApproval = (s as StageSummary).pending_approval;
  const status: DomainStatus =
    pendingApproval != null && pendingApproval.status === 'pending'
      ? 'review'
      : toDomainStatus(s.status);
  const roleId = s.role_id ?? '';
  return {
    order: s.order ?? index + 1,
    name: STAGE_NAME_LABELS[s.name] ?? s.name,
    agentName: agentNameOf(s, roleId),
    status,
    statusLabel: statusLabel(status),
    currentTask: currentTaskOf(s),
    duration: (s as StageRunSummary).duration_s ?? undefined,
    artifact: artifactRefOf(s),
  };
}

/** agent 名: StageRunSummary.agent_id 优先 (原样), 否则 role_id → 人话 (未知原样)。 */
function agentNameOf(s: StageInput, roleId: string): string | undefined {
  const agentId = (s as StageRunSummary).agent_id;
  if (agentId != null && agentId.length > 0) return agentId;
  if (roleId == null || roleId.length === 0) return undefined;
  return ROLE_LABELS[roleId] ?? roleId;
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
