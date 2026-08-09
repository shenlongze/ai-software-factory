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
import { PRODUCT_SECTIONS, UXUI_SECTIONS } from '../models/types';
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
