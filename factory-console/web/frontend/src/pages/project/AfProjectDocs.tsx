/**
 * pages/project/AfProjectDocs.tsx — 项目文档/产出物 (C-3)。
 *
 * 双 Tab:
 *   📄 文档 — 左树右看 (docs 扫描, v1.1.108)
 *   📦 产出物 — Manifest 视图 (类型/文件/版本/生产者/trace) + 版本历史查看 +
 *               版本轮询自动刷新 (实时: 10s 轮询 version, 变化自动重载)
 * 数据: GET /api/projects/{id}/docs + /docs/{doc} + /artifacts + /artifacts/version
 *       + /artifacts/{type}/versions/{v}
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { api } from '../../api/client';
import { useI18n } from '../../i18n';
import type { ProjectArtifactItem, ProjectDocContent, ProjectDocSummary } from '../../models/types';

/* ---------------------------------------------------------------- markdown */
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
      out.push(<h1 key={`h1-${idx}`}>{line.slice(2)}</h1>);
    } else if (line.startsWith('## ')) {
      flushList(`l-${idx}`);
      out.push(<h2 key={`h2-${idx}`}>{line.slice(3)}</h2>);
    } else if (line.startsWith('### ')) {
      flushList(`l-${idx}`);
      out.push(<h3 key={`h3-${idx}`}>{line.slice(4)}</h3>);
    } else if (/^[-*]\s+/.test(line)) {
      list.push(line.replace(/^[-*]\s+/, ''));
    } else if (line.trim() === '') {
      flushList(`l-${idx}`);
    } else {
      flushList(`l-${idx}`);
      out.push(<p key={`p-${idx}`}>{line}</p>);
    }
  });
  flushList('end');
  if (inCode) out.push(<pre key="code-end" className="af-doc-code">{code.join('\n')}</pre>);
  return out;
}

function renderContentBody(content: string | null, kind: string, note?: string | null): ReactNode {
  if (content == null) return <p className="af-home-note">{note ?? '（无内容）'}</p>;
  if (kind === 'md') return <div className="af-doc-md">{renderMarkdown(content)}</div>;
  if (kind === 'json') {
    let pretty = content;
    try {
      pretty = JSON.stringify(JSON.parse(content), null, 2);
    } catch {
      /* 原样 */
    }
    return <pre className="af-doc-code">{pretty}</pre>;
  }
  return <pre className="af-doc-code">{content}</pre>;
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  return iso.slice(0, 16).replace('T', ' ');
}
function fmtSize(size: number): string {
  if (size <= 0) return '';
  return size < 1024 ? `${size} B` : `${(size / 1024).toFixed(1)} KB`;
}

export interface AfProjectDocsProps {
  projectId: string;
  projectName?: string;
}

