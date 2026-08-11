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
import { sampleBacklog } from './fixtures';
import type {
  BacklogEpic,
  BacklogFeature,
  BacklogResponse,
  BacklogStory,
  BacklogTask,
} from '../models/domain';

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

// ------------------------------------------------------------------ toTodoTree (S10-015 Task 002: BacklogResponse 重构)

/** BacklogEpic 快捷工厂 (真实结构: id/name/children id 引用, 无 status)。 */
function bep(id: string, name: string, children: string[] = []): BacklogEpic {
  return { id, name, children };
}

/** BacklogFeature 快捷工厂。 */
function bfeat(id: string, name: string, children: string[] = []): BacklogFeature {
  return { id, name, children };
}

/** BacklogStory 快捷工厂。 */
function bstory(id: string, name: string, children: string[] = []): BacklogStory {
  return { id, name, children };
}

/** BacklogTask 快捷工厂 (真实结构: title/priority/status)。 */
function btask(id: string, title: string, status: string, priority: string = 'P2'): BacklogTask {
  return { id, title, status, priority };
}

describe('api/domain — toTodoTree 层级映射 (children id 反向索引)', () => {
  it('完整映射: Epic→phase / Feature→module / Story→task(带子Task) / Task→task 子节点', () => {
    const backlog: BacklogResponse = {
      epics: [bep('EPIC-1', '计分核心', ['FEAT-1'])],
      features: [bfeat('FEAT-1', '用户系统', ['STORY-1'])],
      stories: [bstory('STORY-1', '用户注册', ['TASK-1', 'TASK-2'])],
      tasks: [btask('TASK-1', '实现注册 API', 'done', 'P0'), btask('TASK-2', '实现登录 API', 'todo', 'P1')],
    };
    const tree = toTodoTree(backlog, 'ScorePocket');
    expect(tree.root.id).toBe('root');
    expect(tree.root.title).toBe('ScorePocket');
    expect(tree.root.type).toBe('phase');
    expect(tree.root.children).toHaveLength(1);
    const phase = tree.root.children[0];
    expect(phase.type).toBe('phase');
    expect(phase.title).toBe('计分核心');
    expect(phase.children).toHaveLength(1);
    const module = phase.children[0];
    expect(module.type).toBe('module');
    expect(module.title).toBe('用户系统');
    expect(module.children).toHaveLength(1);
    const story = module.children[0];
    expect(story.type).toBe('task');
    expect(story.title).toBe('用户注册');
    expect(story.children).toHaveLength(2);
    expect(story.children[0].type).toBe('task');
    expect(story.children[0].title).toBe('实现注册 API');
    expect(story.children[1].title).toBe('实现登录 API');
  });
});

describe('api/domain — toTodoTree Task 六态映射 (含 review)', () => {
  it.each([
    ['todo', 'pending'],
    ['ready', 'pending'],
    ['in_progress', 'running'],
    ['blocked', 'blocked'],
    ['review', 'review'],
    ['done', 'completed'],
  ] as const)('status=%s → %s', (raw, expected) => {
    const backlog: BacklogResponse = {
      epics: [bep('E', '阶段', ['F'])],
      features: [bfeat('F', '模块', ['S'])],
      stories: [bstory('S', '故事', ['T'])],
      tasks: [btask('T', '任务', raw)],
    };
    const leaf = toTodoTree(backlog).root.children[0].children[0].children[0].children[0];
    expect(leaf.status).toBe(expected);
  });
});

