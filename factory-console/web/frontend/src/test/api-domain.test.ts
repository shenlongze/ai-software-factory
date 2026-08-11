/**
 * src/test/api-domain.test.ts — Domain Adapter 真实转换测试 (S10-014 Task 007)。
 *
 * api/domain.ts 由 Task 001 占位 (返回默认值) 升级为真实转换 (S10-014-plan §2.5 + §6):
 *   字段映射 / 派生计算 (riskCount 等) / 聚合 (TodoTree) / 降级 (§6.3 缺失 → 默认值, 不崩溃)。
 * 本文件覆盖: 正常映射 / 缺失降级 / 边界 (空/null/未知状态)。
 */

import { describe, expect, it } from 'vitest';
import type {
  ProjectSummary,
  StageRunSummary,
  WorkflowDetail,
} from '../models/types';
import {
  toAgentSummary,
  toDomainStatus,
  toRuntimeActivity,
  toTaskDetail,
  toTodoTree,
  toWorkflowPipeline,
  toWorkspaceProject,
} from '../api/domain';
import type { BacklogInput } from '../api/domain';

/** 完整 ProjectSummary 工厂 (真实后端结构, 见 models/types.ts)。 */
function proj(overrides: Partial<ProjectSummary> = {}): ProjectSummary {
  return {
    id: 'demo',
    name: 'Demo Project',
    description: '',
    language: '',
    repository: '',
    tech_stack: [],
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
    progress: 0,
    stage_counts: {},
    ...overrides,
  };
}

/** WorkflowDetail 工厂 (真实后端结构, 见 models/types.ts)。 */
function wf(overrides: Partial<WorkflowDetail> = {}): WorkflowDetail {
  return {
    id: 'wf-1',
    project_id: 'demo',
    project_name: 'Demo Project',
    name: '记账 App',
    status: 'active',
    failed_reason: '',
    created_at: '2026-08-06T00:00:00Z',
    started_at: '2026-08-06T00:00:00Z',
    completed_at: null,
    stages: [],
    pending_approvals: [],
    template: ['Idea', 'PM', 'Product', 'UX/UI', 'Architecture', 'Development', 'Test', 'Release'],
    ...overrides,
  };
}

// ------------------------------------------------------------------ toWorkspaceProject

describe('api/domain — toWorkspaceProject 正常映射', () => {
  it('映射 lifecycle_stage / progress / pending_approvals / riskCount (failed+blocked)', () => {
    const p = toWorkspaceProject(
      proj({
        lifecycle_stage: 'development',
        progress: 0.6667,
        pending_approvals: 2,
        stage_counts: { failed: 1, blocked: 2, completed: 3 },
      }),
    );
    expect(p.id).toBe('demo');
    expect(p.name).toBe('Demo Project');
    expect(p.lifecycleStage).toBe('development');
    expect(p.lifecycleLabel).toBe('开发');
    expect(p.progress).toBe(67);
    expect(p.pendingApprovals).toBe(2);
    expect(p.riskCount).toBe(3);
  });

  it('lifecycle_stage 缺失 → 从 status 派生阶段语义 (idea → discovery)', () => {
    const p = toWorkspaceProject(proj({ lifecycle_stage: null, status: 'idea' }));
    expect(p.lifecycleStage).toBe('discovery');
    expect(p.lifecycleLabel).toBe('想法');
  });

  it('status=active → development 阶段语义', () => {
    const p = toWorkspaceProject(proj({ lifecycle_stage: null, status: 'active' }));
    expect(p.lifecycleStage).toBe('development');
  });

  it('riskCount 派生: stage_counts 无 failed/blocked → 0', () => {
    const p = toWorkspaceProject(proj({ stage_counts: { completed: 3 } }));
    expect(p.riskCount).toBe(0);
  });

  it('progress 边界: 1.0→100 / 0→0 / null→0 / 越界 1.5 夹取 100 / 0.5→50', () => {
    expect(toWorkspaceProject(proj({ progress: 1 })).progress).toBe(100);
    expect(toWorkspaceProject(proj({ progress: 0 })).progress).toBe(0);
    expect(toWorkspaceProject(proj({ progress: null as unknown as number })).progress).toBe(0);
    expect(toWorkspaceProject(proj({ progress: 1.5 })).progress).toBe(100);
    expect(toWorkspaceProject(proj({ progress: 0.5 })).progress).toBe(50);
  });
});

