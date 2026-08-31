/**
/**
 * src/test/api.client.test.ts — API 客户端测试 (S9-002 收窄写面 + S10-006.5 项目管理写面)。
 *
 * - fetch 桩注入: 成功 JSON / 非 2xx → ApiError
 * - Permission Boundary: 查询全 GET; 写面 = approve/reject POST (reviewer=console) +
 *   Runtime 生命周期 POST + 项目创建 POST + 项目管理 PATCH/DELETE
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
  it('暴露接口清单 (查询 + 审批决定 + Runtime 生命周期 + K6 Human Console; 无 post/put/patch/delete 方法)', () => {
    const keys = Object.keys(api).sort();
    // K6 Human Console 新增方法 (Conversation/Work/Tower)
    expect(keys).toContain('conversations');
    expect(keys).toContain('createConversation');
    expect(keys).toContain('sendConversationMessage');
    expect(keys).toContain('getConversation');
    expect(keys).toContain('conversationQuality');
    expect(keys).toContain('opsOverview');
    expect(keys).toContain('opsWhoWorking');
    expect(keys).toContain('opsDrill');
    expect(keys).toContain('opsSnapshot');
    expect(keys).toContain('osProjects');
    expect(keys).toContain('osCreateProject');
    expect(keys).toContain('osProjectStatus');
    expect(keys).toContain('osApproveTask');
    expect(keys).toContain('osDecideApproval');
    // 核心旧方法仍在
    expect(keys).toContain('dashboard');
    expect(keys).toContain('createProject');
    expect(keys).toContain('approvals');
    // 全部方法均为函数 (无裸字段)
    for (const k of keys) {
      expect(typeof api[k as keyof typeof api], k).toBe('function');
    }
    // Permission Boundary: 写面 = 审批决定 + Runtime 生命周期 + 项目创建 POST,
    // 项目管理 PATCH/DELETE (updateProject/deleteProject) + W-3 任务管理
    // (updateBacklogTask); 无裸 put/patch 方法名
    expect(keys.some((k) => k.toLowerCase().startsWith('put'))).toBe(false);
    expect(
      keys.filter((k) =>
        [
          'approveApproval',
          'rejectApproval',
          'createRuntime',
          'startRuntime',
          'stopRuntime',
          'screenshotRuntime',
          'createProject',
          'updateProject',
          'deleteProject',
          'updateBacklogTask',
          'createBacklogFeature',
          'updateBacklogFeature',
          'registryExecute',
        ].includes(k),
      ),
    ).toEqual([
      'approveApproval',
      'createBacklogFeature',
      'createProject',
      'createRuntime',
      'deleteProject',
      'registryExecute',
      'rejectApproval',
      'screenshotRuntime',
      'startRuntime',
      'stopRuntime',
      'updateBacklogFeature',
      'updateBacklogTask',
      'updateProject',
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

  it('reviewFeedback(artifactId?) 拼 artifact/gate 过滤查询参数 (S10-006)', async () => {
    const fetchMock = stubFetch({
      '/api/review-feedback?artifact_id=art-a&gate_id=gate-b': [
        { id: 'fb-1', gate_id: 'gate-b', artifact_id: 'art-a', reviewer: 'console', comment: '重做', round: 1, created_at: null },
      ],
      '/api/review-feedback?artifact_id=art-a': [],
      '/api/review-feedback': [],
    });
    const got = await api.reviewFeedback('art-a', 'gate-b');
    expect(got[0].round).toBe(1);
    expect(got[0].comment).toBe('重做');
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/review-feedback?artifact_id=art-a&gate_id=gate-b');
    await api.reviewFeedback('art-a');
    expect(String(fetchMock.mock.calls[1][0])).toBe('/api/review-feedback?artifact_id=art-a');
    await api.reviewFeedback();
    expect(String(fetchMock.mock.calls[2][0])).toBe('/api/review-feedback');
  });

  it('saveReviewFeedback → POST /api/review-feedback (reviewer 缺省 console)', async () => {
    const fetchMock = stubFetch({
      '/api/review-feedback': {
        id: 'fb-9',
        gate_id: 'gate-1',
        artifact_id: 'art-1',
        reviewer: 'console',
        comment: 'MVP 范围过大, 请重做',
        round: 1,
        created_at: null,
      },
    });
    const got = await api.saveReviewFeedback({
      artifact_id: 'art-1',
      gate_id: 'gate-1',
      comment: 'MVP 范围过大, 请重做',
    });
    expect(got.round).toBe(1);
    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe('/api/review-feedback');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({
      reviewer: 'console',
      artifact_id: 'art-1',
      gate_id: 'gate-1',
      comment: 'MVP 范围过大, 请重做',
    });
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

  it('updateProject → PATCH /api/projects/{id} (重命名 body + URL 编码, S10-006.5)', async () => {
    const fetchMock = stubFetch({
      '/api/projects/a%2Fb': { project_id: 'a/b', name: '记账本', idea: '记账', status: 'active' },
    });
    const got = await api.updateProject('a/b', { name: '记账本' });
    expect(got.name).toBe('记账本');
    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe('/api/projects/a%2Fb');
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(String(init.body))).toEqual({ name: '记账本' });
  });

  it('updateProject 只发送提供的键 (仅 idea, S10-006.5)', async () => {
    const fetchMock = stubFetch({
      '/api/projects/demo': { project_id: 'demo', name: 'Demo', idea: '新想法', status: 'idea' },
    });
    await api.updateProject('demo', { idea: '新想法' });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ idea: '新想法' });
  });

  it('deleteProject → DELETE /api/projects/{id} (成功 {deleted: true}, S10-006.5)', async () => {
    const fetchMock = stubFetch({
      '/api/projects/demo': { deleted: true, project_id: 'demo' },
    });
    const got = await api.deleteProject('demo');
    expect(got.deleted).toBe(true);
    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe('/api/projects/demo');
    expect(init.method).toBe('DELETE');
  });

  it('deleteProject 409 → ApiError status 409 (运行中保护, S10-006.5)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 409, json: async () => ({ detail: 'running' }) }) as Response),
    );
    await expect(api.deleteProject('demo')).rejects.toMatchObject({
      name: 'ApiError',
      path: '/api/projects/demo',
      status: 409,
    });
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
