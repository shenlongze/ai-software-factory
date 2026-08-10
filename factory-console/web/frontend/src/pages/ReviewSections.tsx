/**
 * pages/ReviewSections.tsx — 评审节渲染 (S9-003 共享组件)。
 *
 * - SectionValue: 契约载荷节值智能渲染 (string 文本 / 数组列表 / 对象 JSON,
 *   保留换行; null/undefined/空数组 → 占位)
 * - SectionCard: 单节卡片 (label + value)
 * - WireframePreview: wireframe 节特殊渲染 — ASCII 布局 <pre> 原样预览
 *   (UX/UI Designer Agent S8-002 机器可读结构) + Screen 组件/动作卡片
 * - ProductReview: PRD 6 节 (PRODUCT_SECTIONS)
 * - UXUIReview: UX/UI 7 节 (UXUI_SECTIONS; wireframe 节走预览)
 *
 * 全部纯展示 (零副作用); 缺节 → 跳过, 全部缺失 → EmptyState (宽容失败安全)。
 */
import { isValidElement } from 'react';
import { EmptyState } from '../components/State';
import {
  ARCHITECTURE_SECTIONS,
  PRODUCT_SECTIONS,
  UXUI_SECTIONS,
} from '../models/types';
import type { ArtifactDetail } from '../models/types';
import { parseWireframeScreens } from '../utils/wireframe';

/** 单节值渲染 (字符串/标量/数组/对象/React 元素; JSON 保留结构)。 */
export function SectionValue({ value }: { value: unknown }): JSX.Element {
  // 调用方传入预渲染 JSX (如 UXUIReview wireframe 预览) → 直接渲染,
  // 不做 JSON 序列化 (React 元素含 fiber 引用, stringify 会循环引用崩溃)
  if (isValidElement(value)) {
    return <>{value}</>;
  }
  if (value === null || value === undefined) {
    return <span className="muted">—</span>;
  }
  if (typeof value === 'string') {
    return <p className="section-text">{value}</p>;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return <p className="section-text">{String(value)}</p>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="muted">—</span>;
    if (value.every((x) => typeof x === 'string' || typeof x === 'number')) {
      return (
        <ul className="section-list">
          {value.map((x, i) => (
            <li key={i}>{String(x)}</li>
          ))}
        </ul>
      );
    }
    return <pre className="section-json">{JSON.stringify(value, null, 2)}</pre>;
  }
  if (typeof value === 'object') {
    return <pre className="section-json">{JSON.stringify(value, null, 2)}</pre>;
  }
  return <p className="section-text">{String(value)}</p>;
}

/** 单节卡片 (label + 值)。 */
export function SectionCard({ title, value }: { title: string; value: unknown }): JSX.Element {
  return (
    <section className="section-card">
      <h4 className="section-title">{title}</h4>
      <SectionValue value={value} />
    </section>
  );
}

/**
 * wireframe 节预览 — ASCII 线框 → 页面预览 (S9-003 核心可视化)。
 * 每屏: 名称 + ASCII 布局 <pre> + 组件清单 (skill-tag) + 交互动作列表。
 * 结构缺失 → 回退通用 JSON 渲染 (宽容失败安全)。
 */