describe('api/domain — toWorkspaceProject 降级与边界', () => {
  it('未知 lifecycle_stage → lifecycleStage=draft (降级), 标签原样', () => {
    const p = toWorkspaceProject(proj({ lifecycle_stage: 'weird-phase' }));
    expect(p.lifecycleStage).toBe('draft');
    expect(p.lifecycleLabel).toBe('weird-phase');
  });

  it('空对象 → 全默认值, 不崩溃', () => {
    const p = toWorkspaceProject({} as ProjectSummary);
    expect(p.id).toBe('');
    expect(p.name).toBe('');
    expect(p.lifecycleStage).toBe('draft');
    expect(p.lifecycleLabel).toBe('—');
    expect(p.progress).toBe(0);
    expect(p.pendingApprovals).toBe(0);
    expect(p.riskCount).toBe(0);
  });

  it('undefined 输入 → 全默认值, 不崩溃', () => {
    const p = toWorkspaceProject(undefined);
    expect(p.id).toBe('');
    expect(p.riskCount).toBe(0);
  });

  it('pending_approvals / stage_counts 缺失 → 0', () => {
    const p = toWorkspaceProject(proj({ pending_approvals: undefined as unknown as number }));
    expect(p.pendingApprovals).toBe(0);
    expect(p.riskCount).toBe(0);
  });
});

// ------------------------------------------------------------------ toTodoTree

describe('api/domain — toTodoTree 项目级降级树 (lifecycle 派生)', () => {
  it('development → 产品 completed / 开发 running / 测试发布 pending, root 聚合', () => {
    const tree = toTodoTree(proj({ lifecycle_stage: 'development', progress: 0.5 }));
    expect(tree.root.id).toBe('demo');
    expect(tree.root.title).toBe('Demo Project');
    expect(tree.root.type).toBe('phase');
    expect(tree.root.children).toHaveLength(3);
    const [product, development, release] = tree.root.children;
    expect(product.title).toBe('产品设计');
    expect(product.type).toBe('phase');
    expect(product.status).toBe('completed');
    expect(product.progress).toBe(100);
    expect(development.title).toBe('开发');
    expect(development.status).toBe('running');
    expect(development.progress).toBe(50);
    expect(release.title).toBe('测试发布');
    expect(release.status).toBe('pending');
    expect(release.progress).toBe(0);
    expect(tree.root.status).toBe('running');
    expect(tree.root.progress).toBe(50);
    expect(tree.root.statusLabel).toBe('执行中');
  });

  it('idea (无 lifecycle) → 全部 pending; workflow failed → 首阶段 failed; blocked → 次阶段 blocked', () => {
    const tree = toTodoTree(
      proj({
        status: 'idea',
        workflow_status: 'failed',
        current_stage: 'product',
        current_stage_status: 'failed',
        stage_counts: { failed: 1, blocked: 2 },
      }),
    );
    const [product, development, release] = tree.root.children;
    expect(product.status).toBe('failed');
    expect(development.status).toBe('blocked');
    expect(release.status).toBe('pending');
    expect(tree.root.status).toBe('failed');
  });

  it('stage_counts 驱动: completed=2 + running=1 → 前两阶段完成, 第三阶段运行中', () => {
    const tree = toTodoTree(
      proj({ status: 'idea', workflow_status: 'active', stage_counts: { completed: 2, running: 1 } }),
    );
    const [product, development, release] = tree.root.children;
    expect(product.status).toBe('completed');
    expect(development.status).toBe('completed');
    expect(release.status).toBe('running');
    expect(tree.root.status).toBe('running');
    expect(tree.root.progress).toBe(83);
  });

  it('stage_counts.completed >= 3 → 全部 completed', () => {
    const tree = toTodoTree(proj({ status: 'idea', stage_counts: { completed: 3 } }));
    expect(tree.root.children.every((c) => c.status === 'completed')).toBe(true);
    expect(tree.root.status).toBe('completed');
    expect(tree.root.progress).toBe(100);
  });

  it('release → 测试发布 running; maintenance → 全部 completed', () => {
    const releaseTree = toTodoTree(proj({ lifecycle_stage: 'release' }));
    expect(releaseTree.root.children[2].status).toBe('running');
    const maintTree = toTodoTree(proj({ lifecycle_stage: 'maintenance' }));
    expect(maintTree.root.children.every((c) => c.status === 'completed')).toBe(true);
  });
});

