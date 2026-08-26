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
  starred?: boolean;                   // 收藏/关注 (Founder 2026-08-26; 旧数据缺省=未收藏)
  archived?: boolean;                  // 归档 (软归档可恢复, 2026-08-26)
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

/** POST /api/projects 创建结果 (S10-006.5 用户创建闭环投影)。 */
export interface ProjectCreatedSummary {
  project_id: string;
  name: string;
  idea: string;
  status: string;
}

/** POST /api/projects/suggest — AI 想法理解 (S10-007 阶段三增强: 想法确认对话)。

 * 用户输入想法 → AI 提议名称/一句话理解/1-3 澄清问题 → 前端确认卡 (名称可编辑)
 * → 确认后 POST /projects {idea, name} 创建。ai_generated=false → 诚实
 * fallback (规则提炼, questions=[] — 前端标注"快速模式", 不冒充 AI 理解)。
 */
export interface IdeaSuggestion {
  idea: string;
  suggested_name: string;
  slug: string;
  summary: string;
  questions: string[];
  ai_generated: boolean;
}

/** PATCH /api/projects/{id} 更新结果 (S10-006.5 项目管理: 重命名/改 idea)。 */
export interface ProjectUpdatedSummary {
  project_id: string;
  name: string;
  idea: string;
  status: string;
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

/** 单产物详情 (S9-003 Review 数据源: metadata 契约载荷 + review 审批门)。 */
export interface ArtifactDetail extends ArtifactSummary {
  metadata: Record<string, unknown>;
  review: ApprovalGateSummary | null;
}

/** S10-005: GET /artifacts/{id}/content — 产物渲染内容 (Code diff 兜底 /
 * Release 下载源; 文件缺失/越界 → content null 失败安全)。 */
export interface ArtifactContent {
  artifact_id: string;
  type: string;
  location: string;
  content: string | null;
}

/** S10-006: 审核反馈记录 (Feedback Loop — GET/POST /api/review-feedback)。

 * Reject 决定后前端同时保存的结构化驳回意见: round 按产物递增 (第几轮
 * 反馈), 作为下一轮 Agent 重生成输入的数据源; 与 gate.comment (S9-001
 * 审计落库) 并列的 Loop 数据流。 */
export interface ReviewFeedback {
  id: string;
  gate_id: string;
  artifact_id: string;
  reviewer: string;
  comment: string;
  round: number;
  created_at: string | null;
}

/** S10-006: 审核门 → 待审清单摘要 (Review Queue 行: 门 + 对应产物)。 */
export interface ReviewQueueItem {
  gate: ApprovalGateSummary;
  /** 门对应产物 (按 stage_id 匹配; 无 → null — 只读展示, 无法决定)。 */
  artifact: ArtifactSummary | null;
}

/** PRD (product Artifact) Review 节 (S9-003 任务规格 6 节)。 */
export const PRODUCT_SECTIONS: readonly { key: string; label: string }[] = [
  { key: 'market_analysis', label: '市场分析' },
  { key: 'user_persona', label: '用户画像' },
  { key: 'user_journey', label: '用户旅程' },
  { key: 'feature_list', label: '功能列表' },
  { key: 'mvp_scope', label: 'MVP 范围' },
  { key: 'user_stories', label: '用户故事' },
];

/** UX/UI Artifact Review 节 (7 节; wireframe 特殊渲染 — ASCII 预览)。 */
export const UXUI_SECTIONS: readonly { key: string; label: string }[] = [
  { key: 'information_architecture', label: '信息架构' },
  { key: 'user_flow', label: '用户流程' },
  { key: 'wireframe', label: '线框图' },
  { key: 'screen_specifications', label: '屏幕规格' },
  { key: 'component_definition', label: '组件定义' },
  { key: 'design_tokens', label: '设计令牌' },
  { key: 'prototype', label: '原型说明' },
];

/** wireframe Screen (S8-002 UX/UI Designer 产物结构: 机器可读 ASCII 布局)。 */
export interface WireframeScreen {
  name: string;
  ascii: string;
  components: string[];
  actions: string[];
}

/** S10-005: design Artifact (Architect S8-003 输出) Review 节 — org CONTRACTS
 * design 契约 7 键 (system_architecture/technical_stack/database_design/api_design/
 * frontend_architecture/backend_architecture/task_breakdown)。 */
export const ARCHITECTURE_SECTIONS: readonly { key: string; label: string }[] = [
  { key: 'system_architecture', label: '系统架构' },
  { key: 'technical_stack', label: '技术栈' },
  { key: 'database_design', label: '数据库设计' },
  { key: 'api_design', label: 'API 设计' },
  { key: 'frontend_architecture', label: '前端架构' },
  { key: 'backend_architecture', label: '后端架构' },
  { key: 'task_breakdown', label: '任务拆解' },
];

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
  /** S10-002: mock fallback 标记 (后端数据缺失 → 演示数据, 前端据此显示标识)。 */
  is_mock?: boolean;
}

