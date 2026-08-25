/**
 * pages/workspace/AfProjectManage.tsx — 项目管理页 (WebUI #2, Founder 2026-08-26)。
 *
 * 全部项目表格视图 + 批量操作 (收藏/取消收藏/改名/删除)。
 * 入口: 左栏"全部"区 ⚙ 管理 → #/workspace/manage
 * 数据: GET /api/projects; 操作: PATCH {starred/name} / DELETE。
 */

import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api/client';
import type { ProjectSummary } from '../../models/types';

export function AfProjectManage(): JSX.Element {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState<boolean>(true);
  const [msg, setMsg] = useState<string>('');

  const load = () => {
    setLoading(true);
    api
      .projects()
      .then((list) => setProjects(list))
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const refresh = () => {
    setSelected(new Set());
    load();
  };

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const star = (id: string, value: boolean) => {
    api.updateProject(id, { starred: value }).then(refresh).catch((e) => setMsg(`收藏失败: ${e}`));
  };

  const batchStar = (value: boolean) => {
    Promise.all([...selected].map((id) => api.updateProject(id, { starred: value })))
      .then(() => {
        setMsg(`已${value ? '收藏' : '取消收藏'} ${selected.size} 个项目`);
        refresh();
      })
      .catch((e) => setMsg(`批量收藏失败: ${e}`));
  };

  const rename = (id: string, current: string) => {
    // eslint-disable-next-line no-alert
    const name = window.prompt('新名称:', current);
    if (!name || !name.trim()) return;
    api.updateProject(id, { name: name.trim() }).then(refresh).catch((e) => setMsg(`改名失败: ${e}`));
  };

  const remove = (id: string, name: string) => {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`确认删除项目「${name}」? (不可恢复)`)) return;
    api.deleteProject(id).then(refresh).catch((e) => setMsg(`删除失败: ${e}`));
  };

  const batchRemove = () => {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`确认删除选中的 ${selected.size} 个项目? (不可恢复)`)) return;
    Promise.all([...selected].map((id) => api.deleteProject(id)))
      .then(() => {
        setMsg(`已删除 ${selected.size} 个项目`);
        refresh();
      })
      .catch((e) => setMsg(`批量删除失败: ${e}`));
  };

  const sorted = useMemo(
    () => [...projects].sort((a, b) => String(b.last_activity ?? '').localeCompare(String(a.last_activity ?? ''))),
    [projects],
  );

  return (
    <div className="af-manage" data-testid="af-project-manage">
      <div className="af-manage-head">
        <h2 className="af-detail-name">项目管理</h2>
        <button type="button" className="af-preview-btn" onClick={refresh} aria-label="刷新项目列表">
          ⟳ 刷新
        </button>
      </div>
      {msg ? <p className="af-composer-msg">{msg}</p> : null}
      {selected.size > 0 ? (
        <div className="af-manage-batch" data-testid="af-manage-batch">
          <span>已选 {selected.size} 项</span>
          <button type="button" className="af-preview-btn" onClick={() => batchStar(true)}>
            ⭐ 批量收藏
          </button>
          <button type="button" className="af-preview-btn" onClick={() => batchStar(false)}>
            取消收藏
          </button>
          <button type="button" className="af-preview-btn af-danger" onClick={batchRemove}>
            批量删除
          </button>
        </div>
      ) : null}
      {loading ? (
        <p className="af-home-note">加载中…</p>
      ) : (
        <table className="af-manage-table" data-testid="af-manage-table">
          <thead>
            <tr>
              <th aria-label="选择" />
              <th>名称</th>
              <th>状态</th>
              <th>生命周期</th>
              <th>收藏</th>
              <th>最近活动</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((p) => (
              <tr key={p.id} data-testid={`af-manage-row-${p.id}`}>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`选择 ${p.name}`}
                    checked={selected.has(p.id)}
                    onChange={() => toggleSelect(p.id)}
                  />
                </td>
                <td>
                  <a className="af-manage-name" href={`#/project/${p.id}`}>
                    {p.name}
                  </a>
                </td>
                <td>{p.status}</td>
                <td>{p.lifecycle_stage ?? p.lifecycle_status ?? '—'}</td>
                <td>
                  <button
                    type="button"
                    className={`af-star-btn${p.starred ? ' active' : ''}`}
                    onClick={() => star(p.id, !p.starred)}
                    aria-label={p.starred ? `取消收藏 ${p.name}` : `收藏 ${p.name}`}
                  >
                    {p.starred ? '★' : '☆'}
                  </button>
                </td>
                <td className="af-manage-time">{p.last_activity ? p.last_activity.slice(0, 16).replace('T', ' ') : '—'}</td>
                <td>
                  <div className="af-manage-ops">
                    <button type="button" className="af-preview-btn" onClick={() => rename(p.id, p.name)}>
                      改名
                    </button>
                    <button
                      type="button"
                      className="af-preview-btn af-danger"
                      onClick={() => remove(p.id, p.name)}
                    >
                      删除
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
