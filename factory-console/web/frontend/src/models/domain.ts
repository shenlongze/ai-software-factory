/**
 * models/domain.ts — Frontend Domain Model (S10-014-plan §6.1)。
 *
 * AI Factory 前端业务语义模型 (人话), 与后端 JSON (models/types.ts) 解耦:
 *   - 全部为只读投影; 不携带任何执行/修改指令
 *   - 字段缺失用可选 (?) 表达 (§6.3 降级原则: 缺字段 → 默认值, 不崩溃)
 *   - 后端 JSON → Domain 转换由 api/domain.ts (Domain Adapter) 完成 — Task 007 实现
 */

/** 状态语义 (§4.2 状态色: 完成绿 / 执行中蓝 / 待办灰 / 阻塞紫 / 失败红 / 待审核橙)。 */
export type DomainStatus = 'completed' | 'running' | 'pending' | 'blocked' | 'failed' | 'review';

/** 项目生命周期阶段 (§5.1: 草稿/探索/定义/开发/发布/维护)。 */
export type ProjectLifecycleStage =
  | 'draft'
  | 'discovery'
  | 'definition'
  | 'development'
  | 'release'
  | 'maintenance';

/** Todo Tree 节点类型 (§5.2: 阶段 → 模块 → 任务)。 */
export type TreeNodeType = 'phase' | 'module' | 'task';

/** AI 员工状态 (§4.3 AgentCard: 可用/停用/废弃)。 */
export type AgentStatus = 'available' | 'disabled' | 'retired';

/** 工作台项目卡 (§6.1: id/名称/生命周期阶段+人话标签/完成度/待审数/风险数)。 */
export interface WorkspaceProject {
  id: string;
  name: string;
  lifecycleStage: ProjectLifecycleStage;
  lifecycleLabel: string;
  progress: number;
  pendingApprovals: number;
  riskCount: number;
}

// ------------------------------------------------------------------ Backlog 输入契约 (S10-015 Task 002)

/**
 * Backlog 层次条目 (Epic/Feature/Story 共用, 对齐真实 GET /api/projects/{id}/backlog)。
 *
 * 真实结构: 4 个平行数组 (epics/features/stories/tasks), 层级只靠自上而下的
 * `children` id 引用关联 (Epic.children → Feature id, Feature.children → Story id,
 * Story.children → Task id); Epic/Feature/Story 均无 status/进度字段
 * (节点状态只能从子 Task 聚合); 无回溯字段 (epic_id/feature_id/story_id)。
 */
export interface BacklogEpic {
  id?: string | null;
  name?: string | null;
  description?: string | null;
  /** 子 Feature id 引用 (悬空引用由 Adapter 跳过, 孤儿 children=[] 保留为空阶段)。 */
  children?: string[] | null;
  created_at?: string | null;
  updated_at?: string | null;
}

/** Feature (Epic 的子层, children = Story id 引用)。 */
export interface BacklogFeature {
  id?: string | null;
  name?: string | null;
  description?: string | null;
  children?: string[] | null;
  created_at?: string | null;
  updated_at?: string | null;
}

/** Story (Feature 的子层, children = Task id 引用; 无 status — 从子 Task 聚合)。 */
export interface BacklogStory {
  id?: string | null;
  name?: string | null;
  description?: string | null;
  children?: string[] | null;
  created_at?: string | null;
  updated_at?: string | null;
}

/** Task (Story 的子层, 唯一有 status 的执行单元; 后端六态 todo/ready/in_progress/blocked/review/done)。 */
export interface BacklogTask {
  id?: string | null;
  title?: string | null;
  description?: string | null;
  /** P0-P3 (完成度加权: P0=4/P1=3/P2=2/P3=1, 缺失=1)。 */
  priority?: string | null;
  /** 六态: todo/ready/in_progress/blocked/review/done。 */
  status?: string | null;
  assignee?: string | null;
  dependency?: string[] | null;
  created_at?: string | null;
  updated_at?: string | null;
  history?: Array<Record<string, unknown>> | null;
  /** 执行绑定 (方案A v1.1.141): exec request id EXR-* / 引擎任务 id; 空 = 未绑定。 */
  exec_ref?: string | null;
  /** 最近执行结果 id (EXS-*); 空 = 无。 */
  exec_result?: string | null;
}