export function WireframePreview({ wireframe }: { wireframe: unknown }): JSX.Element {
  const screens = parseWireframeScreens(wireframe);
  if (screens.length === 0) {
    return <SectionValue value={wireframe} />;
  }
  return (
    <div className="wireframe-grid">
      {screens.map((s, i) => (
        <div className="screen-card" key={s.name || `screen-${i}`}>
          <h5 className="screen-name">{s.name || '未命名屏幕'}</h5>
          {s.ascii ? <pre className="wireframe-pre">{s.ascii}</pre> : null}
          {s.components.length > 0 ? (
            <div className="screen-block">
              <span className="muted">组件:</span>
              <div className="skill-tags">
                {s.components.map((c) => (
                  <span key={c} className="skill-tag">
                    {c}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
          {s.actions.length > 0 ? (
            <div className="screen-block">
              <span className="muted">交互动作:</span>
              <ul className="section-list">
                {s.actions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

/** PRD (product Artifact) 评审 — 6 节渲染 (S9-003 任务规格)。 */
export function ProductReview({ detail }: { detail: ArtifactDetail }): JSX.Element {
  const present = PRODUCT_SECTIONS.filter((s) => s.key in detail.metadata);
  if (present.length === 0) {
    return <EmptyState message="该产物无结构化 PRD metadata" />;
  }
  return (
    <div className="review-sections">
      {present.map((s) => (
        <SectionCard key={s.key} title={s.label} value={detail.metadata[s.key]} />
      ))}
    </div>
  );
}

/** UX/UI Artifact 评审 — 7 节渲染; wireframe 节 → ASCII 预览 (S9-003)。 */
export function UXUIReview({ detail }: { detail: ArtifactDetail }): JSX.Element {
  const present = UXUI_SECTIONS.filter((s) => s.key in detail.metadata);
  if (present.length === 0) {
    return <EmptyState message="该产物无结构化 UX/UI metadata" />;
  }
  return (
    <div className="review-sections">
      {present.map((s) => (
        <SectionCard
          key={s.key}
          title={s.label}
          value={
            s.key === 'wireframe' ? (
              <WireframePreview wireframe={detail.metadata[s.key]} />
            ) : (
              detail.metadata[s.key]
            )
          }
        />
      ))}
    </div>
  );
}

/** 未知类型产物 — 通用 metadata 节渲染 (宽容: 任何契约载荷可审)。 */
export function GenericReview({ detail }: { detail: ArtifactDetail }): JSX.Element {
  const entries = Object.entries(detail.metadata);
  if (entries.length === 0) {
    return <EmptyState message="该产物无结构化 metadata" />;
  }
  return (
    <div className="review-sections">
      {entries.map(([k, v]) => (
        <SectionCard key={k} title={k} value={v} />
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ S10-005 Artifact Center 类型化渲染

/** S10-005: design Artifact (Architect S8-003 输出) — 架构 7 节渲染。 */
export function ArchitectureReview({ detail }: { detail: ArtifactDetail }): JSX.Element {
  const present = ARCHITECTURE_SECTIONS.filter((s) => s.key in detail.metadata);
  if (present.length === 0) {
    return <EmptyState message="该产物无结构化架构 metadata" />;
  }
  return (
    <div className="review-sections">
      {present.map((s) => (
        <SectionCard key={s.key} title={s.label} value={detail.metadata[s.key]} />
      ))}
    </div>
  );
}

/** S10-005: code Artifact — 文件清单 chips + diff <pre> (metadata.changes 缺失
 * → content 兜底, 由 Artifact Center 预先拉取 GET /artifacts/{id}/content)。 */
export function CodeReview({
  detail,
  content,
}: {
  detail: ArtifactDetail;
  /** GET /content 渲染内容 (changes 缺失时兜底; 无 → null)。 */
  content: string | null;
}): JSX.Element {
  const files = Array.isArray(detail.metadata.files)
    ? detail.metadata.files.filter((f): f is string => typeof f === 'string' && f.length > 0)
    : [];
  const changes =
    typeof detail.metadata.changes === 'string' && detail.metadata.changes.length > 0
      ? detail.metadata.changes
      : null;
  const diff = changes ?? content;
  if (files.length === 0 && diff == null) {
    return <EmptyState message="该产物无文件清单与代码变更" />;
  }
  return (
    <div className="review-sections">
      {files.length > 0 ? (
        <section className="section-card">
          <h4 className="section-title">文件清单</h4>
          <div className="skill-tags">
            {files.map((f) => (
              <span key={f} className="skill-tag">
                {f}
              </span>
            ))}
          </div>
        </section>
      ) : null}
      {diff != null ? (
        <section className="section-card">
          <h4 className="section-title">
            代码变更{changes == null && content != null ? ' (content 兜底)' : ''}
          </h4>
          <pre className="section-json ws-ac-diff">{diff}</pre>
        </section>
      ) : null}
    </div>
  );
}

/** S10-005: test Artifact — passed/failed 统计徽章 + bugs 列表。 */
export function TestReview({ detail }: { detail: ArtifactDetail }): JSX.Element {
  const results =
    typeof detail.metadata.results === 'object' && detail.metadata.results !== null
      ? (detail.metadata.results as Record<string, unknown>)
      : {};
  const passed = typeof results.passed === 'number' ? results.passed : null;
  const failed = typeof results.failed === 'number' ? results.failed : null;
  const skipped = typeof results.skipped === 'number' ? results.skipped : null;
  const duration = typeof results.duration_s === 'number' ? results.duration_s : null;
  const command = typeof results.command === 'string' ? results.command : null;
  const bugs = Array.isArray(detail.metadata.bugs) ? detail.metadata.bugs : [];

  if (passed == null && bugs.length === 0) {
    return <EmptyState message="该产物无结构化测试 metadata" />;
  }
  return (
    <div className="review-sections">
      <section className="section-card">
        <h4 className="section-title">测试结果</h4>
        <div className="ws-ac-stats">
          {passed != null ? (
            <span className="ws-ac-stat ok" data-testid="test-passed">
              ✓ 通过 {passed}
            </span>
          ) : null}
          {failed != null ? (
            <span className="ws-ac-stat fail" data-testid="test-failed">
              ✗ 失败 {failed}
            </span>
          ) : null}
          {skipped != null ? <span className="ws-ac-stat muted">跳过 {skipped}</span> : null}
          {duration != null ? <span className="ws-ac-stat muted">耗时 {duration}s</span> : null}
          {command != null ? (
            <code className="ws-ac-stat-command" data-testid="test-command">
              {command}
            </code>
          ) : null}
        </div>
      </section>
      {bugs.length > 0 ? (
        <section className="section-card">
          <h4 className="section-title">缺陷列表</h4>
          <ul className="section-list ws-ac-bugs">
            {bugs.map((bug, i) => (
              <li key={i} className="ws-ac-bug">
                {renderBug(bug)}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

/** bug 条目渲染 (对象带 id/severity/title → 可读行; 否则 JSON 兜底)。 */
function renderBug(bug: unknown): string {
  if (typeof bug !== 'object' || bug === null) return String(bug);
  const item = bug as Record<string, unknown>;
  const id = typeof item.id === 'string' ? item.id : null;
  const severity = typeof item.severity === 'string' ? item.severity : null;
  const title = typeof item.title === 'string' ? item.title : null;
  if (id != null || title != null) {
    return [id, severity, title].filter((part) => part != null && part.length > 0).join(' · ');
  }
  return JSON.stringify(bug);
}

/** S10-005: release Artifact — 版本 + 构建状态 + 包文件 + 下载链接 + 部署。 */
export function ReleaseReview({ detail }: { detail: ArtifactDetail }): JSX.Element {
  const m = detail.metadata;
  const version = typeof m.version === 'string' ? m.version : null;
  const buildResult =
    typeof m.build_result === 'object' && m.build_result !== null
      ? (m.build_result as Record<string, unknown>)
      : null;
  const pkg =
    typeof m.package === 'object' && m.package !== null ? (m.package as Record<string, unknown>) : null;
  const pkgFiles = Array.isArray(pkg?.files)
    ? pkg.files.filter((f): f is string => typeof f === 'string' && f.length > 0)
    : [];
  const hasAny = version != null || buildResult != null || pkg != null || 'deployment' in m;

  if (!hasAny) {
    return <EmptyState message="该产物无结构化 Release metadata" />;
  }
  return (
    <div className="review-sections">
      {version != null ? (
        <section className="section-card" data-testid="release-version">
          <h4 className="section-title">版本</h4>
          <p className="section-text">{version}</p>
        </section>
      ) : null}
      {buildResult != null ? (
        <SectionCard title="构建结果" value={buildResult} />
      ) : null}
      {pkg != null ? (
        <section className="section-card">
          <h4 className="section-title">安装包</h4>
          <p className="section-text">
            {typeof pkg.name === 'string' ? pkg.name : ''}
            {typeof pkg.type === 'string' ? ` (${pkg.type})` : ''}
          </p>
          {pkgFiles.length > 0 ? (
            <div className="skill-tags">
              {pkgFiles.map((f) => (
                <span key={f} className="skill-tag">
                  {f}
                </span>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}
      <section className="section-card" data-testid="release-download">
        <h4 className="section-title">下载</h4>
        <p className="section-text">
          <a
            className="ws-ac-download"
            href={`/api/artifacts/${encodeURIComponent(detail.id)}/content`}
            download
          >
            ⬇ 下载产物{version != null ? ` v${version}` : ''}
          </a>
          {detail.location ? <span className="muted"> ({detail.location})</span> : null}
        </p>
      </section>
      {'release_notes' in m ? <SectionCard title="发布说明" value={m.release_notes} /> : null}
      {'deployment' in m ? <SectionCard title="部署信息" value={m.deployment} /> : null}
    </div>
  );
}
