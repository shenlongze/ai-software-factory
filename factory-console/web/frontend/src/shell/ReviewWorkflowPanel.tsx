/**
 * shell/ReviewWorkflowPanel.tsx — S10-006 Review Workflow (Factory Panel Review Tab)。
 *
 * 三栏审核工作台:
 * - Queue (左): 项目待审门清单 (Product/UXUI/Architecture/Release — pending
 *   approval gates) + 关联产物摘要 + 状态; 空态 "没有待审核的门"
 * - Content (中): 选中门对应产物的类型化审阅 (复用 S9-003/S10-005 ReviewSections:
 *   product 6 节 / ux_ui wireframe → Screen Card (ASCII + 组件/动作) /
 *   design 架构 / code diff / test 统计 / release 下载 — 按 gate.stage_id
 *   关联 artifact)
 * - Decision (右): ✅ 通过 / ❌ 驳回 + 意见输入 + 反馈历史 (Feedback Loop:
 *   Reject + 意见 → POST /api/review-feedback 保存结构化反馈, 作为下一轮
 *   Agent 重生成输入; 决定走 S9-001 approve/reject 端点, 成功后刷新 Queue)
 *
 * 数据源 (复用 S10-002/005 Runtime API, 零重设计):
 * - runtimeClient.getReviewQueue(projectId) → {gate, artifact}[] (pending gates
 *   + 按 stage_id 匹配产物; 无后端 → mock fallback, is_mock 诚实徽章)
 * - runtimeClient.getArtifactDetail / getReviewFeedback → Content / 反馈历史
 * - 写面 (直接 API, 失败诚实报错不 fallback): api.approveApproval /
 *   api.rejectApproval / runtimeClient.saveReviewFeedback
 *
 * Timeline 联动: focusGateId + focusNonce (nonce 递增防重) → 定位队列中对应
 * 审核门 + "已从 Timeline 打开审核门 X" 提示; 处理后 onFocusConsumed 清
 * Shell state (与 S10-004/005 同模式; 队列未就绪时等就绪后补定位)。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import { runtimeClient } from '../api/runtimeClient';
import { Button, StatusBadge, Textarea } from '../components/ds';
import { artifactStatusLabel, artifactTypeLabel } from '../models/types';
import type { ArtifactDetail, ReviewFeedback, ReviewQueueItem } from '../models/types';
import { artifactBody, formatArtifactTime } from './ArtifactCenter';

/** 审核门 stage_id → 队列行标题 (Product/UXUI/Architecture/Release 四门;
 * 未知 stage_id 原样显示)。 */
export function gateStageLabel(stageId: string): string {
  const id = stageId.toLowerCase();
  if (id.includes('product')) return 'Product';
  if (id.includes('ux')) return 'UX/UI';
  if (id.includes('arch')) return 'Architecture';
  if (id.includes('release')) return 'Release';
  return stageId;
}

