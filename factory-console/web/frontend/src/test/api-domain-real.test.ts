/**
 * src/test/api-domain-real.test.ts — Domain Adapter 真实结构 fixture 测试 (S10-014 Task 007 + S10-015 Task 002)。
 *
 * fixture 直接来自真实后端响应 (GET http://127.0.0.1:8011, 实测):
 *   - /api/projects → ProjectSummary[] (markpad / P-100b4453 / P-16775f9f)
 *   - /api/projects/{id}/workflow → WorkflowDetail (P-16775f9f 设计链, 3 阶段)
 *   - /api/projects/{id}/timeline → TimelineEventSummary[] (P-16775f9f 前 2 条)
 *   - /api/projects/P-806fe6e8/backlog → BacklogResponse (S10-015 §2.1, 2026-08-12 实测:
 *     3 Epic / 2 Feature / 2 Story / 3 Task, 含 2 个孤儿 Epic + children id 引用)
 *   - /api/dashboard.agents → 后端 AgentSummary[] (id/name/role/status/skills/current_task)
 * 字段保留真实值 (仅截断/省略无关项), 证明 Adapter 吃真实 JSON 结构不崩溃、映射正确。
 */

import { describe, expect, it } from 'vitest';
import type {
  ProjectSummary,
  TimelineEventSummary,
  WorkflowDetail,
} from '../models/types';
import type { BacklogResponse } from '../models/domain';
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

/** 真实 /api/projects/P-806fe6e8/backlog 响应 (S10-015 §2.1, 2026-08-12 实测节选):
 * 3 Epic (含 2 个孤儿 children=[] + 1 个带子), 2 Feature, 2 Story, 3 Task。
 * 字段保留真实值; 层级只靠 children id 引用 (无回溯字段), Task 全部 todo。 */
const REAL_BACKLOG_P806FE6E8: BacklogResponse = {
  project_id: 'P-806fe6e8',
  epics: [
    {
      id: 'EPIC-6ffd3c02',
      name: '计分核心',
      description: '台球计分',
      children: [],
      created_at: '2026-08-11T17:49:45.602701Z',
      updated_at: '2026-08-11T17:49:45.602701Z',
    },
    {
      id: 'EPIC-89bcd292',
      name: 'UI 界面',
      description: 'Flutter 界面',
      children: [],
      created_at: '2026-08-11T17:49:45.602701Z',
      updated_at: '2026-08-11T17:49:45.602701Z',
    },
    {
      id: 'EPIC-c6cac2d8',
      name: '计分核心',
      description: '台球计分核心功能',
      children: ['FEAT-39a91953', 'FEAT-f6d9c303'],
      created_at: '2026-08-11T17:49:45.602701Z',
      updated_at: '2026-08-11T17:49:45.602701Z',
    },
  ],
  features: [
    {
      id: 'FEAT-39a91953',
      name: '用户系统',
      description: '注册登录',
      children: ['STORY-9f928023'],
      created_at: '2026-08-11T17:49:45.602701Z',
      updated_at: '2026-08-11T17:49:45.602701Z',
    },
    {
      id: 'FEAT-f6d9c303',
      name: '比赛管理',
      description: '创建比赛/计分',
      children: ['STORY-317aed7b'],
      created_at: '2026-08-11T17:49:45.602701Z',
      updated_at: '2026-08-11T17:49:45.602701Z',
    },
  ],
  stories: [
    {
      id: 'STORY-9f928023',
      name: '用户注册',
      description: '手机号注册',
      children: ['TASK-a8a01f8d', 'TASK-e10a6043'],
      created_at: '2026-08-11T17:49:45.602701Z',
      updated_at: '2026-08-11T17:49:45.602701Z',
    },
    {
      id: 'STORY-317aed7b',
      name: '创建比赛',
      description: '新比赛',
      children: ['TASK-425bf30b'],
      created_at: '2026-08-11T17:49:45.602701Z',
      updated_at: '2026-08-11T17:49:45.602701Z',
    },
  ],
  tasks: [
    {
      id: 'TASK-425bf30b',
      title: '计分逻辑',
      description: '实时计分',
      priority: 'P0',
      status: 'todo',
      assignee: '',
      dependency: [],
      created_at: '2026-08-11T17:49:45.602701Z',
      updated_at: '2026-08-11T17:49:45.602701Z',
      history: [],
    },
    {
      id: 'TASK-a8a01f8d',
      title: '实现注册 API',
      description: 'POST /api/register',
      priority: 'P1',
      status: 'todo',
      assignee: '',
      dependency: [],
      created_at: '2026-08-11T17:49:45.602701Z',
      updated_at: '2026-08-11T17:49:45.602701Z',
      history: [],
    },
    {
      id: 'TASK-e10a6043',
      title: '实现登录 API',
      description: 'POST /api/login JWT',
      priority: 'P1',
      status: 'todo',
      assignee: '',
      dependency: [],
      created_at: '2026-08-11T17:49:45.602701Z',
      updated_at: '2026-08-11T17:49:45.602701Z',
      history: [],
    },
  ],
};

