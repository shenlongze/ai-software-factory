/**
 * components/af/AfWorkflowViewer.tsx — AI Factory Workflow Instance 可视化 (S10-015 Task 004)。
 *
 * 依据 (唯一): S10-015-architecture-review §4 (Workflow Adapter 设计) + 用户 Task 004
 * 设计约束 (Workflow Viewer 不是静态流程图 — 必须真实 Workflow Instance 可视化)。
 *
 * 回答 5 问:
 *   ① 当前流程运行到哪里?  → 运行流程区块 (Instance): running 阶段卡高亮 (af-wf-stage--active 呼吸)
 *   ② 哪个 Agent 正在执行? → 阶段卡 Agent 人话名 (ROLE_LABELS: 产品经理/UI 设计师/… + Agent 后缀)
 *   ③ 哪个节点完成?        → completed 阶段绿勾 ✓ + AfStatusBadge 已完成
 *   ④ 哪个节点等待?        → pending 阶段灰 (AfStatusBadge 待办)
 *   ⑤ 为什么阻塞?          → blocked 阶段紫 + blockedReason (depends_on 前置阶段人话 / 依赖未就绪)
 *
 * 三层展示 (用户约束, 禁只展示模板不展示实例):
 *   ① 运行流程 (Workflow Instance): 阶段卡流水线 (真实状态, 顺序箭头 ↓)
 *   ② 设计流程 (Workflow Template): 折叠区 — 模板名 + 阶段序列
 *   ③ 历史 (Audit Timeline): 复用 AfTimeline (time/actor/action/result)
 *
 * 诚实降级:
 *   - isMock=true → 顶部警告徽标 "演示数据 — 非真实执行" (禁冒充真实执行)
 *   - failedReason (工作流级失败原因) → 头部失败横幅
 *   - 空 stages → AfEmptyState (禁空白)
 * 纯展示组件: 不 fetch, pipeline/timeline 由父层传入 (页面数据必须来自真实后端)。
 */

import { toDomainStatus } from '../../api/domain';
import type { RuntimeActivity, WorkflowPipeline, WorkflowStage } from '../../models/domain';
import { AfEmptyState } from './AfState';
import { AfStatusBadge } from './AfStatusBadge';
import { AfTimeline, type AfTimelineItem } from './AfTimeline';
import './af.css';

export interface AfWorkflowViewerProps {
  /** 流水线 (domain; 由 toWorkflowPipeline(workflowDetail) 真实转换)。 */
  pipeline: WorkflowPipeline;
  /** 历史事件 (domain; 由 toRuntimeActivity(timeline) 真实转换)。 */
  timeline?: RuntimeActivity[];
}

/** RuntimeActivity → AfTimelineItem (状态点色: result → DomainStatus 语义)。 */
function toTimelineItems(events: RuntimeActivity[]): AfTimelineItem[] {
  return events.map((ev) => ({
    time: ev.time,
    actor: ev.actor,
    action: ev.action,
    result: ev.result,
    status: toDomainStatus(ev.result),
  }));
}