/** GET /api/projects/{id}/backlog 响应 (4 个平行数组 + project_id)。 */
export interface BacklogResponse {
  project_id?: string | null;
  epics?: BacklogEpic[] | null;
  features?: BacklogFeature[] | null;
  stories?: BacklogStory[] | null;
  tasks?: BacklogTask[] | null;
}

/** 进度树节点 (§6.1: 阶段|模块|任务; 可选字段表达缺失 — §6.3 降级)。 */
export interface TreeNode {
  id: string;
  title: string;
  type: TreeNodeType;
  status: DomainStatus;
  statusLabel: string;
  progress: number;
  agent?: string;
  owner?: string;
  startedAt?: string;
  completedAt?: string;
  nextAction?: string;
  blockedReason?: string;
  children: TreeNode[];
}

/** 进度树 (§6.1: 单根树, 聚合由 Domain Adapter 完成)。 */
export interface TodoTree {
  root: TreeNode;
}

/** 流水线阶段 (§6.1: 顺序/角色 Agent/状态/当前任务/耗时/产物)。 */
export interface WorkflowStage {
  order: number;
  name: string;
  /** 后端角色 id (product-manager/ui-designer/…; 真实数据溯源, 缺失 → undefined)。 */
  roleId?: string;
  /** 人话 Agent 名 (ROLE_LABELS[role_id] ?? role_id; 缺失 → undefined)。 */
  agentName?: string;
  status: DomainStatus;
  statusLabel: string;
  currentTask?: string;
  duration?: number;
  artifact?: string;
  /** 阻塞原因 (blocked 阶段: 前置阶段人话 / 后端 failed_reason; 缺失 → undefined)。 */
  blockedReason?: string;
}

/** 流程流水线 (§6.1: 模板 + 阶段列表; S10-015 Task 004: 实例状态/is_mock 降级标记)。 */
export interface WorkflowPipeline {
  templateId: string;
  templateName: string;
  /** 实例状态 (workflow.status → DomainStatus; 缺失 → undefined)。 */
  status?: DomainStatus;
  /** mock 降级标记: 后端 is_mock=true → 演示数据 (前端必须显式标注, 不冒充真实执行)。 */
  isMock?: boolean;
  startedAt?: string;
  completedAt?: string;
  /** 工作流级失败原因 (后端 failed_reason; 缺失 → undefined)。 */
  failedReason?: string;
  stages: WorkflowStage[];
}

/** 活动条目 (RuntimeActivity 与 TaskDetail.history 共用结构, §6.1)。 */
export interface Activity {
  time: string;
  actor: string;
  action: string;
  result: string;
}

/** 实时活动 (§6.1: 时间/执行者/动作/结果; 项目名可选 — 全局流 vs 项目流)。 */
export interface RuntimeActivity extends Activity {
  projectName?: string;
  /** 关联阶段 id (timeline 事件 stage_id; Runtime Timeline 阶段定位用, 缺失 → undefined)。 */
  stageId?: string;
  /** 原始事件类型 (org.workflow.* / org.artifact.*; 缺失 → undefined)。 */
  eventType?: string;
}

/**
 * 任务详情 (Context Panel, §5.4: 状态/AI 员工/负责人/时间/下一步/阻塞/历史/产物)。
 * S10-015 Task 005 增强: 所属 Epic/Feature/Story (为什么存在) + priority/description/
 * dependency + agent (assignee → ROLE_LABELS 人话)。缺失字段 → undefined (诚实降级)。
 */
