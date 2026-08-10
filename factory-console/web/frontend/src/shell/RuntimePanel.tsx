/**
 * shell/RuntimePanel.tsx — S10-004 Runtime Workspace Panel (Factory Panel Runtime Tab)。
 *
 * 设计对齐 workspace-architecture.md §4 (Instance 模式, 非固定 Browser Tab):
 * - Instances 列表: 卡片 (类型图标 browser|terminal / 状态徽章 starting|running|
 *   stopped|error / 绑定 Artifact / 创建时间)
 * - [+] 按钮 → Create Runtime Modal (Browser Runtime | Terminal Runtime → POST 创建)
 * - Browser Instance: iframe 沙箱预览 (url) + 工具栏 (刷新/截图/打开新窗口)
 * - Terminal Instance: 终端样式 (等宽/滚动) + mock stream (npm test/build 模拟,
 *   标注 "演示" — 真实 Agent 执行日志后续接入)
 * - 空态 "还没有 Runtime — 点击 + 创建"
 * - REST 轮询 (2s, RUNTIME_POLL_MS) 刷新实例状态 — 不依赖 SSE runtime.* 事件
 *   (Core 事件枚举冻结无 org.runtime.* 成员 → 事件不落库, 诚实走轮询; 面板
 *   不订阅 SSE)
 * - Screenshot 预留: POST /runtimes/{id}/screenshot → "已保存截图 artifact"
 *   (只落记录, 完整 Feedback Loop 后续实现)
 * - Timeline 联动: focusArtifactId/focusNonce → 定位绑定实例或提示创建
 * - mock fallback (listRuntimes 无后端) → "演示数据" 徽章 (诚实标注)
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { RUNTIME_POLL_MS, runtimeClient } from '../api/runtimeClient';
import { Button, Modal, StatusBadge } from '../components/ds';
import { RUNTIME_STATUS_LABELS, runtimeTypeLabel } from '../models/types';
import type { RuntimeInstance } from '../models/types';

/** Runtime 卡片创建时间 → "MM-DD HH:MM" (非法/缺失 → —)。 */
export function formatRuntimeTime(createdAt: string | null): string {
  if (createdAt == null) return '—';
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) return '—';
  const pad = (n: number): string => String(n).padStart(2, '0');
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** Terminal mock stream 日志行 (演示 — 真实 Agent 执行日志流后续接入)。 */
export const TERMINAL_MOCK_LINES: readonly string[] = [
  '$ npm test',
  '> factory-console@0.1.0 test',
  '✓ 213 tests passed (20 files)',
  '✓ Runtime Panel: 25 tests passed',
  '$ npm run build',
  '✓ built in 3.2s (vite)',
];

/** Terminal 实例: 终端样式 mock 流 (等宽/滚动 + 演示标注)。 */
export function TerminalMockStream({ instanceId }: { instanceId: string }): JSX.Element {
  return (
    <div className="ws-rt-terminal" data-testid={`runtime-terminal-${instanceId}`}>
      <pre className="ws-rt-terminal-body">
        {TERMINAL_MOCK_LINES.join('\n')}
        {'\n'}（演示数据 — 真实 Agent 执行日志将在后续接入）
      </pre>
    </div>
  );
}