describe('api/domain — toTodoTree Story 状态聚合 (子 Task 派生)', () => {
  function storyTree(taskStatuses: Array<[string, string]>): ReturnType<typeof toTodoTree> {
    const backlog: BacklogResponse = {
      epics: [bep('E', '阶段', ['F'])],
      features: [bfeat('F', '模块', ['S'])],
      stories: [bstory('S', '故事', taskStatuses.map(([id]) => id))],
      tasks: taskStatuses.map(([id, status]) => btask(id, `任务-${id}`, status)),
    };
    return toTodoTree(backlog);
  }

  it('全 done → completed', () => {
    const story = storyTree([
      ['T1', 'done'],
      ['T2', 'done'],
    ]).root.children[0].children[0].children[0];
    expect(story.status).toBe('completed');
  });

  it('有 in_progress → running', () => {
    const story = storyTree([
      ['T1', 'done'],
      ['T2', 'in_progress'],
    ]).root.children[0].children[0].children[0];
    expect(story.status).toBe('running');
  });

  it('有 blocked → blocked', () => {
    const story = storyTree([
      ['T1', 'done'],
      ['T2', 'blocked'],
    ]).root.children[0].children[0].children[0];
    expect(story.status).toBe('blocked');
  });

  it('有 review → review', () => {
    const story = storyTree([
      ['T1', 'done'],
      ['T2', 'review'],
    ]).root.children[0].children[0].children[0];
    expect(story.status).toBe('review');
  });

  it('全部 todo/ready (无完成信号) → pending', () => {
    const story = storyTree([
      ['T1', 'todo'],
      ['T2', 'ready'],
    ]).root.children[0].children[0].children[0];
    expect(story.status).toBe('pending');
  });
});

describe('api/domain — toTodoTree 完成度 (P0-P3 加权)', () => {
  function treeWithTasks(tasks: Array<[string, string, string]>): ReturnType<typeof toTodoTree> {
    const backlog: BacklogResponse = {
      epics: [bep('E', '阶段', ['F'])],
      features: [bfeat('F', '模块', ['S'])],
      stories: [bstory('S', '故事', tasks.map(([id]) => id))],
      tasks: tasks.map(([id, status, priority]) => btask(id, `任务-${id}`, status, priority)),
    };
    return toTodoTree(backlog);
  }

  it('叶子 Task: done=100%, todo=0%', () => {
    const tree = treeWithTasks([
      ['T1', 'done', 'P0'],
      ['T2', 'todo', 'P0'],
    ]);
    const story = tree.root.children[0].children[0].children[0];
    expect(story.children[0].progress).toBe(100);
    expect(story.children[1].progress).toBe(0);
  });

  it('Story 加权: P0 done + P3 todo → 80% (P0=4 权重大于 P3=1)', () => {
    const tree = treeWithTasks([
      ['T1', 'done', 'P0'],
      ['T2', 'todo', 'P3'],
    ]);
    const story = tree.root.children[0].children[0].children[0];
    expect(story.progress).toBe(80); // (4*100 + 1*0) / 5
  });

  it('反向: P0 todo + P3 done → 20% (P0 权重拖低)', () => {
    const tree = treeWithTasks([
      ['T1', 'todo', 'P0'],
      ['T2', 'done', 'P3'],
    ]);
    const story = tree.root.children[0].children[0].children[0];
    expect(story.progress).toBe(20); // (4*0 + 1*100) / 5
  });

  it('无 priority → 权重 1 (等同 P3)', () => {
    const backlog: BacklogResponse = {
      epics: [bep('E', '阶段', ['F'])],
      features: [bfeat('F', '模块', ['S'])],
      stories: [bstory('S', '故事', ['T1', 'T2'])],
      tasks: [
        { id: 'T1', title: '无优先级-完成', status: 'done' },
        { id: 'T2', title: '无优先级-待办', status: 'todo' },
      ],
    };
    const story = toTodoTree(backlog).root.children[0].children[0].children[0];
    expect(story.progress).toBe(50); // (1*100 + 1*0) / 2
  });

  it('阶段/模块递归加权聚合: 单 Story 50% → module=50% → phase=50%', () => {
    const backlog: BacklogResponse = {
      epics: [bep('E', '阶段', ['F'])],
      features: [bfeat('F', '模块', ['S'])],
      stories: [bstory('S', '故事', ['T1'])],
      tasks: [btask('T1', '任务', 'done')],
    };
    const tree = toTodoTree(backlog);
    const phase = tree.root.children[0];
    const module = phase.children[0];
    expect(module.progress).toBe(100);
    expect(phase.progress).toBe(100);
    expect(tree.root.progress).toBe(100);
  });
});

