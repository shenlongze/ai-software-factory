/**
 * pages/project/AfProjectDocs.tsx — 项目文档管理 (v1.1.108, Founder 要求)。
 *
 * 左树右看: 左侧文档清单 (核心资产 + 目录扫描), 右侧内容预览
 * 数据: GET /api/projects/{id}/docs + /docs/{doc} (真实, 路径安全)
 * 渲染: markdown 简单渲染 / JSON 格式化 / 纯文本; 不支持/缺失 → 诚实提示。
 */

import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { api } from '../../api/client';
import type { ProjectDocContent, ProjectDocSummary } from '../../models/types';

/** 简单 markdown 渲染 (标题/列表/段落/代码 — 安全, 不注入 HTML)。 */
function renderMarkdown(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let list: string[] = [];
  let code: string[] = [];
  let inCode = false;
  const flushList = (key: string) => {
    if (list.length > 0) {
      out.push(
        <ul key={key} className="af-doc-list">
          {list.map((li, i) => (
            <li key={`${key}-${i}`}>{li}</li>
          ))}
        </ul>,
      );
      list = [];
    }
  };
  const lines = text.split('\n');
  lines.forEach((line, idx) => {
    if (line.trim().startsWith('```')) {
      if (inCode) {
        out.push(<pre key={`code-${idx}`} className="af-doc-code">{code.join('\n')}</pre>);
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
      out.push(<h1 key={`h1-${idx}`}>{line.slice(2)}</h1>);
    } else if (line.startsWith('## ')) {
      flushList(`l-${idx}`);
      out.push(<h2 key={`h2-${idx}`}>{line.slice(3)}</h2>);
    } else if (line.startsWith('### ')) {
      flushList(`l-${idx}`);
      out.push(<h3 key={`h3-${idx}`}>{line.slice(4)}</h3>);
    } else if (/^[-*]\s+/.test(line)) {
      list.push(line.replace(/^[-*]\s+/, ''));
    } else if (/^\d+\.\s+/.test(line)) {
      flushList(`l-${idx}`);
      out.push(<p key={`p-${idx}`} className="af-doc-list">{line}</p>);
    } else if (line.trim() === '') {
      flushList(`l-${idx}`);
    } else {
      flushList(`l-${idx}`);
      out.push(<p key={`p-${idx}`}>{line}</p>);
    }
  });
  flushList('end');
  if (inCode) {
    out.push(<pre key="code-end" className="af-doc-code">{code.join('\n')}</pre>);
  }
  return out;
}

function fmtSize(size: number): string {
  if (size <= 0) return '';
  if (size < 1024) return `${size} B`;
  return `${(size / 1024).toFixed(1)} KB`;
}

export interface AfProjectDocsProps {
  projectId: string;
  projectName?: string;
}

export function AfProjectDocs({ projectId, projectName }: AfProjectDocsProps): JSX.Element {
  const [docs, setDocs] = useState<ProjectDocSummary[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [content, setContent] = useState<ProjectDocContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [contentLoading, setContentLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .projectDocs(projectId)
      .then((list) => {
        if (cancelled) return;
        setDocs(list);
        const first = list.find((d) => d.exists && (d.kind === 'md' || d.kind === 'json' || d.kind === 'txt'));
        if (first) setActive(first.name);
      })
      .catch(() => {
        if (!cancelled) setDocs([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => {
    if (active == null) {
      setContent(null);
      return;
    }
    let cancelled = false;
    setContentLoading(true);
    api
      .projectDocContent(projectId, active)
      .then((c) => {
        if (!cancelled) setContent(c);
      })
      .catch(() => {
        if (!cancelled) setContent(null);
      })
      .finally(() => {
        if (!cancelled) setContentLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, active]);

  const core = useMemo(() => docs.filter((d) => !d.extra), [docs]);
  const extras = useMemo(() => docs.filter((d) => d.extra), [docs]);
  const folders = useMemo(() => {
    const m = new Map<string, ProjectDocSummary[]>();
    for (const d of extras) {
      const folder = d.folder || d.name.split('/')[0];
      if (!m.has(folder)) m.set(folder, []);
      m.get(folder)?.push(d);
    }
    return [...m.entries()];
  }, [extras]);

  const renderDocRow = (d: ProjectDocSummary) => (
    <button
      key={d.name}
      type="button"
      className={`af-doc-item${active === d.name ? ' af-doc-item--active' : ''}${!d.exists ? ' af-doc-item--missing' : ''}`}
      onClick={() => setActive(d.name)}
      title={d.name}
    >
      <span className="af-doc-item-label">{d.label || d.name}</span>
      <span className="af-doc-item-meta">{fmtSize(d.size)}{!d.exists ? '（未生成）' : ''}</span>
    </button>
  );

  let body: ReactNode;
  if (contentLoading) {
    body = <p className="af-home-note">加载文档…</p>;
  } else if (content == null) {
    body = <p className="af-home-note">（文档加载失败）</p>;
  } else if (content.content == null) {
    body = <p className="af-home-note">{content.note ?? '（无内容）'}</p>;
  } else if (content.kind === 'md') {
    body = <div className="af-doc-md">{renderMarkdown(content.content)}</div>;
  } else if (content.kind === 'json') {
    let pretty = content.content;
    try {
      pretty = JSON.stringify(JSON.parse(content.content), null, 2);
    } catch {
      /* 非合法 JSON → 原样展示 */
    }
    body = <pre className="af-doc-code">{pretty}</pre>;
  } else {
    body = <pre className="af-doc-code">{content.content}</pre>;
  }

  return (
    <div className="af-docs" data-testid="af-docs">
      <h2 className="af-detail-name">📄 文档 · {projectName ?? projectId}</h2>
      <div className="af-docs-layout">
        <aside className="af-docs-nav" data-testid="af-docs-nav">
          {loading ? (
            <p className="af-home-note">加载清单…</p>
          ) : docs.length === 0 ? (
            <p className="af-home-note">（暂无文档 — 生成 PRD/工程计划后自动出现）</p>
          ) : (
            <>
              <div className="af-doc-group">核心资产</div>
              {core.map(renderDocRow)}
              {folders.length > 0 ? (
                <>
                  <div className="af-doc-group">其他文件</div>
                  {folders.map(([folder, items]) => (
                    <div key={folder}>
                      <div className="af-doc-folder">📁 {folder}</div>
                      {items.map(renderDocRow)}
                    </div>
                  ))}
                </>
              ) : null}
            </>
          )}
        </aside>
        <main className="af-docs-view" data-testid="af-docs-view">
          {content != null && content.content != null ? (
            <div className="af-doc-head">
              <span className="af-doc-title">{content.label ?? content.name}</span>
              <span className="af-doc-kind">{content.kind}</span>
            </div>
          ) : null}
          {body}
        </main>
      </div>
    </div>
  );
}
