/**
 * src/test/fixtures-structure.test.ts — fixture 结构校验测试 (S10-014 Task 008)。
 *
 * 职责: 保证 src/test/fixtures.ts 每个 fixture 与后端真实 API 响应结构一致
 * (models/types.ts 投影)。字段子集断言 = 真实响应键集合的超集保护:
 *   - 每个 fixture 至少包含对应类型的全部必填键 (缺键 → 测试失败)
 *   - 数组型 fixture (timeline/backlog) 逐元素校验
 *   - FIXTURE_SOURCES 标注覆盖 (每个 sample* 都有来源 + 验证日期)
 *
 * 真实结构对照 (2026-08-11, curl http://127.0.0.1:8011):
 *   GET /api/projects                      → ProjectSummary[]
 *   GET /api/dashboard                     → ConsoleDashboard (含 agents)
 *   GET /api/projects/{id}/workflow        → WorkflowDetail
 *   GET /api/projects/{id}/timeline        → TimelineEventSummary[]
 *   GET /api/projects/{id}/backlog         → {project_id, epics, features, stories, tasks}
 *   (backlog/sprints 本环境 404 — 项目无 management store; 结构取 factory-console
 *    service.list_backlog 真实契约: Epic/Feature/Story {id,name,description,children,
 *    created_at,updated_at}, Task 另含 title/priority/status/assignee/dependency/history)
 */

import { describe, expect, expectTypeOf, it } from 'vitest';
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
import {
  FIXTURE_SOURCES,
  sampleAgent,
  sampleApproval,
  sampleApprovalDecision,
  sampleApprovalGate,
  sampleArtifact,
  sampleArtifactDetail,
  sampleBacklog,
  sampleDashboard,
  sampleDecision,
  sampleExperience,
  sampleLifecycle,
  sampleProject,
  sampleProvider,
  sampleRecommendation,
  sampleTimelineEvents,
  sampleUXUIDetail,
  sampleWorkflow,
  sampleWorkflowDetail,
} from './fixtures';

/** 对象包含全部给定键 (宽松: 只要求键存在 — 子集断言, 允许多余键)。 */
function hasKeys(obj: unknown, keys: readonly string[]): boolean {
  return (
    typeof obj === 'object' &&
    obj !== null &&
    keys.every((k) => k in (obj as Record<string, unknown>))
  );
}

/** 数组全部元素满足键子集。 */
function everyHasKeys(arr: unknown, keys: readonly string[]): boolean {
  return Array.isArray(arr) && arr.every((item) => hasKeys(item, keys));
}

// ------------------------------------------------------------------ 真实 API 键集合 (验证于 2026-08-11)

const PROJECT_KEYS = [
  'id',
  'name',
  'description',
  'language',
  'repository',
  'tech_stack',
  'status',
  'lifecycle_stage',
  'lifecycle_status',
  'pending_approvals',
  'tasks',
  'last_activity',
  'workflow_id',
  'workflow_name',
  'workflow_status',
  'current_stage',
  'current_stage_status',
  'progress',
  'stage_counts',
] as const;

const STAGE_KEYS = [
  'id',
  'workflow_id',
  'role_id',
  'name',
  'order',
  'status',
  'depends_on',
  'input_artifacts',
  'output_artifacts',
  'approval_required',
  'artifact',
  'pending_approval',
] as const;

const TIMELINE_EVENT_KEYS = [
  'id',
  'seq',
  'project_id',
  'type',
  'event_type',
  'stage_id',
  'agent_id',
  'artifact_id',
  'gate_id',
  'message',
  'status',
  'payload',
  'created_at',
] as const;

/** backlog 层级项 (Epic/Feature/Story 真实契约键)。 */
const BACKLOG_NODE_KEYS = ['id', 'name', 'description', 'children', 'created_at', 'updated_at'] as const;

/** backlog Task 真实契约键 (org.management Task: title 而非 name; priority/status 枚举)。 */
const BACKLOG_TASK_KEYS = [
  'id',
  'title',
  'description',
  'priority',
  'status',
  'assignee',
  'dependency',
  'created_at',
  'updated_at',
  'history',
] as const;

