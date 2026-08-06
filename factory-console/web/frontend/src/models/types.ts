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
