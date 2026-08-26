/**
 * src/test/af-project-docs.test.tsx — 项目文档管理 (v1.1.108)。
 *
 * 左树右看: 清单分组 + 内容预览 (markdown/JSON); 缺失/不支持 → 诚实提示。
 */

import { render, screen } from '@testing-library/react';
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
    expect(screen.getByText('核心资产')).toBeInTheDocument();
    expect(screen.getByText('其他文件')).toBeInTheDocument();
    expect(screen.getByText('📁 docs')).toBeInTheDocument();
    // 默认选中第一个可读文档 → 渲染 markdown 标题
    expect(await screen.findByRole('heading', { name: '需求' })).toBeInTheDocument();
    expect(screen.getByText('功能A')).toBeInTheDocument();
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
