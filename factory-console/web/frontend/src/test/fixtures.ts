/**
 * src/test/fixtures.ts — 测试数据工厂 + fetch 桩辅助 (仅测试用, 不计覆盖率)。
 *
 * 数据形状对齐 src/models/types.ts (11A 响应模型投影)。
 * 来源标注 (S10-014 Task 008): 每个 fixture 结构与真实后端 API 响应一致
 * (curl http://127.0.0.1:8011 验证于 2026-08-11); 完整映射见 FIXTURE_SOURCES。
 */

import type {
  AgentSummary,
  ApprovalDecisionSummary,
  ApprovalGateSummary,
  ApprovalSummary,
  ArtifactDetail,
  ArtifactSummary,
  ConsoleDashboard,
  DecisionSummary,
  ExperienceSummary,
  LifecycleSummary,
  ProjectSummary,
  ProviderSummary,
  RecommendationSummary,
  StageSummary,
  TimelineEventSummary,
  WorkflowDetail,
  WorkflowSummary,
} from '../models/types';
import { toTodoTree } from '../api/domain';
import type { TodoTree } from '../models/domain';

/**
 * 每个 fixture 的来源标注 (S10-014 Task 008: 结构与真实 API 响应一致 + 验证日期)。
 * 修改 fixture 形状时必须同步更新 (fixtures-structure.test.ts 全量校验)。
 */
export const FIXTURE_SOURCES: Readonly<Record<string, string>> = {
  sampleProject: '结构与 GET /api/projects 真实响应一致 (验证于 2026-08-11)',
  sampleApproval: '结构与 GET /api/approvals 真实响应一致 (验证于 2026-08-11)',
  sampleApprovalGate: '结构与 GET /api/approval-gates 真实响应一致 (验证于 2026-08-11)',
  sampleApprovalDecision: '结构与 POST /api/approvals/{id}/approve|reject 真实响应一致 (验证于 2026-08-11)',
  sampleStage: '结构与 GET /api/projects/{id}/workflow stages 真实响应一致 (验证于 2026-08-11)',
  sampleWorkflow: '结构与 GET /api/workflows 真实响应一致 (验证于 2026-08-11)',
  sampleWorkflowDetail: '结构与 GET /api/projects/{id}/workflow 真实响应一致 (验证于 2026-08-11)',
  sampleArtifact: '结构与 GET /api/artifacts 真实响应一致 (验证于 2026-08-11)',
  sampleArtifactDetail: '结构与 GET /api/artifacts/{artifact_id} 真实响应一致 (验证于 2026-08-11)',
  sampleUXUIDetail: '结构与 GET /api/artifacts/{artifact_id} 真实响应一致 (验证于 2026-08-11)',
  sampleDecision: '结构与 GET /api/decisions/{decision_id} 真实响应一致 (验证于 2026-08-11)',
  sampleLifecycle: '结构与 GET /api/projects/{id}/lifecycle 真实响应一致 (验证于 2026-08-11)',
  sampleRecommendation: '结构与 GET /api/recommendations 真实响应一致 (验证于 2026-08-11)',
  sampleExperience: '结构与 GET /api/experience 真实响应一致 (验证于 2026-08-11)',
  sampleProvider: '结构与 GET /api/providers 真实响应一致 (验证于 2026-08-11)',
  sampleDashboard: '结构与 GET /api/dashboard 真实响应一致 (验证于 2026-08-11)',
  sampleTimelineEvents: '结构与 GET /api/projects/{id}/timeline 真实响应一致 (验证于 2026-08-11)',
  sampleBacklog: '结构与 GET /api/projects/{id}/backlog 真实响应一致 (验证于 2026-08-11)',
  sampleAgent: '结构与 GET /api/dashboard agents 真实响应一致 (验证于 2026-08-11)',
};

/** 返回一个只读 JSON 响应 (client 只消费 ok + json())。 */
function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as Response;
}

/**
 * 按 path → body 映射注册全局 fetch 桩。
 * 未命中路径 → 404 (失败安全: 抛 ApiError)。
 */
export function stubFetch(routes: Record<string, unknown>): ReturnType<typeof vi.fn> {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path in routes) {
      return jsonResponse(routes[path]);
    }
    return { ok: false, status: 404, json: async () => ({ detail: 'not found' }) } as Response;
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

/** 来源: 结构与 GET /api/projects 真实响应一致 (验证于 2026-08-11)。 */
export function sampleProject(overrides: Partial<ProjectSummary> = {}): ProjectSummary {
  return {
    id: 'demo',
    name: 'Demo Project',
    description: 'A demo',
    language: 'python',
    repository: 'demo/repo',
    tech_stack: ['python'],
    status: 'active',
    lifecycle_stage: 'build',
    lifecycle_status: 'running',
    workflow_id: null,
    workflow_name: null,
    workflow_status: null,
    current_stage: null,
    current_stage_status: null,
    progress: 0,
    stage_counts: {},
    pending_approvals: 1,
    tasks: { done: 3 },
    last_activity: '2026-08-06T00:00:00Z',
    ...overrides,
  };
}

/** 来源: 结构与 GET /api/approvals 真实响应一致 (验证于 2026-08-11)。 */
export function sampleApproval(overrides: Partial<ApprovalSummary> = {}): ApprovalSummary {
  return {
    id: 'req-1',
    artifact_id: 'art-1',
    artifact_type: 'design',
    gate: 'design_gate',
    status: 'pending',
    confidence: 0.86,
    risk: 'medium',
    evidence: ['ev:1', 'ev:2', 'ev:3'],
    idea_id: 'idea-1',
    by: 'planner',
    comment: null,
    requested_at: '2026-08-06T00:00:00Z',
    artifact_version: 3,
    ...overrides,
  };
}

