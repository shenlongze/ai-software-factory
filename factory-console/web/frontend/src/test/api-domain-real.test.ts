/**
 * src/test/api-domain-real.test.ts — Domain Adapter 真实结构 fixture 测试 (S10-014 Task 007)。
 *
 * fixture 直接来自真实后端响应 (GET http://127.0.0.1:8011, 2026-08-11 实测):
 *   - /api/projects → ProjectSummary[] (markpad / P-100b4453 / P-16775f9f)
 *   - /api/projects/{id}/workflow → WorkflowDetail (P-16775f9f 设计链, 3 阶段)
 *   - /api/projects/{id}/timeline → TimelineEventSummary[] (P-16775f9f 前 2 条)
 *   - /api/dashboard.agents → 后端 AgentSummary[] (id/name/role/status/skills/current_task)
 * 字段保留真实值 (仅截断/省略无关项), 证明 Adapter 吃真实 JSON 结构不崩溃、映射正确。
 */

import { describe, expect, it } from 'vitest';
import type { ProjectSummary, TimelineEventSummary, WorkflowDetail } from '../models/types';
import {
  toAgentSummary,
  toRuntimeActivity,
  toTodoTree,
  toWorkflowPipeline,
  toWorkspaceProject,
} from '../api/domain';

/** 真实 /api/projects 响应 (2026-08-11): P-16775f9f — status=idea, workflow active, 2 阶段完成 1 运行。 */
const REAL_PROJECT_ACTIVE: ProjectSummary = {
  id: 'P-16775f9f',
  name: 'ledger-app',
  description: '',
  language: '',
  repository: '',
  tech_stack: [],
  status: 'idea',
  lifecycle_stage: null,
  lifecycle_status: null,
  pending_approvals: 0,
  tasks: {},
  last_activity: null,
  workflow_id: 'WF-P-16775f9f-R1786354365624-DESIGN',
  workflow_name: 'P-16775f9f 设计链 (product→ux_ui→design) [R1786354365624]',
  workflow_status: 'active',
  current_stage: 'design',
  current_stage_status: 'running',
  progress: 0.6667,
  stage_counts: { completed: 2, running: 1 },
};

/** 真实 /api/projects 响应: P-100b4453 — workflow failed + 1 failed + 2 blocked。 */
const REAL_PROJECT_FAILED: ProjectSummary = {
  ...REAL_PROJECT_ACTIVE,
  id: 'P-100b4453',
  workflow_id: 'WF-P-100b4453-R1786354225741-DESIGN',
  workflow_name: 'P-100b4453 设计链 (product→ux_ui→design) [R1786354225741]',
  workflow_status: 'failed',
  current_stage: 'product',
  current_stage_status: 'failed',
  progress: 0.0,
  stage_counts: { failed: 1, blocked: 2 },
};

/** 真实 /api/projects 响应: markpad — status=active, 无 workflow, stage_counts 空。 */
const REAL_PROJECT_MARKPAD: ProjectSummary = {
  id: 'markpad',
  name: 'markpad',
  description: 'MarkPad — 跨平台 Markdown 编辑器 (Flutter/Dart, Typora-like)',
  language: 'dart',
  repository: '/Users/Shared/work/markpad',
  tech_stack: ['flutter', 'dart'],
  status: 'active',
  lifecycle_stage: null,
  lifecycle_status: null,
  pending_approvals: 0,
  tasks: {},
  last_activity: null,
  workflow_id: null,
  workflow_name: null,
  workflow_status: null,
  current_stage: null,
  current_stage_status: null,
  progress: 0.0,
  stage_counts: {},
};

