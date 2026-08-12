/**
 * src/test/dashboard-adapter.test.ts — Dashboard Adapter 单元测试 (S10-015 Task 006)。
 *
 * 测试对象: toDashboardViewModel (api/domain.ts) — 组合真实 dashboard + projects +
 * workflow + timeline + backlog → DashboardViewModel (6 域, 缺失 → 空/Unavailable)。
 *
 * 数据来源: 真实环境 fixtures (sampleDashboardReal: 2 项目 + 3 Agent AVAILABLE +
 * 1 pending 审批 + cost/experience + activity [] 诚实空态; sampleFailedWorkflow:
 * P-806fe6e8 failed 3 阶段链; sampleBacklogP806: 3 todo Task)。
 *
 * 关键断言:
 * - projects → WorkspaceProject (复用 toWorkspaceProject)
 * - agents AVAILABLE → runningAgents [] (诚实: 无执行中)
 * - agents RUNNING/EXECUTING → runningAgents (名称/当前任务/Workflow Stage/状态)
 * - activity [] → recentEvents [] (诚实空态)
 * - timeline + activity 合并 → 按时间倒序, 上限 10 条
 * - workflowStatus ← workflow 实例阶段链 (无实例项目不编造)
 * - blockedTasks ← backlog blocked Task (无 → [])
 * - qualitySummary ← cost/approvals/experience (无 → undefined → UI Unavailable)
 * - 缺失降级: dashboard null → 全空/Unavailable, 不崩溃
 */

import { describe, expect, it } from 'vitest';
import { toDashboardViewModel } from '../api/domain';
import {
  sampleBacklogP806,
  sampleDashboardReal,
  sampleFailedTimeline,
  sampleFailedWorkflow,
} from './fixtures';