/** org 审批门 (S9-001 ApprovalGate; Console 决定操作对象 — Approval 页)。
 * 来源: 结构与 GET /api/approval-gates 真实响应一致 (验证于 2026-08-11)。 */
export function sampleApprovalGate(
  overrides: Partial<ApprovalGateSummary> = {},
): ApprovalGateSummary {
  return {
    id: 'gate-1',
    stage_id: 'design',
    workflow_id: 'wf-1',
    project_id: 'demo',
    status: 'pending',
    reviewer: 'console',
    comment: '',
    requested_at: '2026-08-06T00:00:00Z',
    approved_at: null,
    rejected_at: null,
    ...overrides,
  };
}

/** POST approve/reject 决定结果投影。
 * 来源: 结构与 POST /api/approvals/{id}/approve|reject 真实响应一致 (验证于 2026-08-11)。 */
export function sampleApprovalDecision(
  overrides: Partial<ApprovalDecisionSummary> = {},
): ApprovalDecisionSummary {
  return {
    action: 'approved',
    gate: sampleApprovalGate(),
    workflow_id: 'wf-1',
    workflow_status: 'running',
    ...overrides,
  };
}

/** 阶段链节点 (WorkflowDetail.stages)。
 * 来源: 结构与 GET /api/projects/{id}/workflow stages 真实响应一致 (验证于 2026-08-11)。 */
export function sampleStage(overrides: Partial<StageSummary> = {}): StageSummary {
  return {
    id: 'stage-design',
    workflow_id: 'wf-1',
    role_id: 'designer',
    name: 'Design',
    order: 3,
    status: 'waiting',
    depends_on: ['stage-pm'],
    input_artifacts: ['prd-1'],
    output_artifacts: ['design-1'],
    approval_required: true,
    artifact: null,
    pending_approval: null,
    ...overrides,
  };
}

/** org Workflow 运行摘要 (Workflow 页表格行)。
 * 来源: 结构与 GET /api/workflows 真实响应一致 (验证于 2026-08-11)。 */
export function sampleWorkflow(overrides: Partial<WorkflowSummary> = {}): WorkflowSummary {
  return {
    id: 'wf-1',
    project_id: 'demo',
    project_name: 'Demo Project',
    name: '记账 App',
    status: 'running',
    stage_count: 8,
    completed_count: 3,
    progress: 0.375,
    current_stage: 'Design',
    current_stage_status: 'waiting',
    failed_reason: '',
    ...overrides,
  };
}

/** 单 Workflow 8 阶段链全视图 (Workflow 页详情)。
 * 来源: 结构与 GET /api/projects/{id}/workflow 真实响应一致 (验证于 2026-08-11)。 */
export function sampleWorkflowDetail(
  overrides: Partial<WorkflowDetail> = {},
): WorkflowDetail {
  return {
    id: 'wf-1',
    project_id: 'demo',
    project_name: 'Demo Project',
    name: '记账 App',
    status: 'running',
    failed_reason: '',
    created_at: '2026-08-06T00:00:00Z',
    started_at: '2026-08-06T00:00:00Z',
    completed_at: null,
    stages: [sampleStage()],
    pending_approvals: [],
    template: ['Idea', 'PM', 'Product', 'UX/UI', 'Architecture', 'Development', 'Test', 'Release'],
    ...overrides,
  };
}

/** org Artifact 投影 (6 类产物链, Artifacts 页表格行)。
 * 来源: 结构与 GET /api/artifacts 真实响应一致 (验证于 2026-08-11)。 */
export function sampleArtifact(overrides: Partial<ArtifactSummary> = {}): ArtifactSummary {
  return {
    id: 'art-1',
    stage_id: 'design',
    workflow_id: 'wf-1',
    project_id: 'demo',
    type: 'design',
    ref: 'designs/design-1',
    version: '3',
    status: 'approved',
    producer_role: 'designer',
    producer_agent: 'designer-agent',
    location: 'org/artifacts/design-1.md',
    created_at: '2026-08-06T00:00:00Z',
    updated_at: '2026-08-06T00:00:00Z',
    ...overrides,
  };
}

/** product Artifact 详情 (S9-003 Review 数据源: PRD 6 节 + pending 审批门)。
 * 来源: 结构与 GET /api/artifacts/{artifact_id} 真实响应一致 (验证于 2026-08-11)。 */
export function sampleArtifactDetail(
  overrides: Partial<ArtifactDetail> = {},
): ArtifactDetail {
  return {
    ...sampleArtifact({ id: 'art-1', type: 'product', stage_id: 'product', producer_role: 'pm' }),
    metadata: {
      market_analysis: '目标市场: 个人记账用户; 竞争: 手工表格/同类 App',
      user_persona: '25-40 岁上班族, 需要简单记账与月度报表',
      user_journey: '记录一笔支出 → 查看分类统计 → 月底生成报表',
      feature_list: ['支出记录', '分类统计', '月度报表'],
      mvp_scope: { in: ['支出记录', '分类统计'], out: ['多人协作'] },
      user_stories: [
        { 'as-a': '用户', 'i-want': '快速记录支出', 'so-that': '不遗漏' },
      ],
    },
    review: sampleApprovalGate({ id: 'gate-1', stage_id: 'product' }),
    ...overrides,
  };
}

