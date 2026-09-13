/**
 * src/test/af-project-docs.test.tsx — 项目文档管理 (v1.1.108)。
 *
 * 左树右看: 清单分组 + 内容预览 (markdown/JSON); 缺失/不支持 → 诚实提示。
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { AfProjectDocs } from '../pages/project/AfProjectDocs';

function jsonResponse(v: unknown): Response {
  return { ok: true, status: 200, json: async () => v } as Response;
}

function stubDocs(docs: unknown[], contents: Record<string, unknown>) {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === '/api/projects/p1/docs') {
      return jsonResponse({ items: docs, count: docs.length });
    }
    const m = url.match(/^\/api\/projects\/p1\/docs\/(.+)$/);
    if (m) {
      const key = decodeURIComponent(m[1]);
      return jsonResponse(contents[key] ?? { name: key, kind: 'missing', content: null, note: '未生成' });
    }
    return { ok: false, status: 404, json: async () => ({ detail: 'nf' }) } as Response;
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

const DOCS = [
  { name: 'PRD.md', label: '需求文档', kind: 'md', size: 120, mtime: 1, exists: true, extra: false, folder: '', source_dir: 'sys' },
  { name: 'engineering.json', label: '工程计划', kind: 'json', size: 80, mtime: 1, exists: true, extra: false, folder: '', source_dir: 'sys' },
  { name: 'docs/guide.md', label: 'docs/guide.md', kind: 'md', size: 50, mtime: 1, exists: true, extra: true, folder: 'docs', source_dir: 'docs' },
];

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AfProjectDocs (项目文档管理)', () => {
  it('左树: 核心资产 + 目录分组; 右看: markdown 渲染', async () => {
    stubDocs(DOCS, {
      'PRD.md': { name: 'PRD.md', label: '需求文档', kind: 'md', content: '# 需求\n\n- 功能A\n- 功能B' },
    });
    render(<AfProjectDocs projectId="p1" projectName="测试项目" />);
    expect(await screen.findByTestId('af-docs')).toBeInTheDocument();
    expect(screen.getByText('核心资产（2）')).toBeInTheDocument();
    expect(screen.getByText('文档目录（1）')).toBeInTheDocument();
    expect(screen.getByTestId('af-doc-folder-docs')).toBeInTheDocument();
    // 目录默认收起 → 点开可见条目
    await userEvent.click(screen.getByTestId('af-doc-folder-docs'));
    expect(screen.getByText('docs/guide.md')).toBeInTheDocument();
    // 默认选中第一个可读文档 → 渲染 markdown 标题
    expect(await screen.findByRole('heading', { name: '需求' })).toBeInTheDocument();
    expect(screen.getByText('功能A')).toBeInTheDocument();
  });

  it('有章法分组: 排除代码目录, 关键目录展开, 非关键目录默认折叠', async () => {
    const rich = [
      { name: 'PRD.md', label: '需求文档', kind: 'md', size: 1, mtime: 1, exists: true, extra: false, folder: '', source_dir: 'sys' },
      { name: 'README.md', label: 'README.md', kind: 'md', size: 1, mtime: 1, exists: true, extra: true, folder: '', source_dir: 'repo' },
      { name: 'docs/products/agent-product-spec.md', label: 'agent-product-spec.md', kind: 'md', size: 1, mtime: 1, exists: true, extra: true, folder: 'docs/products', source_dir: 'repo' },
      { name: 'docs/guide.md', label: 'docs/guide.md', kind: 'md', size: 1, mtime: 1, exists: true, extra: true, folder: 'docs', source_dir: 'repo' },
      { name: 'desktop/README.md', label: 'desktop/README.md', kind: 'md', size: 1, mtime: 1, exists: true, extra: true, folder: 'desktop', source_dir: 'repo' },
      { name: 'misc/note.md', label: 'misc/note.md', kind: 'md', size: 1, mtime: 1, exists: true, extra: true, folder: 'misc', source_dir: 'repo' },
    ];
    stubDocs(rich, { 'PRD.md': { name: 'PRD.md', label: '需求文档', kind: 'md', content: '# 需求' } });
    render(<AfProjectDocs projectId="p1" projectName="测试项目" />);
    await screen.findByTestId('af-docs');
    // 根文档组 (README)
    expect(screen.getByText('根文档（1）')).toBeInTheDocument();
    expect(screen.getAllByText('README.md').length).toBeGreaterThan(0);
    // 代码目录 desktop 被排除 (非项目文档)
    expect(screen.queryByText('desktop/README.md')).not.toBeInTheDocument();
    // 所有文档目录默认收起 (太长了): 目录可见, 条目不可见 (折叠初始化异步)
    expect(screen.getByTestId('af-doc-folder-docs-products')).toBeInTheDocument();
    expect(screen.getByTestId('af-doc-folder-misc')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText('agent-product-spec.md')).not.toBeInTheDocument());
    expect(screen.queryByText('misc/note.md')).not.toBeInTheDocument();
    // 点开 docs/products → 条目出现; 点开 misc → 条目出现
    await userEvent.click(screen.getByTestId('af-doc-folder-docs-products'));
    expect(screen.getByText('agent-product-spec.md')).toBeInTheDocument();
    await userEvent.click(screen.getByTestId('af-doc-folder-misc'));
    expect(screen.getByText('misc/note.md')).toBeInTheDocument();
  });

  it('切换文档 → 显示 JSON 格式化内容', async () => {
    stubDocs(DOCS, {
      'PRD.md': { name: 'PRD.md', label: '需求文档', kind: 'md', content: '# 需求' },
      'engineering.json': { name: 'engineering.json', label: '工程计划', kind: 'json', content: '{"stages":3}' },
    });
    render(<AfProjectDocs projectId="p1" projectName="测试项目" />);
    await screen.findByRole('heading', { name: '需求' });
    await userEvent.click(screen.getByText('工程计划'));
    expect(await screen.findByText(/"stages": 3/)).toBeInTheDocument();
  });

  it('未生成文档 → 诚实提示 (不伪造)', async () => {
    stubDocs(DOCS, {
      'PRD.md': { name: 'PRD.md', label: '需求文档', kind: 'md', content: '# 需求' },
    });
    render(<AfProjectDocs projectId="p1" projectName="测试项目" />);
    await screen.findByRole('heading', { name: '需求' });
    await userEvent.click(screen.getByText('工程计划'));
    expect(await screen.findByText('未生成')).toBeInTheDocument();
  });

  it('空清单 → 提示暂无文档', async () => {
    stubDocs([], {});
    render(<AfProjectDocs projectId="p1" projectName="测试项目" />);
    expect(await screen.findByText(/暂无文档/)).toBeInTheDocument();
  });
});

/* ================= C-3: 产出物 tab (manifest + 历史 + 版本链) ================= */