describe('toDashboardViewModel — 真实 dashboard 结构映射 (S10-015 Task 006)', () => {
  it('projects: dashboard.projects → WorkspaceProject (复用 toWorkspaceProject)', () => {
    const vm = toDashboardViewModel(sampleDashboardReal());
    expect(vm.projects).toHaveLength(2);
    const [markpad, p806] = vm.projects;
    expect(markpad.id).toBe('markpad');
    expect(markpad.name).toBe('markpad');
    expect(markpad.lifecycleStage).toBe('development'); // status=active → development
    expect(markpad.riskCount).toBe(0);
    expect(p806.id).toBe('P-806fe6e8');
    expect(p806.name).toBe('ScorePocket');
    expect(p806.lifecycleStage).toBe('discovery'); // status=idea → discovery
    expect(p806.riskCount).toBe(1); // stage_counts.failed=1
  });

  it('agents 全部 AVAILABLE → runningAgents [] (诚实: 无执行中)', () => {
    const vm = toDashboardViewModel(sampleDashboardReal());
    expect(vm.runningAgents).toEqual([]);
  });

  it('agents RUNNING/EXECUTING → runningAgents (agentName/currentTask/workflowStage/status)', () => {
    const dash = sampleDashboardReal({
      agents: [
        {
          id: 'backend-1',
          name: 'backend-1',
          role: 'backend-dev',
          status: 'RUNNING',
          skills: ['python'],
          current_task: '实现登录 API',
        },
        {
          id: 'tester-1',
          name: 'tester-1',
          role: 'tester',
          status: 'EXECUTING',
          skills: ['pytest'],
          current_task: '运行测试',
        },
        {
          id: 'flutter-dev',
          name: 'flutter-dev',
          role: 'frontend-dev',
          status: 'AVAILABLE',
          skills: ['flutter'],
          current_task: null,
        },
      ],
    });
    // workflow 实例: testing 阶段 running (role=tester) → tester-1 workflowStage='测试'
    const wf = sampleFailedWorkflow();
    wf.stages[1] = { ...wf.stages[1], status: 'running' };
    const vm = toDashboardViewModel(dash, { workflows: { 'P-806fe6e8': wf } });

    expect(vm.runningAgents).toHaveLength(2);
    const [backend, tester] = vm.runningAgents;
    expect(backend.agentName).toBe('backend-1');
    expect(backend.currentTask).toBe('实现登录 API');
    expect(backend.status).toBe('running');
    // backend-dev 无匹配运行中阶段 → null (诚实, 不编造)
    expect(backend.workflowStage).toBeNull();
    expect(tester.agentName).toBe('tester-1');
    expect(tester.currentTask).toBe('运行测试');
    expect(tester.workflowStage).toBe('测试'); // STAGE_NAME_LABELS testing → 测试
    expect(tester.status).toBe('running');
  });

  it('activity 空 → recentEvents [] (诚实空态)', () => {
    const vm = toDashboardViewModel(sampleDashboardReal());
    expect(vm.recentEvents).toEqual([]);
  });

  it('recentEvents: timeline + activity 合并, 按时间倒序 (最新在前)', () => {
    const dash = sampleDashboardReal({
      activity: [
        {
          seq: 900,
          type: 'stage',
          timestamp: '2026-08-12T04:00:00Z',
          source: 'engine',
          project_id: 'P-806fe6e8',
          task_id: null,
          action: 'completed',
          result: 'ok',
        },
      ],
    });
    const vm = toDashboardViewModel(dash, {
      timelines: { 'P-806fe6e8': sampleFailedTimeline() },
    });
    expect(vm.recentEvents.length).toBeGreaterThan(0);
    // activity 04:00 晚于 timeline 最后一条 03:45 → 第一
    expect(vm.recentEvents[0].time).toBe('2026-08-12T04:00:00Z');
    // timeline 事件带项目名 (全局流可溯源)
    expect(vm.recentEvents.some((e) => e.projectName === 'ScorePocket')).toBe(true);
  });

  it('recentEvents 上限 10 条 (最近 N 条)', () => {
    const many = Array.from({ length: 25 }, (_, i) => ({
      ...sampleFailedTimeline()[0],
      id: `evt-${i}`,
      seq: i,
      created_at: `2026-08-12T03:${String(i).padStart(2, '0')}:00Z`,
    }));
    const vm = toDashboardViewModel(sampleDashboardReal(), {
      timelines: { 'P-806fe6e8': many },
    });
    expect(vm.recentEvents).toHaveLength(10);
  });

  it('workflowStatus: 从 workflow 实例聚合阶段链 (P-806fe6e8 failed)', () => {
    const vm = toDashboardViewModel(sampleDashboardReal(), {
      workflows: { 'P-806fe6e8': sampleFailedWorkflow() },
    });
    expect(vm.workflowStatus).toHaveLength(1);
    const item = vm.workflowStatus[0];
    expect(item.projectId).toBe('P-806fe6e8');
    expect(item.projectName).toBe('ScorePocket');
    expect(item.status).toBe('failed');
    expect(item.currentStage).toBe('development'); // project.current_stage 真实值
    expect(item.stages).toHaveLength(3);
    expect(item.stages[0].name).toBe('开发'); // STAGE_NAME_LABELS development → 开发
    expect(item.stages[0].status).toBe('failed');
    expect(item.stages[0].agentName).toBe('开发工程师'); // ROLE_LABELS developer
    expect(item.stages[1].name).toBe('测试');
    expect(item.stages[1].status).toBe('pending');
  });

  it('workflowStatus: 无 workflow 实例的项目 (markpad) 不编造阶段链', () => {
    const vm = toDashboardViewModel(sampleDashboardReal());
    expect(vm.workflowStatus).toEqual([]);
  });

  it('blockedTasks: backlog 无 blocked → []; blocked Task → 任务名/原因/负责人/下一步', () => {
    const vm = toDashboardViewModel(sampleDashboardReal(), {
      backlogs: { 'P-806fe6e8': sampleBacklogP806() },
    });
    expect(vm.blockedTasks).toEqual([]); // 3 todo Task → 无阻塞

    const backlog = sampleBacklogP806({
      tasks: [
        {
          id: 'TASK-b1',
          title: '实现登录 API',
          description: 'POST /api/login JWT',
          priority: 'P1',
          status: 'blocked',
          assignee: 'developer',
          dependency: ['TASK-a1'],
          created_at: null,
          updated_at: null,
          history: [],
        },
        {
          id: 'TASK-a1',
          title: '实现注册 API',
          description: 'POST /api/register',
          priority: 'P1',
          status: 'completed',
          assignee: 'developer',
          dependency: [],
          created_at: null,
          updated_at: null,
          history: [],
        },
      ],
    });
    const vm2 = toDashboardViewModel(sampleDashboardReal(), {
      backlogs: { 'P-806fe6e8': backlog },
    });
    expect(vm2.blockedTasks).toHaveLength(1);
    const bt = vm2.blockedTasks[0];
    expect(bt.taskName).toBe('实现登录 API');
    expect(bt.reason).toBe('等待: 实现注册 API'); // dependency id → 真实任务标题
    expect(bt.ownerAgent).toBe('开发工程师'); // assignee developer → ROLE_LABELS
    expect(bt.nextAction).toBe('解除阻塞后继续执行');
  });

  it('qualitySummary: cost/approvals/experience 真实映射', () => {
    const vm = toDashboardViewModel(sampleDashboardReal());
    expect(vm.qualitySummary.tests).toBe('执行 8 次 · 成功率 13%'); // cost.calls=8, 0.125
    expect(vm.qualitySummary.qualityGate).toContain('PRD'); // approvals[0].gate=prd
    expect(vm.qualitySummary.buildStatus).toBe('经验 2 条 · 成功率 50%'); // experience.total=2
  });

  it('缺失降级: dashboard null → 全空/Unavailable, 不崩溃', () => {
    const vm = toDashboardViewModel(null);
    expect(vm.projects).toEqual([]);
    expect(vm.runningAgents).toEqual([]);
    expect(vm.workflowStatus).toEqual([]);
    expect(vm.blockedTasks).toEqual([]);
    expect(vm.recentEvents).toEqual([]);
    expect(vm.qualitySummary.tests).toBeUndefined();
    expect(vm.qualitySummary.qualityGate).toBeUndefined();
    expect(vm.qualitySummary.buildStatus).toBeUndefined();
  });

  it('缺失降级: cost/approvals/experience 无数据 → qualitySummary undefined (UI Unavailable)', () => {
    const dash = sampleDashboardReal({
      cost: {
        total_cost: 0,
        calls: 0,
        success_rate: 0,
        avg_cost: 0,
        total_tokens: 0,
        by_provider: {},
      },
      approvals: [],
      experience: { total: 0, by_domain: {}, success_rate: 0, avg_score: 0, avg_confidence: 0 },
    });
    const vm = toDashboardViewModel(dash);
    expect(vm.qualitySummary.tests).toBeUndefined();
    expect(vm.qualitySummary.qualityGate).toBeUndefined();
    expect(vm.qualitySummary.buildStatus).toBeUndefined();
  });
});