/** S10-002: 阶段运行明细 (Task 面板数据源 — GET /workflows/{id}/stages)。 */
export interface StageRunSummary {
  id: string;
  workflow_id: string;
  role_id: string;
  name: string;
  order: number;
  status: string;
  /** 执行 Agent (org 无独立 Agent 实体 — 角色即执行者, agent_id = role_id)。 */
  agent_id: string | null;
  /** 从事件流推导 (stage_started → stage_completed 时间戳差; 缺 → null)。 */
  duration_s: number | null;
  /** org 未跟踪成本 → null (诚实; 仅 mock 数据带示例值)。 */
  cost_usd: number | null;
  started_at: string | null;
  completed_at: string | null;
  depends_on: string[];
  input_artifacts: string[];
  output_artifacts: string[];
  artifacts: ArtifactSummary[];
}

/** S10-002: Timeline 事件节点 (Agent Timeline 数据源 — GET /projects/{id}/timeline)。 */
export interface TimelineEventSummary {
  id: string;
  seq: number;
  project_id: string;
  /** user | stage | artifact | review | error (api-data-model §1)。 */
  type: string;
  event_type: string;
  stage_id: string | null;
  agent_id: string | null;
  artifact_id: string | null;
  gate_id: string | null;
  message: string;
  status: string | null;
  payload: Record<string, unknown>;
  created_at: string | null;
}

/** S10-002: Runtime Instance 基础模型 (workspace-architecture.md §4; 只建模型)。

 * type: browser|terminal (沙箱实例类型); status: starting|running|stopped|error
 * (生命周期状态机); artifact_id: 绑定产物 (browser 预览 ux_ui/code/release 对应
 * 产物, 无 → null); url: browser 预览地址 / session: terminal 会话标识 (按 type
 * 二选一, 未就绪 → null); created_at: UTC 时间戳。S10-004 实现实例/生命周期。
 */
export interface RuntimeInstance {
  id: string;
  project_id: string;
  type: 'browser' | 'terminal';
  status: 'starting' | 'running' | 'stopped' | 'error';
  artifact_id: string | null;
  url: string | null;
  session: string | null;
  created_at: string | null;
}

/** Runtime 状态中文标签 (Runtime Panel 状态徽章显示)。 */
export const RUNTIME_STATUS_LABELS: Record<RuntimeInstance['status'], string> = {
  starting: '启动中',
  running: '运行中',
  stopped: '已停止',
  error: '异常',
};

/** Runtime 类型中文标签 (创建菜单/卡片类型图标 title)。 */
export const RUNTIME_TYPE_LABELS: Record<RuntimeInstance['type'], string> = {
  browser: 'Browser Runtime',
  terminal: 'Terminal Runtime',
};

export function runtimeTypeLabel(type: string): string {
  return RUNTIME_TYPE_LABELS[type as RuntimeInstance['type']] ?? type;
}

/** S10-004: Runtime 截图记录 (截图反馈预留 — 只落记录, 不实现完整 Loop)。 */
export interface RuntimeScreenshot {
  id: string;
  instance_id: string;
  project_id: string;
  /** 预留产物引用 (完整 Feedback Loop 后续实现)。 */
  artifact_id: string;
  created_at: string | null;
}