const AGENT_KEYS = ['id', 'name', 'role', 'status', 'skills', 'current_task'] as const;

const APPROVAL_KEYS = [
  'id',
  'artifact_id',
  'artifact_type',
  'gate',
  'status',
  'confidence',
  'risk',
  'evidence',
  'idea_id',
  'by',
  'comment',
  'requested_at',
  'artifact_version',
] as const;

const APPROVAL_DECISION_KEYS = ['action', 'gate', 'workflow_id', 'workflow_status'] as const;

const ARTIFACT_KEYS = [
  'id',
  'stage_id',
  'workflow_id',
  'project_id',
  'type',
  'ref',
  'version',
  'status',
  'producer_role',
  'producer_agent',
  'location',
  'created_at',
  'updated_at',
] as const;

const DECISION_KEYS = [
  'id',
  'decision_type',
  'subject_id',
  'description',
  'status',
  'options',
  'recommendation',
  'score',
  'confidence',
  'reasoning',
  'evidence',
  'risk',
  'risk_level',
  'requires_approval',
  'approval_request_id',
  'created_at',
] as const;

const LIFECYCLE_KEYS = [
  'project_id',
  'lifecycle_id',
  'idea_id',
  'template_name',
  'status',
  'current_stage',
  'completed_stages',
  'pending_approval',
  'next_actions',
] as const;

const RECOMMENDATION_KEYS = [
  'id',
  'target_type',
  'candidate',
  'score',
  'factors',
  'explanation',
  'evidence',
  'confidence',
  'risk',
  'created_at',
] as const;

const EXPERIENCE_KEYS = [
  'id',
  'domain',
  'subject',
  'result',
  'score',
  'confidence',
  'freshness',
  'task_type',
  'capability',
  'created_at',
] as const;

const PROVIDER_KEYS = [
  'id',
  'name',
  'type',
  'status',
  'capabilities',
  'models',
  'version',
  'cost',
  'performance',
  'experience',
  'usage_calls',
] as const;

const DASHBOARD_KEYS = [
  'projects',
  'approvals',
  'agents',
  'decisions',
  'cost',
  'experience',
  'activity',
] as const;

const GATE_KEYS = [
  'id',
  'stage_id',
  'workflow_id',
  'project_id',
  'status',
  'reviewer',
  'comment',
  'requested_at',
  'approved_at',
  'rejected_at',
] as const;

const WORKFLOW_SUMMARY_KEYS = [
  'id',
  'project_id',
  'project_name',
  'name',
  'status',
  'stage_count',
  'completed_count',
  'progress',
  'current_stage',
  'current_stage_status',
  'failed_reason',
] as const;

const WORKFLOW_DETAIL_KEYS = [
  'id',
  'project_id',
  'project_name',
  'name',
  'status',
  'failed_reason',
  'created_at',
  'started_at',
  'completed_at',
  'stages',
  'pending_approvals',
  'template',
] as const;

// ------------------------------------------------------------------ 单 fixture 结构断言