export interface TaskDetail {
  id: string;
  title: string;
  status: DomainStatus;
  statusLabel: string;
  /** 哪个 Agent (assignee → ROLE_LABELS 人话角色; 无 → undefined)。 */
  agent?: string;
  /** 谁负责 (assignee 原值; 空串归一 undefined)。 */
  owner?: string;
  /** 优先级 (P0-P3; 缺失 → undefined)。 */
  priority?: string;
  description?: string;
  /** 依赖任务 id 列表 (缺失 → undefined)。 */
  dependency?: string[];
  startedAt?: string;
  completedAt?: string;
  /** 下一步动作 (后端字段优先; 缺失 → 从 status 派生人话, 不臆造)。 */
  nextAction?: string;
  blockedReason?: string;
  /** 为什么存在 — 所属 Epic (backlog 定位; 缺失 → undefined)。 */
  epicName?: string;
  /** 为什么存在 — 所属 Feature (backlog 定位; 缺失 → undefined)。 */
  featureName?: string;
  /** 为什么存在 — 所属 Story (backlog 定位; 缺失 → undefined)。 */
  storyName?: string;
  /** 所属 Sprint (后端 backlog 无此字段 → 恒 undefined, 诚实降级)。 */
  sprintName?: string;
  /** 后端原始六态 (todo/ready/in_progress/blocked/review/done) — 操作按钮
      计算合法状态机路径用 (DomainStatus 已归一 pending/running, 丢失原始态)。 */
  rawStatus?: string;
  /** 执行绑定 (exec request id EXR-*); 空 = 未绑定 (审计溯源)。 */
  execRef?: string;
  /** 最近执行结果 id (EXS-*); 空 = 无 (审计溯源)。 */
  execResult?: string;
  history: Activity[];
  artifacts: string[];
}

/** AI 员工摘要 (§4.3 AgentCard: 头像/名称/状态/技能/版本/统计)。 */
export interface AgentSummary {
  id: string;
  name: string;
  role: string;
  status: AgentStatus;
  skills: string[];
  version: string;
  successRate?: number;
  avgDuration?: number;
}

// ------------------------------------------------------------------ Dashboard 视图模型 (S10-015 Task 006)

/** 执行中 AI 员工 (Dashboard 模块②: 名称/当前任务/所属工作流阶段/状态)。 */
export interface RunningAgent {
  agentName: string;
  /** 当前任务 (backend current_task; 无 → null 诚实)。 */
  currentTask: string | null;
  /** 所属 Workflow 阶段 (从运行中阶段 role 匹配人话名; 无 → null, 不编造)。 */
  workflowStage: string | null;
  status: DomainStatus;
}

/** 阻塞任务 (Dashboard 模块④: 任务名/原因/负责人/下一步; projectId 供跳转)。 */
export interface BlockedTask {
  taskName: string;
  /** 阻塞原因 (dependency 依赖任务标题翻译; 无 → undefined → UI '—' 诚实)。 */
  reason?: string;
  /** 负责人 Agent 人话名 (assignee → ROLE_LABELS; 无 → undefined)。 */
  ownerAgent?: string;
  /** 下一步动作 (从真实 status 派生: 解除阻塞后继续执行)。 */
  nextAction: string;
  /** 所属项目 id (点击 → #/project/{id}/todo; 无 → undefined)。 */
  projectId?: string;
}

/** 工作流状态项 (Dashboard 模块③: 项目 + 真实实例阶段链 + 当前阶段)。 */
export interface WorkflowStatusItem {
  projectId: string;
  projectName: string;
  status: DomainStatus;
  statusLabel: string;
  /** 当前阶段 (project.current_stage 真实值; 缺失 → undefined)。 */
  currentStage?: string;
  /** 阶段链 (workflow 实例 stages → WorkflowStage; 无实例 → [])。 */
  stages: WorkflowStage[];
}

/** 质量摘要 (Dashboard 模块⑥: 执行质量/审批门/构建经验; 无数据 → undefined → UI Unavailable)。 */
export interface QualitySummary {
  /** 执行质量: cost.calls + success_rate (无 → undefined)。 */
  tests?: string;
  /** 审批门: approvals pending (无 → undefined)。 */
  qualityGate?: string;
  /** 构建/经验: experience.total + success_rate (无 → undefined)。 */
  buildStatus?: string;
}

/** Dashboard 视图模型 (Control Center — 6 模块数据源; 全部真实聚合, 缺失 → 空/Unavailable)。 */
export interface DashboardViewModel {
  /** 我的项目 (复用 toWorkspaceProject; 无 → [])。 */
  projects: WorkspaceProject[];
  /** 当前执行 AI 员工 (agents status=RUNNING/EXECUTING…; 无 → [])。 */
  runningAgents: RunningAgent[];
  /** 工作流状态 (有真实 workflow 实例的项目; 无 → [])。 */
  workflowStatus: WorkflowStatusItem[];
  /** 阻塞任务 (backlog status=blocked; 无 → [])。 */
  blockedTasks: BlockedTask[];
  /** 最近活动 (timeline + activity 合并, 最近 N 条; 无 → [])。 */
  recentEvents: RuntimeActivity[];
  /** 质量摘要 (cost/approvals/experience; 无 → undefined → UI Unavailable)。 */
  qualitySummary: QualitySummary;
}