function stubArtifacts(state: {
  items: unknown[];
  meta: { version: number; updated_at: string | null };
  versions: Record<string, Record<number, { file: string; content: string }>>;
}) {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === '/api/projects/p1/artifacts/version') {
      return jsonResponse(state.meta);
    }
    if (url === '/api/projects/p1/artifacts') {
      return jsonResponse({ items: state.items, meta: state.meta, drift: [] });
    }
    const m = url.match(/^\/api\/projects\/p1\/artifacts\/([^/]+)\/versions\/(\d+)$/);
    if (m) {
      const type = decodeURIComponent(m[1]);
      const ver = Number(m[2]);
      const hit = state.versions[type]?.[ver];
      return jsonResponse(hit ?? { version: ver, file: '?', content: null });
    }
    return { ok: false, status: 404, json: async () => ({ detail: 'nf' }) } as Response;
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

const ARTIFACTS = {
  items: [
    { type: 'prd', label: '需求文档', kind: 'md', file: 'PRD.md', exists: true, legacy: false, schema_ok: true, version: 2, producer: 'change-control', trace_id: 't-2', created_at: '2026-08-26T00:00:00Z', updated_at: '2026-08-26T00:00:00Z', versions: [{ version: 1, file: 'history/PRD.v1.md', created_at: '...', producer: 'pipeline', trace_id: 't-1' }, { version: 2, file: 'PRD.md', created_at: '...', producer: 'change-control', trace_id: 't-2' }] },
    { type: 'product', label: '产品定义', kind: 'json', file: 'product.json', exists: false, legacy: false, schema_ok: true, version: null, producer: null, trace_id: null, created_at: null, updated_at: null, versions: [] },
  ],
  meta: { version: 2, updated_at: '2026-08-26T00:00:00Z' },
  versions: {
    prd: {
      1: { file: 'history/PRD.v1.md', content: '# 需求 v1' },
      2: { file: 'PRD.md', content: '# 需求 v2' },
    },
  },
};

describe('AfProjectDocs · 产出物 tab (C-3)', () => {
  it('manifest 列表 + 版本信号展示', async () => {
    stubArtifacts(ARTIFACTS);
    render(<AfProjectDocs projectId="p1" projectName="测试项目" />);
    await userEvent.click(screen.getByRole('tab', { name: /📦 产出物/ }));
    expect(await screen.findByText(/版本 v2/)).toBeInTheDocument();
    expect(screen.getByText('需求文档')).toBeInTheDocument();
    expect(screen.getAllByText(/v2/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('产品定义')).toBeInTheDocument();
  });

  it('选中产出物 → 当前版本内容 + 版本链可切换历史', async () => {
    stubArtifacts(ARTIFACTS);
    render(<AfProjectDocs projectId="p1" projectName="测试项目" />);
    await userEvent.click(screen.getByRole('tab', { name: /📦 产出物/ }));
    await userEvent.click(await screen.findByText('需求文档'));
    expect(await screen.findByRole('heading', { name: '需求 v2' })).toBeInTheDocument();
    // 版本链 → v1 → 历史内容
    await userEvent.click(screen.getByRole('button', { name: 'v1' }));
    expect(await screen.findByRole('heading', { name: '需求 v1' })).toBeInTheDocument();
    expect(screen.getByText('history/PRD.v1.md')).toBeInTheDocument();
  });

  it('未生成产出物 → 如实标注', async () => {
    stubArtifacts(ARTIFACTS);
    render(<AfProjectDocs projectId="p1" projectName="测试项目" />);
    await userEvent.click(screen.getByRole('tab', { name: /📦 产出物/ }));
    expect(await screen.findByText('未生成')).toBeInTheDocument();
  });
});