/** 真实 /api/projects/{id}/workflow 响应 (P-16775f9f, 2026-08-11): 3 阶段链。 */
const REAL_WORKFLOW: WorkflowDetail = {
  id: 'WF-P-16775f9f-R1786354365624-DESIGN',
  project_id: 'P-16775f9f',
  project_name: 'ledger-app',
  name: 'P-16775f9f 设计链 (product→ux_ui→design) [R1786354365624]',
  status: 'active',
  failed_reason: '',
  created_at: '2026-08-10T09:32:45.712868+00:00',
  started_at: '2026-08-10T09:32:45.720477+00:00',
  completed_at: null,
  stages: [
    {
      id: 'STG-P-16775f9f-R1786354365624-PRODUCT',
      workflow_id: 'WF-P-16775f9f-R1786354365624-DESIGN',
      role_id: 'product-manager',
      name: 'product',
      order: 1,
      status: 'completed',
      depends_on: [],
      input_artifacts: ['P-16775f9f-R1786354365624-IDEA'],
      output_artifacts: ['P-16775f9f-R1786354365624-PRODUCT'],
      approval_required: false,
      artifact: {
        id: 'P-16775f9f-R1786354365624-PRODUCT',
        stage_id: 'STG-P-16775f9f-R1786354365624-PRODUCT',
        workflow_id: 'WF-P-16775f9f-R1786354365624-DESIGN',
        project_id: 'P-16775f9f',
        type: 'product',
        ref: 'file:///docs/product.json',
        version: '1',
        status: 'validated',
        producer_role: 'product-manager',
        producer_agent: '',
        location: '',
        created_at: '2026-08-10T09:33:39.387132+00:00',
        updated_at: '2026-08-10T09:33:39.388477+00:00',
      },
      pending_approval: null,
    },
    {
      id: 'STG-P-16775f9f-R1786354365624-UXUI',
      workflow_id: 'WF-P-16775f9f-R1786354365624-DESIGN',
      role_id: 'ui-designer',
      name: 'ux_ui',
      order: 2,
      status: 'completed',
      depends_on: ['STG-P-16775f9f-R1786354365624-PRODUCT'],
      input_artifacts: ['P-16775f9f-R1786354365624-PRODUCT'],
      output_artifacts: ['P-16775f9f-R1786354365624-UXUI'],
      approval_required: false,
      artifact: {
        id: 'P-16775f9f-R1786354365624-UXUI',
        stage_id: 'STG-P-16775f9f-R1786354365624-UXUI',
        workflow_id: 'WF-P-16775f9f-R1786354365624-DESIGN',
        project_id: 'P-16775f9f',
        type: 'ux_ui',
        ref: 'file:///docs/ux_ui.json',
        version: '1',
        status: 'validated',
        producer_role: 'ui-designer',
        producer_agent: '',
        location: '',
        created_at: '2026-08-10T09:36:24.112211+00:00',
        updated_at: '2026-08-10T09:36:24.115813+00:00',
      },
      pending_approval: null,
    },
    {
      id: 'STG-P-16775f9f-R1786354365624-DESIGN',
      workflow_id: 'WF-P-16775f9f-R1786354365624-DESIGN',
      role_id: 'architect',
      name: 'design',
      order: 3,
      status: 'running',
      depends_on: ['STG-P-16775f9f-R1786354365624-UXUI'],
      input_artifacts: ['P-16775f9f-R1786354365624-PRODUCT', 'P-16775f9f-R1786354365624-UXUI'],
      output_artifacts: [],
      approval_required: false,
      artifact: null,
      pending_approval: null,
    },
  ],
  pending_approvals: [],
  template: ['Idea', 'PM', 'Product', 'UX/UI', 'Architecture', 'Development', 'Test', 'Release'],
  is_mock: false,
};

/** 真实 /api/projects/{id}/timeline 响应前 2 条 (P-16775f9f, 2026-08-11)。 */
const REAL_TIMELINE: TimelineEventSummary[] = [
  {
    id: 'evt-61',
    seq: 61,
    project_id: 'P-16775f9f',
    type: 'stage',
    event_type: 'org.workflow.created',
    stage_id: null,
    agent_id: null,
    artifact_id: null,
    gate_id: null,
    message: '工作流创建 P-16775f9f 设计链 (product→ux_ui→design) [R1786354365624]',
    status: 'OK',
    payload: { workflow_id: 'WF-P-16775f9f-R1786354365624-DESIGN', status: 'draft', stage_count: 0 },
    created_at: '2026-08-10T09:32:45.713312+00:00',
  },
  {
    id: 'evt-65',
    seq: 65,
    project_id: 'P-16775f9f',
    type: 'artifact',
    event_type: 'org.artifact.created',
    stage_id: 'STG-P-16775f9f-R1786354365624-PRODUCT',
    agent_id: null,
    artifact_id: 'P-16775f9f-R1786354365624-IDEA',
    gate_id: null,
    message: '产物生成',
    status: 'OK',
    payload: { artifact_id: 'P-16775f9f-R1786354365624-IDEA', type: 'idea', status: 'created', version: '1' },
    created_at: '2026-08-10T09:32:45.717412+00:00',
  },
];

/** 真实 /api/dashboard.agents 形状 (后端 AgentSummary: status=WORKING 大写)。 */
const REAL_AGENT_WORKING = {
  id: 'agent-1',
  name: 'Planner',
  role: 'planner',
  status: 'WORKING',
  skills: ['planning'],
  current_task: 'write plan',
};

