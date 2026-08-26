/**
 * components/af/markdown.tsx — 轻量安全 Markdown 渲染 (会话栏 + 文档页共用)。
 *
 * 支持: 标题/粗体/斜体/行内代码/列表/有序列表/代码块/段落/引用/链接/表格。
 * 纯 React 元素, 不注入 HTML (XSS 安全); 零依赖 (无 marked/remark)。
 *
 * Founders 2026-08-26: 会话回复的 markdown 表格显示源码 → 补表格/引用/链接。
 */

import type { ReactNode } from 'react';

/** 安全链接: 拒绝危险协议 (javascript:/data:/vbscript:) 与空白/尖括号; 允许相对路径。 */
const URL_SAFE_RE = /^(?!\s*(?:javascript|data|vbscript):)[^\s<>"']+$/;

/** 行内渲染: **粗体** · *斜体* · `代码` · [链接](url) (安全拆分, 无 HTML)。 */
export function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]\n]+\]\([^)\s]+\))/g);
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
    const link = /^\[([^\]\n]+)\]\(([^)\s]+)\)$/.exec(p);
    if (link != null) {
      const url = link[2].trim();
      if (URL_SAFE_RE.test(url)) {
        return (
          <a key={i} href={url} target={url.startsWith('http') ? '_blank' : undefined} rel="noreferrer">
            {renderInline(link[1])}
          </a>
        );
      }
      return <span key={i}>{p}</span>;
    }
    return p;
  });
}

/** 单元格文本 (去掉外层空白与行内管道转义)。 */
function cellText(cell: string): string {
  return cell.trim().replace(/\\\|/g, '|');
}

/** 是否为表格分隔行 (如 |---|---|)。 */
function isTableSeparator(line: string): boolean {
  const cells = line.trim().replace(/^\||\|$/g, '').split('|');
  return (
    cells.length >= 1 &&
    cells.every((c) => /^:?-{2,}:?$/.test(c.trim()))
  );
}

/** 收集连续表格行 → 数组; 无分隔行 → 不是表格 (返回 null)。 */
function collectTable(lines: string[], start: number): { rows: string[][]; next: number } | null {
  const cells = (line: string) => line.trim().replace(/^\||\|$/g, '').split('|').map(cellText);
  if (start + 1 >= lines.length || !isTableSeparator(lines[start + 1])) {
    return null; // 无分隔行 → 不是 GFM 表格
  }
  const header = cells(lines[start]);
  const rows: string[][] = [];
  let next = start + 2;
  while (next < lines.length && lines[next].trim().startsWith('|')) {
    rows.push(cells(lines[next]));
    next += 1;
  }
  return { rows: [header, ...rows], next };
}

function renderTable(rows: string[][]): ReactNode {
  const [header, ...body] = rows;
  return (
    <table key={`tbl-${Math.random().toString(36).slice(2, 8)}`} className="af-md-table">
      <thead>
        <tr>
          {header.map((h, i) => (
            <th key={i}>{renderInline(h)}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {body.map((r, ri) => (
          <tr key={ri}>
            {r.map((c, ci) => (
              <td key={ci}>{renderInline(c)}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** 块级渲染: 标题/列表/有序列表/代码块/段落/引用/表格。 */
export function renderMarkdown(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const lines = String(text ?? '').split('\n');
  let list: string[] = [];
  let ordered: string[] = [];
  let quote: string[] = [];
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
  const flushOrdered = (key: string) => {
    if (ordered.length > 0) {
      out.push(
        <ol key={key}>
          {ordered.map((li, i) => (
            <li key={`${key}-${i}`}>{renderInline(li)}</li>
          ))}
        </ol>,
      );
      ordered = [];
    }
  };
  const flushQuote = (key: string) => {
    if (quote.length > 0) {
      out.push(
        <blockquote key={key} className="af-md-quote">
          {quote.map((q, i) => (
            <p key={`${key}-${i}`}>{renderInline(q)}</p>
          ))}
        </blockquote>,
      );
      quote = [];
    }
  };

  let idx = 0;
  while (idx < lines.length) {
    const line = lines[idx];
    if (line.trim().startsWith('```')) {
      if (inCode) {
        out.push(<pre key={`c-${idx}`} className="af-doc-code">{code.join('\n')}</pre>);
        code = [];
      }
      inCode = !inCode;
      idx += 1;
      continue;
    }
    if (inCode) {
      code.push(line);
      idx += 1;
      continue;
    }
    if (line.trim().startsWith('|')) {
      flushList(`l-${idx}`);
      flushOrdered(`o-${idx}`);
      flushQuote(`q-${idx}`);
      const table = collectTable(lines, idx);
      if (table != null) {
        out.push(renderTable(table.rows));
        idx = table.next;
        continue;
      }
    }
    if (line.startsWith('# ')) {
      flushList(`l-${idx}`); flushOrdered(`o-${idx}`); flushQuote(`q-${idx}`);
      out.push(<h4 key={`h1-${idx}`}>{renderInline(line.slice(2))}</h4>);
    } else if (line.startsWith('## ')) {
      flushList(`l-${idx}`); flushOrdered(`o-${idx}`); flushQuote(`q-${idx}`);
      out.push(<h5 key={`h2-${idx}`}>{renderInline(line.slice(3))}</h5>);
    } else if (line.startsWith('### ')) {
      flushList(`l-${idx}`); flushOrdered(`o-${idx}`); flushQuote(`q-${idx}`);
      out.push(<h6 key={`h3-${idx}`}>{renderInline(line.slice(4))}</h6>);
    } else if (/^[-*]\s+/.test(line)) {
      flushOrdered(`o-${idx}`); flushQuote(`q-${idx}`);
      list.push(line.replace(/^[-*]\s+/, ''));
    } else if (/^\d+[.)]\s+/.test(line)) {
      flushList(`l-${idx}`); flushQuote(`q-${idx}`);
      ordered.push(line.replace(/^\d+[.)]\s+/, ''));
    } else if (/^>\s?/.test(line)) {
      flushList(`l-${idx}`); flushOrdered(`o-${idx}`);
      quote.push(line.replace(/^>\s?/, ''));
    } else if (line.trim() === '') {
      flushList(`l-${idx}`); flushOrdered(`o-${idx}`); flushQuote(`q-${idx}`);
    } else {
      flushList(`l-${idx}`); flushOrdered(`o-${idx}`); flushQuote(`q-${idx}`);
      out.push(<p key={`p-${idx}`}>{renderInline(line)}</p>);
    }
    idx += 1;
  }
  flushList('end');
  flushOrdered('end');
  flushQuote('end');
  if (inCode) out.push(<pre key="code-end" className="af-doc-code">{code.join('\n')}</pre>);
  return out;
}
