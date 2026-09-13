/**
 * src/test/markdown.test.tsx — 轻量 Markdown 渲染 (会话栏 AI 回复)。
 */

import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderMarkdown } from '../components/af/markdown';

describe('renderMarkdown', () => {
  it('标题/粗体/斜体/行内代码/列表 → 渲染为元素 (无原始符号)', () => {
    const { container } = render(
      <div>{renderMarkdown('# 标题\n\n**核心价值** 与 *斜体* 和 `code`\n\n- 项目A\n- 项目B')}</div>,
    );
    const html = container.innerHTML;
    expect(html).toContain('<h4>');
    expect(html).toContain('<strong>核心价值</strong>');
    expect(html).toContain('<em>斜体</em>');
    expect(html).toContain('<code');
    expect(html).toContain('<ul>');
    // 不残留原始 markdown 符号
    expect(html).not.toContain('**核心价值**');
    expect(html).not.toContain('# 标题');
  });

  it('代码块 → pre', () => {
    const { container } = render(
      <div>{renderMarkdown('```\nconst a = 1;\n```')}</div>,
    );
    expect(container.innerHTML).toContain('<pre');
    expect(container.innerHTML).toContain('const a = 1;');
  });
});

describe('renderMarkdown 表格/引用/链接 (v1.1.147, Founder: markdown 源码显示)', () => {
  it('GFM 表格 → table/thead/tbody, 无源码管道符残留', () => {
    const { container } = render(
      <div>
        {renderMarkdown(
          '| 产品文档 | 状态 |\n|---------|------|\n| agent-orchestration | ✅ 已实现 |\n| channel-platform | 📋 设计完成 |',
        )}
      </div>,
    );
    const html = container.innerHTML;
    expect(html).toContain('<table');
    expect(html).toContain('<thead>');
    expect(html).toContain('<tbody>');
    expect(html).toContain('<th>产品文档</th>');
    expect(html).toContain('<td>✅ 已实现</td>');
    expect(html).not.toContain('|---------|');
  });

  it('引用行 → blockquote; 链接 → a 标签', () => {
    const { container } = render(
      <div>
        {renderMarkdown('> 状态: Founder 批准\n\n查看 [API规范](docs/API规范.md)')}
      </div>,
    );
    const html = container.innerHTML;
    expect(html).toContain('<blockquote');
    expect(html).toContain('> 状态'.length === 0 ? 'x' : '状态: Founder 批准');
    expect(html).not.toContain('&gt; 状态');
    expect(html).toContain('<a href="docs/API规范.md"');
    expect(html).toContain('API规范');
  });

  it('链接安全: javascript: 协议不渲染为链接 (原样文本)', () => {
    const { container } = render(
      <div>{renderMarkdown('[点我](javascript:alert(1))')}</div>,
    );
    const html = container.innerHTML;
    expect(html).not.toContain('href="javascript:');
  });
});