describe('api/domain 真实结构 — toTodoTree (/api/projects/P-806fe6e8/backlog 实测)', () => {
  it('孤儿 Epic 保留为空阶段: 3 phase (2 空 + 1 带子), root 聚合', () => {
    const tree = toTodoTree(REAL_BACKLOG_P806FE6E8, 'ScorePocket');
    expect(tree.root.id).toBe('root');
    expect(tree.root.title).toBe('ScorePocket');
    expect(tree.root.type).toBe('phase');
    expect(tree.root.children).toHaveLength(3);
    const [orphan1, orphan2, main] = tree.root.children;
    expect(orphan1.id).toBe('EPIC-6ffd3c02');
    expect(orphan1.title).toBe('计分核心');
    expect(orphan1.status).toBe('pending');
    expect(orphan1.progress).toBe(0);
    expect(orphan1.children).toHaveLength(0);
    expect(orphan2.id).toBe('EPIC-89bcd292');
    expect(orphan2.title).toBe('UI 界面');
    expect(orphan2.children).toHaveLength(0);
    expect(main.id).toBe('EPIC-c6cac2d8');
    expect(main.children).toHaveLength(2);
  });

  it('children id 反向索引组装: Epic→Feature→Story→Task 层级与真实引用一致', () => {
    const tree = toTodoTree(REAL_BACKLOG_P806FE6E8, 'ScorePocket');
    const main = tree.root.children[2];
    // EPIC-c6cac2d8.children → [FEAT-39a91953, FEAT-f6d9c303]
    expect(main.children.map((m) => m.id)).toEqual(['FEAT-39a91953', 'FEAT-f6d9c303']);
    expect(main.children.map((m) => m.type)).toEqual(['module', 'module']);
    const userSystem = main.children[0];
    expect(userSystem.title).toBe('用户系统');
    expect(userSystem.children).toHaveLength(1);
    const story = userSystem.children[0];
    expect(story.id).toBe('STORY-9f928023');
    expect(story.title).toBe('用户注册');
    expect(story.type).toBe('task');
    // STORY-9f928023.children → [TASK-a8a01f8d, TASK-e10a6043]
    expect(story.children.map((t) => t.id)).toEqual(['TASK-a8a01f8d', 'TASK-e10a6043']);
    expect(story.children.map((t) => t.title)).toEqual(['实现注册 API', '实现登录 API']);
    expect(story.children.map((t) => t.type)).toEqual(['task', 'task']);
    const match = main.children[1];
    expect(match.title).toBe('比赛管理');
    expect(match.children[0].children[0].id).toBe('TASK-425bf30b');
    expect(match.children[0].children[0].title).toBe('计分逻辑');
  });

  it('Task 六态映射 + Story 聚合: 全 todo → pending, 完成度 0', () => {
    const tree = toTodoTree(REAL_BACKLOG_P806FE6E8, 'ScorePocket');
    const userSystem = tree.root.children[2].children[0];
    const story = userSystem.children[0];
    expect(story.children[0].status).toBe('pending'); // todo → pending
    expect(story.children[1].status).toBe('pending');
    expect(story.status).toBe('pending'); // 全 todo (无完成信号) → pending
    expect(story.progress).toBe(0);
    expect(userSystem.status).toBe('pending');
    expect(userSystem.progress).toBe(0);
    expect(tree.root.status).toBe('pending');
    expect(tree.root.progress).toBe(0);
  });

  it('真实任务详情字段透传: priority/description 保留在 BacklogTask (输入契约不丢数据)', () => {
    const tree = toTodoTree(REAL_BACKLOG_P806FE6E8, 'ScorePocket');
    const scoreTask = tree.root.children[2].children[1].children[0].children[0];
    expect(scoreTask.id).toBe('TASK-425bf30b');
    expect(scoreTask.title).toBe('计分逻辑');
    // 输入层 BacklogTask 保留真实字段 (priority P0 / 空 assignee / 空 dependency)
    const raw = REAL_BACKLOG_P806FE6E8.tasks?.[0];
    expect(raw?.priority).toBe('P0');
    expect(raw?.assignee).toBe('');
    expect(raw?.dependency).toEqual([]);
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
