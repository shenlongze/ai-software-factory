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
  agentName?: string;
  status: DomainStatus;
  statusLabel: string;
  currentTask?: string;
  duration?: number;
  artifact?: string;
}

/** 流程流水线 (§6.1: 模板 + 阶段列表)。 */
export interface WorkflowPipeline {
  templateId: string;
  templateName: string;
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
}

/** 任务详情 (Context Panel, §5.4: 状态/AI 员工/负责人/时间/下一步/阻塞/历史/产物)。 */
export interface TaskDetail {
  id: string;
  title: string;
  status: DomainStatus;
  statusLabel: string;
  agent?: string;
  owner?: string;
  startedAt?: string;
  completedAt?: string;
  nextAction?: string;
  blockedReason?: string;
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