describe('api/domain — toTodoTree backlog 聚合 (epic→phase, feature→module, task→task)', () => {
  const backlog: BacklogInput = {
    epics: [
      {
        id: 'ep-1',
        title: '记账核心',
        status: 'active',
        features: [
          {
            id: 'f-1',
            title: '支出记录',
            status: 'completed',
            items: [
              { id: 't-1', title: '记录表单', status: 'completed' },
              { id: 't-2', title: '分类统计', status: 'pending' },
            ],
          },
        ],
      },
    ],
  };

  it('三层聚合: phase(epic) → module(feature) → task(item)', () => {
    const tree = toTodoTree(proj(), backlog);
    expect(tree.root.title).toBe('Demo Project');
    const phase = tree.root.children[0];
    expect(phase.type).toBe('phase');
    expect(phase.title).toBe('记账核心');
    expect(phase.status).toBe('running');
    const module = phase.children[0];
    expect(module.type).toBe('module');
    expect(module.title).toBe('支出记录');
    expect(module.status).toBe('completed');
    expect(module.children).toHaveLength(2);
    const task = module.children[0];
    expect(task.type).toBe('task');
    expect(task.title).toBe('记录表单');
    expect(task.status).toBe('completed');
    expect(module.children[1].status).toBe('pending');
  });

  it('backlog 为数组 → 视为 epics', () => {
    const tree = toTodoTree(proj(), backlog.epics as unknown as BacklogInput);
    expect(tree.root.children[0].title).toBe('记账核心');
  });

  it('backlog 缺 epics / 空对象 / undefined / null → 项目级降级树 (不崩溃)', () => {
    expect(toTodoTree(proj(), {} as BacklogInput).root.children).toHaveLength(3);
    expect(toTodoTree(proj(), { epics: [] }).root.children).toHaveLength(3);
    expect(toTodoTree(proj(), undefined).root.children).toHaveLength(3);
    expect(toTodoTree(proj(), null).root.children).toHaveLength(3);
  });
});

// ------------------------------------------------------------------ toWorkflowPipeline