describe('fixtures — 结构 = 真实 API 响应 (models/types.ts 兼容)', () => {
  it('sampleProject 与 GET /api/projects 单条响应键一致', () => {
    const p = sampleProject();
    expect(hasKeys(p, PROJECT_KEYS)).toBe(true);
    expect(typeof p.progress).toBe('number');
    expectTypeOf(p).toMatchTypeOf<ProjectSummary>();
  });

  it('sampleWorkflowDetail 与 GET /api/projects/{id}/workflow 响应键一致', () => {
    const wf = sampleWorkflowDetail();
    expect(hasKeys(wf, WORKFLOW_DETAIL_KEYS)).toBe(true);
    expect(wf.stages.length).toBeGreaterThan(0);
    expect(hasKeys(wf.stages[0], STAGE_KEYS)).toBe(true);
    expect(Array.isArray(wf.pending_approvals)).toBe(true);
    expect(Array.isArray(wf.template)).toBe(true);
    expectTypeOf(wf).toMatchTypeOf<WorkflowDetail>();
    expectTypeOf(wf.stages[0]).toMatchTypeOf<StageSummary>();
  });

  it('sampleWorkflow 与 GET /api/workflows 单条响应键一致', () => {
    const wf = sampleWorkflow();
    expect(hasKeys(wf, WORKFLOW_SUMMARY_KEYS)).toBe(true);
    expectTypeOf(wf).toMatchTypeOf<WorkflowSummary>();
  });

  it('sampleTimelineEvents 与 GET /api/projects/{id}/timeline 响应键一致', () => {
    const events = sampleTimelineEvents();
    expect(events.length).toBeGreaterThan(0);
    expect(everyHasKeys(events, TIMELINE_EVENT_KEYS)).toBe(true);
    for (const e of events) {
      expect(typeof e.seq).toBe('number');
      expect(typeof e.message).toBe('string');
      expect(typeof e.payload).toBe('object');
    }
    expectTypeOf(events).toMatchTypeOf<TimelineEventSummary[]>();
  });

  it('sampleBacklog 与 GET /api/projects/{id}/backlog 响应键一致 (四分组)', () => {
    const backlog = sampleBacklog();
    expect(hasKeys(backlog, ['project_id', 'epics', 'features', 'stories', 'tasks'])).toBe(true);
    expect(everyHasKeys(backlog.epics, BACKLOG_NODE_KEYS)).toBe(true);
    expect(everyHasKeys(backlog.features, BACKLOG_NODE_KEYS)).toBe(true);
    expect(everyHasKeys(backlog.stories, BACKLOG_NODE_KEYS)).toBe(true);
    expect(everyHasKeys(backlog.tasks, BACKLOG_TASK_KEYS)).toBe(true);
    for (const t of backlog.tasks) {
      expect(['P0', 'P1', 'P2', 'P3']).toContain(t.priority);
      expect(['todo', 'ready', 'in_progress', 'blocked', 'review', 'done']).toContain(t.status);
      expect(Array.isArray(t.dependency)).toBe(true);
    }
  });

  it('sampleAgent 与 GET /api/dashboard agents 条目键一致', () => {
    const agent = sampleAgent();
    expect(hasKeys(agent, AGENT_KEYS)).toBe(true);
    expect(Array.isArray(agent.skills)).toBe(true);
    expectTypeOf(agent).toMatchTypeOf<AgentSummary>();
  });

  it('sampleDashboard 与 GET /api/dashboard 七域键一致', () => {
    const dash = sampleDashboard();
    expect(hasKeys(dash, DASHBOARD_KEYS)).toBe(true);
    expect(Array.isArray(dash.projects)).toBe(true);
    expect(Array.isArray(dash.agents)).toBe(true);
    expectTypeOf(dash).toMatchTypeOf<ConsoleDashboard>();
  });

  it('sampleApprovalGate 与 org ApprovalGate 投影键一致 (S9-001)', () => {
    const gate = sampleApprovalGate();
    expect(hasKeys(gate, GATE_KEYS)).toBe(true);
    expectTypeOf(gate).toMatchTypeOf<ApprovalGateSummary>();
  });

  it('sampleApproval 与 ApprovalSummary 键一致', () => {
    const a = sampleApproval();
    expect(hasKeys(a, APPROVAL_KEYS)).toBe(true);
    expect(Array.isArray(a.evidence)).toBe(true);
    expectTypeOf(a).toMatchTypeOf<ApprovalSummary>();
  });

  it('sampleApprovalDecision 与 ApprovalDecisionSummary 键一致', () => {
    const d = sampleApprovalDecision();
    expect(hasKeys(d, APPROVAL_DECISION_KEYS)).toBe(true);
    expect(hasKeys(d.gate, GATE_KEYS)).toBe(true);
    expectTypeOf(d).toMatchTypeOf<ApprovalDecisionSummary>();
  });

  it('sampleArtifact 与 GET /api/artifacts 单条响应键一致', () => {
    const a = sampleArtifact();
    expect(hasKeys(a, ARTIFACT_KEYS)).toBe(true);
    expectTypeOf(a).toMatchTypeOf<ArtifactSummary>();
  });

  it('sampleArtifactDetail / sampleUXUIDetail 与 ArtifactDetail 键一致 (summary + metadata + review)', () => {
    for (const detail of [sampleArtifactDetail(), sampleUXUIDetail()]) {
      expect(hasKeys(detail, ARTIFACT_KEYS)).toBe(true);
      expect(hasKeys(detail, ['metadata', 'review'])).toBe(true);
      expect(typeof detail.metadata).toBe('object');
      expectTypeOf(detail).toMatchTypeOf<ArtifactDetail>();
    }
  });

  it('sampleDecision 与 DecisionSummary 键一致', () => {
    const d = sampleDecision();
    expect(hasKeys(d, DECISION_KEYS)).toBe(true);
    expect(Array.isArray(d.options)).toBe(true);
    expect(d.options.length).toBeGreaterThan(0);
    expectTypeOf(d).toMatchTypeOf<DecisionSummary>();
  });

  it('sampleLifecycle 与 LifecycleSummary 键一致', () => {
    const lc = sampleLifecycle();
    expect(hasKeys(lc, LIFECYCLE_KEYS)).toBe(true);
    expect(Array.isArray(lc.completed_stages)).toBe(true);
    expect(Array.isArray(lc.next_actions)).toBe(true);
    expectTypeOf(lc).toMatchTypeOf<LifecycleSummary>();
  });

  it('sampleRecommendation 与 RecommendationSummary 键一致', () => {
    const r = sampleRecommendation();
    expect(hasKeys(r, RECOMMENDATION_KEYS)).toBe(true);
    expect(typeof r.factors).toBe('object');
    expectTypeOf(r).toMatchTypeOf<RecommendationSummary>();
  });

  it('sampleExperience 与 ExperienceSummary 键一致', () => {
    const e = sampleExperience();
    expect(hasKeys(e, EXPERIENCE_KEYS)).toBe(true);
    expect(Array.isArray(e.capability)).toBe(true);
    expectTypeOf(e).toMatchTypeOf<ExperienceSummary>();
  });

  it('sampleProvider 与 ProviderSummary 键一致', () => {
    const p = sampleProvider();
    expect(hasKeys(p, PROVIDER_KEYS)).toBe(true);
    expect(Array.isArray(p.capabilities)).toBe(true);
    expect(Array.isArray(p.models)).toBe(true);
    expectTypeOf(p).toMatchTypeOf<ProviderSummary>();
  });
});

