/**
 * src/test/api-live.test.ts — api client 与真实后端 (FastAPI 8011) 联调验证 (S10-014 Task 002)。
 *
 * - 真实联调: fetch 桩仅做"相对路径 → 8011 绝对 URL"前缀转发 (不伪造任何数据),
 *   验证 api.projects()/api.dashboard() 封装 + 真实后端数据全链路 (等价 vite /api 代理)。
 * - 环境兜底: 后端不可达 (如 CI 无后端) → 联调用例自动跳过, 契约用例 (请求路径 +
 *   真实响应结构快照) 恒绿 — 本地联调由真实用例覆盖。
 */

import { describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';

const BACKEND_BASE = 'http://127.0.0.1:8011';

/** stub 前的真实 fetch (转发代理必须绕过被替换的全局 fetch, 避免递归)。 */
const realFetch = globalThis.fetch;

/** 相对路径 → 8011 绝对 URL 前缀转发 (等价 vite proxy: /api → 127.0.0.1:8011)。 */
function forwardFetchToBackend(): ReturnType<typeof vi.fn> {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    const url = path.startsWith('http') ? path : `${BACKEND_BASE}${path}`;
    return realFetch(url, { headers: { Accept: 'application/json' } });
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

describe('api client ↔ 真实后端 8011 联调 (S10-014 Task 002)', () => {
  it('api.projects() 全链路: /api/projects → 真实项目数组 (markpad/ledger-app)', async () => {
    // 后端不可达 (CI 无后端) → 跳过; 契约兜底由下方用例覆盖
    let up = false;
    try {
      const probe = await fetch(`${BACKEND_BASE}/api/projects`);
      up = probe.ok;
    } catch {
      up = false;
    }
    if (!up) return;

    const fetchMock = forwardFetchToBackend();
    const projects = await api.projects();
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/projects');
    expect(Array.isArray(projects)).toBe(true);
    expect(projects.length).toBeGreaterThan(0);
    const names = projects.map((p) => p.name);
    expect(names).toContain('markpad');
    expect(names.some((n) => n === 'ledger-app')).toBe(true);

    // 真实字段契约 (S10-014 §2.5/§6 消费字段 — 键存在, 值可 null/空)
    const first = projects[0];
    expect(first).toHaveProperty('id');
    expect(first).toHaveProperty('name');
    expect(first).toHaveProperty('status');
    expect(first).toHaveProperty('lifecycle_stage');
    expect(first).toHaveProperty('workflow_status');
    expect(first).toHaveProperty('current_stage');
    expect(first).toHaveProperty('progress');
    expect(first).toHaveProperty('stage_counts');
    // 真实运行痕迹: 至少一个项目有 workflow_id 或非空 stage_counts
    expect(
      projects.some(
        (p) => p.workflow_id != null || (p.stage_counts != null && Object.keys(p.stage_counts).length > 0),
      ),
    ).toBe(true);
  });

  it('api.dashboard() 全链路: /api/dashboard → {projects: [...]} 真实数组', async () => {
    let up = false;
    try {
      const probe = await fetch(`${BACKEND_BASE}/api/projects`);
      up = probe.ok;
    } catch {
      up = false;
    }
    if (!up) return;

    forwardFetchToBackend();
    const dash = await api.dashboard();
    expect(Array.isArray(dash.projects)).toBe(true);
    expect(dash.projects.length).toBeGreaterThan(0);
    expect(dash.projects[0]).toHaveProperty('id');
  });

  it('请求路径契约 (后端不可达环境兜底): api.projects() 请求 /api/projects + 真实响应结构', async () => {
    // 结构快照 = 真实后端 8011 响应字段子集 (markpad 项目)
    const realShape = [
      {
        id: 'markpad',
        name: 'markpad',
        status: 'active',
        lifecycle_stage: null,
        workflow_status: null,
        current_stage: null,
        progress: 0,
        stage_counts: {},
      },
    ];
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) => ({
      ok: true,
      status: 200,
      json: async () => realShape,
    }));
    vi.stubGlobal('fetch', fetchMock);
    const got = await api.projects();
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/projects');
    expect(got[0].id).toBe('markpad');
    expect(got[0]).toHaveProperty('workflow_status');
    expect(got[0]).toHaveProperty('stage_counts');
  });
});