describe('api/domain — toWorkflowPipeline 正常映射', () => {
  it('workflowDetail.stages → 阶段名/角色/状态 人话映射', () => {
    const detail = wf({
      id: 'wf-1',
      name: '记账 App 设计链',
      stages: [
        {
          id: 's1',
          workflow_id: 'wf-1',
          role_id: 'product-manager',
          name: 'product',
          order: 1,
          status: 'completed',
          depends_on: [],
          input_artifacts: [],
          output_artifacts: [],
          approval_required: false,
          artifact: {
            id: 'art-1',
            stage_id: 's1',
            workflow_id: 'wf-1',
            project_id: 'demo',
            type: 'product',
            ref: 'file:///docs/product.json',
            version: '1',
            status: 'validated',
            producer_role: 'product-manager',
            producer_agent: '',
            location: '',
            created_at: '2026-08-06T00:00:00Z',
            updated_at: '2026-08-06T00:00:00Z',
          },
          pending_approval: null,
        },
        {
          id: 's2',
          workflow_id: 'wf-1',
          role_id: 'ui-designer',
          name: 'ux_ui',
          order: 2,
          status: 'running',
          depends_on: [],
          input_artifacts: [],
          output_artifacts: [],
          approval_required: false,
          artifact: null,
          pending_approval: null,
        },
        {
          id: 's3',
          workflow_id: 'wf-1',
          role_id: 'architect',
          name: 'design',
          order: 3,
          status: 'waiting',
          depends_on: [],
          input_artifacts: [],
          output_artifacts: [],
          approval_required: false,
          artifact: null,
          pending_approval: null,
        },
      ],
    });
    const pipeline = toWorkflowPipeline(proj(), detail);
    expect(pipeline.templateId).toBe('wf-1');
    expect(pipeline.templateName).toBe('记账 App 设计链');
    expect(pipeline.stages).toHaveLength(3);
    const [s1, s2, s3] = pipeline.stages;
    expect(s1.order).toBe(1);
    expect(s1.name).toBe('产品设计');
    expect(s1.agentName).toBe('产品经理');
    expect(s1.status).toBe('completed');
    expect(s1.statusLabel).toBe('已完成');
    expect(s1.artifact).toBe('file:///docs/product.json');
    expect(s2.name).toBe('UI/UX 设计');
    expect(s2.agentName).toBe('UI 设计师');
    expect(s2.status).toBe('running');
    expect(s2.statusLabel).toBe('执行中');
    expect(s3.name).toBe('架构设计');
    expect(s3.status).toBe('pending');
    expect(s3.agentName).toBe('架构师');
  });

  it('stages 独立参数 (StageRunSummary) → duration_s 映射为 duration', () => {
    const runs: StageRunSummary[] = [
      {
        id: 's1',
        workflow_id: 'wf-1',
        role_id: 'developer',
        name: 'development',
        order: 1,
        status: 'completed',
        agent_id: 'dev-agent',
        duration_s: 340,
        cost_usd: null,
        started_at: '2026-08-06T00:00:00Z',
        completed_at: '2026-08-06T00:01:00Z',
        depends_on: [],
        input_artifacts: [],
        output_artifacts: [],
        artifacts: [],
      },
    ];
    const pipeline = toWorkflowPipeline(proj(), null, runs);
    expect(pipeline.stages).toHaveLength(1);
    expect(pipeline.stages[0].name).toBe('开发');
    expect(pipeline.stages[0].agentName).toBe('dev-agent');
    expect(pipeline.stages[0].duration).toBe(340);
    expect(pipeline.stages[0].status).toBe('completed');
  });

  it('pending_approval 存在 → 阶段状态 review', () => {
    const detail = wf({
      stages: [
        {
          id: 's1',
          workflow_id: 'wf-1',
          role_id: 'pm',
          name: 'product',
          order: 1,
          status: 'pending',
          depends_on: [],
          input_artifacts: [],
          output_artifacts: [],
          approval_required: true,
          artifact: null,
          pending_approval: {
            id: 'gate-1',
            stage_id: 's1',
            workflow_id: 'wf-1',
            project_id: 'demo',
            status: 'pending',
            reviewer: 'console',
            comment: '',
            requested_at: '2026-08-06T00:00:00Z',
            approved_at: null,
            rejected_at: null,
          },
        },
      ],
    });
    const pipeline = toWorkflowPipeline(proj(), detail);
    expect(pipeline.stages[0].status).toBe('review');
    expect(pipeline.stages[0].statusLabel).toBe('待审核');
  });

  it('未知 stage status → pending (降级)', () => {
    const detail = wf({
      stages: [
        {
          id: 's1',
          workflow_id: 'wf-1',
          role_id: 'pm',
          name: 'product',
          order: 1,
          status: 'weird-state',
          depends_on: [],
          input_artifacts: [],
          output_artifacts: [],
          approval_required: false,
          artifact: null,
          pending_approval: null,
        },
      ],
    });
    expect(toWorkflowPipeline(proj(), detail).stages[0].status).toBe('pending');
  });
});

describe('api/domain — toWorkflowPipeline 降级', () => {
  it('无 workflow → templateName=未启动, stages=[] (不崩溃)', () => {
    const pipeline = toWorkflowPipeline(proj(), null);
    expect(pipeline.templateId).toBe('');
    expect(pipeline.templateName).toBe('未启动');
    expect(pipeline.stages).toHaveLength(0);
  });

  it('project.workflow_name 存在但 detail 缺失 → 用 project 字段兜底', () => {
    const pipeline = toWorkflowPipeline(proj({ workflow_id: 'wf-x', workflow_name: '运行中的链' }), null);
    expect(pipeline.templateId).toBe('wf-x');
    expect(pipeline.templateName).toBe('运行中的链');
  });

  it('undefined detail/stages → 降级', () => {
    const pipeline = toWorkflowPipeline(proj(), undefined, undefined);
    expect(pipeline.stages).toHaveLength(0);
  });
});

// ------------------------------------------------------------------ toTaskDetail

