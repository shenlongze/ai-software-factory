/**
 * components/af/BrowserWorkspace.tsx — 类浏览器多标签工作区 (W-T1/T2, v1.1.270).
 *
 * Chrome 式: 首页 tab 固定不可关(项目状态页) + ➕ 新标签打开项目资源
 * (运行应用/文档/产物/文件/终端/审查 占位)。
 * 每 tab 独立内容; 新标签页 = 项目入口页 (NewTabPage)。
 *
 * Tab 类型:
 * - home     项目状态页 (固定, 不可关)
 * - newtab   ➕ 新标签页 (项目入口)
 * - browser  外部/应用 URL (iframe)
 * - doc      文档 markdown 渲染
 * - artifact 产物查看
 * - file     文件只读代码查看
 * - terminal 终端 (二期占位)
 * - audit    审查 (二期占位)
 */

import { useCallback, useEffect, useState } from 'react';
import { AfProjectHome } from '../../pages/project/AfProjectHome';
import './af.css';

export type TabType = 'home' | 'project' | 'newtab' | 'browser' | 'doc' | 'artifact' | 'file' | 'terminal' | 'audit';

export interface WorkspaceTab {
  id: string;
  type: TabType;
  title: string;
  projectId?: string | null;  // 项目作用域
  url?: string;        // browser / 运行应用 URL
  docPath?: string;    // 文档相对路径
  artifactType?: string;
  filePath?: string;   // 文件相对路径
}

export interface BrowserWorkspaceProps {
  projectId?: string | null;
  projectName?: string | null;
}

let _tabSeq = 0;
function nextId(): string {
  _tabSeq += 1;
  return `tab-${Date.now()}-${_tabSeq}`;
}

// ---------------------------------------------------------------- Tab 内容分发
function TabContent({ tab, projectId, onOpen }: {
  tab: WorkspaceTab; projectId?: string | null;
  onOpen: (t: Omit<WorkspaceTab, 'id'>) => void;
}): JSX.Element {
  switch (tab.type) {
    case 'newtab':
      return <NewTabPage projectId={projectId} onOpen={onOpen} />;
    case 'browser':
      return <BrowserFrame url={tab.url || ''} />;
    case 'doc':
      return <DocView path={tab.docPath || ''} projectId={projectId} />;
    case 'artifact':
      return <ArtifactView artifactType={tab.artifactType || ''} projectId={projectId} />;
    case 'file':
      return <FileView path={tab.filePath || ''} projectId={projectId} />;
    case 'terminal':
      return <Placeholder icon="💻" title="终端 (二期)" note="后端 shell 桥接入后可用" />;
    case 'audit':
      return <Placeholder icon="🔍" title="审查 (二期)" note="定义审查范围后实现" />;
    case 'project':
      return <ProjectTab projectId={tab.projectId || projectId} projectName={tab.title} />;
    case 'home':
    default:
      return <MyCompanyTab onOpen={onOpen} />;
  }
}

// ---------------------------------------------------------------- 首页 (我的公司, 固定不可关)
interface CompanyProject {
  id: string; name: string; status?: string; starred?: boolean;
  lifecycle_stage?: string | null; repository?: string;
  created_at?: string | null; updated_at?: string | null;
  pending_plan_count?: number;
  stage_progress?: Record<string, { done: number; total: number; pct: number }>;
}

