/**
 * components/af/AfQualityGate.tsx — Quality Gate 界面 (S10-015 Task 007)。
 *
 * 依据 (唯一): docs/design/AF-UI-Architecture.md §1.5/§3.2 (AI Employee 与 Human 的
 * 责任边界) + 用户 Task 007 设计约束。
 *
 * Quality Gate = "AI 生产出来的软件, 是否达到交付标准?" — AI Execution → Artifact →
 * Verification → Quality Decision → Human Approval → Release。
 *
 * 5 模块 (用户指定, 全部真实数据驱动 — viewModel 经 toQualityGateViewModel 转换,
 * UI 不直接依赖 API DTO; 禁止 fake passed checks / fake approval / fake quality score):
 *   ① Current Quality Gate  — 当前 Gate 卡 (名称/状态 PENDING-PASS-FAILED/artifact/
 *                             置信度/风险); 无审批 → Unavailable
 *   ② Required Checks      — 5 项交付检查 (PRD Exists / Architecture Review /
 *                             Tests Passed / Build Available / Human Approval);
 *                             无数据 → Unavailable
 *   ③ Quality Decision     — WAITING_FOR_REVIEW / APPROVED / FAILED / UNKNOWN;
 *                             无数据 → Unavailable (无法评估)
 *   ④ Human Approval       — Waiting for approval / Approved by / Rejected reason;
 *                             后端无 → Not available
 *   ⑤ Decision History     — 复用 AfTimeline (timeline org.approval./org.artifact. 事件);
 *                             无 → 空态 (暂无历史决策)
 *
 * 诚实降级 (§6.3): 任何数据缺失 → Unavailable/Not available (这是正确行为, 不编造)。
 */

import { toDomainStatus } from '../../api/domain';
import type { QualityCheckStatus, QualityGateViewModel } from '../../models/domain';
import { AfStatusBadge } from './AfStatusBadge';
import { AfTimeline, type AfTimelineItem } from './AfTimeline';
import { formatTime } from './afLabels';
import './af.css';

export interface AfQualityGateProps {
  /** Quality Gate 视图模型 (Domain Adapter 输出; 缺失字段已降级)。 */
  viewModel: QualityGateViewModel;
}

/** 质量状态 → 徽标语义 (pending→橙待审核 / passed→绿 / failed→红 / unavailable→灰 Unavailable)。 */
function qualityBadge(status: QualityCheckStatus): { badgeStatus: string; label: string } {
  switch (status) {
    case 'passed':
      return { badgeStatus: 'completed', label: '已通过' };
    case 'failed':
      return { badgeStatus: 'failed', label: '未通过' };
    case 'pending':
      return { badgeStatus: 'review', label: '待审核' };
    default:
      return { badgeStatus: 'neutral', label: 'Unavailable' };
  }
}

/** 检查状态 → 图标 (✓ 通过 / ◌ 待审核 / ✗ 未通过 / — 无数据)。 */
function checkIcon(status: QualityCheckStatus): string {
  switch (status) {
    case 'passed':
      return '✓';
    case 'pending':
      return '◌';
    case 'failed':
      return '✗';
    default:
      return '—';
  }
}

/** 人工审批状态 → 主文案 (Waiting for approval / Approved by / Rejected reason)。 */
function approvalHeadline(approval: NonNullable<QualityGateViewModel['approval']>): string {
  if (approval.status === 'pending') return 'Waiting for approval';
  if (approval.status === 'approved') return `Approved by ${approval.by ?? '—'}`;
  return approval.comment != null && approval.comment.length > 0
    ? `Rejected: ${approval.comment}`
    : 'Rejected';
}