export function RuntimePanel({
  projectId,
  focusArtifactId,
  focusNonce,
  onFocusConsumed,
}: {
  projectId: string;
  /** Timeline artifact 联动: 待定位的 artifact_id (null = 无请求)。 */
  focusArtifactId?: string | null;
  /** 联动请求序号 (每次点击 +1; 与 focusArtifactId 配对触发 effect)。 */
  focusNonce?: number | null;
  /** 联动已处理回调 (WorkspaceShell 清除 focus, 避免重复提示)。 */
  onFocusConsumed?: () => void;
}): JSX.Element {
  const [instances, setInstances] = useState<RuntimeInstance[]>([]);
  const [isMock, setIsMock] = useState(false);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [loadError, setLoadError] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [creating, setCreating] = useState<'browser' | 'terminal' | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [focusNotice, setFocusNotice] = useState<string | null>(null);
  const [highlightedId, setHighlightedId] = useState<string | null>(null);
  const [iframeKeys, setIframeKeys] = useState<Record<string, number>>({});
  const handledNonceRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const { data, is_mock: mock } = await runtimeClient.listRuntimes(projectId);
      setInstances(data);
      setIsMock(mock);
      setLoadState('ready');
      setLoadError('');
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
      setLoadState('error');
    }
  }, [projectId]);

  // REST 轮询 (2s) — 不依赖 SSE runtime.* (Core 事件枚举冻结, 诚实走轮询)
  useEffect(() => {
    let cancelled = false;
    const poll = async (): Promise<void> => {
      try {
        const { data, is_mock: mock } = await runtimeClient.listRuntimes(projectId);
        if (cancelled) return;
        setInstances(data);
        setIsMock(mock);
        setLoadState('ready');
        setLoadError('');
      } catch (err) {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : String(err));
        setLoadState('error');
      }
    };
    poll();
    const timer = setInterval(poll, RUNTIME_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [projectId]);

  // Timeline artifact 联动 (定位绑定实例 / 提示创建)
  useEffect(() => {
    if (focusArtifactId == null || focusNonce == null) return;
    if (handledNonceRef.current === focusNonce) return;
    handledNonceRef.current = focusNonce;
    const found = instances.find((inst) => inst.artifact_id === focusArtifactId);
    setHighlightedId(found?.id ?? null);
    setFocusNotice(
      found != null
        ? `已从 Timeline 打开产物 ${focusArtifactId} 的 Runtime (${runtimeTypeLabel(found.type)})`
        : `产物 ${focusArtifactId} 暂无 Runtime — 点击 + 创建`,
    );
    onFocusConsumed?.();
  }, [focusArtifactId, focusNonce, instances, onFocusConsumed]);

  const handleCreate = async (type: 'browser' | 'terminal'): Promise<void> => {
    setCreating(type);
    setCreateError(null);
    try {
      await runtimeClient.createRuntime(projectId, type);
      setModalOpen(false);
      await load(); // 创建后立即刷新列表
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreating(null);
    }
  };

  const handleScreenshot = async (instance: RuntimeInstance): Promise<void> => {
    setNotice(null);
    try {
      const shot = await runtimeClient.screenshotRuntime(instance.id);
      setNotice({
        kind: 'ok',
        text: `已保存截图 artifact ${shot.artifact_id ?? shot.id} (${instance.id})`,
      });
    } catch (err) {
      setNotice({
        kind: 'error',
        text: `截图失败: ${err instanceof Error ? err.message : String(err)}`,
      });
    }
  };

  const refreshIframe = (instanceId: string): void => {
    setIframeKeys((prev) => ({ ...prev, [instanceId]: (prev[instanceId] ?? 0) + 1 }));
  };

  const openNewWindow = (instance: RuntimeInstance): void => {
    if (instance.url == null) return;
    window.open(instance.url, '_blank', 'noopener');
  };

  return (
    <div className="ws-rt" data-testid="runtime-panel">
      <div className="ws-rt-head">
        <h2 className="ws-rt-title">Runtime</h2>
        {isMock ? (
          <span className="ws-rt-mock" data-testid="runtime-panel-mock">
            演示数据
          </span>
        ) : null}
        <Button
          size="sm"
          variant="primary"
          className="ws-rt-create-btn"
          data-testid="runtime-create-open"
          aria-label="创建 Runtime"
          onClick={() => setModalOpen(true)}
        >
          +
        </Button>
      </div>

      {focusNotice != null ? (
        <p className="ws-rt-notice" data-testid="runtime-focus-notice">
          {focusNotice}
        </p>
      ) : null}
      {notice != null ? (
        <p
          className={`ws-rt-notice${notice.kind === 'error' ? ' is-error' : ''}`}
          data-testid="runtime-notice"
        >
          {notice.text}
        </p>
      ) : null}

      <div className="ws-rt-list" data-testid="runtime-instances">
        {loadState === 'loading' ? (
          <div className="ws-rt-empty" data-testid="runtime-loading">
            <span className="ws-rt-empty-icon" aria-hidden="true">
              ⏳
            </span>
            加载 Runtime…
          </div>
        ) : null}

        {loadState === 'error' ? (
          <div className="ws-rt-empty" data-testid="runtime-error-state">
            <span className="ws-rt-empty-icon" aria-hidden="true">
              ⛔
            </span>
            <p className="ws-rt-error-text">Runtime 列表加载失败: {loadError}</p>
          </div>
        ) : null}

        {loadState === 'ready' && instances.length === 0 ? (
          <div className="ws-rt-empty" data-testid="runtime-panel-empty">
            <span className="ws-rt-empty-icon" aria-hidden="true">
              🚀
            </span>
            <p className="ws-rt-empty-title">还没有 Runtime — 点击 + 创建</p>
            <p className="ws-rt-empty-hint">Browser 预览 AI 产物 / Terminal 查看执行日志</p>
          </div>
        ) : null}

        {loadState === 'ready' && instances.length > 0
          ? instances.map((instance) => (
              <article
                key={instance.id}
                className={`ws-rt-card${highlightedId === instance.id ? ' is-highlighted' : ''}`}
                data-testid={`runtime-card-${instance.id}`}
                data-runtime-type={instance.type}
                data-status={instance.status}
              >
                <header className="ws-rt-card-head">
                  <span className="ws-rt-card-icon" aria-hidden="true">
                    {instance.type === 'browser' ? '🌐' : '💻'}
                  </span>
                  <span className="ws-rt-card-type">{runtimeTypeLabel(instance.type)}</span>
                  <StatusBadge status={instance.status} label={RUNTIME_STATUS_LABELS[instance.status]} />
                  {highlightedId === instance.id ? (
                    <span className="ws-rt-highlight" data-testid="runtime-highlight">
                      已定位
                    </span>
                  ) : null}
                </header>
                <dl className="ws-rt-card-meta">
                  <div className="ws-rt-card-meta-row">
                    <dt>实例</dt>
                    <dd className="ws-rt-mono">{instance.id}</dd>
                  </div>
                  <div className="ws-rt-card-meta-row">
                    <dt>绑定 Artifact</dt>
                    <dd>{instance.artifact_id ?? '未绑定'}</dd>
                  </div>
                  <div className="ws-rt-card-meta-row">
                    <dt>创建时间</dt>
                    <dd>{formatRuntimeTime(instance.created_at)}</dd>
                  </div>
                </dl>

                {instance.type === 'browser' ? (
                  <div className="ws-rt-browser">
                    <div className="ws-rt-toolbar" data-testid={`runtime-toolbar-${instance.id}`}>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => refreshIframe(instance.id)}
                      >
                        刷新
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => {
                          void handleScreenshot(instance);
                        }}
                      >
                        截图
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => openNewWindow(instance)}>
                        新窗口
                      </Button>
                    </div>
                    {instance.url != null ? (
                      <iframe
                        key={iframeKeys[instance.id] ?? 0}
                        className="ws-rt-iframe"
                        data-testid={`runtime-iframe-${instance.id}`}
                        src={instance.url}
                        sandbox="allow-scripts allow-same-origin"
                        title={`${runtimeTypeLabel(instance.type)} ${instance.id} 沙箱预览`}
                      />
                    ) : (
                      <p className="ws-rt-unready" data-testid={`runtime-unready-${instance.id}`}>
                        预览地址未就绪
                      </p>
                    )}
                  </div>
                ) : (
                  <TerminalMockStream instanceId={instance.id} />
                )}
              </article>
            ))
          : null}
      </div>

      <Modal open={modalOpen} title="创建 Runtime" onClose={() => setModalOpen(false)}>
        <div className="ws-rt-create">
          <p className="ws-rt-create-desc">选择 Runtime 类型 — 创建后实例出现在下方列表。</p>
          <div className="ws-rt-create-options">
            <button
              type="button"
              className="ws-rt-create-option"
              data-testid="create-browser"
              disabled={creating != null}
              onClick={() => {
                void handleCreate('browser');
              }}
            >
              <span className="ws-rt-create-icon" aria-hidden="true">
                🌐
              </span>
              <span className="ws-rt-create-name">Browser Runtime</span>
              <span className="ws-rt-option-desc">沙箱 iframe 预览 AI 产物 (绑定 Artifact)</span>
            </button>
            <button
              type="button"
              className="ws-rt-create-option"
              data-testid="create-terminal"
              disabled={creating != null}
              onClick={() => {
                void handleCreate('terminal');
              }}
            >
              <span className="ws-rt-create-icon" aria-hidden="true">
                💻
              </span>
              <span className="ws-rt-create-name">Terminal Runtime</span>
              <span className="ws-rt-option-desc">终端样式执行日志 (mock 流, 演示)</span>
            </button>
          </div>
          {creating != null ? (
            <p className="ws-rt-create-status" data-testid="runtime-creating">
              创建 {runtimeTypeLabel(creating)}…
            </p>
          ) : null}
          {createError != null ? (
            <p className="ws-rt-create-error" data-testid="runtime-create-error">
              创建失败: {createError}
            </p>
          ) : null}
        </div>
      </Modal>
    </div>
  );
}