describe('api/domain — toTodoTree 孤儿/悬空/空降级', () => {
  it('孤儿 Epic (children=[]) → 保留为空阶段 (pending, 0%)', () => {
    const backlog: BacklogResponse = {
      epics: [bep('EPIC-orphan', 'UI 界面'), bep('EPIC-2', '有子', ['F1'])],
      features: [bfeat('F1', '模块', [])],
      stories: [],
      tasks: [],
    };
    const tree = toTodoTree(backlog);
    expect(tree.root.children).toHaveLength(2);
    const orphan = tree.root.children[0];
    expect(orphan.id).toBe('EPIC-orphan');
    expect(orphan.title).toBe('UI 界面');
    expect(orphan.type).toBe('phase');
    expect(orphan.status).toBe('pending');
    expect(orphan.progress).toBe(0);
    expect(orphan.children).toHaveLength(0);
  });

  it('悬空引用 (children 指向不存在的 id) → 跳过, 不崩溃', () => {
    const backlog: BacklogResponse = {
      epics: [bep('E', '阶段', ['F-missing', 'F-ok'])],
      features: [bfeat('F-ok', '存在的模块', ['S-missing'])],
      stories: [bstory('S-ok', '存在的故事', ['T-missing'])],
      tasks: [btask('T-ok', '存在的任务', 'done')],
    };
    const tree = toTodoTree(backlog);
    const phase = tree.root.children[0];
    expect(phase.children).toHaveLength(1);
    expect(phase.children[0].title).toBe('存在的模块');
    expect(phase.children[0].children).toHaveLength(0); // S-missing 悬空 → Story 跳过
  });

  it('空 backlog → 单根降级 (projectName, phase, pending, 0%)', () => {
    const tree = toTodoTree({ epics: [], features: [], stories: [], tasks: [] }, 'ScorePocket');
    expect(tree.root.id).toBe('root');
    expect(tree.root.title).toBe('ScorePocket');
    expect(tree.root.type).toBe('phase');
    expect(tree.root.status).toBe('pending');
    expect(tree.root.progress).toBe(0);
    expect(tree.root.children).toHaveLength(0);
  });

  it('空 backlog 且缺 projectName → root.title=项目', () => {
    const tree = toTodoTree({ epics: [], features: [], stories: [], tasks: [] });
    expect(tree.root.title).toBe('项目');
    expect(tree.root.children).toHaveLength(0);
  });

  it('backlog 为 null / undefined → 单根降级 (不崩溃)', () => {
    expect(toTodoTree(null, 'P').root.title).toBe('P');
    expect(toTodoTree(undefined, 'P').root.title).toBe('P');
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

// ------------------------------------------------------------------ toTaskDetail (S10-015 Task 005: backlog 定位 + 关联)

describe('api/domain — toTaskDetail backlog 定位 + Epic/Feature/Story 关联', () => {
  it('从 backlog 定位 Task + 关联 Epic/Feature/Story (为什么存在)', () => {
    const detail = toTaskDetail(sampleBacklog(), 'task-1');
    expect(detail.id).toBe('task-1');
    expect(detail.title).toBe('实现支出记录 API');
    expect(detail.description).toBe('POST /api/transactions 新增支出记录');
    expect(detail.status).toBe('running');
    expect(detail.statusLabel).toBe('执行中');
    expect(detail.owner).toBe('developer');
    expect(detail.agent).toBe('开发工程师'); // assignee → ROLE_LABELS 人话
    expect(detail.priority).toBe('P1');
    expect(detail.epicName).toBe('记账核心');
    expect(detail.featureName).toBe('支出记录');
    expect(detail.storyName).toBe('记录支出');
    expect(detail.dependency).toEqual([]);
    expect(detail.history).toHaveLength(1);
    expect(detail.history[0]).toEqual({
      time: '2026-08-11T00:05:00Z',
      actor: 'developer',
      action: 'started',
      result: 'ok',
    });
  });

  it('assignee 空串 → owner/agent undefined (诚实降级); 依赖透传; 孤儿 Task 关联缺失', () => {
    const detail = toTaskDetail(sampleBacklog(), 'task-2');
    expect(detail.owner).toBeUndefined();
    expect(detail.agent).toBeUndefined();
    expect(detail.priority).toBe('P2');
    expect(detail.dependency).toEqual(['task-1']);
    expect(detail.status).toBe('pending');
    // task-2 不在任何 story.children (孤儿) → Epic/Feature/Story 关联缺失, 诚实降级
    expect(detail.epicName).toBeUndefined();
    expect(detail.featureName).toBeUndefined();
    expect(detail.storyName).toBeUndefined();
    expect(detail.history).toHaveLength(0);
  });

  it('taskId 未找到 → 降级空对象 (不崩溃)', () => {
    const detail = toTaskDetail(sampleBacklog(), 'no-such-task');
    expect(detail.id).toBe('');
    expect(detail.title).toBe('');
    expect(detail.status).toBe('pending');
    expect(detail.epicName).toBeUndefined();
  });

  it('null / undefined backlog → 降级空对象 (不崩溃)', () => {
    expect(toTaskDetail(null, 'task-1').id).toBe('');
    expect(toTaskDetail(undefined, 'task-1').id).toBe('');
  });

  it('backlog 内 Task 无匹配 (孤儿) → 降级, 不抛异常', () => {
    const detail = toTaskDetail(sampleBacklog({ tasks: [] }), 'task-1');
    expect(detail.id).toBe('');
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
    // S10-015 Task 005: agent_id → ROLE_LABELS 人话 + Agent 后缀 (不再是原始 role id)
    expect(activities[0].actor).toBe('产品经理 Agent');
    expect(activities[0].action).toBe('工作流创建 Demo');
    // S10-015 Task 005: status → result 人话 (OK → 通过)
    expect(activities[0].result).toBe('通过');
    // stage_id/event_type 透传 (Runtime Timeline 关联用)
    expect(activities[0].stageId).toBeUndefined();
    expect(activities[0].eventType).toBe('org.workflow.created');
  });

  it('agent_id → 人话 Agent; 未知 role 原样 (不臆造)', () => {
    const [a] = toRuntimeActivity([{ agent_id: 'developer' }]);
    expect(a.actor).toBe('开发工程师 Agent');
    const [b] = toRuntimeActivity([{ agent_id: 'custom-role' }]);
    expect(b.actor).toBe('custom-role');
  });

  it('无 agent (null/空) → 系统; source/actor 原样透传', () => {
    const [a] = toRuntimeActivity([{ event_type: 'org.workflow.failed' }]);
    expect(a.actor).toBe('系统');
    const [b] = toRuntimeActivity([{ source: 'engine' }]);
    expect(b.actor).toBe('engine');
    const [c] = toRuntimeActivity([{ actor: 'console' }]);
    expect(c.actor).toBe('console');
  });

  it('stage_id 透传 → RuntimeActivity.stageId', () => {
    const [a] = toRuntimeActivity([{ stage_id: 'STG-dev' }]);
    expect(a.stageId).toBe('STG-dev');
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
    // S10-015 Task 005: 已知状态值 → 人话 result (ok → 通过)
    expect(a.result).toBe('通过');
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

  it('缺字段事件 → 默认值, 不崩溃 (无 agent → 系统)', () => {
    const [a] = toRuntimeActivity([{}]);
    expect(a.time).toBe('');
    expect(a.actor).toBe('系统');
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