/** ux_ui Artifact 详情 (S9-003: 7 节 + wireframe ASCII 预览数据源)。
 * 来源: 结构与 GET /api/artifacts/{artifact_id} 真实响应一致 (验证于 2026-08-11)。 */
export function sampleUXUIDetail(overrides: Partial<ArtifactDetail> = {}): ArtifactDetail {
  return {
    ...sampleArtifact({ id: 'art-ux1', type: 'ux_ui', stage_id: 'ux-ui', producer_role: 'designer' }),
    metadata: {
      information_architecture: {
        screens: ['screen_home', 'screen_record'],
        navigation: '底部 Tab 导航: 首页/记录/报表',
      },
      user_flow: [
        { step: '打开应用', screen: 'screen_home' },
        { step: '记录一笔支出', screen: 'screen_record' },
      ],
      wireframe: {
        screens: [
          {
            name: 'screen_home',
            ascii: '+------------+\n| 余额卡片   |\n| 近期流水   |\n+------------+',
            components: ['BalanceCard', 'TransactionList'],
            actions: ['下拉刷新', '点击流水进入详情'],
          },
          {
            name: 'screen_record',
            ascii: '+------------+\n| 金额输入   |\n+------------+',
            components: ['AmountInput'],
            actions: ['提交后返回首页'],
          },
        ],
      },
      screen_specifications: [
        {
          screen: 'screen_home',
          elements: ['余额卡片', '近期流水'],
          behaviors: ['下拉刷新'],
          acceptance: ['余额展示正确'],
        },
      ],
      component_definition: [
        { name: 'BalanceCard', description: '余额展示卡片', usage: '首页顶部' },
      ],
      design_tokens: {
        colors: { primary: '#1A73E8', background: '#FFFFFF' },
        typography: { title: '18px/600', body: '14px/400' },
        spacing: { xs: 4, sm: 8 },
      },
      prototype: '点击底部 Tab 切换; 记录页提交后返回首页并刷新余额; 纯文本描述。',
    },
    review: sampleApprovalGate({ id: 'gate-ux1', stage_id: 'ux-ui' }),
    ...overrides,
  };
}

/** 来源: 结构与 GET /api/decisions/{decision_id} 真实响应一致 (验证于 2026-08-11)。 */
export function sampleDecision(overrides: Partial<DecisionSummary> = {}): DecisionSummary {
  return {
    id: 'dec-1',
    decision_type: 'provider',
    subject_id: 'subj-1',
    description: '选择 Provider',
    status: 'recommended',
    options: [
      {
        id: 'opt-a',
        name: 'Provider A',
        score: 0.9,
        factors: { capability: 0.9, cost: 0.7, performance: 0.8, experience: 0.6 },
        reasoning: ['能力最强'],
        evidence: ['ev:1'],
      },
      {
        id: 'opt-b',
        name: 'Provider B',
        score: 0.6,
        factors: { capability: 0.6, cost: 0.9, performance: 0.5, experience: 0.4 },
        reasoning: [],
        evidence: [],
      },
    ],
    recommendation: 'opt-a',
    score: 0.9,
    confidence: 0.9,
    reasoning: ['综合评分最高', '成本可控'],
    evidence: ['ev:1', 'ev:2'],
    risk: 0.2,
    risk_level: 'low',
    requires_approval: true,
    approval_request_id: 'req-9',
    created_at: '2026-08-06T00:00:00Z',
    ...overrides,
  };
}

/** 来源: 结构与 GET /api/projects/{id}/lifecycle 真实响应一致 (验证于 2026-08-11)。 */
export function sampleLifecycle(overrides: Partial<LifecycleSummary> = {}): LifecycleSummary {
  return {
    project_id: 'demo',
    lifecycle_id: 'lc-1',
    idea_id: 'idea-1',
    template_name: 'standard',
    status: 'running',
    current_stage: { name: 'build', status: 'running', detail: 'writing code' },
    completed_stages: ['planning'],
    pending_approval: sampleApproval({ id: 'req-2', artifact_id: 'art-2' }),
    next_actions: ['完成 build 阶段', '提交测试'],
    ...overrides,
  };
}

/** 来源: 结构与 GET /api/recommendations 真实响应一致 (验证于 2026-08-11)。 */
export function sampleRecommendation(
  overrides: Partial<RecommendationSummary> = {},
): RecommendationSummary {
  return {
    id: 'rec-1',
    target_type: 'provider',
    candidate: 'hermes',
    score: 0.92,
    factors: { capability: 0.9, cost: 0.8 },
    explanation: ['经验丰富', '成本低'],
    evidence: ['ev:1', 'ev:2'],
    confidence: 0.9,
    risk: 0.1,
    created_at: '2026-08-06T00:00:00Z',
    ...overrides,
  };
}

/** 来源: 结构与 GET /api/experience 真实响应一致 (验证于 2026-08-11)。 */
export function sampleExperience(overrides: Partial<ExperienceSummary> = {}): ExperienceSummary {
  return {
    id: 'exp-1',
    domain: 'provider',
    subject: 'hermes',
    result: 'success',
    score: 0.8,
    confidence: 0.9,
    freshness: 0.7,
    task_type: 'generate',
    capability: ['code'],
    created_at: '2026-08-06T00:00:00Z',
    ...overrides,
  };
}

