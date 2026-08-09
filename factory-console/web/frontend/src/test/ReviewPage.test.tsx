/**
 * src/test/ReviewPage.test.tsx — 单产物评审页 (S9-003 UX/UI Review Interface)。
 *
 * - product 详情: PRD 6 节渲染 (PRODUCT_SECTIONS) + 内容 + pending 门表单
 * - approve/reject with comment → POST body {reviewer, comment} 并刷新详情
 * - ux_ui 详情: 7 节渲染 + wireframe ASCII <pre> 预览 + Screen 组件/动作卡片
 * - 终态门 → 无决定表单 (不可撤销); 无门 → 只读提示
 * - 空 metadata → 空态; API 错误 → ErrorState; 返回按钮
 */

import { useEffect } from 'react';
import type { ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AppStateProvider, useAppState } from '../state/AppState';
import type { Page } from '../state/AppState';
import { ReviewPage } from '../pages/ReviewPage';
import {
  sampleApprovalDecision,
  sampleApprovalGate,
  sampleArtifactDetail,
  sampleUXUIDetail,
  stubFetch,
} from './fixtures';

/** 渲染 ReviewPage 并预先导航到 review 页 (artifactId)。 */
function renderReview(artifactId = 'art-1') {
  function Harness({ children }: { children: ReactNode }) {
    const { navigate } = useAppState();
    useEffect(() => {
      navigate({ name: 'review', artifactId } satisfies Page);
    }, [navigate, artifactId]);
    return <>{children}</>;
  }
  return render(
    <AppStateProvider>
      <Harness>
        <ReviewPage />
      </Harness>
    </AppStateProvider>,
  );
}

describe('ReviewPage · Product (PRD 6 节)', () => {
  it('渲染 PRD 6 节 (市场分析/用户画像/用户旅程/功能列表/MVP 范围/用户故事) + 内容 + 门状态', async () => {
    stubFetch({ '/api/artifacts/art-1': sampleArtifactDetail() });
    renderReview();
    expect(await screen.findByRole('heading', { name: '评审 · Product' })).toBeInTheDocument();
    for (const label of ['市场分析', '用户画像', '用户旅程', '功能列表', 'MVP 范围', '用户故事']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText('目标市场: 个人记账用户; 竞争: 手工表格/同类 App')).toBeInTheDocument();
    expect(screen.getByText('25-40 岁上班族, 需要简单记账与月度报表')).toBeInTheDocument();
    expect(screen.getByText('支出记录')).toBeInTheDocument(); // feature_list <li>
    expect(screen.getByText(/快速记录支出/)).toBeInTheDocument(); // user_stories JSON
    // pending 门 + 决定表单
    expect(screen.getByText(/审批门 product — gate-1/)).toBeInTheDocument();
    expect(screen.getByLabelText('评审意见')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '← 返回产物' })).toBeInTheDocument();
  });

  it('输入意见 → Approve → POST /api/approvals/gate-1/approve body 带 comment 并刷新', async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch({
      '/api/artifacts/art-1': sampleArtifactDetail(),
      '/api/approvals/gate-1/approve': sampleApprovalDecision(),
    });
    renderReview();
    await screen.findByRole('heading', { name: '评审 · Product' });
    await user.type(screen.getByLabelText('评审意见'), 'MVP 只做支出记录');
    await user.click(screen.getByRole('button', { name: 'Approve' }));
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(
        (c) => (c[1] as RequestInit | undefined)?.method === 'POST',
      );
      expect(post).toBeDefined();
      expect(String(post![0])).toBe('/api/approvals/gate-1/approve');
      expect(JSON.parse(String((post![1] as RequestInit).body))).toEqual({
        reviewer: 'console',
        comment: 'MVP 只做支出记录',
      });
    });
    // 决定成功后刷新详情 (初始 1 次 + 刷新 ≥2 次)
    await waitFor(() => {
      const gets = fetchMock.mock.calls.filter((c) => String(c[0]) === '/api/artifacts/art-1');
      expect(gets.length).toBeGreaterThanOrEqual(2);
    });
    // 意见已持久化提示
    expect(await screen.findByText(/已批准 — 意见已持久化到审批门/)).toBeInTheDocument();
  });

  it('输入意见 → Reject → POST /api/approvals/gate-1/reject body 带 comment', async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch({
      '/api/artifacts/art-1': sampleArtifactDetail(),
      '/api/approvals/gate-1/reject': sampleApprovalDecision({ action: 'rejected' }),
    });
    renderReview();
    await screen.findByRole('heading', { name: '评审 · Product' });
    await user.type(screen.getByLabelText('评审意见'), 'MVP 范围过大: 移除月度报表');
    await user.click(screen.getByRole('button', { name: 'Reject' }));
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(
        (c) => (c[1] as RequestInit | undefined)?.method === 'POST',
      );
      expect(post).toBeDefined();
      expect(String(post![0])).toBe('/api/approvals/gate-1/reject');
      expect(JSON.parse(String((post![1] as RequestInit).body))).toEqual({
        reviewer: 'console',
        comment: 'MVP 范围过大: 移除月度报表',
      });
    });
    expect(await screen.findByText(/已驳回 — 意见为下轮重生成反馈输入/)).toBeInTheDocument();
  });

  it('空意见 Approve → body 不含 comment 键 (S9-002 兼容)', async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch({
      '/api/artifacts/art-1': sampleArtifactDetail(),
      '/api/approvals/gate-1/approve': sampleApprovalDecision(),
    });
    renderReview();
    await screen.findByRole('heading', { name: '评审 · Product' });
    await user.click(screen.getByRole('button', { name: 'Approve' }));
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(
        (c) => (c[1] as RequestInit | undefined)?.method === 'POST',
      );
      expect(JSON.parse(String((post![1] as RequestInit).body))).toEqual({ reviewer: 'console' });
    });
  });
});