function MyCompanyTab({ onOpen }: { onOpen: (t: Omit<WorkspaceTab, 'id'>) => void }): JSX.Element {
  const [projects, setProjects] = useState<CompanyProject[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/projects', { headers: { Accept: 'application/json' } });
        if (res.ok) {
          const raw = (await res.json()) as { items?: unknown[] } | unknown[];
          const list = Array.isArray(raw) ? raw : (raw as { items?: unknown[] }).items ?? [];
          if (!cancelled) setProjects(list as CompanyProject[]);
        }
      } catch { /* 失败安全 */ }
      if (!cancelled) setLoading(false);
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="bw-home bw-home--company" data-testid="bw-home">
      <h2>🏢 我的公司</h2>
      <p className="bw-home-sub">公司级工作台 — 按最近更新排序，点项目进入</p>
      <div className="bw-company-card" data-testid="bw-company-card">
        <div className="bw-company-card-head">📁 项目</div>
      {loading ? <p className="bw-muted bw-card-pad">加载中…</p> : projects.length === 0 ? (
        <p className="bw-muted bw-card-pad">暂无项目 — 点 ➕ 新建或从侧栏创建</p>
      ) : (
        <ol className="bw-company-list">
          {projects.map((p, idx) => {
            return (
              <li key={p.id} className="bw-company-item" data-testid={`bw-company-${p.id}`}>
                <span className="bw-company-idx">{idx + 1}.</span>
                <button
                  type="button"
                  className="bw-company-name"
                  onClick={() => onOpen({ type: 'project', title: p.name, projectId: p.id })}
                >
                  {p.starred ? '⭐ ' : ''}{p.name}
                </button>
                <span className="bw-badge bw-badge--stage">{p.lifecycle_stage || p.status || '—'}</span>
                <span className="bw-company-plan">未完成 {p.pending_plan_count ?? 0}</span>
                <span className="bw-company-meta">更新 {p.updated_at || '—'}</span>
                {p.repository ? (
                  <a className="bw-company-repo" href={p.repository} target="_blank" rel="noreferrer" title={p.repository}>
                    🔗 仓库
                  </a>
                ) : <span className="bw-company-repo bw-muted">🔗 无仓库</span>}
              </li>
            );
          })}
        </ol>
      )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- 项目页 (点"我的公司"项目打开 → 真实项目概览)
function ProjectTab({ projectId, projectName }: { projectId?: string | null; projectName?: string }): JSX.Element {
  if (!projectId) return <Placeholder icon="📁" title="项目" note="未指定项目" />;
  return (
    <div className="bw-project" data-testid="bw-project">
      <AfProjectHome projectId={projectId} projectName={projectName || projectId} />
    </div>
  );
}

// ---------------------------------------------------------------- 新标签页 (➕ 入口)
function NewTabPage({ projectId, onOpen }: {
  projectId?: string | null;
  onOpen: (t: Omit<WorkspaceTab, 'id'>) => void;
}): JSX.Element {
  const [url, setUrl] = useState('');
  const [runtimes, setRuntimes] = useState<{ id: string; url?: string; status?: string; name?: string }[]>([]);
  const [docs, setDocs] = useState<string[]>([]);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/runtimes`, {
          headers: { Accept: 'application/json' },
        });
        if (res.ok) {
          const raw = (await res.json()) as { items?: unknown[] } | unknown[];
          const list = Array.isArray(raw) ? raw : (raw as { items?: unknown[] }).items ?? [];
          if (!cancelled) setRuntimes(list as { id: string; url?: string; status?: string; name?: string }[]);
        }
      } catch { /* 失败安全 */ }
      try {
        const res2 = await fetch(`/api/projects/${encodeURIComponent(projectId)}/docs`, {
          headers: { Accept: 'application/json' },
        });
        if (res2.ok) {
          const raw2 = (await res2.json()) as { items?: unknown[] } | unknown[];
          const list2 = Array.isArray(raw2) ? raw2 : (raw2 as { items?: unknown[] }).items ?? [];
          if (!cancelled) setDocs((list2 as { path?: string; name?: string }[]).map((d) => d.path || d.name || '').filter(Boolean));
        }
      } catch { /* 失败安全 */ }
    })();
    return () => { cancelled = true; };
  }, [projectId]);

  const openBrowser = () => {
    const v = url.trim();
    if (v) onOpen({ type: 'browser', title: v, url: /^https?:\/\//.test(v) ? v : `http://${v}` });
  };

  return (
    <div className="bw-newtab" data-testid="bw-newtab">
      <div className="bw-newtab-address">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && openBrowser()}
          placeholder="输入 URL 打开浏览器 (如 http://127.0.0.1:8000)"
          aria-label="新标签地址"
        />
        <button type="button" className="bw-btn" onClick={openBrowser}>打开</button>
      </div>
      <div className="bw-newtab-sections">
        <section>
          <h3>🚀 运行中的应用</h3>
          {runtimes.length ? (
            <ul className="bw-list">
              {runtimes.map((r) => (
                <li key={r.id}>
                  <button type="button" onClick={() => r.url && onOpen({ type: 'browser', title: r.name || r.url, url: r.url })}>
                    {r.name || r.id} · {r.status || 'unknown'} {r.url ? `→ ${r.url}` : ''}
                  </button>
                </li>
              ))}
            </ul>
          ) : <p className="bw-muted">暂无运行实例</p>}
        </section>
        <section>
          <h3>📄 项目文档</h3>
          {docs.length ? (
            <ul className="bw-list">
              {docs.map((d) => (
                <li key={d}>
                  <button type="button" onClick={() => onOpen({ type: 'doc', title: d.split('/').pop() || d, docPath: d })}>
                    {d}
                  </button>
                </li>
              ))}
            </ul>
          ) : <p className="bw-muted">暂无文档</p>}
        </section>
        <section>
          <h3>🗂 文件管理</h3>
          <button type="button" className="bw-btn" onClick={() => onOpen({ type: 'file', title: '文件浏览', filePath: '' })}>
            打开文件浏览 (只读)
          </button>
        </section>
        <section>
          <h3>更多</h3>
          <div className="bw-row">
            <button type="button" className="bw-btn" onClick={() => onOpen({ type: 'terminal', title: '终端' })}>💻 终端</button>
            <button type="button" className="bw-btn" onClick={() => onOpen({ type: 'audit', title: '审查' })}>🔍 审查</button>
          </div>
        </section>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- 内容组件 (T3 简化版)
function BrowserFrame({ url }: { url: string }): JSX.Element {
  return url ? (
    <iframe className="bw-frame" title="浏览器" src={url} sandbox="allow-scripts allow-same-origin allow-forms" />
  ) : (
    <Placeholder icon="🌐" title="浏览器" note="地址栏输入 URL 打开" />
  );
}

function DocView({ path, projectId }: { path: string; projectId?: string | null }): JSX.Element {
  const [content, setContent] = useState('');
  useEffect(() => {
    if (!projectId || !path) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/docs/${encodeURIComponent(path)}`, {
          headers: { Accept: 'application/json' },
        });
        if (res.ok) {
          const d = (await res.json()) as { content?: string };
          if (!cancelled) setContent(d.content || '');
        }
      } catch { /* 失败安全 */ }
    })();
    return () => { cancelled = true; };
  }, [projectId, path]);
  return (
    <div className="bw-doc">
      {path ? (
        <pre className="bw-doc-raw">{content || '加载中…'}</pre>
      ) : (
        <Placeholder icon="📄" title="文档" note="从新标签页选择文档打开" />
      )}
    </div>
  );
}

function ArtifactView({ artifactType }: { artifactType: string; projectId?: string | null }): JSX.Element {
  return <Placeholder icon="📦" title={`产物${artifactType ? ` · ${artifactType}` : ''}`} note="产物查看 (二期细化)" />;
}

function FileView({ path }: { path: string; projectId?: string | null }): JSX.Element {
  return <Placeholder icon="🗂" title={path ? `文件 · ${path}` : '文件浏览'} note="文件树/只读代码查看 (W-T3 细化)" />;
}

function Placeholder({ icon, title, note }: { icon: string; title: string; note: string }): JSX.Element {
  return (
    <div className="bw-placeholder" data-testid="bw-placeholder">
      <div className="bw-placeholder-icon">{icon}</div>
      <div className="bw-placeholder-title">{title}</div>
      <div className="bw-placeholder-note">{note}</div>
    </div>
  );
}

// ---------------------------------------------------------------- 主组件: 多标签工作区
export function BrowserWorkspace({ projectId, projectName }: BrowserWorkspaceProps): JSX.Element {
  const [tabs, setTabs] = useState<WorkspaceTab[]>([]);
  const [activeId, setActiveId] = useState<string>('');

  // 初始化: 固定首页 tab
  useEffect(() => {
    setTabs([{ id: 'home', type: 'home', title: '🏢 我的公司' }]);
    setActiveId('home');
  }, [projectId, projectName]);

  const openTab = useCallback((t: Omit<WorkspaceTab, 'id'>) => {
    const id = nextId();
    setTabs((prev) => [...prev, { ...t, id }]);
    setActiveId(id);
  }, []);

  const closeTab = useCallback((id: string) => {
    if (id === 'home') return; // 首页不可关
    setTabs((prev) => {
      const idx = prev.findIndex((t) => t.id === id);
      const next = prev.filter((t) => t.id !== id);
      if (activeId === id) {
        const fallback = next[Math.min(idx, next.length - 1)];
        setActiveId(fallback ? fallback.id : 'home');
      }
      return next;
    });
  }, [activeId]);

  const active = tabs.find((t) => t.id === activeId) || tabs[0];

  return (
    <div className="bw" data-testid="browser-workspace">
      <div className="bw-bar" role="tablist">
        {tabs.map((t) => (
          <div
            key={t.id}
            role="tab"
            aria-selected={t.id === activeId}
            className={`bw-tab${t.id === activeId ? ' bw-tab--active' : ''}${t.id === 'home' ? ' bw-tab--home' : ''}`}
            onClick={() => setActiveId(t.id)}
          >
            <span className="bw-tab-title">{t.title.length > 18 ? t.title.slice(0, 18) + '…' : t.title}</span>
            {t.id !== 'home' && (
              <button
                type="button"
                className="bw-tab-close"
                aria-label={`关闭 ${t.title}`}
                onClick={(e) => { e.stopPropagation(); closeTab(t.id); }}
              >
                ×
              </button>
            )}
          </div>
        ))}
        <button type="button" className="bw-add" aria-label="新标签页" onClick={() => openTab({ type: 'newtab', title: '新标签页' })}>
          ➕
        </button>
      </div>
      <div className="bw-body">
        {active ? <TabContent tab={active} projectId={projectId} onOpen={openTab} /> : null}
      </div>
    </div>
  );
}

export default BrowserWorkspace;
