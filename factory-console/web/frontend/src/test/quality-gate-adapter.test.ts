/**
 * src/test/quality-gate-adapter.test.ts — Quality Gate Adapter (S10-015 Task 007)。
 *
 * toQualityGateViewModel: 组合 approvals (GET /api/approvals) + workflow 实例
 * (GET /api/projects/{id}/workflow) + timeline (GET /api/projects/{id}/timeline)
 * 真实数据 → QualityGateViewModel (UI 不直接依赖 API DTO — Adapter Layer)。
 *
 * 验证 (用户 Task 007 约束 — 禁止 fake passed checks / fake approval / fake quality score):
 * - 真实 APR-001 结构映射: currentGate (PRD/pending/v7/confidence 0/risk medium)
 * - approval pending → decision WAITING_FOR_REVIEW; approved → APPROVED; rejected → FAILED
 * - 无 approval → currentGate null / decision UNKNOWN / approval null / checks unavailable
 * - 5 checks 从真实数据推导: PRD 存在←approval artifact_type; Architecture/Tests/Build←
 *   workflow 阶段 (无对应阶段 → unavailable 诚实态, 不编造 passed)
 * - history ← timeline org.approval./org.artifact. 事件 (倒序; 无 → [])
 * - 缺失降级: null 输入 → 不崩溃, 全降级
 */

import { describe, expect, it } from 'vitest';
import { toQualityGateViewModel } from '../api/domain';
import {
  sampleApproval,
  sampleApprovalReal,
  sampleFailedWorkflow,
  sampleQualityTimeline,
} from './fixtures';

