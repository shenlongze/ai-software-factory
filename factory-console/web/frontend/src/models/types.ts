/**
 * models/types.ts — 前端 TS 类型 (对齐 factory-console/models.py 11A 响应模型)。
 *
 * 全部为只读投影 (与后端 JSON 键一一对应); 不携带任何执行/修改指令。
 * 字段缺失用可选/null 表达 (后端失败安全: 无数据 → 空列表/None)。
 */

export interface ProjectSummary {
  id: string;
  name: string;
  description: string;
  language: string;
  repository: string;
  tech_stack: string[];
  status: string;
  lifecycle_stage: string | null;
  lifecycle_status: string | null;
  pending_approvals: number;
  tasks: Record<string, number>;
  last_activity: string | null;
  // S9-002: org 聚合 (当前 Workflow 运行 + 阶段链进度)
  workflow_id: string | null;
  workflow_name: string | null;
  workflow_status: string | null;
  current_stage: string | null;
  current_stage_status: string | null;
  progress: number;
  stage_counts: Record<string, number>;
}

export interface LifecycleSummary {
  project_id: string;
  lifecycle_id: string | null;
  idea_id: string | null;
  template_name: string;
  status: string;
  current_stage: Record<string, unknown> | null;
  completed_stages: string[];
  pending_approval: ApprovalSummary | null;
  next_actions: string[];
}

export interface ApprovalSummary {
  id: string;
  artifact_id: string;
  artifact_type: string;
  gate: string;
  status: string;
  confidence: number;
  risk: string | null;
  evidence: string[];
  idea_id: string | null;
  by: string;
  comment: string | null;
  requested_at: string | null;
  artifact_version: number | null;
}

export interface DecisionOption {
  id: string;
  name: string;
  score: number;
  factors: Record<string, number>;
  reasoning: string[];
  evidence: unknown[];
}

export interface DecisionSummary {
  id: string;
  decision_type: string;
  subject_id: string;
  description: string;
  status: string;
  options: DecisionOption[];
  recommendation: string | null;
  score: number;
  confidence: number;
  reasoning: string[];
  evidence: string[];
  risk: number;
  risk_level: string;
  requires_approval: boolean;
  approval_request_id: string | null;
  created_at: string | null;
}

export interface RecommendationSummary {
  id: string;
  target_type: string;
  candidate: string;
  score: number;
  factors: Record<string, number>;
  explanation: string[];
  evidence: string[];
  confidence: number;
  risk: number;
  created_at: string | null;
}

export interface ExperienceSummary {
  id: string;
  domain: string;
  subject: string;
  result: string;
  score: number;
  confidence: number;
  freshness: number;
  task_type: string;
  capability: string[];
  created_at: string | null;
}

export interface ProviderSummary {
  id: string;
  name: string;
  type: string;
  status: string;
  capabilities: string[];
  models: string[];
  version: string;
  cost: number | null;
  performance: number | null;
  experience: number | null;
  usage_calls: number;
}

export interface CostSummary {
  total_cost: number;
  calls: number;
  success_rate: number;
  avg_cost: number;
  total_tokens: number;
  by_provider: Record<string, Record<string, number | string>>;
}

export interface ExperienceSummaryModel {
  total: number;
  by_domain: Record<string, number>;
  success_rate: number;
  avg_score: number;
  avg_confidence: number;
}

export interface AgentSummary {
  id: string;
  name: string;
  role: string;
  status: string;
  skills: string[];
  current_task: string | null;
}

export interface EventSummary {
  seq: number;
  type: string;
  timestamp: string;
  source: string;
  project_id: string | null;
  task_id: string | null;
  action: string | null;
  result: string | null;
}

/** ConsoleDashboard 七域 (11A ConsoleDashboard 投影)。 */
export interface ConsoleDashboard {
  projects: ProjectSummary[];
  approvals: ApprovalSummary[];
  agents: AgentSummary[];
  decisions: DecisionSummary[];
  cost: CostSummary;
  experience: ExperienceSummaryModel;
  activity: EventSummary[];
}

/** 决策选项评分因素 (capability/cost/performance/experience)。 */
export const FACTOR_LABELS: Record<string, string> = {
  capability: 'Capability',
  cost: 'Cost',
  performance: 'Performance',
  experience: 'Experience',
};

export function factorLabel(key: string): string {
  return FACTOR_LABELS[key] ?? key;
}

// ------------------------------------------------------------------ S9-002 org 投影类型

/** org ApprovalGate 投影 (S9-001 审批门; Console 决定操作对象)。 */
export interface ApprovalGateSummary {
  id: string;
  stage_id: string;
  workflow_id: string;
  project_id: string;
  status: string;
  reviewer: string;
  comment: string;
  requested_at: string | null;
  approved_at: string | null;
  rejected_at: string | null;
}

/** POST /approvals/{id}/approve|reject 决定结果投影。 */
export interface ApprovalDecisionSummary {
  action: string;
  gate: ApprovalGateSummary;
  workflow_id: string;
  workflow_status: string;
}

/** org Artifact 只读投影 (6 类产物链: prd/ui/architecture/code/test/release…)。 */
export interface ArtifactSummary {
  id: string;
  stage_id: string;
  workflow_id: string;
  project_id: string;
  type: string;
  ref: string;
  version: string;
  status: string;
  producer_role: string;
  producer_agent: string;
  location: string;
  created_at: string | null;
  updated_at: string | null;
}

/** 阶段链节点投影 (status/role/artifact)。 */
export interface StageSummary {
  id: string;
  workflow_id: string;
  role_id: string;
  name: string;
  order: number;
  status: string;
  depends_on: string[];
  input_artifacts: string[];
  output_artifacts: string[];
  approval_required: boolean;
  artifact: ArtifactSummary | null;
  pending_approval: ApprovalGateSummary | null;
}

/** 组织级 Workflow 运行摘要。 */
export interface WorkflowSummary {
  id: string;
  project_id: string;
  project_name: string;
  name: string;
  status: string;
  stage_count: number;
  completed_count: number;
  progress: number;
  current_stage: string | null;
  current_stage_status: string | null;
  failed_reason: string;
}

/** 单 Workflow 8 阶段链全视图。 */
export interface WorkflowDetail {
  id: string;
  project_id: string;
  project_name: string;
  name: string;
  status: string;
  failed_reason: string;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  stages: StageSummary[];
  pending_approvals: ApprovalGateSummary[];
  template: string[];
}

/** 规范 8 阶段链 (与后端 WORKFLOW_TEMPLATE 同源; 前端标签/占位映射)。 */
export const STAGE_TEMPLATE: readonly string[] = [
  'Idea',
  'PM',
  'Product',
  'UX/UI',
  'Architecture',
  'Development',
  'Test',
  'Release',
];

/** Artifact 类型中文标签 (6 类 Viewer 分组; 未知类型原样显示)。 */
export const ARTIFACT_TYPE_LABELS: Record<string, string> = {
  idea: 'Idea',
  product: 'Product',
  ux_ui: 'UX/UI',
  prd: 'PRD',
  design: 'Design',
  code: 'Code',
  test: 'Test',
  bug_report: 'Bug Report',
  release: 'Release',
};

export function artifactTypeLabel(type: string): string {
  return ARTIFACT_TYPE_LABELS[type] ?? type;
}
