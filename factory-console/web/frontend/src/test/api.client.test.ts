/**
 * src/test/api.client.test.ts — API 客户端测试 (S9-002 收窄写面)。
 *
 * - fetch 桩注入: 成功 JSON / 非 2xx → ApiError
 * - Permission Boundary: 全部查询 GET; 写面仅 approve/reject 两 POST (reviewer=console)
 * - S9-002: approvalGates / workflows / workflow / artifacts 查询形状 + 路径编码
 */

import { describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '../api/client';
import {
  sampleApproval,
  sampleApprovalDecision,
  sampleApprovalGate,
  sampleArtifact,
  sampleDashboard,
  sampleDecision,
  sampleExperience,
  sampleLifecycle,
  sampleProject,
  sampleProvider,
  sampleRecommendation,
  sampleWorkflow,
  sampleWorkflowDetail,
  stubFetch,
} from './fixtures';

describe('api client — 只读契约 + S9-002 审批写面 + S10-004 Runtime 写面', () => {
  it('暴露接口清单 (查询 + 审批决定 + Runtime 生命周期; 无 post/put/patch/delete 方法)', () => {
    const keys = Object.keys(api).sort();
    expect(keys).toEqual([
      'approvalGates',
      'approvals',
      'approveApproval',
      'artifact',
      'artifacts',
      'createRuntime',
      'dashboard',
      'decision',
      'experience',
      'lifecycle',
      // S10-002: Runtime 查询 (只读 GET; SSE 在 runtimeClient)
      'projectRuntimes',
      'projectTimeline',
      'projectWorkflow',
      'projects',
      'providers',
      'recommendations',
      'rejectApproval',
      'runtimeDetail',
      'screenshotRuntime',
      'startRuntime',
      'stopRuntime',
      'workflow',
      'workflowStages',
      'workflows',
    ]);
    // Permission Boundary: 写面仅 审批决定 + Runtime 生命周期 两类 POST
    // (无 put/patch/delete 方法)
    for (const verb of ['put', 'patch', 'delete']) {
      expect(keys.some((k) => k.toLowerCase().startsWith(verb))).toBe(false);
    }
    expect(
      keys.filter((k) =>
        ['approveApproval', 'rejectApproval', 'createRuntime', 'startRuntime', 'stopRuntime', 'screenshotRuntime'].includes(k),
      ),
    ).toEqual([
      'approveApproval',
      'createRuntime',
      'rejectApproval',
      'screenshotRuntime',
      'startRuntime',
      'stopRuntime',
    ]);
  });

  it('dashboard() 请求 /api/dashboard 并返回 JSON', async () => {
    const dashboard = sampleDashboard();
    stubFetch({ '/api/dashboard': dashboard });
    const got = await api.dashboard();
    expect(got.projects[0].id).toBe('demo');
  });

  it('projects() 请求 /api/projects', async () => {
    const fetchMock = stubFetch({ '/api/projects': [sampleProject()] });
    const got = await api.projects();
    expect(got[0].id).toBe('demo');
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/projects');
  });

  it('lifecycle() 对 projectId 做 URL 编码', async () => {
    const fetchMock = stubFetch({ '/api/projects/a%2Fb/lifecycle': sampleLifecycle() });
    const got = await api.lifecycle('a/b');
    expect(got.project_id).toBe('demo');
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/projects/a%2Fb/lifecycle');
  });

  it('approvals(pendingOnly) 带 pending_only 查询参数', async () => {
    const fetchMock = stubFetch({
      '/api/approvals?pending_only=true': [sampleApproval()],
      '/api/approvals': [sampleApproval({ status: 'approved' })],
    });
    await api.approvals(true);
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/approvals?pending_only=true');
    await api.approvals();
    expect(String(fetchMock.mock.calls[1][0])).toBe('/api/approvals');
  });

  it('approvalGates(pendingOnly) 请求 /api/approval-gates (status=pending 过滤)', async () => {
    const fetchMock = stubFetch({
      '/api/approval-gates?status=pending': [sampleApprovalGate()],
      '/api/approval-gates': [sampleApprovalGate({ status: 'approved' })],
    });
    await api.approvalGates(true);
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/approval-gates?status=pending');
    await api.approvalGates();
    expect(String(fetchMock.mock.calls[1][0])).toBe('/api/approval-gates');
  });

  it('workflows(projectId) / workflow(id) 查询形状与编码', async () => {
    const fetchMock = stubFetch({
      '/api/workflows?project_id=demo': [sampleWorkflow()],
      '/api/workflows': [sampleWorkflow()],
      '/api/workflows/wf%201': sampleWorkflowDetail(),
    });
    const list = await api.workflows('demo');
    expect(list[0].id).toBe('wf-1');
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/workflows?project_id=demo');
    await api.workflows();
    expect(String(fetchMock.mock.calls[1][0])).toBe('/api/workflows');
    const detail = await api.workflow('wf 1');
    expect(detail.stages[0].name).toBe('Design');
    expect(String(fetchMock.mock.calls[2][0])).toBe('/api/workflows/wf%201');
  });

  it('artifacts(filters) 拼 project/workflow/type 查询参数', async () => {
    const fetchMock = stubFetch({
      '/api/artifacts?project_id=demo&workflow_id=wf-1&type=design': [sampleArtifact()],
      '/api/artifacts': [sampleArtifact()],
    });
    await api.artifacts({ projectId: 'demo', workflowId: 'wf-1', type: 'design' });
    expect(String(fetchMock.mock.calls[0][0])).toBe(
      '/api/artifacts?project_id=demo&workflow_id=wf-1&type=design',
    );
    await api.artifacts();
    expect(String(fetchMock.mock.calls[1][0])).toBe('/api/artifacts');
  });

  it('approveApproval(id) → POST /api/approvals/{id}/approve (reviewer=console)', async () => {
    const fetchMock = stubFetch({
      '/api/approvals/gate-1/approve': sampleApprovalDecision({ action: 'approved' }),
    });
    const got = await api.approveApproval('gate-1');
    expect(got.action).toBe('approved');
    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe('/api/approvals/gate-1/approve');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ reviewer: 'console' });
  });

  it('rejectApproval(id) → POST /api/approvals/{id}/reject (reviewer=console)', async () => {
    const fetchMock = stubFetch({
      '/api/approvals/gate-1/reject': sampleApprovalDecision({ action: 'rejected' }),
    });
    const got = await api.rejectApproval('gate-1');
    expect(got.action).toBe('rejected');
    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe('/api/approvals/gate-1/reject');
    expect(init.method).toBe('POST');
  });

  it('decision() 请求详情并编码 id', async () => {
    const fetchMock = stubFetch({ '/api/decisions/dec%201': sampleDecision() });
    const got = await api.decision('dec 1');
    expect(got.recommendation).toBe('opt-a');
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/decisions/dec%201');
  });

  it('recommendations/experience 带 limit 参数', async () => {
    const fetchMock = stubFetch({
      '/api/recommendations?limit=20': [sampleRecommendation()],
      '/api/experience?limit=5': [sampleExperience()],
    });
    await api.recommendations(20);
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/recommendations?limit=20');
    await api.experience(5);
    expect(String(fetchMock.mock.calls[1][0])).toBe('/api/experience?limit=5');
  });

  it('providers() 请求 /api/providers', async () => {
    stubFetch({ '/api/providers': [sampleProvider()] });
    const got = await api.providers();
    expect(got[0].id).toBe('hermes');
  });

  it('非 2xx → ApiError (带 path 与 status)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }) as Response),
    );
    await expect(api.projects()).rejects.toMatchObject({
      name: 'ApiError',
      path: '/api/projects',
      status: 500,
    });
  });

  it('ApiError.message 含路径与状态码', () => {
    const err = new ApiError('/api/projects', 404);
    expect(err.message).toContain('/api/projects');
    expect(err.message).toContain('404');
    expect(err).toBeInstanceOf(Error);
  });
});
