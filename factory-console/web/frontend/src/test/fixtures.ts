/**
 * src/test/fixtures.ts — 测试数据工厂 + fetch 桩辅助 (仅测试用, 不计覆盖率)。
 *
 * 数据形状对齐 src/models/types.ts (11A 响应模型投影)。
 */

import type {
  ApprovalSummary,
  ConsoleDashboard,
  DecisionSummary,
  ExperienceSummary,
  LifecycleSummary,
  ProjectSummary,
  ProviderSummary,
  RecommendationSummary,
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