// ------------------------------------------------------------------ Quality Gate 视图模型 (S10-015 Task 007)

/**
 * Quality Gate 检查状态 (从真实数据推导; 后端无对应数据 → 'unavailable' — UI 显示
 * Unavailable, 禁止 fake passed/failed 冒充质量结果)。
 */
export type QualityCheckStatus = 'passed' | 'pending' | 'failed' | 'unavailable';

/** 质量检查项 (Required Checks: PRD/架构/测试/构建/人工审批; 真实状态 + 证据 detail)。 */
export interface QualityCheck {
  name: string;
  status: QualityCheckStatus;
  /** 状态说明 (真实证据: 产物版本/审批人/失败原因; 无 → undefined)。 */
  detail?: string;
}

/** 当前质量 Gate (审批门 + 产物信息; 无审批 → null → UI Unavailable)。 */
export interface QualityGateInfo {
  /** Gate 名 (gate → 人话: prd → PRD; 未知 → 原样)。 */
  name: string;
  /** Gate 状态 (approval.status → pending/passed/failed; 无审批 → unavailable)。 */
  status: QualityCheckStatus;
  /** 产物类型 (approval.artifact_type; 缺失 → undefined)。 */
  artifactType?: string;
  /** 产物版本 (approval.artifact_version; 缺失 → undefined)。 */
  artifactVersion?: number;
  /** AI 自评置信度 (approval.confidence — 真实值, 0 也是真实值; 缺失 → undefined)。 */
  confidence?: number;
  /** 风险等级 (approval.risk; 缺失 → undefined)。 */
  risk?: string;
  /** 审批请求时间 (approval.requested_at; 缺失 → undefined)。 */
  requestedAt?: string;
}

/** 质量决策状态 (4 态: 待人工审核/已通过/未通过/无法评估)。 */
export type QualityDecisionStatus =
  | 'WAITING_FOR_REVIEW'
  | 'APPROVED'
  | 'FAILED'
  | 'UNKNOWN';

/** 质量决策 (Quality Decision 模块; 无审批数据 → UNKNOWN → UI Unavailable)。 */
export interface QualityDecision {
  status: QualityDecisionStatus;
  /** 人话 label (等待人工审核/已通过/未通过/无法评估)。 */
  label: string;
  /** 决策依据 (approval.comment 真实意见; 无 → undefined)。 */
  reason?: string;
}

/** 人工审批视图 (Human Approval 模块; 无审批 → null → UI Not available)。 */
export interface QualityApproval {
  status: 'pending' | 'approved' | 'rejected';
  /** 审批人 (approval.by; 缺失 → undefined)。 */
  by?: string;
  /** 审批意见 (approval.comment; 缺失 → undefined)。 */
  comment?: string;
  /** 审批请求时间 (approval.requested_at; 缺失 → undefined)。 */
  requestedAt?: string;
}

/** 历史决策条目 (Decision History — timeline org.approval./org.artifact. 事件投影)。 */
export interface QualityHistoryItem {
  time: string;
  actor: string;
  action: string;
  result: string;
}

/**
 * Quality Gate 视图模型 (5 模块数据源, UI 不直接依赖 API DTO — Adapter Layer):
 *   - currentGate: 当前质量 Gate 卡 (无审批 → null)
 *   - checks:      Required Checks 5 项 (真实数据推导; 无数据 → unavailable)
 *   - decision:    Quality Decision (pending→WAITING_FOR_REVIEW / approved→APPROVED /
 *                  rejected→FAILED / 无审批→UNKNOWN)
 *   - approval:    Human Approval (无审批 → null)
 *   - history:     Decision History (timeline 质量事件倒序; 无 → [])
 * 降级 (§6.3): 任何输入缺失 → null/[]/UNKNOWN/unavailable, 不崩溃; 全部纯函数无副作用。
 */
export interface QualityGateViewModel {
  currentGate: QualityGateInfo | null;
  checks: QualityCheck[];
  decision: QualityDecision;
  approval: QualityApproval | null;
  history: QualityHistoryItem[];
}
