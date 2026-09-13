/**
 * src/test/af-quality-gate.test.tsx — AfQualityGate 组件测试 (S10-015 Task 007)。
 *
 * Quality Gate 5 模块 (用户指定, 全部真实数据驱动 — viewModel 经 toQualityGateViewModel
 * 真实 Adapter 转换, 无 mock 冒充):
 *   ① Current Quality Gate  — 当前 Gate 卡 (名称/状态/artifact/confidence/risk); 无 → Unavailable
 *   ② Required Checks      — 5 项检查 (PRD/架构/测试/构建/人工审批); 无数据 → Unavailable
 *   ③ Quality Decision     — WAITING_FOR_REVIEW/APPROVED/FAILED/UNKNOWN; 无数据 → Unavailable
 *   ④ Human Approval       — Waiting for approval / Approved by / Rejected; 无 → Not available
 *   ⑤ Decision History     — 复用 AfTimeline (历史决策); 无 → 空态 (暂无历史决策)
 */

import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { toQualityGateViewModel } from '../api/domain';
import { AfQualityGate } from '../components/af/AfQualityGate';
import {
  sampleApprovalReal,
  sampleFailedWorkflow,
  sampleQualityTimeline,
} from './fixtures';

/** 真实组合 → viewModel (与页面数据流一致: approvals + workflow + timeline)。 */
function realViewModel() {
  return toQualityGateViewModel({
    approvals: [sampleApprovalReal()], // 真实 APR-001 prd gate pending
    workflow: sampleFailedWorkflow(), // development failed → testing/release pending (无 architect)
    timeline: sampleQualityTimeline(), // org.artifact.* + org.approval.* 4 条
  });
}