/** S10-016: Runtime Session 事件 (执行会话时间线条目 — 内嵌于 session.events)。 */
export interface RuntimeEventPayload {
  event_id: string;
  session_id: string;
  /** RuntimeEventType: agent_started/task_received/thinking_started/decision_created/
   * tool_requested/tool_started/tool_completed/tool_failed/execution_completed 等。 */
  type: string;
  message: string;
  created_at: string | null;
  data: Record<string, unknown> | null;
}

/** S10-016: Runtime Session (Agent 执行会话记录 — 后端 exec.runtime_session)。

 * session_id/agent_id/task_id/workflow_id: 会话身份字段 (workflow_id 可选);
 * status: 五态状态机 pending|running|success|failed|cancelled; started_at/
 * finished_at: 生命周期时间戳 (未发生 → null); events: 保序事件链 (终态冻结)。
 * API 数据源: POST /api/agents/{id}/sessions + /api/runtime-sessions/*。
 */
export interface RuntimeSessionPayload {
  session_id: string;
  agent_id: string;
  task_id: string;
  workflow_id: string;
  status: 'pending' | 'running' | 'success' | 'failed' | 'cancelled' | string;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  events: RuntimeEventPayload[];
}

/** S10-016 Task 002: POST /api/runtime/execute 响应 (Agent Executor 执行结果)。 */
export interface ExecuteResponse {
  runtime_session_id: string;
  status: 'pending' | 'running' | 'success' | 'failed' | 'cancelled' | string;
  output?: {
    execution_output?: string;
    execution_summary?: string;
    raw_response?: string;
  } | null;
  /** S10-017 Task 001: Agent Execution Loop 步骤记录 (RECEIVE_TASK→ANALYZE→DECISION→FINAL)。 */
  execution_steps?: ExecutionStep[];
}

/** S10-017 Task 001: Agent 内部执行步骤 (Goal→Reason→Act→Observe→Complete)。 */
export interface ExecutionStep {
  id: string;
  session_id: string;
  step_number: number;
  step_type:
    | 'RECEIVE_TASK'
    | 'ANALYZE'
    | 'DECISION'
    | 'ACTION'
    | 'OBSERVATION'
    | 'FINAL'
    | string;
  input?: string | null;
  output?: string | null;
  status: string;
  created_at: string | null;
}

/** S10-018 Task 001: Tool Runtime — GET /api/tools 返回的工具清单项。 */
export interface ToolInfo {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
}

/** S10-018 Task 001: Tool 执行结果 (POST /api/tools/{tool_id}/execute)。 */
export interface ToolResult {
  success: boolean;
  output?: unknown | null;
  error?: string | null;
  metadata?: Record<string, unknown> | null;
}

/** S10-019 Task 001: Skill — GET /api/skills 返回的职业能力项。 */
export interface SkillInfo {
  id: string;
  name: string;
  description: string;
  version: string;
  category: string;
  tools: string[];
  enabled: boolean;
}

/** S10-020 Task 001: MCP Connection — 外部 MCP 服务连接。 */
export interface MCPConnection {
  id: string;
  name: string;
  server_url: string;
  transport: string;
  enabled: boolean;
  created_at: string | null;
}

/** S10-020 Task 001: MCP Tool — 经 Adapter 导入的 MCP 工具 (内部 Tool 视图)。 */
export interface MCPTool {
  id: string;
  name: string;
  description: string;
  server: string;
}

/** S10-002: SSE 事件名 (与后端 SSE_EVENT_MAP 同源; 业务 7 类 + error 通道)。 */
export const RUNTIME_EVENT_NAMES = [
  'stage.started',
  'stage.completed',
  'artifact.created',
  'approval.required',
  'approval.completed',
  'error',
  // S10-002: Runtime Instance 生命周期 (契约先行 — S10-004 Runtime 服务发射)
  'runtime.created',
  'runtime.status.changed',
] as const;

export type RuntimeEventName = (typeof RUNTIME_EVENT_NAMES)[number];

/** S10-002: runtime.created 事件载荷 (instance/type/status/artifact)。 */
export interface RuntimeCreatedEventData {
  instance_id: string | null;
  type: string | null;
  status: string | null;
  artifact_id: string | null;
  project_id: string | null;
}

