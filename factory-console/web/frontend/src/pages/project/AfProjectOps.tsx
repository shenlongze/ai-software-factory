/**
 * pages/project/AfProjectOps.tsx — 项目运维/监控页 (D 系列, v1.1.134)。
 *
 * 统一 Monitor 数据源: 系统状态 (前端/后端端口+版本+模型) + 项目监控
 * (阶段/质量/任务/产出物/文档/运行实例/失败/最近活动) + 快照趋势。
 * 数据: GET /api/monitor (系统+全部项目+快照, 过滤当前项目)。
 */

import { useEffect, useState } from 'react';
import { api } from '../../api/client';

interface MonitorProject {
  project_id: string;
  name: string;
  lifecycle: string;
  runtimes: number;
  failed: number;
  quality: number | null;
  tasks: Record<string, number>;
  artifacts_version: number;
  docs: number;
  last_activity: string | null;
  collected_at: string;
}
interface Snapshot {
  at: string;
  system?: { version?: string };
  projects?: MonitorProject[];
}

export function AfProjectOps({ projectId, projectName }: { projectId: string; projectName?: string }): JSX.Element {
  const [data, setData] = useState<{ system?: { version: string; frontend: { up: boolean }; backend: { up: boolean }; model: string }; project?: MonitorProject; snapshots?: Snapshot[] } | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    api
      .monitor()
      .then((m) => {
        if (cancelled) return;
        const project = (m.projects ?? []).find((p) => p.project_id === projectId);
        setData({ system: m.system, project, snapshots: m.snapshots ?? [] });
      })
      .catch(() => {
        if (!cancelled) setError('监控数据加载失败（后端不可达）');
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const fmt = (iso: string | null | undefined) => (iso ? iso.slice(5, 16).replace('T', ' ') : '—');
  const taskTotal = Object.values(data?.project?.tasks ?? {}).reduce((a, b) => a + b, 0);

  return (
    <div className="af-ops" data-testid="af-ops">
      <h2 className="af-detail-name">🛰 运维 · {projectName ?? projectId}</h2>
      {error ? <p className="af-home-note">{error}</p> : null}

      <section className="af-home-card" data-testid="af-ops-system">
        <h3>⚡ 系统状态</h3>
        <div className="af-health-row">
          <span className="af-health-chip">v{data?.system?.version ?? '—'}</span>
          <span className="af-health-chip">
            🌐 前端 5180: {data?.system?.frontend?.up ? '运行中' : '未运行'}
          </span>
          <span className="af-health-chip">
            ⚙️ 后端 8011: {data?.system?.backend?.up ? '运行中' : '未运行'}
          </span>
          <span className="af-health-chip">🤖 {data?.system?.model || '模型 —'}</span>
        </div>
      </section>

      <section className="af-home-card" data-testid="af-ops-project">
        <h3>📦 项目监控（{projectName ?? projectId}）</h3>
        {data?.project ? (
          <table className="af-manage-table">
            <tbody>
              <tr><td>生命周期</td><td>{data.project.lifecycle || '—'}</td></tr>
              <tr><td>质量分</td><td>{data.project.quality != null ? data.project.quality.toFixed(2) : '未生成'}</td></tr>
              <tr><td>运行实例 / 失败</td><td>{data.project.runtimes} / {data.project.failed}</td></tr>
              <tr><td>任务</td><td>{taskTotal} 个（{Object.entries(data.project.tasks).map(([k, v]) => `${k}:${v}`).join(' · ') || '—'}）</td></tr>
              <tr><td>产出物版本</td><td>v{data.project.artifacts_version}</td></tr>
              <tr><td>文档</td><td>{data.project.docs} 份</td></tr>
              <tr><td>最近活动</td><td>{fmt(data.project.last_activity)}</td></tr>
              <tr><td>采集时间</td><td>{fmt(data.project.collected_at)}</td></tr>
            </tbody>
          </table>
        ) : (
          <p className="af-home-note">（暂无监控数据）</p>
        )}
      </section>

      <section className="af-home-card" data-testid="af-ops-trend">
        <h3>📈 最近快照（趋势）</h3>
        {data?.snapshots && data.snapshots.length > 0 ? (
          <table className="af-manage-table">
            <thead>
              <tr><th>时间</th><th>版本</th><th>项目数</th></tr>
            </thead>
            <tbody>
              {data.snapshots.slice(-8).reverse().map((s, i) => (
                <tr key={i}>
                  <td>{fmt(s.at)}</td>
                  <td>{s.system?.version ?? '—'}</td>
                  <td>{s.projects?.length ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="af-home-note">（暂无快照 — 打开监控后自动累积）</p>
        )}
      </section>
    </div>
  );
}
