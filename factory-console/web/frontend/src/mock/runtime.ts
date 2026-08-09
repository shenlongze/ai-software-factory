/**
 * mock/runtime.ts — S10-002 Runtime API 的 mock 数据 (无后端可展示)。
 *
 * 约束: mock 仅作 fallback — 数据缺失/请求失败时由 client.withMockFallback
 * 注入, 全部携带 is_mock: true 标记 (诚实标注, 不冒充真实数据); 形状对齐
 * 后端 mock (service.build_mock_workflow) 与 mock/workspace.ts MOCK_PROJECTS
 * (Product→UX/UI→Architecture→Code→Test→Release, Architecture 待审核)。
 */

import type {
  StageRunSummary,
  TimelineEventSummary,
  WorkflowDetail,
} from '../models/types';

/** mock 工作流详情 (与后端 build_mock_workflow 同形状; is_mock 恒 true)。 */
export function mockWorkflowDetail(projectId = 'ledger-app', projectName = '记账 App'): WorkflowDetail {
  const stage = (
    id: string,
    name: string,
    roleId: string,
    status: string,
    artifactType: string | null,
  ) => ({
    id,
    workflow_id: `mock-wf-${projectId}`,
    role_id: roleId,
    name,
    order: 0,
    status,
    depends_on: [],
    input_artifacts: [],
    output_artifacts: [],
    approval_required: status === 'waiting_review',
    artifact: artifactType
      ? {
          id: `mock-art-${id}`,
          stage_id: id,
          workflow_id: `mock-wf-${projectId}`,
          project_id: projectId,
          type: artifactType,
          ref: `mock://${artifactType}`,
          version: '1',
          status: 'validated',
          producer_role: roleId,
          producer_agent: '',
          location: '',
          created_at: '2026-08-10T00:00:00+00:00',
          updated_at: '2026-08-10T00:00:00+00:00',
        }
      : null,
    pending_approval: status === 'waiting_review'
      ? {
          id: 'mock-gate-arch',
          stage_id: id,
          workflow_id: `mock-wf-${projectId}`,
          project_id: projectId,
          status: 'pending',
          reviewer: '',
          comment: '',
          requested_at: '2026-08-10T00:00:00+00:00',
          approved_at: null,
          rejected_at: null,
        }
      : null,
  });

  return {
    id: `mock-wf-${projectId}`,
    project_id: projectId,
    project_name: projectName,
    name: 'Mock Workflow (演示数据)',
    status: 'active',
    failed_reason: '',
    created_at: '2026-08-10T00:00:00+00:00',
    started_at: '2026-08-10T00:00:00+00:00',
    completed_at: null,
    is_mock: true,
    stages: [
      { ...stage('mock-product', 'Product', 'product-manager', 'completed', 'product'), order: 1 },
      { ...stage('mock-ux_ui', 'UX/UI', 'ui-designer', 'completed', 'ux_ui'), order: 2 },
      { ...stage('mock-architect', 'Architecture', 'architect', 'waiting_review', 'design'), order: 3 },
      { ...stage('mock-developer', 'Code', 'developer', 'pending', null), order: 4 },
      { ...stage('mock-tester', 'Test', 'tester', 'pending', null), order: 5 },
      { ...stage('mock-release', 'Release', 'devops', 'pending', null), order: 6 },
    ],
    pending_approvals: [
      {
        id: 'mock-gate-arch',
        stage_id: 'mock-architect',
        workflow_id: `mock-wf-${projectId}`,
        project_id: projectId,
        status: 'pending',
        reviewer: '',
        comment: '',
        requested_at: '2026-08-10T00:00:00+00:00',
        approved_at: null,
        rejected_at: null,
      },
    ],
    template: ['Idea', 'PM', 'Product', 'UX/UI', 'Architecture', 'Development', 'Test', 'Release'],
  };
}

/** mock 阶段运行明细 (Task 面板数据源; is_mock 由调用方透传标记)。 */
export function mockStageRuns(projectId = 'ledger-app'): StageRunSummary[] {
  const run = (
    id: string,
    name: string,
    roleId: string,
    status: string,
    artifactType: string | null,
    durationS: number | null,
    costUsd: number | null,
  ): StageRunSummary => ({
    id,
    workflow_id: `mock-wf-${projectId}`,
    role_id: roleId,
    name,
    order: 0,
    status,
    agent_id: roleId,
    duration_s: durationS,
    cost_usd: costUsd,
    started_at: '2026-08-10T00:00:00+00:00',
    completed_at: status === 'completed' ? '2026-08-10T00:02:00+00:00' : null,
    depends_on: [],
    input_artifacts: [],
    output_artifacts: artifactType ? [`mock-art-${id}`] : [],
    artifacts: artifactType
      ? [
          {
            id: `mock-art-${id}`,
            stage_id: id,
            workflow_id: `mock-wf-${projectId}`,
            project_id: projectId,
            type: artifactType,
            ref: `mock://${artifactType}`,
            version: '1',
            status: 'validated',
            producer_role: roleId,
            producer_agent: '',
            location: '',
            created_at: '2026-08-10T00:02:00+00:00',
            updated_at: '2026-08-10T00:02:00+00:00',
          },
        ]
      : [],
  });

  return [
    { ...run('mock-product', 'Product', 'product-manager', 'completed', 'product', 120, 0.05), order: 1 },
    { ...run('mock-ux_ui', 'UX/UI', 'ui-designer', 'completed', 'ux_ui', 95, 0.04), order: 2 },
    { ...run('mock-architect', 'Architecture', 'architect', 'waiting_review', 'design', 60, 0.03), order: 3 },
    { ...run('mock-developer', 'Code', 'developer', 'pending', null, null, null), order: 4 },
    { ...run('mock-tester', 'Test', 'tester', 'pending', null, null, null), order: 5 },
    { ...run('mock-release', 'Release', 'devops', 'pending', null, null, null), order: 6 },
  ];
}

/** mock Timeline 事件流 (Agent Timeline 数据源; user/stage/artifact/review 五类)。 */
export function mockTimeline(projectId = 'ledger-app'): TimelineEventSummary[] {
  const node = (
    seq: number,
    type: TimelineEventSummary['type'],
    message: string,
    extra: Partial<TimelineEventSummary> = {},
  ): TimelineEventSummary => ({
    id: `evt-${seq}`,
    seq,
    project_id: projectId,
    type,
    event_type: '',
    stage_id: null,
    agent_id: null,
    artifact_id: null,
    gate_id: null,
    message,
    status: 'OK',
    payload: {},
    created_at: '2026-08-10T00:00:00+00:00',
    ...extra,
  });

  return [
    node(1, 'user', '项目创建: 记账 App', { event_type: 'org.project.created' }),
    node(2, 'stage', '工作流启动', { event_type: 'org.workflow.started', agent_id: 'pm' }),
    node(3, 'stage', '阶段开始 PM', {
      event_type: 'org.workflow.stage_started',
      stage_id: 'mock-product',
      agent_id: 'product-manager',
    }),
    node(4, 'artifact', '产物生成', {
      event_type: 'org.artifact.created',
      artifact_id: 'mock-art-product',
    }),
    node(5, 'stage', '阶段完成 Product', {
      event_type: 'org.workflow.stage_completed',
      stage_id: 'mock-product',
      agent_id: 'product-manager',
    }),
    node(6, 'review', '审批待处理 (需求/设计/发布门)', {
      event_type: 'org.approval.created',
      gate_id: 'mock-gate-arch',
      stage_id: 'mock-architect',
    }),
  ];
}