describe('ReviewPage · UX/UI (7 节 + wireframe 预览)', () => {
  it('渲染 7 节 (信息架构/用户流程/线框图/屏幕规格/组件定义/设计令牌/原型说明) + wireframe ASCII 预览 + Screen 卡片', async () => {
    stubFetch({ '/api/artifacts/art-ux1': sampleUXUIDetail() });
    renderReview('art-ux1');
    expect(await screen.findByRole('heading', { name: '评审 · UX/UI' })).toBeInTheDocument();
    for (const label of ['信息架构', '用户流程', '线框图', '屏幕规格', '组件定义', '设计令牌', '原型说明']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    // wireframe ASCII 布局原样预览 (| 余额卡片 | 只出现在线框 pre, JSON 中带引号)
    expect(screen.getByText(/\| 余额卡片\s+\|/)).toBeInTheDocument();
    // Screen 卡片: 组件 tag + 交互动作
    expect(screen.getAllByText('BalanceCard').length).toBeGreaterThan(0);
    expect(screen.getAllByText('screen_record').length).toBeGreaterThan(0);
    expect(screen.getAllByText('下拉刷新').length).toBeGreaterThan(0);
    expect(screen.getByText('点击流水进入详情')).toBeInTheDocument();
    // pending 门 + 表单
    expect(screen.getByText(/审批门 ux-ui — gate-ux1/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument();
  });

  it('wireframe 节结构缺失 → 回退通用 JSON 渲染 (宽容失败安全)', async () => {
    stubFetch({
      '/api/artifacts/art-ux1': sampleUXUIDetail({
        metadata: {
          wireframe: 'not-a-structure',
          information_architecture: 'IA 说明',
        },
      }),
    });
    renderReview('art-ux1');
    await screen.findByRole('heading', { name: '评审 · UX/UI' });
    // 无 Screen 卡片; wireframe 原始字符串值直接展示 (宽容失败安全)
    expect(screen.queryByText('screen_home')).toBeNull();
    expect(screen.getByText('not-a-structure')).toBeInTheDocument();
  });
});

describe('ReviewPage · 门状态 / 空态 / 错误', () => {
  it('终态门 (approved + comment) → 无决定表单, 展示评审意见与不可撤销提示', async () => {
    stubFetch({
      '/api/artifacts/art-1': sampleArtifactDetail({
        review: sampleApprovalGate({
          id: 'gate-1',
          stage_id: 'product',
          status: 'approved',
          comment: '需求确认, 开始设计',
        }),
      }),
    });
    renderReview();
    await screen.findByRole('heading', { name: '评审 · Product' });
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull();
    expect(screen.queryByLabelText('评审意见')).toBeNull();
    expect(screen.getByText(/评审意见: 需求确认, 开始设计/)).toBeInTheDocument();
    expect(screen.getByText(/该门已决定, 不可撤销/)).toBeInTheDocument();
  });

  it('无绑定审批门 → 只读提示 (无表单)', async () => {
    stubFetch({ '/api/artifacts/art-1': sampleArtifactDetail({ review: null }) });
    renderReview();
    await screen.findByRole('heading', { name: '评审 · Product' });
    expect(screen.getByText(/该产物暂无绑定审批门/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
  });

  it('空 metadata → 空态 (PRD 无结构化数据)', async () => {
    stubFetch({ '/api/artifacts/art-1': sampleArtifactDetail({ metadata: {} }) });
    renderReview();
    expect(await screen.findByText('该产物无结构化 PRD metadata')).toBeInTheDocument();
  });

  it('API 错误 (404) → ErrorState', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) }) as Response),
    );
    renderReview();
    expect(await screen.findByTestId('error-state')).toHaveTextContent(/404/);
  });

  it('决定失败 (409 终态冲突) → 错误提示展示, 不崩溃', async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input);
        if (path === '/api/artifacts/art-1') {
          return { ok: true, status: 200, json: async () => sampleArtifactDetail() } as Response;
        }
        return {
          ok: false,
          status: 409,
          json: async () => ({ detail: 'approval already decided' }),
        } as Response;
      }),
    );
    renderReview();
    await screen.findByRole('heading', { name: '评审 · Product' });
    await user.click(screen.getByRole('button', { name: 'Reject' }));
    expect(await screen.findByTestId('error-state')).toHaveTextContent(/409/);
  });
});
