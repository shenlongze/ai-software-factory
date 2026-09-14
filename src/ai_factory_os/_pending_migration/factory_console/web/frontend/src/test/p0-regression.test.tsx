/** P0 回归: 项目列表回答 (含表格) 必须渲染正文 + 工具证据。 */
import { describe, expect, it } from 'vitest';
import { renderMarkdown } from '../components/af/markdown';

describe('P0 Regression: 项目列表表格回答', () => {
  it('renderMarkdown 渲染含表格的完整回答 (不丢正文)', () => {
    const content =
      '当前共有 8 个项目，以下是完整列表：\n\n' +
      '| 项目名 | 状态 |\n' +
      '|--------|------|\n' +
      '| **ai-factory-self** | development |\n' +
      '| **番茄钟** | development |';
    const out = renderMarkdown(content);
    // 表格必须存在 (原生元素 type 是字符串 'table')
    expect(out.some((n) => (n as { type?: unknown })?.type === 'table')).toBe(true);
    // 段落保留
    expect(out.some((n) => (n as { type?: unknown })?.type === 'p')).toBe(true);
  });
});
