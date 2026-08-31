/**
 * components/af/AfProjectsView.tsx — 项目管理视图 (S35-UI)。
 *
 * 数据源: GET /api/projects (统一后端, ConsoleService → org SSOT)。
 * 渲染: 项目卡片 (名称/ID/状态/阶段/描述) — 点击 → #/project/:id 项目详情。
 * 原则: 纯 Projection — 不前端计算状态, 不写业务数据; 后端不可达 → 空态不崩。
 */

import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import './af.css';

interface ProjectSummaryRow {
  id: string;
  name: string;
  description?: string | null;
  status?: string | null;
  lifecycle_stage?: string | null;
  starred?: boolean;
  archived?: boolean;
}

export function AfProjectsView(): JSX.Element {
  const [projects, setProjects] = useState<ProjectSummaryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    api
      .projects()
      .then((list) => {
        if (!cancelled) setProjects(list.filter((p) => !p.archived));
      })
      .catch((err) => {
        if (!cancelled) setError(`加载失败: ${String(err)}`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) return <div className="af-projects-view af-projects-empty">加载项目…</div>;

  return (
    <div className="af-projects-view" data-testid="af-projects-view">
      <div className="af-projects-head">
        <h3>📁 项目管理</h3>
        <span className="af-projects-count">{projects.length} 个项目</span>
      </div>
      {error ? <p className="af-projects-note">{error}</p> : null}
      {projects.length === 0 ? (
        <p className="af-projects-note">
          {error ? '（后端不可达）' : '暂无项目 — 在对话里说"我想做…"或点左侧 ＋ 创建'}
        </p>
      ) : (
        <div className="af-projects-list">
          {projects.map((p) => (
            <a key={p.id} className="af-project-card" href={`#/project/${encodeURIComponent(p.id)}`}>
              <div className="af-project-card-row">
                <span className="af-project-card-name">{p.name || p.id}</span>
                {p.lifecycle_stage ? (
                  <span className="af-project-card-stage">{p.lifecycle_stage}</span>
                ) : null}
              </div>
              <code className="af-project-card-id">{p.id}</code>
              {p.description ? (
                <p className="af-project-card-desc">{String(p.description).slice(0, 80)}</p>
              ) : null}
              <div className="af-project-card-row af-project-card-meta">
                <span>状态: {p.status || '—'}</span>
                {p.starred ? <span>⭐ 收藏</span> : null}
              </div>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