describe('api/domain — toTaskDetail 正常映射', () => {
  it('task 字段映射 + history 投影', () => {
    const detail = toTaskDetail({
      id: 't-1',
      title: 'API 开发',
      status: 'running',
      agent: 'dev-agent',
      owner: '开发 Agent',
      started_at: '2026-08-11T09:00:00Z',
      completed_at: null,
      next_action: '实现 /api/health 接口',
      blocked_reason: null,
      history: [
        {
          created_at: '2026-08-11T09:00:00Z',
          actor: 'dev-agent',
          action: '开始任务',
          result: '已启动',
        },
      ],
      artifacts: ['/artifacts/t-1/design.md'],
    });
    expect(detail.id).toBe('t-1');
    expect(detail.title).toBe('API 开发');
    expect(detail.status).toBe('running');
    expect(detail.statusLabel).toBe('执行中');
    expect(detail.agent).toBe('dev-agent');
    expect(detail.owner).toBe('开发 Agent');
    expect(detail.startedAt).toBe('2026-08-11T09:00:00Z');
    expect(detail.completedAt).toBeUndefined();
    expect(detail.nextAction).toBe('实现 /api/health 接口');
    expect(detail.blockedReason).toBeUndefined();
    expect(detail.history).toHaveLength(1);
    expect(detail.history[0]).toEqual({
      time: '2026-08-11T09:00:00Z',
      actor: 'dev-agent',
      action: '开始任务',
      result: '已启动',
    });
    expect(detail.artifacts).toEqual(['/artifacts/t-1/design.md']);
  });

  it('history 条目缺 action/result → 用 message/status 兜底', () => {
    const detail = toTaskDetail({
      history: [{ time: 't1', actor: 'a', message: '发生什么', status: 'OK' }],
    });
    expect(detail.history[0].action).toBe('发生什么');
    expect(detail.history[0].result).toBe('OK');
  });

  it('未知 status → pending', () => {
    expect(toTaskDetail({ id: 't-1', title: 'x', status: 'mystery' }).status).toBe('pending');
  });
});

describe('api/domain — toTaskDetail 降级', () => {
  it('字段缺失 → 可选字段 undefined, 列表空, 不崩溃', () => {
    const detail = toTaskDetail({});
    expect(detail.id).toBe('');
    expect(detail.title).toBe('');
    expect(detail.status).toBe('pending');
    expect(detail.agent).toBeUndefined();
    expect(detail.owner).toBeUndefined();
    expect(detail.startedAt).toBeUndefined();
    expect(detail.nextAction).toBeUndefined();
    expect(detail.blockedReason).toBeUndefined();
    expect(detail.history).toHaveLength(0);
    expect(detail.artifacts).toHaveLength(0);
  });

  it('null / undefined 输入 → 默认, 不崩溃', () => {
    expect(toTaskDetail(null).id).toBe('');
    expect(toTaskDetail(undefined).id).toBe('');
  });
});

// ------------------------------------------------------------------ toRuntimeActivity

describe('api/domain — toRuntimeActivity 正常映射', () => {
  it('timeline 事件 → 活动条目 (time/actor/action/result)', () => {
    const activities = toRuntimeActivity([
      {
        created_at: '2026-08-10T09:32:45.713312+00:00',
        agent_id: 'product-manager',
        message: '工作流创建 Demo',
        status: 'OK',
        event_type: 'org.workflow.created',
      },
    ]);
    expect(activities).toHaveLength(1);
    expect(activities[0].time).toBe('2026-08-10T09:32:45.713312+00:00');
    expect(activities[0].actor).toBe('product-manager');
    expect(activities[0].action).toBe('工作流创建 Demo');
    expect(activities[0].result).toBe('OK');
  });

  it('message 缺失 → event_type 人话映射', () => {
    const [a] = toRuntimeActivity([{ event_type: 'org.workflow.started' }]);
    expect(a.action).toBe('启动工作流');
  });

  it('EventSummary (dashboard.activity) 结构 → 活动条目', () => {
    const [a] = toRuntimeActivity([
      {
        timestamp: '2026-08-06T00:00:00Z',
        source: 'engine',
        action: 'completed',
        result: 'ok',
      },
    ]);
    expect(a.time).toBe('2026-08-06T00:00:00Z');
    expect(a.actor).toBe('engine');
    expect(a.action).toBe('completed');
    expect(a.result).toBe('ok');
  });

  it('projectName 参数 → 透传到每条活动', () => {
    const activities = toRuntimeActivity([{ message: 'x' }, { message: 'y' }], 'ledger-app');
    expect(activities.every((a) => a.projectName === 'ledger-app')).toBe(true);
  });
});