/** 来源: 结构与 GET /api/providers 真实响应一致 (验证于 2026-08-11)。 */
export function sampleProvider(overrides: Partial<ProviderSummary> = {}): ProviderSummary {
  return {
    id: 'hermes',
    name: 'Hermes',
    type: 'llm',
    status: 'available',
    capabilities: ['code', 'reasoning'],
    models: ['deepseek'],
    version: '1.0',
    cost: 0.5,
    performance: 0.9,
    experience: 0.8,
    usage_calls: 42,
    ...overrides,
  };
}

/** 来源: 结构与 GET /api/dashboard 真实响应一致 (验证于 2026-08-11)。 */
export function sampleDashboard(overrides: Partial<ConsoleDashboard> = {}): ConsoleDashboard {
  return {
    projects: [sampleProject()],
    approvals: [sampleApproval()],
    agents: [sampleAgent()],
    decisions: [sampleDecision()],
    cost: {
      total_cost: 1.2345,
      calls: 12,
      success_rate: 0.9,
      avg_cost: 0.1,
      total_tokens: 1234,
      by_provider: { hermes: { calls: 12, cost: 1.23 } },
    },
    experience: {
      total: 3,
      by_domain: { provider: 3 },
      success_rate: 0.67,
      avg_score: 0.8,
      avg_confidence: 0.9,
    },
    activity: [
      {
        seq: 1,
        type: 'task.completed',
        timestamp: '2026-08-06T00:00:00Z',
        source: 'engine',
        project_id: 'demo',
        task_id: 't-1',
        action: 'completed',
        result: 'ok',
      },
    ],
    ...overrides,
  };
}

// ------------------------------------------------------------------ S10-015 Task 003: Todo Tree UI fixtures
// sampleTodoBacklog: 全 6 态 Task (todo/ready/in_progress/blocked/review/done) + P0-P3 全优先级,
//   结构对齐真实 GET /api/projects/{id}/backlog (children id 引用, 无回溯字段)。
// sampleTodoTree: toTodoTree(sampleTodoBacklog()) → TodoTree (真实 Adapter 转换, 非手工树)。
// sampleTaskMeta: backlog.tasks → {id → {priority, owner}} (AfTodoTree 优先级/负责人补充数据源;
//   Adapter 未映射 priority/assignee 时的页面级投影, 真实字段来源)。

/** 全 6 态 + P0-P3 的 backlog (S10-015 Task 003 组件测试用; 结构同真实响应)。 */
export interface TodoBacklog extends BacklogResponse {}

/** 来源: 结构与 GET /api/projects/{id}/backlog 真实响应一致 (验证于 2026-08-11/12)。 */
export function sampleTodoBacklog(overrides: Partial<BacklogResponse> = {}): TodoBacklog {
  return {
    project_id: 'demo',
    epics: [
      {
        id: 'epic-dev',
        name: '开发阶段',
        description: '核心功能开发',
        children: ['feat-user'],
        created_at: '2026-08-12T00:00:00Z',
        updated_at: '2026-08-12T00:00:00Z',
      },
      {
        id: 'epic-qa',
        name: '质量保障',
        description: '测试与发布',
        children: ['feat-test'],
        created_at: '2026-08-12T00:00:00Z',
        updated_at: '2026-08-12T00:00:00Z',
      },
    ],
    features: [
      {
        id: 'feat-user',
        name: '用户系统',
        description: '注册登录',
        children: ['story-reg', 'story-login'],
        created_at: '2026-08-12T00:00:00Z',
        updated_at: '2026-08-12T00:00:00Z',
      },
      {
        id: 'feat-test',
        name: '自动化测试',
        description: '回归与发布',
        children: ['story-regression', 'story-release'],
        created_at: '2026-08-12T00:00:00Z',
        updated_at: '2026-08-12T00:00:00Z',
      },
    ],
    stories: [
      {
        id: 'story-reg',
        name: '用户注册',
        description: '手机号注册',
        children: ['t-reg-api', 't-reg-db'],
        created_at: '2026-08-12T00:00:00Z',
        updated_at: '2026-08-12T00:00:00Z',
      },
      {
        id: 'story-login',
        name: '用户登录',
        description: '登录鉴权',
        children: ['t-login-api'],
        created_at: '2026-08-12T00:00:00Z',
        updated_at: '2026-08-12T00:00:00Z',
      },
      {
        id: 'story-regression',
        name: '回归测试',
        description: '全量回归',
        children: ['t-regr-run', 't-regr-report'],
        created_at: '2026-08-12T00:00:00Z',
        updated_at: '2026-08-12T00:00:00Z',
      },
      {
        id: 'story-release',
        name: '发布准备',
        description: '发布检查',
        children: ['t-release-check'],
        created_at: '2026-08-12T00:00:00Z',
        updated_at: '2026-08-12T00:00:00Z',
      },
    ],
    tasks: [
      {
        id: 't-reg-api',
        title: '实现注册 API',
        description: 'POST /api/register',
        priority: 'P1',
        status: 'in_progress',
        assignee: 'developer',
        dependency: [],
        created_at: '2026-08-12T00:00:00Z',
        updated_at: '2026-08-12T00:00:00Z',
        history: [],
      },
      {
        id: 't-reg-db',
        title: '用户数据模型',
        description: '用户表设计',
        priority: 'P2',
        status: 'done',
        assignee: 'developer',
        dependency: [],
        created_at: '2026-08-12T00:00:00Z',
        updated_at: '2026-08-12T00:00:00Z',
        history: [],
      },
      {
        id: 't-login-api',
        title: '实现登录 API',
        description: 'POST /api/login JWT',
        priority: 'P1',
        status: 'blocked',
        assignee: '',
        dependency: ['t-reg-api'],
        created_at: '2026-08-12T00:00:00Z',
        updated_at: '2026-08-12T00:00:00Z',
        history: [],
      },
      {
        id: 't-regr-run',
        title: '回归测试执行',
        description: '全量回归跑批',
        priority: 'P3',
        status: 'review',
        assignee: 'tester',
        dependency: [],
        created_at: '2026-08-12T00:00:00Z',
        updated_at: '2026-08-12T00:00:00Z',
        history: [],
      },
      {
        id: 't-regr-report',
        title: '测试报告',
        description: '回归结果汇总',
        priority: 'P2',
        status: 'failed',
        assignee: 'tester',
        dependency: ['t-regr-run'],
        created_at: '2026-08-12T00:00:00Z',
        updated_at: '2026-08-12T00:00:00Z',
        history: [],
      },
      {
        id: 't-release-check',
        title: '发布检查单',
        description: '上线前检查',
        priority: 'P0',
        status: 'todo',
        assignee: '',
        dependency: [],
        created_at: '2026-08-12T00:00:00Z',
        updated_at: '2026-08-12T00:00:00Z',
        history: [],
      },
    ],
    ...overrides,
  };
}