describe('AfQualityGate (Quality Gate — 5 模块)', () => {
  it('5 模块全部渲染 (标题 + 根节点)', () => {
    render(<AfQualityGate viewModel={realViewModel()} />);
    expect(screen.getByTestId('af-quality-gate')).toBeInTheDocument();
    // 模块标题 (Human Approval 同时是检查名 — 用 testid 限定作用域)
    expect(
      within(screen.getByTestId('af-quality-current-gate')).getByText('Current Quality Gate'),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('af-quality-checks')).getByText('Required Checks'),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('af-quality-decision')).getByText('Quality Decision'),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('af-quality-approval')).getByText('Human Approval'),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('af-quality-history')).getByText('Decision History'),
    ).toBeInTheDocument();
  });

  it('① Current Quality Gate 卡: 真实 APR-001 (PRD + 待审核 + artifact/版本/置信度/风险)', () => {
    render(<AfQualityGate viewModel={realViewModel()} />);
    const module = screen.getByTestId('af-quality-current-gate');
    expect(within(module).getByText('PRD')).toBeInTheDocument();
    expect(within(module).getByText('待审核')).toBeInTheDocument(); // status pending 徽标
    expect(within(module).getByText('prd')).toBeInTheDocument(); // artifact type
    expect(within(module).getByText('7')).toBeInTheDocument(); // artifact version
    expect(within(module).getByText('0')).toBeInTheDocument(); // confidence 0 (真实值, 非伪造)
    expect(within(module).getByText('medium')).toBeInTheDocument(); // risk
  });

  it('② Required Checks: 5 项真实状态 (PRD pending / Architecture Unavailable / Tests pending / Build pending / Approval pending)', () => {
    render(<AfQualityGate viewModel={realViewModel()} />);
    const module = screen.getByTestId('af-quality-checks');
    const checks = within(module).getAllByTestId('af-quality-check');
    expect(checks).toHaveLength(5);
    // PRD Exists — APR-001 pending → 待审核
    expect(within(checks[0]).getByText('PRD Exists')).toBeInTheDocument();
    expect(within(checks[0]).getByText('待审核')).toBeInTheDocument();
    // Architecture Review — 本 workflow 无 architect 阶段 → Unavailable (诚实态)
    expect(within(checks[1]).getByText('Architecture Review')).toBeInTheDocument();
    expect(within(checks[1]).getByText('Unavailable')).toBeInTheDocument();
    expect(within(checks[1]).getByText('无架构阶段记录')).toBeInTheDocument();
    // Tests Passed / Build Available — testing/release 阶段 pending
    expect(within(checks[2]).getByText('Tests Passed')).toBeInTheDocument();
    expect(within(checks[3]).getByText('Build Available')).toBeInTheDocument();
    expect(within(checks[4]).getByText('Human Approval')).toBeInTheDocument();
  });

  it('③ Quality Decision: WAITING_FOR_REVIEW → 等待人工审核 + 真实 comment 依据', () => {
    render(<AfQualityGate viewModel={realViewModel()} />);
    const module = screen.getByTestId('af-quality-decision');
    expect(within(module).getByText('等待人工审核')).toBeInTheDocument();
    expect(
      within(module).getByText('auto-requested after prd generation (mandatory gate)'),
    ).toBeInTheDocument();
  });

  it('④ Human Approval: pending → Waiting for approval + by + 请求时间', () => {
    render(<AfQualityGate viewModel={realViewModel()} />);
    const module = screen.getByTestId('af-quality-approval');
    expect(within(module).getByText('Waiting for approval')).toBeInTheDocument();
    expect(within(module).getByText('by cli')).toBeInTheDocument();
    expect(
      within(module).getByText('auto-requested after prd generation (mandatory gate)'),
    ).toBeInTheDocument();
  });

  it('⑤ Decision History: 复用 AfTimeline (4 条 org.artifact./org.approval. 事件, 最新在前)', () => {
    render(<AfQualityGate viewModel={realViewModel()} />);
    const module = screen.getByTestId('af-quality-history');
    expect(within(module).getByTestId('af-timeline')).toBeInTheDocument();
    const items = within(module).getAllByTestId('af-timeline-item');
    expect(items).toHaveLength(4);
    expect(items[0]).toHaveTextContent('审批通过'); // 最新 (10:41:00) 在前
    expect(items[3]).toHaveTextContent('产物生成');
  });

  it('无数据 → 诚实 Unavailable/Not available (Current Gate Unavailable / Decision Unavailable / Approval Not available / 5 检查 Unavailable / History 空态)', () => {
    const vm = toQualityGateViewModel(null);
    render(<AfQualityGate viewModel={vm} />);
    // ① Current Gate → Unavailable
    expect(screen.getByTestId('af-quality-gate-unavailable')).toHaveTextContent('Unavailable');
    // ③ Decision → 无法评估 + Unavailable
    const decision = screen.getByTestId('af-quality-decision');
    expect(within(decision).getByText('无法评估')).toBeInTheDocument();
    expect(within(decision).getByText('Unavailable')).toBeInTheDocument();
    // ④ Human Approval → Not available
    expect(screen.getByTestId('af-quality-approval-unavailable')).toHaveTextContent('Not available');
    // ② 5 项检查全部 Unavailable
    const checks = within(screen.getByTestId('af-quality-checks')).getAllByTestId('af-quality-check');
    expect(checks).toHaveLength(5);
    for (const check of checks) {
      expect(within(check).getByText('Unavailable')).toBeInTheDocument();
    }
    // ⑤ History → 空态 (暂无历史决策, 不渲染 AfTimeline)
    const history = screen.getByTestId('af-quality-history');
    expect(within(history).getByText('暂无历史决策')).toBeInTheDocument();
    expect(within(history).queryByTestId('af-timeline')).not.toBeInTheDocument();
  });

  it('History 无质量事件 → 空态 (暂无历史决策)', () => {
    const vm = toQualityGateViewModel({
      approvals: [sampleApprovalReal()],
      workflow: sampleFailedWorkflow(),
      timeline: [], // 真实环境 timeline 可能只有 org.workflow.* 事件
    });
    render(<AfQualityGate viewModel={vm} />);
    const history = screen.getByTestId('af-quality-history');
    expect(within(history).getByText('暂无历史决策')).toBeInTheDocument();
  });

  it('approval approved → Current Gate 已通过 + Decision 已通过 + Human Approval Approved by', () => {
    const vm = toQualityGateViewModel({
      approvals: [sampleApprovalReal({ status: 'approved', by: 'human', comment: null })],
      workflow: sampleFailedWorkflow(),
      timeline: sampleQualityTimeline(),
    });
    render(<AfQualityGate viewModel={vm} />);
    expect(within(screen.getByTestId('af-quality-current-gate')).getByText('已通过')).toBeInTheDocument();
    expect(within(screen.getByTestId('af-quality-decision')).getByText('已通过')).toBeInTheDocument();
    expect(
      within(screen.getByTestId('af-quality-approval')).getByText('Approved by human'),
    ).toBeInTheDocument();
  });

  it('approval rejected → Human Approval 显示 Rejected 意见', () => {
    const vm = toQualityGateViewModel({
      approvals: [sampleApprovalReal({ status: 'rejected', comment: 'PRD 需求不清' })],
      workflow: sampleFailedWorkflow(),
      timeline: sampleQualityTimeline(),
    });
    render(<AfQualityGate viewModel={vm} />);
    const module = screen.getByTestId('af-quality-approval');
    expect(within(module).getByText(/Rejected/)).toBeInTheDocument();
    expect(within(module).getByText('PRD 需求不清')).toBeInTheDocument();
  });
});
