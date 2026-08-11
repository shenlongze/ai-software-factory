/**
 * src/test/af-workflow-viewer.test.tsx — Workflow Viewer (S10-015 Task 004)。
 *
 * 验证 (S10-015-architecture-review §4 + 用户 Task 004 设计约束):
 * - Adapter (toWorkflowPipeline 真实实例结构): is_mock=false 真实实例映射 /
 *   is_mock=true 降级标记 / role_id→人话 Agent 名 / 5 状态映射 (含 waiting_review→review) /
 *   blocked 阶段 blockedReason (depends_on 前置阶段人话)
 * - AfWorkflowViewer: 流水线节点 (阶段卡: 名称 + Agent + AfStatusBadge + 顺序箭头 ↓) —
 *   当前阶段高亮 (running 呼吸) / 完成绿勾 / 等待灰 / 阻塞紫+原因
 * - 三层展示: ① 运行流程 (Instance) ② 设计流程 (Template, 折叠) ③ 历史 (Audit Timeline)
 * - isMock 警告徽标 (演示数据 — 非真实执行, 禁冒充); 空 stages → AfEmptyState
 */

import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { toRuntimeActivity, toWorkflowPipeline } from '../api/domain';
import { AfWorkflowViewer } from '../components/af/AfWorkflowViewer';
import type { WorkflowPipeline } from '../models/domain';
import {
  sampleWorkflowInstance,
  sampleWorkflowInstanceMock,
  sampleWorkflowTimeline,
} from './fixtures';

// ------------------------------------------------------------------ Adapter (真实实例结构)

describe('api/domain — toWorkflowPipeline 真实实例结构 (S10-015 Task 004)', () => {
  it('真实实例 (is_mock=false): templateName/status/startedAt + role_id→人话 Agent 名 + 状态映射', () => {
    const pipeline = toWorkflowPipeline(undefined, sampleWorkflowInstance());
    expect(pipeline.isMock).toBe(false);
    expect(pipeline.status).toBe('running'); // workflow status active → running
    expect(pipeline.templateName).toBe(
      'P-806fe6e8 设计链 (product→ux_ui→design) [R1786473507972]',
    );
    expect(pipeline.startedAt).toBe('2026-08-11T18:38:28.056279+00:00');
    expect(pipeline.completedAt).toBeUndefined();
    expect(pipeline.stages).toHaveLength(3);

    const [product, uxUi, design] = pipeline.stages;
    // ① product: completed (完成)
    expect(product.order).toBe(1);
    expect(product.name).toBe('产品设计');
    expect(product.roleId).toBe('product-manager');
    expect(product.agentName).toBe('产品经理');
    expect(product.status).toBe('completed');
    expect(product.statusLabel).toBe('已完成');
    expect(product.artifact).toBe('file:///docs/product.json');
    // ② ux_ui: running (执行中)
    expect(uxUi.name).toBe('UI/UX 设计');
    expect(uxUi.agentName).toBe('UI 设计师');
    expect(uxUi.status).toBe('running');
    // ③ design: blocked + 阻塞原因 (depends_on → 前置阶段人话)
    expect(design.name).toBe('架构设计');
    expect(design.agentName).toBe('架构师');
    expect(design.status).toBe('blocked');
    expect(design.blockedReason).toContain('前置阶段');
    expect(design.blockedReason).toContain('UI 设计师');
  });

  it('is_mock=true → isMock 降级标记 (不冒充真实执行)', () => {
    const pipeline = toWorkflowPipeline(undefined, sampleWorkflowInstanceMock());
    expect(pipeline.isMock).toBe(true);
    expect(pipeline.stages).toHaveLength(6);
  });

  it('5 状态映射: completed/running/pending/review(waiting_review→review)/blocked', () => {
    const mock = toWorkflowPipeline(undefined, sampleWorkflowInstanceMock());
    const byOrder = new Map(mock.stages.map((s) => [s.order, s]));
    expect(byOrder.get(1)?.status).toBe('completed'); // completed
    expect(byOrder.get(3)?.status).toBe('review'); // waiting_review → review
    expect(byOrder.get(3)?.statusLabel).toBe('待审核');
    expect(byOrder.get(4)?.status).toBe('pending'); // pending
    const real = toWorkflowPipeline(undefined, sampleWorkflowInstance());
    expect(real.stages[1].status).toBe('running'); // running
    expect(real.stages[2].status).toBe('blocked'); // blocked
  });

  it('role_id → 人话 Agent 名 (含 devops→发布工程师; 未知 role 原样)', () => {
    const mock = toWorkflowPipeline(undefined, sampleWorkflowInstanceMock());
    const byOrder = new Map(mock.stages.map((s) => [s.order, s]));
    expect(byOrder.get(1)?.agentName).toBe('产品经理');
    expect(byOrder.get(2)?.agentName).toBe('UI 设计师');
    expect(byOrder.get(3)?.agentName).toBe('架构师');
    expect(byOrder.get(4)?.agentName).toBe('开发工程师');
    expect(byOrder.get(5)?.agentName).toBe('测试工程师');
    expect(byOrder.get(6)?.agentName).toBe('发布工程师'); // devops 补齐
  });

  it('blocked 且无 depends_on → 通用阻塞原因 (不臆造前置名)', () => {
    const wf = sampleWorkflowInstance();
    wf.stages[2].depends_on = [];
    const pipeline = toWorkflowPipeline(undefined, wf);
    expect(pipeline.stages[2].blockedReason).toBe('依赖未就绪');
  });
});