/** 任务补充元数据: id → {priority, owner} (来自真实 backlog.tasks 字段投影)。 */
export interface TaskMeta {
  priority?: string;
  owner?: string;
}

/** sampleTodoBacklog().tasks → TaskMeta 映射 (assignee 空串 → owner undefined, 诚实降级)。 */
export function sampleTaskMeta(backlog: TodoBacklog = sampleTodoBacklog()): Record<string, TaskMeta> {
  const meta: Record<string, TaskMeta> = {};
  for (const task of backlog.tasks ?? []) {
    meta[task.id] = {
      priority: task.priority != null && task.priority.length > 0 ? task.priority : undefined,
      owner: task.assignee != null && task.assignee.length > 0 ? task.assignee : undefined,
    };
  }
  return meta;
}

/** 来源: 结构与 GET /api/projects/{id}/backlog 真实响应一致 (验证于 2026-08-12) → toTodoTree。 */
export function sampleTodoTree(projectName = '演示项目'): TodoTree {
  return toTodoTree(sampleTodoBacklog(), projectName);
}

/** sampleTodoFixture: 组件测试一站式 (树 + 元数据)。 */
export function sampleTodoFixture(): { tree: TodoTree; meta: Record<string, TaskMeta> } {
  return { tree: sampleTodoTree(), meta: sampleTaskMeta() };
}

// ------------------------------------------------------------------ S10-014 Task 008 补齐: agent / timeline / backlog
// 真实结构对照 (2026-08-11): GET /api/dashboard (agents 域), GET /api/projects/{id}/timeline,
// GET /api/projects/{id}/backlog (本环境无 management store → 404; 结构取 service.list_backlog
// 真实契约: Epic/Feature/Story {id,name,description,children,created_at,updated_at}, Task 另含
// title/priority/status/assignee/dependency/history)。

/** 来源: 结构与 GET /api/dashboard agents 域真实响应一致 (验证于 2026-08-11)。 */
export function sampleAgent(overrides: Partial<AgentSummary> = {}): AgentSummary {
  return {
    id: 'agent-1',
    name: 'Planner',
    role: 'planner',
    status: 'WORKING',
    skills: ['planning'],
    current_task: 'write plan',
    ...overrides,
  };
}

/**
 * 单条 Timeline 事件 (GET /api/projects/{id}/timeline 真实响应条目;
 * 键: id/seq/project_id/type/event_type/stage_id/agent_id/artifact_id/gate_id/
 * message/status/payload/created_at — 验证于 2026-08-11)。
 */
export function sampleTimelineEvent(
  overrides: Partial<TimelineEventSummary> = {},
): TimelineEventSummary {
  return {
    id: 'evt-1',
    seq: 1,
    project_id: 'demo',
    type: 'stage',
    event_type: 'org.workflow.started',
    stage_id: null,
    agent_id: null,
    artifact_id: null,
    gate_id: null,
    message: '工作流启动',
    status: 'OK',
    payload: { workflow_id: 'wf-1', project_id: 'demo', from_status: 'draft', to_status: 'active' },
    created_at: '2026-08-11T00:00:00Z',
    ...overrides,
  };
}

/**
 * Timeline 事件流 (5 类: user/stage/artifact/review/error; Agent Timeline 数据源)。
 * 来源: 结构与 GET /api/projects/{id}/timeline 真实响应一致 (验证于 2026-08-11)。
 */
export function sampleTimelineEvents(): TimelineEventSummary[] {
  return [
    sampleTimelineEvent({
      id: 'evt-1',
      seq: 1,
      type: 'user',
      event_type: 'org.project.created',
      message: '项目创建: Demo Project',
    }),
    sampleTimelineEvent({
      id: 'evt-2',
      seq: 2,
      type: 'stage',
      event_type: 'org.workflow.started',
      message: '工作流启动',
    }),
    sampleTimelineEvent({
      id: 'evt-3',
      seq: 3,
      type: 'stage',
      event_type: 'org.workflow.stage_started',
      stage_id: 'stage-design',
      agent_id: 'designer',
      message: '阶段开始 Design',
    }),
    sampleTimelineEvent({
      id: 'evt-4',
      seq: 4,
      type: 'artifact',
      event_type: 'org.artifact.created',
      artifact_id: 'art-1',
      message: '产物生成',
    }),
    sampleTimelineEvent({
      id: 'evt-5',
      seq: 5,
      type: 'review',
      event_type: 'org.approval.created',
      gate_id: 'gate-1',
      stage_id: 'stage-design',
      message: '审批待处理',
    }),
  ];
}