export function AfQualityGate({ viewModel }: AfQualityGateProps): JSX.Element {
  const { currentGate, checks, decision, approval, history } = viewModel;
  const historyItems: AfTimelineItem[] = history.map((item) => ({
    time: item.time,
    actor: item.actor,
    action: item.action,
    result: item.result,
    status: toDomainStatus(item.result),
  }));

  return (
    <div className="af-quality-gate" data-testid="af-quality-gate">
      <header className="af-quality-head">
        <h2 className="af-section-title">Quality Gate</h2>
        <p className="af-quality-sub">
          AI 生产出来的软件, 是否达到交付标准? — 全部来自真实后端数据
        </p>
      </header>
      <div className="af-quality-grid">
        {/* ① Current Quality Gate — 当前 Gate 卡 (无审批 → Unavailable 诚实态) */}
        <section className="af-quality-module" data-testid="af-quality-current-gate">
          <h3 className="af-quality-module-title">
            Current Quality Gate <span className="af-quality-module-sub">当前质量门</span>
          </h3>
          {currentGate == null ? (
            <div className="af-quality-unavailable" data-testid="af-quality-gate-unavailable">
              Unavailable
            </div>
          ) : (
            <div className="af-quality-gate-card">
              <div className="af-quality-gate-head">
                <span className="af-quality-gate-name">{currentGate.name}</span>
                <AfStatusBadge
                  status={qualityBadge(currentGate.status).badgeStatus}
                  label={qualityBadge(currentGate.status).label}
                />
              </div>
              <dl className="af-quality-gate-fields">
                {currentGate.artifactType != null ? (
                  <div className="af-quality-field">
                    <dt>产物类型</dt>
                    <dd>{currentGate.artifactType}</dd>
                  </div>
                ) : null}
                {currentGate.artifactVersion != null ? (
                  <div className="af-quality-field">
                    <dt>产物版本</dt>
                    <dd>{currentGate.artifactVersion}</dd>
                  </div>
                ) : null}
                {currentGate.confidence != null ? (
                  <div className="af-quality-field">
                    <dt>置信度</dt>
                    <dd>{currentGate.confidence}</dd>
                  </div>
                ) : null}
                {currentGate.risk != null ? (
                  <div className="af-quality-field">
                    <dt>风险</dt>
                    <dd>{currentGate.risk}</dd>
                  </div>
                ) : null}
                {currentGate.requestedAt != null ? (
                  <div className="af-quality-field">
                    <dt>请求时间</dt>
                    <dd>{formatTime(currentGate.requestedAt)}</dd>
                  </div>
                ) : null}
              </dl>
            </div>
          )}
        </section>

        {/* ② Required Checks — 5 项交付检查 (无数据 → Unavailable) */}
        <section className="af-quality-module" data-testid="af-quality-checks">
          <h3 className="af-quality-module-title">
            Required Checks <span className="af-quality-module-sub">交付检查</span>
          </h3>
          <ul className="af-quality-checks">
            {checks.map((check) => {
              const meta = qualityBadge(check.status);
              return (
                <li
                  key={check.name}
                  className={`af-quality-check af-quality-check--${check.status}`}
                  data-testid="af-quality-check"
                >
                  <span className="af-quality-check-icon" aria-hidden="true">
                    {checkIcon(check.status)}
                  </span>
                  <span className="af-quality-check-name">{check.name}</span>
                  {check.detail != null && check.detail.length > 0 ? (
                    <span className="af-quality-check-detail">{check.detail}</span>
                  ) : null}
                  <AfStatusBadge status={meta.badgeStatus} label={meta.label} />
                </li>
              );
            })}
          </ul>
        </section>

        {/* ③ Quality Decision — 当前质量决策 (无数据 → Unavailable) */}
        <section className="af-quality-module" data-testid="af-quality-decision">
          <h3 className="af-quality-module-title">
            Quality Decision <span className="af-quality-module-sub">质量决策</span>
          </h3>
          <div className="af-quality-decision">
            <div
              className="af-quality-decision-status"
              data-testid="af-quality-decision-status"
            >
              {decision.label}
              {decision.status === 'UNKNOWN' ? (
                <span className="af-quality-decision-unavailable">Unavailable</span>
              ) : null}
            </div>
            {decision.reason != null && decision.reason.length > 0 ? (
              <div className="af-quality-decision-reason">{decision.reason}</div>
            ) : null}
          </div>
        </section>

        {/* ④ Human Approval — 人工审批 (后端无 → Not available) */}
        <section className="af-quality-module" data-testid="af-quality-approval">
          <h3 className="af-quality-module-title">
            Human Approval <span className="af-quality-module-sub">人工审批</span>
          </h3>
          {approval == null ? (
            <div className="af-quality-unavailable" data-testid="af-quality-approval-unavailable">
              Not available
            </div>
          ) : (
            <div className="af-quality-approval">
              <div className="af-quality-approval-status" data-testid="af-quality-approval-status">
                {approvalHeadline(approval)}
              </div>
              {approval.status === 'pending' && approval.by != null ? (
                <div className="af-quality-approval-by">by {approval.by}</div>
              ) : null}
              {approval.comment != null && approval.comment.length > 0 ? (
                <div className="af-quality-approval-comment">{approval.comment}</div>
              ) : null}
              {approval.requestedAt != null ? (
                <div className="af-quality-approval-time">
                  请求时间: {formatTime(approval.requestedAt)}
                </div>
              ) : null}
            </div>
          )}
        </section>

        {/* ⑤ Decision History — 复用 AfTimeline (无 → 空态) */}
        <section className="af-quality-module" data-testid="af-quality-history">
          <h3 className="af-quality-module-title">
            Decision History <span className="af-quality-module-sub">历史决策</span>
          </h3>
          {history.length === 0 ? (
            <div className="af-quality-empty" data-testid="af-quality-history-empty">
              暂无历史决策
            </div>
          ) : (
            <AfTimeline items={historyItems} />
          )}
        </section>
      </div>
    </div>
  );
}