// ------------------------------------------------------------------ 来源标注覆盖

describe('fixtures — 来源标注 (结构与真实 API 一致 + 验证日期)', () => {
  const ANNOTATION_PATTERN = /结构与 (GET|POST) \/api\/.+ 真实响应一致 \(验证于 2026-08-11\)/;

  const KNOWN_FIXTURES = [
    'sampleProject',
    'sampleApproval',
    'sampleApprovalGate',
    'sampleApprovalDecision',
    'sampleStage',
    'sampleWorkflow',
    'sampleWorkflowDetail',
    'sampleArtifact',
    'sampleArtifactDetail',
    'sampleUXUIDetail',
    'sampleDecision',
    'sampleLifecycle',
    'sampleRecommendation',
    'sampleExperience',
    'sampleProvider',
    'sampleDashboard',
    'sampleTimelineEvents',
    'sampleBacklog',
    'sampleAgent',
  ] as const;

  it('每个 sample* fixture 都有 FIXTURE_SOURCES 来源标注', () => {
    for (const name of KNOWN_FIXTURES) {
      expect(FIXTURE_SOURCES[name], `${name} 缺少来源标注`).toBeDefined();
      expect(FIXTURE_SOURCES[name]).toMatch(ANNOTATION_PATTERN);
      expect(FIXTURE_SOURCES[name]).toContain('2026-08-11');
    }
  });

  it('FIXTURE_SOURCES 不包含多余键 (防标注漂移)', () => {
    expect(Object.keys(FIXTURE_SOURCES).sort()).toEqual([...KNOWN_FIXTURES].sort());
  });
});