// ------------------------------------------------------------------ S10-015 Task 004: Workflow Instance fixtures
// sampleWorkflowInstance: 真实 P-806fe6e8 ScorePocket 设计链实例 (is_mock=false),
//   结构 = GET /api/projects/P-806fe6e8/workflow 实测 (2026-08-12 02:35):
//   3 阶段 product(completed) → ux_ui(running) → design(blocked, depends_on ux_ui)。
// sampleWorkflowInstanceMock: 演示流 (is_mock=true, 6 阶段 Product→Release) —
//   结构 = 后端 mock fallback 契约 (MOCK_STAGE_CHAIN), 含 waiting_review + devops 角色。
// sampleWorkflowTimeline: 7 条真实运行事件 (org.workflow.* + org.artifact.*)。

/** 真实 P-806fe6e8 Workflow Instance (is_mock=false; 阶段含真实 artifact/依赖)。 */
export function sampleWorkflowInstance(overrides: Partial<WorkflowDetail> = {}): WorkflowDetail {
  const wfId = 'WF-P-806fe6e8-R1786473507972-DESIGN';
  return {
    id: wfId,
    project_id: 'P-806fe6e8',
    project_name: 'ScorePocket',
    name: 'P-806fe6e8 设计链 (product→ux_ui→design) [R1786473507972]',
    status: 'active',
    failed_reason: '',
    created_at: '2026-08-11T18:38:28.047043+00:00',
    started_at: '2026-08-11T18:38:28.056279+00:00',
    completed_at: null,
    stages: [
      {
        id: 'STG-P-806fe6e8-R1786473507972-PRODUCT',
        workflow_id: wfId,
        role_id: 'product-manager',
        name: 'product',
        order: 1,
        status: 'completed',
        depends_on: [],
        input_artifacts: ['P-806fe6e8-R1786473507972-IDEA'],
        output_artifacts: ['P-806fe6e8-R1786473507972-PRODUCT'],
        approval_required: false,
        artifact: {
          id: 'P-806fe6e8-R1786473507972-PRODUCT',
          stage_id: 'STG-P-806fe6e8-R1786473507972-PRODUCT',
          workflow_id: wfId,
          project_id: 'P-806fe6e8',
          type: 'product',
          ref: 'file:///docs/product.json',
          version: '1',
          status: 'validated',
          producer_role: 'product-manager',
          producer_agent: '',
          location: '',
          created_at: '2026-08-11T18:39:03.117160+00:00',
          updated_at: '2026-08-11T18:39:03.125611+00:00',
        },
        pending_approval: null,
      },
      {
        id: 'STG-P-806fe6e8-R1786473507972-UXUI',
        workflow_id: wfId,
        role_id: 'ui-designer',
        name: 'ux_ui',
        order: 2,
        status: 'running',
        depends_on: ['STG-P-806fe6e8-R1786473507972-PRODUCT'],
        input_artifacts: ['P-806fe6e8-R1786473507972-PRODUCT'],
        output_artifacts: [],
        approval_required: false,
        artifact: null,
        pending_approval: null,
      },
      {
        id: 'STG-P-806fe6e8-R1786473507972-DESIGN',
        workflow_id: wfId,
        role_id: 'architect',
        name: 'design',
        order: 3,
        status: 'blocked',
        depends_on: ['STG-P-806fe6e8-R1786473507972-UXUI'],
        input_artifacts: ['P-806fe6e8-R1786473507972-PRODUCT', 'P-806fe6e8-R1786473507972-UXUI'],
        output_artifacts: [],
        approval_required: false,
        artifact: null,
        pending_approval: null,
      },
    ],
    pending_approvals: [],
    template: ['Idea', 'PM', 'Product', 'UX/UI', 'Architecture', 'Development', 'Test', 'Release'],
    is_mock: false,
    ...overrides,
  };
}

/** 演示流 (is_mock=true; 6 阶段链 Product→Release, 含 waiting_review + devops)。 */
export function sampleWorkflowInstanceMock(overrides: Partial<WorkflowDetail> = {}): WorkflowDetail {
  const wfId = 'mock-wf-markpad';
  const stage = (
    id: string,
    roleId: string,
    name: string,
    order: number,
    status: string,
  ): StageSummary => ({
    id,
    workflow_id: wfId,
    role_id: roleId,
    name,
    order,
    status,
    depends_on: [],
    input_artifacts: [],
    output_artifacts: [],
    approval_required: false,
    artifact: null,
    pending_approval: null,
  });
  return {
    id: wfId,
    project_id: 'markpad',
    project_name: 'MarkPad',
    name: 'Mock Workflow (演示数据)',
    status: 'active',
    failed_reason: '',
    created_at: '2026-08-11T17:52:06.202422+00:00',
    started_at: '2026-08-11T17:52:06.202422+00:00',
    completed_at: null,
    stages: [
      stage('mock-product-manager', 'product-manager', 'Product', 1, 'completed'),
      stage('mock-ui-designer', 'ui-designer', 'UX/UI', 2, 'completed'),
      stage('mock-architect', 'architect', 'Architecture', 3, 'waiting_review'),
      stage('mock-developer', 'developer', 'Code', 4, 'pending'),
      stage('mock-tester', 'tester', 'Test', 5, 'pending'),
      stage('mock-devops', 'devops', 'Release', 6, 'pending'),
    ],
    pending_approvals: [],
    template: ['Idea', 'PM', 'Product', 'UX/UI', 'Architecture', 'Development', 'Test', 'Release'],
    is_mock: true,
    ...overrides,
  };
}

