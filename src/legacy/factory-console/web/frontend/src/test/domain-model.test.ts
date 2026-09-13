/**
 * src/test/domain-model.test.ts — Frontend Domain Model 类型基础测试 (S10-014 Task 001)。
 *
 * models/domain.ts 为纯类型模块 (仅类型, 无运行时逻辑, 见 S10-014-plan §6.1);
 * 本测试验证:
 *   1. 全部 6 种 domain 对象可完整构造 (satisfies 在 tsc 层做结构绑定)
 *   2. 可选字段可省略 (缺失降级原则 §6.3: 字段缺失 → 默认值, 不崩溃)
 *   3. mock/projects.ts 示例数据 (ScorePocket) 与 domain 类型一致
 */

import { describe, expect, it } from 'vitest';
import type {
  AgentSummary,
  RuntimeActivity,
  TaskDetail,
  TodoTree,
  TreeNode,
  WorkflowPipeline,
  WorkspaceProject,
} from '../models/domain';
import { MOCK_PROJECTS, MOCK_TODO_TREE } from '../mock/projects';

describe('domain model — WorkspaceProject', () => {
  it('完整字段可构造 (生命周期阶段 + 派生计数)', () => {
    const project = {
      id: 'score-pocket',
      name: 'ScorePocket',
      lifecycleStage: 'development',
      lifecycleLabel: '开发中',
      progress: 62,
      pendingApprovals: 1,
      riskCount: 2,
    } satisfies WorkspaceProject;
    expect(project.id).toBe('score-pocket');
    expect(project.lifecycleLabel).toBe('开发中');
    expect(project.progress).toBe(62);
  });
});

describe('domain model — TodoTree / TreeNode', () => {
  it('三层层级 (phase → module → task) 可构造', () => {
    const tree = {
      root: {
        id: 'phase-dev',
        title: '开发阶段',
        type: 'phase',
        status: 'running',
        statusLabel: '执行中',
        progress: 62,
        children: [
          {
            id: 'mod-backend',
            title: 'Backend',
            type: 'module',
            status: 'running',
            statusLabel: '执行中',
            progress: 80,
            children: [
              {
                id: 'task-api',
                title: 'API 开发',
                type: 'task',
                status: 'running',
                statusLabel: '执行中',
                progress: 40,
                agent: 'backend-dev',
                owner: '开发 Agent',
                startedAt: '2026-08-11T09:00:00Z',
                nextAction: '实现 /api/health 接口',
                children: [],
              },
            ],
          },
        ],
      },
    } satisfies TodoTree;
    expect(tree.root.type).toBe('phase');
    expect(tree.root.children[0].children[0].type).toBe('task');
  });

  it('可选字段省略仍合法 (缺失降级)', () => {
    const leaf: TreeNode = {
      id: 'task-api',
      title: 'API 开发',
      type: 'task',
      status: 'pending',
      statusLabel: '待办',
      progress: 0,
      children: [],
    };
    expect(leaf.agent).toBeUndefined();
    expect(leaf.owner).toBeUndefined();
    expect(leaf.children).toHaveLength(0);
  });
});

describe('domain model — WorkflowPipeline / WorkflowStage', () => {
  it('流水线 + 阶段可构造', () => {
    const pipeline = {
      templateId: 'wf-ideation',
      templateName: '想法到发布',
      stages: [
        {
          order: 1,
          name: '需求分析',
          status: 'completed',
          statusLabel: '完成',
          agentName: '产品经理 Agent',
          duration: 120,
        },
        {
          order: 2,
          name: '架构设计',
          status: 'running',
          statusLabel: '执行中',
          agentName: '架构 Agent',
          currentTask: '系统设计文档',
          artifact: 'design.md',
        },
      ],
    } satisfies WorkflowPipeline;
    expect(pipeline.stages).toHaveLength(2);
    expect(pipeline.stages[0].order).toBe(1);
    expect(pipeline.stages[1].artifact).toBe('design.md');
  });
});

describe('domain model — RuntimeActivity / TaskDetail / AgentSummary', () => {
  it('RuntimeActivity 可构造 (项目名可选)', () => {
    const activity = {
      time: '2026-08-11T10:00:00Z',
      actor: '开发 Agent',
      action: '实现 API 开发',
      result: '已完成',
      projectName: 'ScorePocket',
    } satisfies RuntimeActivity;
    expect(activity.actor).toBe('开发 Agent');
  });

  it('TaskDetail 可构造 (history/artifacts 必填列表)', () => {
    const detail = {
      id: 'task-api',
      title: 'API 开发',
      status: 'running',
      statusLabel: '执行中',
      agent: 'backend-dev',
      owner: '开发 Agent',
      startedAt: '2026-08-11T09:00:00Z',
      nextAction: '实现 /api/health 接口',
      history: [
        {
          time: '2026-08-11T09:00:00Z',
          actor: '开发 Agent',
          action: '开始任务',
          result: '已启动',
        },
      ],
      artifacts: ['/artifacts/task-api/design.md'],
    } satisfies TaskDetail;
    expect(detail.history).toHaveLength(1);
    expect(detail.artifacts[0]).toContain('task-api');
  });

  it('AgentSummary 可构造 (统计可选)', () => {
    const agent = {
      id: 'backend-dev',
      name: '开发 Agent',
      role: 'developer',
      status: 'available',
      skills: ['TypeScript', 'Python'],
      version: '1.2.0',
      successRate: 0.95,
      avgDuration: 340,
    } satisfies AgentSummary;
    expect(agent.skills).toContain('TypeScript');
    expect(agent.successRate).toBeGreaterThan(0.9);
  });
});

describe('domain model — mock/projects.ts 数据一致性 (ScorePocket)', () => {
  it('MOCK_PROJECTS 全部满足 WorkspaceProject', () => {
    expect(MOCK_PROJECTS.length).toBeGreaterThan(0);
    const pocket = MOCK_PROJECTS.find((p) => p.id === 'score-pocket');
    expect(pocket).toBeDefined();
    expect(pocket?.name).toBe('ScorePocket');
  });

  it('MOCK_TODO_TREE 满足 TodoTree 且包含 ScorePocket 示例结构', () => {
    expect(MOCK_TODO_TREE.root.children.length).toBeGreaterThan(0);
    expect(MOCK_TODO_TREE.root.type).toBe('phase');
  });
});
