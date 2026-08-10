/**
 * shell/ArtifactCenter.tsx — S10-005 Artifact Center (右侧 Factory Panel Artifact Tab)。
 *
 * 数据源 (复用 S10-002 Runtime API 统一入口, 零重设计):
 * - runtimeClient.listArtifacts(projectId, type?) → 清单 (类型过滤走服务端
 *   type 参数; 无后端 → mock fallback, is_mock → "演示数据" 徽章)
 * - runtimeClient.getArtifactDetail(artifactId) → Detail Viewer metadata
 *   契约载荷 (org CONTRACTS 同源)
 * - runtimeClient.getArtifactContent(artifactId) → Code diff 兜底 /
 *   Release 下载源 (GET /api/artifacts/{id}/content, 后端 S10-005 已完成)
 *
 * 视图:
 * - List: 6 类产物行 (name/类型/阶段/状态徽章/版本/创建时间) + 类型过滤
 * - Detail Viewer 类型化渲染 (复用 S9-003 ReviewSections + parseWireframeScreens):
 *   product → ProductReview (6 节) / ux_ui → UXUIReview (wireframe →
 *   Screen Card) / design → ArchitectureReview / code → CodeReview (文件 +
 *   diff, changes 缺失 → content 兜底) / test → TestReview (passed/failed +
 *   bugs) / release → ReleaseReview (版本/下载链接/部署) / 未知 → GenericReview
 *   JSON 兜底
 * - Timeline 联动: focusArtifactId + focusNonce (nonce 递增防重) → 打开
 *   对应产物详情 + "已从 Timeline 打开产物 X" 提示; 处理后 onFocusConsumed
 *   清 Shell state (与 S10-004 RuntimePanel 同模式)
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { runtimeClient } from '../api/runtimeClient';
import { Button, StatusBadge } from '../components/ds';
import { useAsync } from '../hooks/useAsync';
import { artifactStatusLabel, artifactTypeLabel } from '../models/types';
import type { ArtifactDetail, ArtifactSummary } from '../models/types';
import {
  ArchitectureReview,
  CodeReview,
  GenericReview,
  ProductReview,
  ReleaseReview,
  TestReview,
  UXUIReview,
} from '../pages/ReviewSections';

/** 类型过滤选项 (空 = 全部; 与服务端 type 参数同值)。 */
export const ARTIFACT_FILTER_TYPES = [
  '',
  'product',
  'ux_ui',
  'design',
  'code',
  'test',
  'release',
] as const;

/** created_at → MM-DD HH:MM 显示 (非法/缺失 → —)。 */
export function formatArtifactTime(createdAt: string | null): string {
  if (createdAt == null) return '—';
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) return '—';
  const day = date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
  const time = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  return `${day} ${time}`;
}

/** 产物类型 → Detail Viewer 内容分派 (product/ux_ui/design/code/test/release
 * 类型化; 未知 → GenericReview JSON 兜底, 宽容失败安全)。 */
export function artifactBody(detail: ArtifactDetail, content: string | null): JSX.Element {
  const type = detail.type.toLowerCase();
  switch (type) {
    case 'product':
    case 'prd':
      return <ProductReview detail={detail} />;
    case 'ux_ui':
      return <UXUIReview detail={detail} />;
    case 'design':
      return <ArchitectureReview detail={detail} />;
    case 'code':
      return <CodeReview detail={detail} content={content} />;
    case 'test':
      return <TestReview detail={detail} />;
    case 'release':
      return <ReleaseReview detail={detail} />;
    default:
      return <GenericReview detail={detail} />;
  }
}

// ------------------------------------------------------------------ List

function ArtifactRow({
  artifact,
  onOpen,
}: {
  artifact: ArtifactSummary;
  onOpen: (artifactId: string) => void;
}): JSX.Element {
  return (
    <button
      type="button"
      className="ws-ac-row"
      data-testid={`artifact-row-${artifact.id}`}
      onClick={() => onOpen(artifact.id)}
    >
      <span className="ws-ac-row-top">
        <span className="ws-ac-row-ref">{artifact.ref || artifact.id}</span>
        <span className="ws-ac-row-type">{artifactTypeLabel(artifact.type)}</span>
      </span>
      <span className="ws-ac-row-meta">
        <StatusBadge status={artifact.status} label={artifactStatusLabel(artifact.status)} />
        <span className="ws-ac-row-stage">{artifact.stage_id}</span>
        <span className="ws-ac-row-version">v{artifact.version ?? '?'}</span>
        <span className="ws-ac-row-time">{formatArtifactTime(artifact.created_at)}</span>
      </span>
    </button>
  );
}