export function AfWorkflowViewer({
  pipeline,
  timeline = [],
}: AfWorkflowViewerProps): JSX.Element {
  if (pipeline.stages.length === 0) {
    return (
      <div className="af-workflow-viewer" data-testid="af-workflow-viewer">
        <AfEmptyState message="暂无流程运行" hint="项目启动工作流后, 将在此展示真实流水线状态" />
      </div>
    );
  }

  const workflowStatus = pipeline.status ?? 'pending';
  const failedReason = pipeline.failedReason;

  return (
    <div className="af-workflow-viewer" data-testid="af-workflow-viewer">
      {/* 头部: 流程名 + 实例状态 (+ isMock 降级警告 / 失败原因) */}
      <div className="af-wf-header">
        <h3 className="af-wf-title" data-testid="af-wf-title">
          {pipeline.templateName}
        </h3>
        <AfStatusBadge status={workflowStatus} />
        {pipeline.isMock === true ? (
          <span
            className="af-wf-mock-badge"
            data-testid="af-wf-mock-badge"
            title="后端未运行真实工作流, 以下为演示数据 (非真实执行)"
          >
            ⚠ 演示数据 — 非真实执行
          </span>
        ) : null}
      </div>
      {failedReason != null && failedReason.length > 0 ? (
        <div className="af-wf-failed" data-testid="af-wf-failed" role="alert">
          流程失败: {failedReason}
        </div>
      ) : null}

      {/* ① 运行流程 (Workflow Instance): 真实阶段卡流水线 */}
      <section className="af-wf-section" data-testid="af-wf-instance">
        <h4 className="af-wf-section-title">
          运行流程 <span className="af-wf-section-sub">Workflow Instance</span>
        </h4>
        <ol className="af-wf-pipeline" data-testid="af-wf-pipeline">
          {pipeline.stages.map((stage, idx) => (
            <WorkflowStageRow
              key={stage.order}
              stage={stage}
              isLast={idx === pipeline.stages.length - 1}
            />
          ))}
        </ol>
      </section>

      {/* ② 设计流程 (Workflow Template): 折叠区 — 模板名 + 阶段序列 */}
      <details className="af-wf-section af-wf-template" data-testid="af-wf-template">
        <summary className="af-wf-section-title">
          设计流程 <span className="af-wf-section-sub">Workflow Template</span>
        </summary>
        <div className="af-wf-template-body">
          <span className="af-wf-template-name">{pipeline.templateName}</span>
          <div className="af-wf-template-seq">
            {pipeline.stages.map((stage, idx) => (
              <span className="af-wf-template-step" key={stage.order}>
                {idx > 0 ? (
                  <span className="af-wf-arrow" aria-hidden="true">
                    →
                  </span>
                ) : null}
                {stage.name}
              </span>
            ))}
          </div>
        </div>
      </details>

      {/* ③ 历史 (Audit Timeline): 真实运行事件 */}
      <section className="af-wf-section" data-testid="af-wf-timeline">
        <h4 className="af-wf-section-title">
          历史 <span className="af-wf-section-sub">Audit Timeline</span>
        </h4>
        <AfTimeline items={toTimelineItems(timeline)} />
      </section>
    </div>
  );
}

/** 单个阶段卡: 顺序号 + 名称 + Agent 人话名 + 状态徽标 + 完成勾/阻塞原因 + 顺序箭头 ↓。 */
function WorkflowStageRow({
  stage,
  isLast,
}: {
  stage: WorkflowStage;
  isLast: boolean;
}): JSX.Element {
  const isActive = stage.status === 'running'; // 当前执行阶段高亮 (呼吸)
  const rowClass = [
    'af-wf-stage',
    `af-wf-stage--${stage.status}`,
    isActive ? 'af-wf-stage--active' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <li className="af-wf-stage-wrap" data-testid={`af-wf-stage-${stage.order}`}>
      <div className={rowClass} data-node-status={stage.status}>
        <span className="af-wf-stage-order" aria-hidden="true">
          {stage.order}
        </span>
        <div className="af-wf-stage-main">
          <div className="af-wf-stage-name-row">
            <span className="af-wf-stage-name">{stage.name}</span>
            <AfStatusBadge status={stage.status} label={stage.statusLabel} />
          </div>
          {stage.agentName != null && stage.agentName.length > 0 ? (
            <span className="af-wf-stage-agent" data-testid="af-wf-stage-agent">
              {stage.agentName} Agent
            </span>
          ) : null}
          {stage.status === 'completed' ? (
            <span className="af-wf-stage-done" data-testid="af-wf-stage-done">
              ✓ 完成
            </span>
          ) : null}
          {stage.status === 'blocked' && stage.blockedReason != null ? (
            <span className="af-wf-stage-blocked" data-testid="af-wf-stage-blocked">
              阻塞: {stage.blockedReason}
            </span>
          ) : null}
          {stage.currentTask != null && stage.currentTask.length > 0 ? (
            <span className="af-wf-stage-task">当前: {stage.currentTask}</span>
          ) : null}
          {stage.artifact != null && stage.artifact.length > 0 ? (
            <span className="af-wf-stage-artifact" title={stage.artifact}>
              产物: {stage.artifact}
            </span>
          ) : null}
        </div>
        {isActive ? (
          <span className="af-wf-stage-pulse" aria-hidden="true" title="当前执行中" />
        ) : null}
      </div>
      {!isLast ? (
        <div className="af-wf-stage-arrow" aria-hidden="true">
          ↓
        </div>
      ) : null}
    </li>
  );
}