/** S10-002: runtime.status.changed 事件载荷 (状态流转)。 */
export interface RuntimeStatusChangedEventData {
  instance_id: string | null;
  status: string | null;
  previous_status: string | null;
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

/** Artifact 生命周期状态中文标签 (S10-005 Artifact Center 状态徽章;
 * created/generated/validated/consumed/archived/invalid + 通用 pending/failed;
 * 未知原样显示)。 */
export function artifactStatusLabel(status: string): string {
  switch (status.toLowerCase()) {
    case 'validated':
      return '已验证';
    case 'generated':
      return '已生成';
    case 'created':
      return '已创建';
    case 'consumed':
      return '已消费';
    case 'archived':
      return '已归档';
    case 'invalid':
      return '无效';
    case 'pending':
      return '待验证';
    case 'failed':
      return '失败';
    default:
      return status;
  }
}

// ------------------------------------------------------------------ S10-007 阶段三: Run 状态 (POST /start + GET /run-status)

/** 单阶段进度投影 (workflow_runner Recorder.stages 条目; 宽松读取, 缺 → null)。 */
export interface RunStageInfo {
  workflow?: string;
  stage?: string;
  role?: string;
  /** RUNNING / COMPLETED / FAILED (进度文件里均为终态; 运行中阶段在内存, 未落盘)。 */
  status?: string;
  note?: string;
  cost_usd_est?: number;
  latency_s?: number;
}

/** 单 run 摘要 (report.json 优先; 无 report → progress.json; 都无 → pending)。 */
export interface RunInfo {
  run_id: string;
  status: string;
  stages: RunStageInfo[];
  totals: Record<string, unknown>;
  errors: Array<{ where?: string; message?: string }>;
  updated_at: string | null;
}

/** GET /api/projects/{id}/run-status 响应 (status: none|running|completed|failed)。 */
export interface RunStatusResponse {
  project_id: string;
  status: string;
  current_run_id: string | null;
  runs: RunInfo[];
  updated_at: string | null;
}


/** K-7e: Web 会话栏 — 会话 (公司/项目作用域, 多线程)。 */
export interface SessionSummary {
  id: string;
  scope: 'company' | 'project';
  project_id: string | null;
  title: string;
  status: 'active' | 'archived';
  created_at: string;
  updated_at: string;
  summary: string | null;
}

/** K-7e: Web 会话栏 — 消息 (user/assistant, append-only)。 */
export interface SessionMessage {
  id: string;
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

/** v1.1.102: 设置 — LLM Provider 配置 (GET/PATCH /api/config/llm 管理面)。 */
export interface LlmProviderConfig {
  id: string;
  enabled: boolean;
  models: string[];
  base_url: string | null;
  api_key_ref: string | null;
  key_configured: boolean;
  default_model: string | null;
  metadata: Record<string, unknown>;
}

/** v1.1.102: 设置 — Agent (GET/POST/DELETE /api/agents 管理面)。 */
export interface AgentInfo {
  id?: string;
  name?: string;
  role?: string;
  skills?: string[];
  status?: string;
}

/** v1.1.108: 项目文档 — 清单项 (GET /api/projects/{id}/docs)。 */
export interface ProjectDocSummary {
  name: string;
  label: string;
  kind: string;
  size: number;
  mtime: number;
  exists: boolean;
  extra: boolean;
  folder: string;
  source_dir: string;
}

/** v1.1.108: 项目文档 — 内容 (GET /api/projects/{id}/docs/{doc})。 */
export interface ProjectDocContent {
  name: string;
  path?: string;
  label?: string;
  kind: string;
  content: string | null;
  note?: string | null;
}

/** C-1/C-3: 产出物契约 — manifest 条目 (GET /api/projects/{id}/artifacts)。 */
export interface ProjectArtifactItem {
  type: string;
  label: string;
  kind: string;
  file: string;
  exists: boolean;
  legacy?: boolean;
  schema_ok: boolean;
  version: number | null;
  producer: string | null;
  trace_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  versions: { version: number; file: string; created_at: string | null; producer: string | null; trace_id: string | null }[];
}