// ------------------------------------------------------------------ AfWorkflowViewer

/** 真实实例 pipeline (Adapter 转换, 非手工)。 */
function realPipeline(): WorkflowPipeline {
  return toWorkflowPipeline(undefined, sampleWorkflowInstance());
}

/** 演示流 pipeline (is_mock=true)。 */
function mockPipeline(): WorkflowPipeline {
  return toWorkflowPipeline(undefined, sampleWorkflowInstanceMock());
}

describe('AfWorkflowViewer (Workflow Instance 可视化 — 5 问回答)', () => {
  it('流水线渲染: 阶段卡 (顺序/名称/Agent/状态徽标) + 顺序箭头', () => {
    render(<AfWorkflowViewer pipeline={realPipeline()} timeline={[]} />);
    expect(screen.getByTestId('af-workflow-viewer')).toBeInTheDocument();
    // ① 当前流程运行到哪里: 运行流程区块 + 3 阶段卡
    expect(screen.getByTestId('af-wf-instance')).toBeInTheDocument();
    const stage1 = screen.getByTestId('af-wf-stage-1');
    const stage2 = screen.getByTestId('af-wf-stage-2');
    const stage3 = screen.getByTestId('af-wf-stage-3');
    expect(within(stage1).getByText('产品设计')).toBeInTheDocument();
    expect(within(stage1).getByText('产品经理 Agent')).toBeInTheDocument();
    expect(within(stage1).getByText('已完成')).toBeInTheDocument();
    expect(within(stage2).getByText('UI/UX 设计')).toBeInTheDocument();
    expect(within(stage2).getByText('UI 设计师 Agent')).toBeInTheDocument();
    expect(within(stage2).getByText('执行中')).toBeInTheDocument();
    expect(within(stage3).getByText('架构设计')).toBeInTheDocument();
    expect(within(stage3).getByText('架构师 Agent')).toBeInTheDocument();
    expect(within(stage3).getByText('阻塞')).toBeInTheDocument();
    // 顺序箭头 ↓ (2 条: 1→2, 2→3)
    expect(screen.getAllByText('↓')).toHaveLength(2);
  });

  it('② 当前阶段高亮: running 阶段卡带 af-wf-stage--active (呼吸)', () => {
    render(<AfWorkflowViewer pipeline={realPipeline()} timeline={[]} />);
    const stage2 = screen.getByTestId('af-wf-stage-2');
    expect(stage2.querySelector('.af-wf-stage')).toHaveClass('af-wf-stage--active');
    expect(stage2.querySelector('.af-wf-stage')).toHaveClass('af-wf-stage--running');
    const stage1 = screen.getByTestId('af-wf-stage-1');
    expect(stage1.querySelector('.af-wf-stage')).not.toHaveClass('af-wf-stage--active');
  });

  it('③ 完成节点绿勾 / ④ 等待节点灰 / ⑤ 阻塞节点紫 + 原因', () => {
    render(<AfWorkflowViewer pipeline={realPipeline()} timeline={[]} />);
    // 完成节点: ✓ 完成
    const stage1 = screen.getByTestId('af-wf-stage-1');
    expect(within(stage1).getByTestId('af-wf-stage-done')).toHaveTextContent('✓ 完成');
    expect(stage1.querySelector('.af-wf-stage')).toHaveClass('af-wf-stage--completed');
    // 阻塞节点: 紫色 class + 原因 (为什么阻塞 → 前置阶段人话)
    const stage3 = screen.getByTestId('af-wf-stage-3');
    expect(stage3.querySelector('.af-wf-stage')).toHaveClass('af-wf-stage--blocked');
    expect(within(stage3).getByTestId('af-wf-stage-blocked')).toHaveTextContent(
      '阻塞: 等待前置阶段完成: UI 设计师',
    );
  });

  it('等待节点灰 (mock 流 pending 阶段)', () => {
    render(<AfWorkflowViewer pipeline={mockPipeline()} timeline={[]} />);
    const stage4 = screen.getByTestId('af-wf-stage-4');
    expect(stage4.querySelector('.af-wf-stage')).toHaveClass('af-wf-stage--pending');
    expect(within(stage4).getByText('开发工程师 Agent')).toBeInTheDocument();
    expect(within(stage4).getByText('待办')).toBeInTheDocument();
  });

  it('三层展示: ① 运行流程 (Instance) ② 设计流程 (Template) ③ 历史 (Audit Timeline)', () => {
    render(
      <AfWorkflowViewer
        pipeline={realPipeline()}
        timeline={toRuntimeActivity(sampleWorkflowTimeline(), 'ScorePocket')}
      />,
    );
    // ① Instance
    expect(screen.getByTestId('af-wf-instance')).toBeInTheDocument();
    // ② Template (折叠区): 模板名 + 阶段序列 (人话)
    const template = screen.getByTestId('af-wf-template');
    expect(template).toBeInTheDocument();
    expect(within(template).getByText(/Workflow Template/)).toBeInTheDocument();
    expect(
      within(template).getByText(
        'P-806fe6e8 设计链 (product→ux_ui→design) [R1786473507972]',
      ),
    ).toBeInTheDocument();
    expect(within(template).getByText('产品设计')).toBeInTheDocument();
    expect(within(template).getByText('UI/UX 设计')).toBeInTheDocument();
    expect(within(template).getByText('架构设计')).toBeInTheDocument();
    // ③ Timeline (历史: 真实事件渲染为 AfTimeline 条目)
    const timelineSection = screen.getByTestId('af-wf-timeline');
    expect(within(timelineSection).getByTestId('af-timeline')).toBeInTheDocument();
    expect(within(timelineSection).getAllByTestId('af-timeline-item')).toHaveLength(7);
    expect(within(timelineSection).getByText('工作流创建 P-806fe6e8 设计链 (product→ux_ui→design) [R1786473507972]')).toBeInTheDocument();
    expect(within(timelineSection).getByText('产物验证通过')).toBeInTheDocument();
  });

  it('isMock=true → 顶部警告徽标 "演示数据 — 非真实执行" (禁冒充)', () => {
    render(<AfWorkflowViewer pipeline={mockPipeline()} timeline={[]} />);
    const badge = screen.getByTestId('af-wf-mock-badge');
    expect(badge).toHaveTextContent('演示数据');
    expect(badge).toHaveTextContent('非真实执行');
  });

  it('isMock=false → 无警告徽标', () => {
    render(<AfWorkflowViewer pipeline={realPipeline()} timeline={[]} />);
    expect(screen.queryByTestId('af-wf-mock-badge')).not.toBeInTheDocument();
  });

  it('空 stages → AfEmptyState (禁空白)', () => {
    const empty: WorkflowPipeline = {
      templateId: '',
      templateName: '未启动',
      stages: [],
    };
    render(<AfWorkflowViewer pipeline={empty} timeline={[]} />);
    expect(screen.getByTestId('af-empty-state')).toBeInTheDocument();
    expect(screen.getByText('暂无流程运行')).toBeInTheDocument();
  });
});
