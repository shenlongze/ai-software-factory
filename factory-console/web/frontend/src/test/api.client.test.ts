/**
 * src/test/api.client.test.ts — 只读 API 客户端测试。
 *
 * - fetch 桩注入: 成功 JSON / 非 2xx → ApiError
 * - Permission Boundary: client 只暴露 GET 方法, 无 post/put/patch/delete
 * - 路径编码 (encodeURIComponent) 与查询参数形状
 */

import { describe, expect, it } from 'vitest';
import { api, ApiError } from '../api/client';
import { sampleApproval, sampleDashboard, sampleDecision, sampleExperience, sampleLifecycle, sampleProject, sampleProvider, sampleRecommendation, stubFetch } from './fixtures';

describe('api client — 只读契约', () => {
  it('暴露的接口全部是数据读取方法 (无写方法)', () => {
    const keys = Object.keys(api) as (keyof typeof api)[];
    expect(keys.sort()).toEqual([
      'approvals',
      'dashboard',
      'decision',
      'experience',
      'lifecycle',
      'projects',
      'providers',
      'recommendations',
    ]);
    // Permission Boundary: 前端不提供任何写方法
    const src = api.toString();
    expect(src).not.toMatch(/\b(post|put|patch|delete)\s*\(/i);
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
