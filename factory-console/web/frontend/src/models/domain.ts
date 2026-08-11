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