/** 真实运行事件 7 条 (org.workflow.* + org.artifact.*; GET /api/projects/{id}/timeline 实测形状)。 */
export function sampleWorkflowTimeline(): TimelineEventSummary[] {
  return [
    sampleTimelineEvent({
      id: 'evt-314',
      seq: 314,
      project_id: 'P-806fe6e8',
      type: 'stage',
      event_type: 'org.workflow.created',
      message: '工作流创建 P-806fe6e8 设计链 (product→ux_ui→design) [R1786473507972]',
      status: 'OK',
      created_at: '2026-08-11T18:38:28.047411+00:00',
    }),
    sampleTimelineEvent({
      id: 'evt-315',
      seq: 315,
      project_id: 'P-806fe6e8',
      type: 'stage',
      event_type: 'org.workflow.started',
      message: '工作流启动 P-806fe6e8 设计链',
      status: 'OK',
      created_at: '2026-08-11T18:38:28.055702+00:00',
    }),
    sampleTimelineEvent({
      id: 'evt-316',
      seq: 316,
      project_id: 'P-806fe6e8',
      type: 'stage',
      event_type: 'org.workflow.stage_ready',
      stage_id: 'STG-P-806fe6e8-R1786473507972-PRODUCT',
      agent_id: 'product-manager',
      message: '阶段就绪 product',
      status: 'ready',
      created_at: '2026-08-11T18:38:28.055937+00:00',
    }),
    sampleTimelineEvent({
      id: 'evt-317',
      seq: 317,
      project_id: 'P-806fe6e8',
      type: 'stage',
      event_type: 'org.workflow.stage_started',
      stage_id: 'STG-P-806fe6e8-R1786473507972-PRODUCT',
      agent_id: 'product-manager',
      message: '阶段开始 product',
      status: 'running',
      created_at: '2026-08-11T18:38:28.056057+00:00',
    }),
    sampleTimelineEvent({
      id: 'evt-318',
      seq: 318,
      project_id: 'P-806fe6e8',
      type: 'artifact',
      event_type: 'org.artifact.created',
      stage_id: 'STG-P-806fe6e8-R1786473507972-PRODUCT',
      artifact_id: 'P-806fe6e8-R1786473507972-IDEA',
      message: '产物生成',
      status: 'OK',
      created_at: '2026-08-11T18:38:28.052090+00:00',
    }),
    sampleTimelineEvent({
      id: 'evt-319',
      seq: 319,
      project_id: 'P-806fe6e8',
      type: 'artifact',
      event_type: 'org.artifact.updated',
      artifact_id: 'P-806fe6e8-R1786473507972-IDEA',
      message: '产物更新',
      status: 'OK',
      created_at: '2026-08-11T18:38:28.052632+00:00',
    }),
    sampleTimelineEvent({
      id: 'evt-320',
      seq: 320,
      project_id: 'P-806fe6e8',
      type: 'artifact',
      event_type: 'org.artifact.validated',
      artifact_id: 'P-806fe6e8-R1786473507972-IDEA',
      message: '产物验证通过',
      status: 'OK',
      created_at: '2026-08-11T18:38:28.053128+00:00',
    }),
  ];
}

/** GET /api/projects/{id}/backlog Epic/Feature/Story 条目 (org.management 契约)。 */
export interface BacklogNodeItem {
  id: string;
  name: string;
  description: string;
  children: string[];
  created_at: string | null;
  updated_at: string | null;
}

/** GET /api/projects/{id}/backlog Task 条目 (title 而非 name; priority/status 枚举)。 */
export interface BacklogTaskItem {
  id: string;
  title: string;
  description: string;
  priority: string; // P0-P3
  status: string; // todo|ready|in_progress|blocked|review|done
  assignee: string;
  dependency: string[];
  created_at: string | null;
  updated_at: string | null;
  history: Array<{ time: string; actor: string; action: string; result: string }>;
}

/** GET /api/projects/{id}/backlog 响应 (四分组; 失败安全空态)。 */
export interface BacklogResponse {
  project_id: string;
  epics: BacklogNodeItem[];
  features: BacklogNodeItem[];
  stories: BacklogNodeItem[];
  tasks: BacklogTaskItem[];
}

// ------------------------------------------------------------------ S10-015 Task 005b: Runtime 失败实例 fixtures
// sampleFailedWorkflow: 真实 P-806fe6e8 ScorePocket 失败工作流 (2026-08-12 实测,
//   status=failed + failed_reason DeveloperError + 3 阶段 development(failed) →
//   testing(pending) → release(pending)) — Runtime Timeline 当前执行卡/失败原因/下一步数据源。
// sampleFailedTimeline: 真实形状运行事件 (org.workflow.* / org.artifact.* / 失败收尾),
//   时间升序 (seq 递增) — AfRuntimeTimeline 需倒序展示 (最新在上)。

