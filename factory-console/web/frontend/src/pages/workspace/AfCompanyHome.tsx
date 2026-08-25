/**
 * pages/workspace/AfCompanyHome.tsx — 我的公司首页 (Founder 2026-08-26, 信息量小)。
 *
 * ① 关注项目: 收藏 + 近期有更新 (无近期更新不占位)
 * ② 我的待办: 公司级聚合 (待审批) + 项目级过滤
 * 数据: GET /api/projects (starred/last_activity) + GET /api/approvals?pending_only=true
 * 原则: 简单 · 克制 · 真实 (质量/成本告警 API 待接入 → 诚实占位)
 */

import { useEffect, useMemo, useState } from 'react';
import type { ProjectSummary } from '../../models/types';

interface ApprovalItem {
  id?: string;
  type?: string;
  artifact_type?: string;
  gate?: string;
  status?: string;
  project_id?: string;
  artifact_id?: string;
  requested_at?: string;
  idea_id?: string;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as T;
}

const RECENT_DAYS = 7;

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '';
  return iso.slice(0, 16).replace('T', ' ');
}

export function AfCompanyHome(): JSX.Element {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [filter, setFilter] = useState<string>('all'); // all | project_id
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    let cancelled = false;
    getJson<{ items: ProjectSummary[] }>('/api/projects')
      .then((d) => {
        if (!cancelled) setProjects(d.items ?? []);
      })
      .catch(() => {
        if (!cancelled) setProjects([]);
      });
    getJson<{ items: ApprovalItem[] }>('/api/approvals?pending_only=true')
      .then((d) => {
        if (!cancelled) setApprovals(d.items ?? []);
      })
      .catch(() => {
        if (!cancelled) setApprovals([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 关注项目: 收藏 + 近期有更新 (无近期更新不占位)
  const focused = useMemo(() => {
    const cutoff = Date.now() - RECENT_DAYS * 24 * 3600 * 1000;
    return projects
      .filter((p) => p.starred)
      .filter((p) => {
        if (!p.last_activity) return false; // 无活动 → 不展示
        return new Date(p.last_activity).getTime() >= cutoff;
      })
      .sort((a, b) => String(b.last_activity ?? '').localeCompare(String(a.last_activity ?? '')));
  }, [projects]);

  // 待办: 待审批 (公司级聚合), 按项目过滤
  const todoItems = useMemo(() => {
    if (filter === 'all') return approvals;
    return approvals.filter((a) => a.project_id === filter);
  }, [approvals, filter]);

  const projectNames = useMemo(() => {
    const m = new Map<string, string>();
    for (const p of projects) m.set(p.id, p.name);
    return m;
  }, [projects]);
  const todoProjects = useMemo(
    () => [...new Set(approvals.map((a) => a.project_id).filter(Boolean) as string[])],
    [approvals],
  );

  const projectLabel = (pid: string | undefined): string => {
    if (!pid) return '项目 —';
    return projectNames.get(pid) ?? pid;
  };

  return (
    <div className="af-company-home" data-testid="af-company-home">
      <h2 className="af-detail-name">我的公司</h2>

      <section className="af-home-card" data-testid="af-home-focused">
        <h3>⭐ 关注项目（近期有更新）</h3>
        {focused.length === 0 ? (
          <p className="af-home-note">
            （暂无近期有更新的收藏项目 — 收藏后自动出现；或点左栏项目 ⭐ 收藏）
          </p>
        ) : (
          <div className="af-focused-grid">
            {focused.map((p) => (
              <a key={p.id} className="af-focused-card" href={`#/project/${p.id}`} data-testid={`af-focused-${p.id}`}>
                <span className="af-focused-name">{p.name}</span>
                <span className="af-focused-status">{p.status}</span>
                {p.last_activity ? <span className="af-focused-time">{fmtTime(p.last_activity)}</span> : null}
              </a>
            ))}
          </div>
        )}
      </section>

      <section className="af-home-card" data-testid="af-home-todo">
        <div className="af-home-card-head">
          <h3>📋 我的待办</h3>
          <select
            className="af-todo-pri"
            aria-label="待办过滤维度"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">全部（公司）</option>
            {todoProjects.map((pid) => (
              <option key={pid} value={pid}>
                {projectNames.get(pid) ?? pid}
              </option>
            ))}
          </select>
        </div>
        {loading ? (
          <p className="af-home-note">加载中…</p>
        ) : todoItems.length === 0 ? (
          <p className="af-home-note">✅ 无待处理（当前过滤维度）</p>
        ) : (
          <div className="af-todo-list">
            {todoItems.map((a) => (
              <div key={a.id ?? a.artifact_id ?? ''} className="af-todo-row" data-testid={`af-todo-${a.id}`}>
                <span className="af-pri af-pri-p0">审批</span>
                <span className="af-todo-title">
                  {(a.artifact_type ?? a.gate ?? '审批').toUpperCase()} · {projectLabel(a.project_id)}
                </span>
                <span className="af-todo-status">{a.status}</span>
                {a.requested_at ? <span className="af-focused-time">{fmtTime(a.requested_at)}</span> : null}
              </div>
            ))}
          </div>
        )}
        <p className="af-home-note">质量待检 / 成本告警 API 待接入（真实数据后自动出现）</p>
      </section>
    </div>
  );
}
