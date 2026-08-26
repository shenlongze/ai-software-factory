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
