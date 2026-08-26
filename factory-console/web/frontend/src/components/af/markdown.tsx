/**
 * components/af/markdown.tsx — 轻量安全 Markdown 渲染 (会话栏等用)。
 *
 * 支持: 标题/粗体/斜体/行内代码/列表/代码块/段落。纯 React 元素, 不注入 HTML。
 */

import type { ReactNode } from 'react';

/** 行内渲染: **粗体** · *斜体* · `代码` (安全拆分, 无 HTML)。 */
export function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g);
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**') && p.length > 4) {
      return <strong key={i}>{p.slice(2, -2)}</strong>;
    }
    if (p.startsWith('`') && p.endsWith('`') && p.length > 2) {
      return (
        <code key={i} className="af-inline-code">
          {p.slice(1, -1)}
        </code>
      );
    }
    if (p.startsWith('*') && p.endsWith('*') && p.length > 2) {
      return <em key={i}>{p.slice(1, -1)}</em>;
    }
    return p;
  });
}

/** 块级渲染: 标题/列表/代码块/段落。 */
export function renderMarkdown(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let list: string[] = [];
  let code: string[] = [];
  let inCode = false;
  const flushList = (key: string) => {
    if (list.length > 0) {
      out.push(
        <ul key={key}>
          {list.map((li, i) => (
            <li key={`${key}-${i}`}>{renderInline(li)}</li>
          ))}
        </ul>,
      );
      list = [];
    }
  };
  text.split('\n').forEach((line, idx) => {
    if (line.trim().startsWith('```')) {
      if (inCode) {
        out.push(<pre key={`c-${idx}`} className="af-doc-code">{code.join('\n')}</pre>);
        code = [];
      }
      inCode = !inCode;
      return;
    }
    if (inCode) {
      code.push(line);
      return;
    }
    if (line.startsWith('# ')) {
      flushList(`l-${idx}`);
      out.push(<h4 key={`h1-${idx}`}>{renderInline(line.slice(2))}</h4>);
    } else if (line.startsWith('## ')) {
      flushList(`l-${idx}`);
      out.push(<h5 key={`h2-${idx}`}>{renderInline(line.slice(3))}</h5>);
    } else if (line.startsWith('### ')) {
      flushList(`l-${idx}`);
      out.push(<h6 key={`h3-${idx}`}>{renderInline(line.slice(4))}</h6>);
    } else if (/^[-*]\s+/.test(line)) {
      list.push(line.replace(/^[-*]\s+/, ''));
    } else if (line.trim() === '') {
      flushList(`l-${idx}`);
    } else {
      flushList(`l-${idx}`);
      out.push(<p key={`p-${idx}`}>{renderInline(line)}</p>);
    }
  });
  flushList('end');
  if (inCode) out.push(<pre key="code-end" className="af-doc-code">{code.join('\n')}</pre>);
  return out;
}