function ArtifactList({
  artifacts,
  isMock,
  type,
  onTypeChange,
  onOpen,
}: {
  artifacts: ArtifactSummary[];
  isMock: boolean;
  type: string;
  onTypeChange: (type: string) => void;
  onOpen: (artifactId: string) => void;
}): JSX.Element {
  return (
    <div className="ws-ac-list" data-testid="artifact-center-list">
      <div className="ws-ac-toolbar">
        <label className="ws-ac-filter">
          类型
          <select
            value={type}
            onChange={(e) => onTypeChange(e.target.value)}
            data-testid="artifact-type-filter"
            aria-label="按类型过滤产物"
          >
            {ARTIFACT_FILTER_TYPES.map((t) => (
              <option key={t} value={t}>
                {t || '全部'}
              </option>
            ))}
          </select>
        </label>
        {isMock ? (
          <span className="ws-ac-mock" data-testid="artifact-center-mock">
            演示数据
          </span>
        ) : null}
      </div>
      {artifacts.length === 0 ? (
        <div className="ws-ac-empty" data-testid="artifact-center-empty">
          暂无产物 — 等待 AI 生成
        </div>
      ) : (
        <div className="ws-ac-rows">
          {artifacts.map((a) => (
            <ArtifactRow key={a.id} artifact={a} onOpen={onOpen} />
          ))}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ Detail Viewer

function ArtifactDetailView({
  artifactId,
  onBack,
}: {
  artifactId: string;
  onBack: () => void;
}): JSX.Element {
  const { data, error, loading } = useAsync(
    useCallback(() => runtimeClient.getArtifactDetail(artifactId), [artifactId]),
    [artifactId],
  );
  const detail: ArtifactDetail | null = data?.data ?? null;
  const isMock = data?.is_mock ?? false;

  // Code 类型: metadata.changes 缺失 → GET /content 兜底渲染 diff
  const needsContent =
    detail != null && detail.type.toLowerCase() === 'code' && !('changes' in detail.metadata);
  const { data: contentData } = useAsync(
    useCallback(
      () =>
        needsContent && detail != null
          ? runtimeClient.getArtifactContent(detail.id)
          : Promise.resolve(null),
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [needsContent, detail?.id],
    ),
    [needsContent, detail?.id],
  );
  const content: string | null =
    contentData != null && typeof contentData.data?.content === 'string'
      ? contentData.data.content
      : null;

  if (loading) {
    return (
      <div className="ws-ac-state" data-testid="artifact-detail-loading">
        加载产物详情…
      </div>
    );
  }
  if (error) {
    return (
      <div className="ws-ac-state ws-ac-error" data-testid="artifact-detail-error">
        产物详情加载失败: {error}
        <Button variant="secondary" size="sm" onClick={onBack}>
          返回列表
        </Button>
      </div>
    );
  }
  if (detail == null) {
    return (
      <div className="ws-ac-state" data-testid="artifact-detail-error">
        产物详情为空
      </div>
    );
  }

  return (
    <div className="ws-ac-detail" data-testid="artifact-detail">
      <header className="ws-ac-detail-head">
        <Button variant="ghost" size="sm" onClick={onBack} data-testid="artifact-detail-back">
          ← 返回列表
        </Button>
        <h4 className="ws-ac-detail-title">
          {artifactTypeLabel(detail.type)}
          <span className="ws-ac-detail-id"> {detail.id}</span>
        </h4>
        <div className="ws-ac-detail-meta">
          <StatusBadge status={detail.status} label={artifactStatusLabel(detail.status)} />
          <span className="ws-ac-detail-meta-item">v{detail.version ?? '?'}</span>
          <span className="ws-ac-detail-meta-item">产出: {detail.producer_role}</span>
          <span className="ws-ac-detail-meta-item">阶段: {detail.stage_id}</span>
        </div>
        {isMock ? (
          <span className="ws-ac-mock" data-testid="artifact-detail-mock">
            演示数据
          </span>
        ) : null}
      </header>
      <div className="ws-ac-detail-body">{artifactBody(detail, content)}</div>
    </div>
  );
}

// ------------------------------------------------------------------ 主组件

export function ArtifactCenter({
  projectId,
  focusArtifactId,
  focusNonce,
  onFocusConsumed,
}: {
  projectId: string;
  /** S10-005 Timeline 联动 — 待定位 artifact_id (透传, 同 RuntimePanel 模式)。 */
  focusArtifactId?: string | null;
  focusNonce?: number | null;
  onFocusConsumed?: () => void;
}): JSX.Element {
  const [type, setType] = useState('');
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [focusNotice, setFocusNotice] = useState<string | null>(null);
  const handledNonceRef = useRef<number | null>(null);

  const { data, error, loading } = useAsync(
    useCallback(() => runtimeClient.listArtifacts(projectId, type || undefined), [projectId, type]),
    [projectId, type],
  );
  const artifacts = data?.data ?? [];
  const isMock = data?.is_mock ?? false;

  // Timeline 联动: focus nonce 递增 → 同一 artifact 二次点击仍触发;
  // handledNonceRef 防重复消费 (onFocusConsumed 只调一次)
  useEffect(() => {
    if (focusArtifactId == null || focusNonce == null) return;
    if (handledNonceRef.current === focusNonce) return;
    handledNonceRef.current = focusNonce;
    setFocusedId(focusArtifactId);
    setFocusNotice(`已从 Timeline 打开产物 ${focusArtifactId}`);
    onFocusConsumed?.();
  }, [focusArtifactId, focusNonce, onFocusConsumed]);

  const openDetail = (artifactId: string): void => {
    setFocusedId(artifactId);
    setFocusNotice(null);
  };
  const closeDetail = (): void => {
    setFocusedId(null);
    setFocusNotice(null);
  };

  return (
    <div className="ws-ac" data-testid="artifact-center">
      <div className="ws-ac-head">
        <h3 className="ws-ac-title">产物中心</h3>
        {focusedId == null && isMock ? (
          <span className="ws-ac-mock" data-testid="artifact-center-mock">
            演示数据
          </span>
        ) : null}
      </div>
      {focusNotice != null ? (
        <p className="ws-ac-notice" data-testid="artifact-focus-notice">
          {focusNotice}
        </p>
      ) : null}
      {focusedId != null ? (
        <ArtifactDetailView artifactId={focusedId} onBack={closeDetail} />
      ) : loading ? (
        <div className="ws-ac-state" data-testid="artifact-center-loading">
          加载产物…
        </div>
      ) : error ? (
        <div className="ws-ac-state ws-ac-error" data-testid="artifact-center-error">
          产物加载失败: {error}
        </div>
      ) : (
        <ArtifactList
          artifacts={artifacts}
          isMock={isMock}
          type={type}
          onTypeChange={setType}
          onOpen={openDetail}
        />
      )}
    </div>
  );
}