describe('toQualityGateViewModel (Quality Gate Adapter — 组合真实数据)', () => {
  it('真实 APR-001 → currentGate PRD pending (artifact v7 / confidence 0 / risk medium)', () => {
    const vm = toQualityGateViewModel({
      approvals: [sampleApprovalReal()],
      workflow: sampleFailedWorkflow(),
      timeline: sampleQualityTimeline(),
    });
    expect(vm.currentGate).toEqual({
      name: 'PRD',
      status: 'pending',
      artifactType: 'prd',
      artifactVersion: 7,
      confidence: 0,
      risk: 'medium',
      requestedAt: '2026-08-06T10:40:50.820090Z',
    });
  });

  it('approval pending → decision WAITING_FOR_REVIEW (label 等待人工审核 + 真实 comment)', () => {
    const vm = toQualityGateViewModel({
      approvals: [sampleApprovalReal()],
      workflow: sampleFailedWorkflow(),
      timeline: sampleQualityTimeline(),
    });
    expect(vm.decision.status).toBe('WAITING_FOR_REVIEW');
    expect(vm.decision.label).toBe('等待人工审核');
    expect(vm.decision.reason).toBe('auto-requested after prd generation (mandatory gate)');
  });

  it('approval → approval 视图 (pending / by cli / comment / requestedAt)', () => {
    const vm = toQualityGateViewModel({
      approvals: [sampleApprovalReal()],
      workflow: sampleFailedWorkflow(),
      timeline: sampleQualityTimeline(),
    });
    expect(vm.approval).toEqual({
      status: 'pending',
      by: 'cli',
      comment: 'auto-requested after prd generation (mandatory gate)',
      requestedAt: '2026-08-06T10:40:50.820090Z',
    });
  });

  it('5 checks 真实推导: PRD pending / Architecture unavailable / Tests pending / Build pending / Human Approval pending', () => {
    const vm = toQualityGateViewModel({
      approvals: [sampleApprovalReal()],
      workflow: sampleFailedWorkflow(), // development failed → testing pending → release pending (无 architect)
      timeline: sampleQualityTimeline(),
    });
    expect(vm.checks.map((c) => [c.name, c.status])).toEqual([
      ['PRD Exists', 'pending'],
      ['Architecture Review', 'unavailable'], // 本 workflow 无 architect 阶段 → 诚实 unavailable
      ['Tests Passed', 'pending'], // testing 阶段 pending
      ['Build Available', 'pending'], // release 阶段 pending
      ['Human Approval', 'pending'], // APR-001 pending
    ]);
    // 无架构阶段记录 → Unavailable 明确 detail (不编造 passed)
    expect(vm.checks[1].detail).toBe('无架构阶段记录');
    // PRD 检查 detail 含真实产物版本
    expect(vm.checks[0].detail).toContain('v7');
  });

  it('approval approved → decision APPROVED + checks passed', () => {
    const vm = toQualityGateViewModel({
      approvals: [sampleApprovalReal({ status: 'approved' })],
      workflow: sampleFailedWorkflow(),
      timeline: sampleQualityTimeline(),
    });
    expect(vm.decision.status).toBe('APPROVED');
    expect(vm.decision.label).toBe('已通过');
    expect(vm.currentGate?.status).toBe('passed');
    expect(vm.checks.find((c) => c.name === 'PRD Exists')?.status).toBe('passed');
    expect(vm.checks.find((c) => c.name === 'Human Approval')?.status).toBe('passed');
    expect(vm.approval?.status).toBe('approved');
  });

  it('approval rejected → decision FAILED + checks failed', () => {
    const vm = toQualityGateViewModel({
      approvals: [sampleApprovalReal({ status: 'rejected', comment: 'PRD 需求不清' })],
      workflow: sampleFailedWorkflow(),
      timeline: sampleQualityTimeline(),
    });
    expect(vm.decision.status).toBe('FAILED');
    expect(vm.decision.label).toBe('未通过');
    expect(vm.decision.reason).toBe('PRD 需求不清');
    expect(vm.currentGate?.status).toBe('failed');
    expect(vm.checks.find((c) => c.name === 'Human Approval')?.status).toBe('failed');
    expect(vm.approval?.status).toBe('rejected');
  });

  it('无 approval → currentGate null / decision UNKNOWN / approval null / 检查 unavailable 或阶段真实态', () => {
    const vm = toQualityGateViewModel({
      approvals: [],
      workflow: sampleFailedWorkflow(),
      timeline: sampleQualityTimeline(),
    });
    expect(vm.currentGate).toBeNull();
    expect(vm.decision).toEqual({ status: 'UNKNOWN', label: '无法评估' });
    expect(vm.approval).toBeNull();
    // 审批类检查 (PRD/Human Approval) 无数据 → unavailable (诚实, 不编造 passed)
    expect(vm.checks.find((c) => c.name === 'PRD Exists')?.status).toBe('unavailable');
    expect(vm.checks.find((c) => c.name === 'Human Approval')?.status).toBe('unavailable');
    // 阶段类检查仍从真实 workflow 阶段推导 (testing/release 阶段 pending → pending)
    expect(vm.checks.find((c) => c.name === 'Tests Passed')?.status).toBe('pending');
    expect(vm.checks.find((c) => c.name === 'Build Available')?.status).toBe('pending');
  });

  it('workflow 阶段真实状态 → 阶段检查 (architect completed → passed; testing failed → failed)', () => {
    const wf = sampleFailedWorkflow();
    const completedWf = sampleFailedWorkflow({
      stages: [
        wf.stages[0], // development failed
        {
          id: 'STG-ARCH',
          workflow_id: 'wf-q',
          role_id: 'architect',
          name: 'design',
          order: 1,
          status: 'completed',
          depends_on: [],
          input_artifacts: [],
          output_artifacts: [],
          approval_required: false,
          artifact: null,
          pending_approval: null,
        },
        {
          id: 'STG-TEST',
          workflow_id: 'wf-q',
          role_id: 'tester',
          name: 'testing',
          order: 2,
          status: 'failed',
          depends_on: [],
          input_artifacts: [],
          output_artifacts: [],
          approval_required: false,
          artifact: null,
          pending_approval: null,
        },
        {
          id: 'STG-REL',
          workflow_id: 'wf-q',
          role_id: 'devops',
          name: 'release',
          order: 3,
          status: 'pending',
          depends_on: [],
          input_artifacts: [],
          output_artifacts: [],
          approval_required: false,
          artifact: null,
          pending_approval: null,
        },
      ],
    });
    const vm = toQualityGateViewModel({
      approvals: [sampleApprovalReal()],
      workflow: completedWf,
      timeline: sampleQualityTimeline(),
    });
    expect(vm.checks.find((c) => c.name === 'Architecture Review')?.status).toBe('passed');
    expect(vm.checks.find((c) => c.name === 'Architecture Review')?.detail).toBe('架构阶段已完成');
    expect(vm.checks.find((c) => c.name === 'Tests Passed')?.status).toBe('failed');
    expect(vm.checks.find((c) => c.name === 'Build Available')?.status).toBe('pending');
  });

  it('history ← timeline org.approval./org.artifact. 事件 (倒序; actor/action/result 人话)', () => {
    const vm = toQualityGateViewModel({
      approvals: [sampleApprovalReal()],
      workflow: sampleFailedWorkflow(),
      timeline: sampleQualityTimeline(),
    });
    expect(vm.history).toHaveLength(4);
    // 倒序: 最新 (10:41:00 审批通过) 在前
    expect(vm.history[0].action).toBe('审批通过');
    expect(vm.history[0].result).toBe('已通过'); // status approved → 人话
    expect(vm.history[3].action).toBe('产物生成');
    expect(vm.history[3].result).toBe('通过'); // status OK → 人话
  });

  it('history: 无 org.approval./org.artifact. 事件 → [] (诚实空态)', () => {
    const vm = toQualityGateViewModel({
      approvals: [sampleApprovalReal()],
      workflow: sampleFailedWorkflow(),
      timeline: [], // 真实环境 timeline 也可能只有 org.workflow.* 事件
    });
    expect(vm.history).toEqual([]);
  });

  it('缺失降级: null 输入 → 不崩溃 (currentGate null / UNKNOWN / 5 检查全 unavailable / [])', () => {
    const vm = toQualityGateViewModel(null);
    expect(vm.currentGate).toBeNull();
    expect(vm.decision.status).toBe('UNKNOWN');
    expect(vm.approval).toBeNull();
    // 5 项 Required Checks 是 UI 清单契约 — 无数据时每项诚实显示 Unavailable
    expect(vm.checks).toHaveLength(5);
    for (const check of vm.checks) {
      expect(check.status).toBe('unavailable');
    }
    expect(vm.history).toEqual([]);
  });

  it('多个 approval → 取最新 pending 为主 (requested_at 倒序)', () => {
    const vm = toQualityGateViewModel({
      approvals: [
        sampleApproval({ id: 'APR-002', gate: 'design', requested_at: '2026-08-07T00:00:00Z' }),
        sampleApprovalReal(), // APR-001 requested 2026-08-06
        sampleApproval({ id: 'APR-003', gate: 'release', requested_at: '2026-08-08T00:00:00Z' }),
      ],
      workflow: sampleFailedWorkflow(),
      timeline: sampleQualityTimeline(),
    });
    expect(vm.currentGate?.name).toBe('发布'); // APR-003 gate=release 最新 pending
    expect(vm.decision.status).toBe('WAITING_FOR_REVIEW');
  });

  it('PRD 检查识别 artifact_type=product (product 也视为 PRD)', () => {
    const vm = toQualityGateViewModel({
      approvals: [sampleApproval({ artifact_type: 'product', status: 'approved', artifact_version: 2 })],
      workflow: sampleFailedWorkflow(),
      timeline: sampleQualityTimeline(),
    });
    expect(vm.checks.find((c) => c.name === 'PRD Exists')?.status).toBe('passed');
    expect(vm.checks.find((c) => c.name === 'PRD Exists')?.detail).toContain('v2');
  });
});