export function AfProjectDocs({ projectId, projectName }: AfProjectDocsProps): JSX.Element {
  const { t } = useI18n();
  const [tab, setTab] = useState<'docs' | 'artifacts'>('docs');
  const [msg, setMsg] = useState<string>('');

  // ---- 文档 tab
  const [docs, setDocs] = useState<ProjectDocSummary[]>([]);
  const [activeDoc, setActiveDoc] = useState<string | null>(null);
  const [docContent, setDocContent] = useState<ProjectDocContent | null>(null);
  const [docsLoading, setDocsLoading] = useState(true);
  const [docLoading, setDocLoading] = useState(false);

  // ---- 产出物 tab
  const [artifacts, setArtifacts] = useState<ProjectArtifactItem[]>([]);
  const [artifactMeta, setArtifactMeta] = useState<{ version: number; updated_at: string | null }>({
    version: 0,
    updated_at: null,
  });
  const [drift, setDrift] = useState<string[]>([]);
  const [artLoading, setArtLoading] = useState(true);
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [artifactContent, setArtifactContent] = useState<{ file: string; kind: string; content: string | null; note?: string | null } | null>(null);
  const [artContentLoading, setArtContentLoading] = useState(false);
  const versionRef = useRef<number | null>(null);

  const flash = (text: string) => {
    setMsg(text);
    window.setTimeout(() => setMsg(''), 4000);
  };

  // ---- 文档加载
  useEffect(() => {
    let cancelled = false;
    setDocsLoading(true);
    api
      .projectDocs(projectId)
      .then((list) => {
        if (cancelled) return;
        setDocs(list);
        const first = list.find((d) => d.exists && (d.kind === 'md' || d.kind === 'json' || d.kind === 'txt'));
        if (first) setActiveDoc(first.name);
      })
      .catch(() => {
        if (!cancelled) setDocs([]);
      })
      .finally(() => {
        if (!cancelled) setDocsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => {
    if (activeDoc == null) {
      setDocContent(null);
      return;
    }
    let cancelled = false;
    setDocLoading(true);
    api
      .projectDocContent(projectId, activeDoc)
      .then((c) => {
        if (!cancelled) setDocContent(c);
      })
      .catch(() => {
        if (!cancelled) setDocContent(null);
      })
      .finally(() => {
        if (!cancelled) setDocLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, activeDoc]);

  // ---- 产出物加载
  const loadArtifacts = useCallback(() => {
    setArtLoading(true);
    api
      .projectArtifacts(projectId)
      .then((d) => {
        setArtifacts(d.items ?? []);
        setArtifactMeta(d.meta ?? { version: 0, updated_at: null });
        setDrift(d.drift ?? []);
        versionRef.current = d.meta?.version ?? 0;
      })
      .catch(() => setArtifacts([]))
      .finally(() => setArtLoading(false));
  }, [projectId]);

  useEffect(() => {
    if (tab !== 'artifacts') return;
    loadArtifacts();
    // 实时: 10s 轮询 version, 变化自动重载
    const iv = window.setInterval(() => {
      api
        .projectArtifactsVersion(projectId)
        .then((v) => {
          if (versionRef.current != null && v.version > versionRef.current) {
            flash(`📦 产出物已更新 → v${v.version}`);
            loadArtifacts();
          }
        })
        .catch(() => {
          /* 失败忽略 */
        });
    }, 10000);
    return () => window.clearInterval(iv);
  }, [tab, projectId, loadArtifacts]);

  // 选中产出物类型 → 加载内容 (默认当前版本)
  useEffect(() => {
    if (selectedType == null) {
      setArtifactContent(null);
      return;
    }
    const item = artifacts.find((a) => a.type === selectedType);
    if (item == null) {
      setArtifactContent(null);
      return;
    }
    let cancelled = false;
    setArtContentLoading(true);
    const load = () => {
      if (cancelled) return;
      setArtContentLoading(false);
    };
    const version = selectedVersion ?? item.version;
    if (version != null && (item.versions ?? []).length > 0) {
      api
        .projectArtifactVersion(projectId, selectedType, version)
        .then((v) => {
          if (cancelled) return;
          setArtifactContent({ file: v.file, kind: item.kind, content: v.content });
          load();
        })
        .catch(() => {
          if (!cancelled) setArtifactContent(null);
          load();
        });
    } else if (item.legacy || (item.versions ?? []).length === 0) {
      // 存量/无版本链 → 直接读文件 (docs API)
      api
        .projectDocContent(projectId, item.file)
        .then((c) => {
          if (cancelled) return;
          setArtifactContent({ file: item.file, kind: item.kind, content: c.content, note: c.note });
          load();
        })
        .catch(() => {
          if (!cancelled) setArtifactContent(null);
          load();
        });
    }
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedType, selectedVersion, artifacts, projectId]);

  // ---- 文档左树渲染
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
      className={`af-doc-item${activeDoc === d.name ? ' af-doc-item--active' : ''}${!d.exists ? ' af-doc-item--missing' : ''}`}
      onClick={() => setActiveDoc(d.name)}
      title={d.name}
    >
      <span className="af-doc-item-label">{d.label || d.name}</span>
      <span className="af-doc-item-meta">{fmtSize(d.size)}{!d.exists ? '（未生成）' : ''}</span>
    </button>
  );

  const selectedItem = artifacts.find((a) => a.type === selectedType) ?? null;

  return (
    <div className="af-docs" data-testid="af-docs">
      <h2 className="af-detail-name">📄 文档 · {projectName ?? projectId}</h2>
      <div className="af-docs-tabs" role="tablist" aria-label="文档/产出物">
        <button type="button" role="tab" aria-selected={tab === 'docs'} className={`af-docs-tab${tab === 'docs' ? ' active' : ''}`} onClick={() => setTab('docs')}>
          {t('docs.tab.docs')}
        </button>
        <button type="button" role="tab" aria-selected={tab === 'artifacts'} className={`af-docs-tab${tab === 'artifacts' ? ' active' : ''}`} onClick={() => setTab('artifacts')}>
          {t('docs.tab.artifacts')}{artifactMeta.version > 0 ? ` · v${artifactMeta.version}` : ''}
        </button>
      </div>
      {msg ? (
        <p className="af-composer-msg" data-testid="af-assets-msg">{msg}</p>
      ) : null}

      {tab === 'docs' ? (
        <div className="af-docs-layout">
          <aside className="af-docs-nav" data-testid="af-docs-nav">
            {docsLoading ? (
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
            {docLoading ? (
              <p className="af-home-note">加载文档…</p>
            ) : docContent == null ? (
              <p className="af-home-note">（文档加载失败）</p>
            ) : (
              <>
                <div className="af-doc-head">
                  <span className="af-doc-title">{docContent.label ?? docContent.name}</span>
                  <span className="af-doc-kind">{docContent.kind}</span>
                </div>
                {renderContentBody(docContent.content, docContent.kind, docContent.note)}
              </>
            )}
          </main>
        </div>
      ) : (
        <div className="af-docs-layout">
          <aside className="af-docs-nav" data-testid="af-artifacts-nav">
            <div className="af-settings-head-row">
              <div className="af-doc-group">产出物清单（{artifacts.length}）</div>
              <button type="button" className="af-settings-action" onClick={loadArtifacts}>⟳ 刷新</button>
            </div>
            {artLoading ? (
              <p className="af-home-note">加载产出物…</p>
            ) : artifacts.length === 0 ? (
              <p className="af-home-note">（暂无产出物 — 引擎产出后自动登记）</p>
            ) : (
              artifacts.map((a) => (
                <button
                  key={a.type}
                  type="button"
                  className={`af-doc-item${selectedType === a.type ? ' af-doc-item--active' : ''}${!a.exists ? ' af-doc-item--missing' : ''}`}
                  onClick={() => {
                    setSelectedType(a.type);
                    setSelectedVersion(null);
                  }}
                  title={`${a.file}${a.legacy ? '（存量）' : ''}`}
                >
                  <span className="af-doc-item-label">{a.label}</span>
                  <span className="af-doc-item-meta">
                    {a.exists ? (a.legacy ? '📦存量' : `v${a.version}`) : '未生成'}
                  </span>
                </button>
              ))
            )}
            {drift.length > 0 ? (
              <p className="af-home-note">⚠️ 漂移: {drift.join(', ')}</p>
            ) : null}
          </aside>
          <main className="af-docs-view" data-testid="af-artifacts-view">
            <div className="af-doc-head">
              <span className="af-doc-title">
                版本 v{artifactMeta.version} · 更新 {fmtTime(artifactMeta.updated_at)}
              </span>
              <button type="button" className="af-settings-action" onClick={loadArtifacts}>⟳ 刷新</button>
            </div>
            {selectedItem == null ? (
              <p className="af-home-note">选择左侧产出物查看内容与历史。</p>
            ) : (
              <>
                <div className="af-artifact-meta">
                  <span className="af-doc-kind">{selectedItem.type}</span>
                  <span className="af-settings-chip">📄 {selectedItem.file}</span>
                  {selectedItem.producer ? <span className="af-settings-chip">✍️ {selectedItem.producer}</span> : null}
                  {selectedItem.trace_id ? <span className="af-settings-chip" title="K-4 链路追溯">🔗 {selectedItem.trace_id}</span> : null}
                  {selectedItem.legacy ? <span className="af-settings-chip">📦 存量（未纳入契约）</span> : null}
                </div>
                {(selectedItem.versions ?? []).length > 1 ? (
                  <div className="af-version-chain">
                    <span className="af-doc-group">版本链:</span>
                    {[...(selectedItem.versions ?? [])]
                      .sort((x, y) => x.version - y.version)
                      .map((v) => (
                        <button
                          key={v.version}
                          type="button"
                          className={`af-version-chip${(selectedVersion ?? selectedItem.version) === v.version ? ' active' : ''}`}
                          onClick={() => setSelectedVersion(v.version)}
                          title={`${v.file} · ${v.producer ?? ''} · ${v.trace_id ?? ''}`}
                        >
                          v{v.version}
                        </button>
                      ))}
                  </div>
                ) : null}
                {artContentLoading ? (
                  <p className="af-home-note">加载内容…</p>
                ) : artifactContent == null ? (
                  <p className="af-home-note">（内容加载失败）</p>
                ) : (
                  <>
                    <div className="af-doc-head">
                      <span className="af-doc-title">{artifactContent.file}</span>
                      <span className="af-doc-kind">{artifactContent.kind}</span>
                    </div>
                    {renderContentBody(artifactContent.content, artifactContent.kind, artifactContent.note)}
                  </>
                )}
              </>
            )}
          </main>
        </div>
      )}
    </div>
  );
}
