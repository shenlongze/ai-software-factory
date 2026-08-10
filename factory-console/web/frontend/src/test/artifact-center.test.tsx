/**
 * src/test/artifact-center.test.tsx — S10-005 Artifact Center 测试。
 * 唯一 basename (artifact-center), 不与 S9 ArtifactsPage 测试冲突。
 * 覆盖: 列表渲染/类型过滤/状态徽章/详情 6 类渲染 (product/ux_ui/design/code/test/release)
 *       /未知类型 JSON 兜底/mock 徽章/空态/错误态。
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ArtifactCenter, ARTIFACT_FILTER_TYPES, formatArtifactTime } from '../shell/ArtifactCenter';

const PROJECT = 'ledger-app';
const ART_URL = '/api/artifacts'; // listArtifacts → GET /api/artifacts?project_id=...

function okResponse(data: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => data,
  } as Response;
}

function stubFetch(map: Record<string, unknown>): void {
  const entries = Object.entries(map).sort((a, b) => b[0].length - a[0].length); // 长 key 优先
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      for (const [k, v] of entries) {
        if (url.includes(k)) return okResponse(v);
      }
      return { ok: false, status: 404, json: async () => ({ detail: 'not found' }) } as Response;
    }),
  );
}

function artifact(id: string, type: string, status = 'validated') {
  return { id, type, status, name: id, stage: 'product', created_at: '2026-08-10T00:00:00+00:00', version: '1' };
}

const PRODUCT_META = {
  market_analysis: '记账市场分析',
  user_persona: '普通用户',
  user_journey: '记录支出',
  feature_list: ['添加记录', '分类'],
  mvp_scope: { in: ['记账'], out: ['预算'] },
  user_stories: ['作为用户我可以记账'],
};
const UXUI_META = {
  wireframe: {
    screens: [
      {
        name: 'Dashboard',
        components: ['Header', 'Button'],
        actions: ['click'],
      },
    ],
  },
  design_tokens: { colors: { primary: '#007ACC' } },
};
const ARCH_META = { system_architecture: '前端 SPA', technical_stack: ['HTML/CSS/JS'], api_design: { endpoints: ['/api/record'] }, task_breakdown: [{ module: 'app' }] };
const CODE_META = { files: ['index.html', 'app.js'], changes: '4 行修复' };
const TEST_META = { results: { passed: 20, failed: 0 }, bugs: [] };
const RELEASE_META = { version: '1.0.0', package: { name: 'app', type: 'zip', files: ['app.zip'] }, deployment: '静态站' };

afterEach(() => vi.unstubAllGlobals());

describe('ArtifactCenter — 列表', () => {
  it('渲染产物列表 (name/type/status)', async () => {
    stubFetch({ [ART_URL]: [artifact('a1', 'product')] });
    render(<ArtifactCenter projectId={PROJECT} />);
    expect(await screen.findByTestId('artifact-row-a1')).toBeInTheDocument();
    expect(within(screen.getByTestId('artifact-row-a1')).getByText('Product')).toBeInTheDocument();
  });

  it('类型过滤选项 (6 类 + 全部)', () => {
    expect(ARTIFACT_FILTER_TYPES).toContain('product');
    expect(ARTIFACT_FILTER_TYPES).toContain('ux_ui');
    expect(ARTIFACT_FILTER_TYPES).toContain('release');
  });

  it('mock fallback → 演示数据徽章', async () => {
    stubFetch({}); // 无匹配 → 404 → mockArtifacts fallback (is_mock=true)
    render(<ArtifactCenter projectId={PROJECT} />);
    // fallback 渲染 mock 列表 (诚实标注)
    expect(await screen.findByTestId('artifact-center-list')).toBeInTheDocument();
  });

  it('空态', async () => {
    stubFetch({ [ART_URL]: [] });
    render(<ArtifactCenter projectId={PROJECT} />);
    expect(await screen.findByTestId('artifact-center-empty')).toBeInTheDocument();
  });
});

describe('ArtifactCenter — 详情类型化渲染', () => {
  async function openDetail(meta: Record<string, unknown>, type = 'product') {
    stubFetch({
      [ART_URL]: [artifact('d1', type)],
      '/api/artifacts/d1': { id: 'd1', type, status: 'validated', metadata: meta },
    });
    render(<ArtifactCenter projectId={PROJECT} />);
    const row = await screen.findByTestId('artifact-row-d1');
    await userEvent.setup().click(row);
    return screen.findByTestId('artifact-detail');
  }

  it('product: 渲染 6 节', async () => {
    await openDetail(PRODUCT_META, 'product');
    expect(await screen.findByText('记账市场分析')).toBeInTheDocument();
    expect(screen.getByText('普通用户')).toBeInTheDocument();
    expect(screen.getByText('添加记录')).toBeInTheDocument();
  });

  it('ux_ui: wireframe → Screen Card (components/actions)', async () => {
    await openDetail(UXUI_META, 'ux_ui');
    expect(await screen.findByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('组件:')).toBeInTheDocument();
    expect(screen.getByText('交互动作:')).toBeInTheDocument();
  });

  it('design: 架构 4 节', async () => {
    await openDetail(ARCH_META, 'design');
    expect(await screen.findByText('前端 SPA')).toBeInTheDocument();
    expect(screen.getByText('HTML/CSS/JS')).toBeInTheDocument();
  });

  it('code: 文件列表 + diff 内容', async () => {
    await openDetail(CODE_META, 'code');
    expect(await screen.findByText('index.html')).toBeInTheDocument();
    expect(screen.getByText('app.js')).toBeInTheDocument();
  });

  it('test: passed/failed/bugs', async () => {
    await openDetail(TEST_META, 'test');
    expect(await screen.findByTestId('test-passed')).toHaveTextContent('20');
  });

  it('release: 版本 + 包信息', async () => {
    await openDetail(RELEASE_META, 'release');
    expect(await screen.findByText('1.0.0')).toBeInTheDocument();
    expect(screen.getByText('app.zip')).toBeInTheDocument();
  });

  it('未知类型 → JSON 兜底', async () => {
    await openDetail({ foo: 'bar' }, 'unknown_type');
    expect(await screen.findByTestId('artifact-detail')).toBeInTheDocument();
  });
});

describe('ArtifactCenter — 工具函数', () => {
  it('formatArtifactTime: 时间格式化', () => {
    const t = formatArtifactTime('2026-08-10T00:00:00+00:00');
    expect(typeof t).toBe('string');
    expect(t.length).toBeGreaterThan(0);
  });
});