export function ReviewWorkflowPanel({
  projectId,
  focusGateId,
  focusNonce,
  onFocusConsumed,
}: {
  projectId: string;
  /** S10-006 Timeline 联动 — 待定位审核门 id (透传, 同 ArtifactCenter 模式)。 */
  focusGateId?: string | null;
  focusNonce?: number | null;
  onFocusConsumed?: () => void;
}): JSX.Element {
  const [queue, setQueue] = useState<ReviewQueueItem[]>([]);
  const [queueState, setQueueState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [queueError, setQueueError] = useState('');
  const [retryToken, setRetryToken] = useState(0);
  const [isMock, setIsMock] = useState(false);
  const [selectedGateId, setSelectedGateId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ArtifactDetail | null>(null);
  const [detailState, setDetailState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [detailError, setDetailError] = useState('');
  const [feedback, setFeedback] = useState<ReviewFeedback[]>([]);
  const [comment, setComment] = useState('');
  const [notice, setNotice] = useState<string | null>(null);
  const [warn, setWarn] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deciding, setDeciding] = useState<'approve' | 'reject' | null>(null);
  const [focusNotice, setFocusNotice] = useState<string | null>(null);
  const handledNonceRef = useRef<number | null>(null);

  const selectedItem = queue.find((item) => item.gate.id === selectedGateId) ?? null;

  /** 加载待审清单 (决定成功后刷新复用; 失败 → 错误态 + 重试)。 */
  const loadQueue = useCallback(async (): Promise<void> => {
    setQueueState('loading');
    try {
      const { data, is_mock } = await runtimeClient.getReviewQueue(projectId);
      setQueue(data);
      setIsMock(is_mock);
      setQueueState('ready');
      // 当前选中门已不在队列 (决定后刷新) → 自动落到下一道待审门
      setSelectedGateId((current) =>
        current != null && data.some((item) => item.gate.id === current)
          ? current
          : (data[0]?.gate.id ?? null),
      );
    } catch (err) {
      setQueueError(err instanceof Error ? err.message : String(err));
      setQueueState('error');
    }
  }, [projectId]);

  useEffect(() => {
    void loadQueue();
  }, [loadQueue, retryToken]);

  // 选中门 → 加载产物详情 + 反馈历史 (按 artifact_id; 无产物 → idle 空态)
  const artifactId = selectedItem?.artifact?.id ?? null;
  useEffect(() => {
    setDetail(null);
    setFeedback([]);
    if (artifactId == null) {
      setDetailState('idle');
      return;
    }
    let cancelled = false;
    setDetailState('loading');
    (async () => {
      try {
        const [detailRes, feedbackRes] = await Promise.all([
          runtimeClient.getArtifactDetail(artifactId),
          runtimeClient.getReviewFeedback(artifactId),
        ]);
        if (cancelled) return;
        setDetail(detailRes.data);
        setFeedback(feedbackRes.data);
        setDetailState('ready');
      } catch (err) {
        if (cancelled) return;
        setDetailError(err instanceof Error ? err.message : String(err));
        setDetailState('error');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [artifactId]);

  // Timeline 联动: focus nonce 递增 → 定位队列审核门; 队列未就绪 → 等就绪
  // 后补定位 (handledNonceRef 防重复消费, onFocusConsumed 只调一次)
  useEffect(() => {
    if (focusGateId == null || focusNonce == null) return;
    if (handledNonceRef.current === focusNonce) return;
    if (queueState !== 'ready') return;
    handledNonceRef.current = focusNonce;
    const item = queue.find((entry) => entry.gate.id === focusGateId);
    if (item != null) {
      setSelectedGateId(focusGateId);
      setFocusNotice(`已从 Timeline 打开审核门 ${focusGateId}`);
    } else {
      setFocusNotice(`未找到审核门 ${focusGateId} (可能已处理)`);
    }
    onFocusConsumed?.();
  }, [focusGateId, focusNonce, queue, queueState, onFocusConsumed]);

  const selectGate = (gateId: string): void => {
    setSelectedGateId(gateId);
    setComment('');
    setNotice(null);
    setWarn(null);
    setError(null);
  };

  /** 审核决定 (S9-001 approve/reject + Feedback Loop): Reject 带意见 → 先
   * POST /api/review-feedback 保存结构化反馈 (失败不影响决定 — 后端 503
   * 失败安全), 再走决定端点; 成功后刷新 Queue。 */
  const decide = async (action: 'approve' | 'reject'): Promise<void> => {
    if (selectedItem == null) return;
    const gate = selectedItem.gate;
    const artifactId = selectedItem.artifact?.id ?? '';
    const trimmed = comment.trim();
    let feedbackSaved = false;
    setDeciding(action);
    setError(null);
    setNotice(null);
    setWarn(null);
    try {
      if (action === 'reject' && trimmed.length > 0 && artifactId.length > 0) {
        try {
          await runtimeClient.saveReviewFeedback({
            artifact_id: artifactId,
            gate_id: gate.id,
            reviewer: 'console',
            comment: trimmed,
          });
          feedbackSaved = true;
          setNotice('反馈已保存, 将作为下一轮 Agent 输入');
        } catch {
          // 失败安全: 反馈保存失败不影响本次审核决定 (后端 503 语义)
          setWarn('反馈保存失败 — 不影响本次审核决定');
        }
      }
      if (action === 'approve') {
        await api.approveApproval(gate.id, trimmed);
        setNotice(`已批准审核门 ${gate.id}`);
      } else {
        await api.rejectApproval(gate.id, trimmed);
        if (!feedbackSaved) setNotice(`已驳回审核门 ${gate.id}`);
      }
      setComment('');
      await loadQueue(); // 决定成功 → 刷新队列 (该门移出待审清单)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeciding(null);
    }
  };

  const canDecide = selectedItem != null && selectedItem.artifact != null && deciding == null;

  return (
    <div className="ws-rv" data-testid="review-workflow-panel">
      {/* 左: Queue — 待审门清单 */}
      <section className="ws-rv-queue" data-testid="review-queue">
        <header className="ws-rv-head">
          <h4 className="ws-rv-title">
            待审核
            {queue.length > 0 ? (
              <span className="ws-rv-count" data-testid="review-queue-count">
                {queue.length}
              </span>
            ) : null}
          </h4>
          {isMock ? (
            <span className="ws-ac-mock" data-testid="review-queue-mock">
              演示数据
            </span>
          ) : null}
        </header>
        {focusNotice != null ? (
          <p className="ws-rv-notice" data-testid="review-focus-notice">
            {focusNotice}
          </p>
        ) : null}
        {queueState === 'loading' ? (
          <div className="ws-rv-state" data-testid="review-queue-loading">
            加载待审清单…
          </div>
        ) : null}
        {queueState === 'error' ? (
          <div className="ws-rv-state ws-rv-error" data-testid="review-queue-error">
            待审清单加载失败: {queueError}
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setRetryToken((token) => token + 1)}
            >
              重试
            </Button>
          </div>
        ) : null}
        {queueState === 'ready' && queue.length === 0 ? (
          <div className="ws-rv-state" data-testid="review-queue-empty">
            没有待审核的门
          </div>
        ) : null}
        {queueState === 'ready' && queue.length > 0 ? (
          <div className="ws-rv-queue-rows" data-testid="review-queue-rows">
            {queue.map((item) => {
              const active = item.gate.id === selectedGateId;
              return (
                <button
                  key={item.gate.id}
                  type="button"
                  className={`ws-rv-q-row${active ? ' active' : ''}`}
                  data-testid={`review-queue-${item.gate.id}`}
                  aria-pressed={active}
                  onClick={() => selectGate(item.gate.id)}
                >
                  <span className="ws-rv-q-top">
                    <span className="ws-rv-q-name">{gateStageLabel(item.gate.stage_id)}</span>
                    <StatusBadge status="pending" label="待审核" />
                  </span>
                  <span className="ws-rv-q-meta">
                    {item.artifact != null ? item.artifact.ref : item.gate.stage_id}
                  </span>
                </button>
              );
            })}
          </div>
        ) : null}
      </section>

      {/* 中: Content — 类型化产物审阅 */}
      <section className="ws-rv-content" data-testid="review-content">
        {selectedItem == null ? (
          <div className="ws-rv-state" data-testid="review-content-empty">
            选择左侧待审门查看产物内容
          </div>
        ) : selectedItem.artifact == null ? (
          <div className="ws-rv-state" data-testid="review-content-no-artifact">
            该审核门暂无对应产物 (无法审阅内容)
          </div>
        ) : detailState === 'loading' ? (
          <div className="ws-rv-state" data-testid="review-detail-loading">
            加载产物详情…
          </div>
        ) : detailState === 'error' ? (
          <div className="ws-rv-state ws-rv-error" data-testid="review-detail-error">
            产物详情加载失败: {detailError}
          </div>
        ) : detail == null ? (
          <div className="ws-rv-state" data-testid="review-detail-error">
            产物详情为空
          </div>
        ) : (
          <div className="ws-rv-detail" data-testid="review-detail">
            <header className="ws-rv-detail-head">
              <h4 className="ws-rv-detail-title">
                {artifactTypeLabel(detail.type)}
                <span className="ws-rv-detail-id"> {detail.id}</span>
              </h4>
              <div className="ws-rv-detail-meta">
                <StatusBadge status={detail.status} label={artifactStatusLabel(detail.status)} />
                <span>v{detail.version ?? '?'}</span>
                <span>产出: {detail.producer_role}</span>
                <span>阶段: {detail.stage_id}</span>
              </div>
            </header>
            <div className="ws-rv-detail-body">{artifactBody(detail, null)}</div>
          </div>
        )}
      </section>

      {/* 右: Decision — 通过/驳回 + 意见 + 反馈历史 */}
      <section className="ws-rv-decision" data-testid="review-decision">
        <h4 className="ws-rv-title">审核决定</h4>
        {selectedItem == null ? (
          <div className="ws-rv-state" data-testid="review-decision-empty">
            选择左侧待审门后执行决定
          </div>
        ) : (
          <>
            <div className="ws-rv-gate" data-testid="review-gate-info">
              <span className="ws-rv-gate-id">门: {selectedItem.gate.id}</span>
              <StatusBadge status="pending" label="待审核" />
            </div>
            {selectedItem.artifact == null ? (
              <p className="ws-rv-hint muted">该门无对应产物 — 无法执行审核决定</p>
            ) : (
              <>
                <Textarea
                  label="审核意见"
                  hint="驳回时填写, 将自动保存为下一轮 Agent 输入"
                  placeholder="输入意见…"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  data-testid="review-comment"
                />
                <div className="ws-rv-actions">
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={!canDecide}
                    loading={deciding === 'approve'}
                    onClick={() => void decide('approve')}
                    data-testid="review-approve"
                  >
                    ✅ 通过
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    disabled={!canDecide}
                    loading={deciding === 'reject'}
                    onClick={() => void decide('reject')}
                    data-testid="review-reject"
                  >
                    ❌ 驳回
                  </Button>
                </div>
              </>
            )}
            {notice != null ? (
              <p className="ws-rv-notice" data-testid="review-notice">
                {notice}
              </p>
            ) : null}
            {warn != null ? (
              <p className="ws-rv-warn" data-testid="review-warn">
                {warn}
              </p>
            ) : null}
            {error != null ? (
              <p className="ws-rv-error" data-testid="review-error">
                {error}
              </p>
            ) : null}
            <div className="ws-rv-history" data-testid="review-history">
              <h5 className="ws-rv-history-title">反馈历史</h5>
              {feedback.length === 0 ? (
                <p className="ws-rv-hint muted" data-testid="review-history-empty">
                  暂无反馈记录
                </p>
              ) : (
                feedback.map((record) => (
                  <div
                    className="ws-rv-history-item"
                    key={record.id}
                    data-testid={`review-feedback-${record.id}`}
                  >
                    <span className="ws-rv-round">R{record.round}</span>
                    <p className="ws-rv-history-comment">{record.comment}</p>
                    <span className="ws-rv-history-meta muted">
                      {record.reviewer} · {formatArtifactTime(record.created_at)}
                    </span>
                  </div>
                ))
              )}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