/** 真实 P-806fe6e8 失败 Workflow (status=failed, 3 阶段: development failed → testing/release pending)。 */
export function sampleFailedWorkflow(overrides: Partial<WorkflowDetail> = {}): WorkflowDetail {
  const wfId = 'WF-P-806fe6e8-R1786473507972-DEV';
  const stage = (
    id: string,
    roleId: string,
    name: string,
    order: number,
    status: string,
  ): StageSummary => ({
    id,
    workflow_id: wfId,
    role_id: roleId,
    name,
    order,
    status,
    depends_on: [],
    input_artifacts: [],
    output_artifacts: [],
    approval_required: false,
    artifact: null,
    pending_approval: null,
  });
  return {
    id: wfId,
    project_id: 'P-806fe6e8',
    project_name: 'ScorePocket',
    name: 'P-806fe6e8 开发链 (development→testing→release)',
    status: 'failed',
    failed_reason:
      'DeveloperError: provider response contains no parseable patch or operations (after 1 retry)',
    created_at: '2026-08-12T03:00:00.000000+00:00',
    started_at: '2026-08-12T03:00:00.000000+00:00',
    completed_at: '2026-08-12T03:45:00.000000+00:00',
    stages: [
      stage('STG-P-806fe6e8-R1786473507972-DEV', 'developer', 'development', 1, 'failed'),
      stage('STG-P-806fe6e8-R1786473507972-TEST', 'tester', 'testing', 2, 'pending'),
      stage('STG-P-806fe6e8-R1786473507972-REL', 'devops', 'release', 3, 'pending'),
    ],
    pending_approvals: [],
    template: ['Idea', 'PM', 'Product', 'UX/UI', 'Architecture', 'Development', 'Test', 'Release'],
    is_mock: false,
    ...overrides,
  };
}

/** 失败运行事件流 4 条 (升序; org.workflow.* + org.artifact.* + 失败收尾)。 */
export function sampleFailedTimeline(): TimelineEventSummary[] {
  return [
    sampleTimelineEvent({
      id: 'evt-501',
      seq: 501,
      project_id: 'P-806fe6e8',
      type: 'stage',
      event_type: 'org.workflow.created',
      message: '工作流创建 P-806fe6e8 开发链',
      status: 'OK',
      created_at: '2026-08-12T03:00:00.000000+00:00',
    }),
    sampleTimelineEvent({
      id: 'evt-502',
      seq: 502,
      project_id: 'P-806fe6e8',
      type: 'stage',
      event_type: 'org.workflow.stage_started',
      stage_id: 'STG-P-806fe6e8-R1786473507972-DEV',
      agent_id: 'developer',
      message: '阶段开始 development',
      status: 'running',
      created_at: '2026-08-12T03:00:05.000000+00:00',
    }),
    sampleTimelineEvent({
      id: 'evt-503',
      seq: 503,
      project_id: 'P-806fe6e8',
      type: 'artifact',
      event_type: 'org.artifact.created',
      stage_id: 'STG-P-806fe6e8-R1786473507972-DEV',
      artifact_id: 'P-806fe6e8-R1786473507972-CODE',
      message: '产物生成',
      status: 'OK',
      created_at: '2026-08-12T03:40:00.000000+00:00',
    }),
    sampleTimelineEvent({
      id: 'evt-504',
      seq: 504,
      project_id: 'P-806fe6e8',
      type: 'error',
      event_type: 'org.workflow.failed',
      stage_id: 'STG-P-806fe6e8-R1786473507972-DEV',
      agent_id: 'developer',
      message: '工作流失败: provider response contains no parseable patch or operations',
      status: 'FAIL',
      created_at: '2026-08-12T03:45:00.000000+00:00',
    }),
  ];
}

/**
 * Backlog 全量分组 (epics/features/stories/tasks; 层级引用: epic.children =
 * Feature id, feature.children = Story id, story.children = Task id — 非包含)。
 * 来源: 结构与 GET /api/projects/{id}/backlog 真实响应一致 (验证于 2026-08-11)。
 */
export function sampleBacklog(overrides: Partial<BacklogResponse> = {}): BacklogResponse {
  return {
    project_id: 'demo',
    epics: [
      {
        id: 'epic-1',
        name: '记账核心',
        description: '核心记账闭环',
        children: ['feat-1'],
        created_at: '2026-08-11T00:00:00Z',
        updated_at: '2026-08-11T00:00:00Z',
      },
    ],
    features: [
      {
        id: 'feat-1',
        name: '支出记录',
        description: '快速记录一笔支出',
        children: ['story-1'],
        created_at: '2026-08-11T00:00:00Z',
        updated_at: '2026-08-11T00:00:00Z',
      },
    ],
    stories: [
      {
        id: 'story-1',
        name: '记录支出',
        description: '作为用户, 我想快速记录支出',
        children: ['task-1'],
        created_at: '2026-08-11T00:00:00Z',
        updated_at: '2026-08-11T00:00:00Z',
      },
    ],
    tasks: [
      {
        id: 'task-1',
        title: '实现支出记录 API',
        description: 'POST /api/transactions 新增支出记录',
        priority: 'P1',
        status: 'in_progress',
        assignee: 'developer',
        dependency: [],
        created_at: '2026-08-11T00:00:00Z',
        updated_at: '2026-08-11T00:00:00Z',
        history: [
          { time: '2026-08-11T00:05:00Z', actor: 'developer', action: 'started', result: 'ok' },
        ],
      },
      {
        id: 'task-2',
        title: '月度分类统计',
        description: 'GET /api/reports/monthly 分类聚合',
        priority: 'P2',
        status: 'todo',
        assignee: '',
        dependency: ['task-1'],
        created_at: '2026-08-11T00:00:00Z',
        updated_at: '2026-08-11T00:00:00Z',
        history: [],
      },
    ],
    ...overrides,
  };
}