describe('api/domain 真实结构 — toWorkspaceProject (/api/projects 实测)', () => {
  it('P-16775f9f: status=idea → discovery 阶段 + 想法标签, progress 67, risk 0', () => {
    const p = toWorkspaceProject(REAL_PROJECT_ACTIVE);
    expect(p.id).toBe('P-16775f9f');
    expect(p.name).toBe('ledger-app');
    expect(p.lifecycleStage).toBe('discovery');
    expect(p.lifecycleLabel).toBe('想法');
    expect(p.progress).toBe(67);
    expect(p.pendingApprovals).toBe(0);
    expect(p.riskCount).toBe(0);
  });

  it('P-100b4453: riskCount = failed(1) + blocked(2) = 3', () => {
    const p = toWorkspaceProject(REAL_PROJECT_FAILED);
    expect(p.riskCount).toBe(3);
    expect(p.progress).toBe(0);
  });

  it('markpad: status=active → development 阶段, progress 0, risk 0', () => {
    const p = toWorkspaceProject(REAL_PROJECT_MARKPAD);
    expect(p.lifecycleStage).toBe('development');
    expect(p.lifecycleLabel).toBe('活跃');
    expect(p.progress).toBe(0);
    expect(p.riskCount).toBe(0);
  });
});

describe('api/domain 真实结构 — toTodoTree (/api/projects 实测降级树)', () => {
  it('P-16775f9f: stage_counts {completed:2, running:1} → 两阶段完成一阶段运行', () => {
    const tree = toTodoTree(REAL_PROJECT_ACTIVE);
    expect(tree.root.title).toBe('ledger-app');
    expect(tree.root.children).toHaveLength(3);
    expect(tree.root.children.map((c) => c.status)).toEqual([
      'completed',
      'completed',
      'running',
    ]);
    expect(tree.root.status).toBe('running');
  });

  it('P-100b4453: workflow failed + blocked → 首阶段 failed, 次阶段 blocked', () => {
    const tree = toTodoTree(REAL_PROJECT_FAILED);
    expect(tree.root.children.map((c) => c.status)).toEqual(['failed', 'blocked', 'pending']);
    expect(tree.root.status).toBe('failed');
  });

  it('markpad: 无 workflow 信号 → active 语义 (产品完成/开发运行中)', () => {
    const tree = toTodoTree(REAL_PROJECT_MARKPAD);
    expect(tree.root.children.map((c) => c.status)).toEqual([
      'completed',
      'running',
      'pending',
    ]);
  });
});

describe('api/domain 真实结构 — toWorkflowPipeline (/api/projects/{id}/workflow 实测)', () => {
  it('P-16775f9f 设计链: 3 阶段 + 人话名称/角色', () => {
    const pipeline = toWorkflowPipeline(REAL_PROJECT_ACTIVE, REAL_WORKFLOW);
    expect(pipeline.templateId).toBe('WF-P-16775f9f-R1786354365624-DESIGN');
    expect(pipeline.templateName).toBe(
      'P-16775f9f 设计链 (product→ux_ui→design) [R1786354365624]',
    );
    expect(pipeline.stages).toHaveLength(3);
    const [s1, s2, s3] = pipeline.stages;
    expect(s1.name).toBe('产品设计');
    expect(s1.agentName).toBe('产品经理');
    expect(s1.status).toBe('completed');
    expect(s1.artifact).toBe('file:///docs/product.json');
    expect(s2.name).toBe('UI/UX 设计');
    expect(s2.agentName).toBe('UI 设计师');
    expect(s2.status).toBe('completed');
    expect(s3.name).toBe('架构设计');
    expect(s3.agentName).toBe('架构师');
    expect(s3.status).toBe('running');
  });

  it('detail 缺失 → 用 project.workflow_name 兜底', () => {
    const pipeline = toWorkflowPipeline(REAL_PROJECT_ACTIVE, null);
    expect(pipeline.templateName).toBe(REAL_PROJECT_ACTIVE.workflow_name);
    expect(pipeline.stages).toHaveLength(0);
  });
});

describe('api/domain 真实结构 — toRuntimeActivity (/api/projects/{id}/timeline 实测)', () => {
  it('真实事件 → 活动条目 (message 人话优先, status=OK 保留)', () => {
    const activities = toRuntimeActivity(REAL_TIMELINE);
    expect(activities).toHaveLength(2);
    expect(activities[0].time).toBe('2026-08-10T09:32:45.713312+00:00');
    expect(activities[0].action).toContain('工作流创建');
    expect(activities[0].result).toBe('OK');
    expect(activities[0].actor).toBe('');
    expect(activities[1].action).toBe('产物生成');
  });
});

describe('api/domain 真实结构 — toAgentSummary (/api/dashboard.agents 实测)', () => {
  it('WORKING 大写状态 → available, 技能直传', () => {
    const agent = toAgentSummary(REAL_AGENT_WORKING);
    expect(agent.id).toBe('agent-1');
    expect(agent.name).toBe('Planner');
    expect(agent.role).toBe('planner');
    expect(agent.status).toBe('available');
    expect(agent.skills).toEqual(['planning']);
  });
});
