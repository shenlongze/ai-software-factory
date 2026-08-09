/**
 * src/test/fixtures.ts — 测试数据工厂 + fetch 桩辅助 (仅测试用, 不计覆盖率)。
 *
 * 数据形状对齐 src/models/types.ts (11A 响应模型投影)。
 */

import type {
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
  WorkflowDetail,
  WorkflowSummary,
} from '../models/types';

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

/** org 审批门 (S9-001 ApprovalGate; Console 决定操作对象 — Approval 页)。 */
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

/** POST approve/reject 决定结果投影。 */
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

/** 阶段链节点 (WorkflowDetail.stages)。 */
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

/** org Workflow 运行摘要 (Workflow 页表格行)。 */
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

/** 单 Workflow 8 阶段链全视图 (Workflow 页详情)。 */
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

/** org Artifact 投影 (6 类产物链, Artifacts 页表格行)。 */
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

/** product Artifact 详情 (S9-003 Review 数据源: PRD 6 节 + pending 审批门)。 */
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

/** ux_ui Artifact 详情 (S9-003: 7 节 + wireframe ASCII 预览数据源)。 */
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

export function sampleDashboard(overrides: Partial<ConsoleDashboard> = {}): ConsoleDashboard {
  return {
    projects: [sampleProject()],
    approvals: [sampleApproval()],
    agents: [
      {
        id: 'agent-1',
        name: 'Planner',
        role: 'planner',
        status: 'WORKING',
        skills: ['planning'],
        current_task: 'write plan',
      },
    ],
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