describe('api/domain — toRuntimeActivity 降级与边界', () => {
  it('空数组 / null / undefined → []', () => {
    expect(toRuntimeActivity([])).toHaveLength(0);
    expect(toRuntimeActivity(null)).toHaveLength(0);
    expect(toRuntimeActivity(undefined)).toHaveLength(0);
  });

  it('缺字段事件 → 默认值, 不崩溃', () => {
    const [a] = toRuntimeActivity([{}]);
    expect(a.time).toBe('');
    expect(a.actor).toBe('');
    expect(a.action).toBe('');
    expect(a.result).toBe('');
  });

  it('非数组输入 → []', () => {
    expect(toRuntimeActivity({} as unknown[])).toHaveLength(0);
  });
});

// ------------------------------------------------------------------ toAgentSummary

describe('api/domain — toAgentSummary 正常映射', () => {
  it('agent 实体 → 卡片字段', () => {
    const agent = toAgentSummary({
      id: 'a-1',
      name: 'Planner',
      role: 'planner',
      status: 'available',
      skills: ['planning', 'writing'],
      current_task: 'write plan',
    });
    expect(agent.id).toBe('a-1');
    expect(agent.name).toBe('Planner');
    expect(agent.role).toBe('planner');
    expect(agent.status).toBe('available');
    expect(agent.skills).toEqual(['planning', 'writing']);
    expect(agent.version).toBe('');
  });

  it('WORKING → available (工作中视为可用)', () => {
    expect(toAgentSummary({ status: 'WORKING' }).status).toBe('available');
  });

  it('success_rate / avg_duration 可选统计透传', () => {
    const agent = toAgentSummary({ success_rate: 0.95, avg_duration: 340 });
    expect(agent.successRate).toBe(0.95);
    expect(agent.avgDuration).toBe(340);
  });
});

describe('api/domain — toAgentSummary 降级与边界', () => {
  it('offline → disabled; retired → retired; 未知 → available', () => {
    expect(toAgentSummary({ status: 'offline' }).status).toBe('disabled');
    expect(toAgentSummary({ status: 'disabled' }).status).toBe('disabled');
    expect(toAgentSummary({ status: 'retired' }).status).toBe('retired');
    expect(toAgentSummary({ status: 'weird' }).status).toBe('available');
  });

  it('空对象 / null / undefined → 默认, 不崩溃', () => {
    expect(toAgentSummary({}).id).toBe('');
    expect(toAgentSummary({}).name).toBe('');
    expect(toAgentSummary({}).status).toBe('available');
    expect(toAgentSummary({}).skills).toHaveLength(0);
    expect(toAgentSummary(null).id).toBe('');
    expect(toAgentSummary(undefined).id).toBe('');
  });

  it('skills 非数组/缺失 → []', () => {
    expect(toAgentSummary({ skills: undefined }).skills).toHaveLength(0);
    expect(toAgentSummary({ skills: 'oops' as unknown as string[] }).skills).toHaveLength(0);
  });
});

// ------------------------------------------------------------------ toDomainStatus

describe('api/domain — toDomainStatus 状态归一', () => {
  it('标准值直通', () => {
    expect(toDomainStatus('completed')).toBe('completed');
    expect(toDomainStatus('running')).toBe('running');
    expect(toDomainStatus('pending')).toBe('pending');
    expect(toDomainStatus('blocked')).toBe('blocked');
    expect(toDomainStatus('failed')).toBe('failed');
    expect(toDomainStatus('review')).toBe('review');
  });

  it('常见别名归一 (大小写不敏感)', () => {
    expect(toDomainStatus('DONE')).toBe('completed');
    expect(toDomainStatus('error')).toBe('failed');
    expect(toDomainStatus('waiting')).toBe('pending');
    expect(toDomainStatus('ready')).toBe('pending');
    expect(toDomainStatus('active')).toBe('running');
    expect(toDomainStatus('working')).toBe('running');
    expect(toDomainStatus('awaiting_approval')).toBe('review');
  });

  it('null/空/未知 → fallback (默认 pending)', () => {
    expect(toDomainStatus(null)).toBe('pending');
    expect(toDomainStatus('')).toBe('pending');
    expect(toDomainStatus('mystery')).toBe('pending');
    expect(toDomainStatus(undefined, 'review')).toBe('review');
  });
});
