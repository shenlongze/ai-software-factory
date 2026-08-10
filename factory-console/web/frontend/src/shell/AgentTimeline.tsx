/**
 * shell/AgentTimeline.tsx — S10-003 Agent Timeline (中间 Workspace 核心区)。
 *
 * 数据接入 (复用 S10-002 Runtime API, 禁止重设计):
 * - runtimeClient.getTimeline(projectId) → 初始历史事件流 ({data, is_mock})
 * - runtimeClient.subscribeEvents(projectId, {onEvent}) → SSE 实时追加节点
 * - is_mock (查询 fallback 或 SSE mock error 事件) → "演示数据" 徽章 (诚实标注)
 *
 * 事件流节点 (消费 Design System Timeline/StageCard/StatusBadge/AgentAvatar/
 * Button — 零重复 CSS, 结构样式 ws- 前缀只补 Shell 专属布局):
 * - user:    用户输入 (只读气泡)
 * - stage:   Stage Card (Agent/状态/Input-Output Artifact/Duration/Cost/查看详情)
 * - artifact: 产物生成 + [查看]
 * - review:  等待审核 + [去审核] (高亮)
 * - diff:    文件清单 + [展开 diff]
 * - error:   失败 + 原因 (红色)
 * - 实时: SSE 事件 → 追加节点 + 滚动到底
 *
 * 底部: 持续开发输入 (仅占位 UI — S10-006 Review Workflow 接入, 本期无写路径)。
 * S10-004 联动: artifact 节点 "查看" → onViewArtifact(artifactId) 回调
 * (WorkspaceShell 选中 Runtime Tab 定位/提示创建; 未提供回调时维持展开详情)。
 * 不实现 Browser/Terminal Runtime (S10-004 RuntimePanel); 不修改 S10-004 设计。
 */

import { useEffect, useRef, useState } from 'react';
import { runtimeClient } from '../api/runtimeClient';
import { api } from '../api/client';
import { Button, StageCard, Timeline, TimelineNode } from '../components/ds';
import { artifactTypeLabel } from '../models/types';
import type { RuntimeEventName, TimelineEventSummary } from '../models/types';

// ------------------------------------------------------------------ 事件 → 节点映射 (纯函数, 可测)

/** 事件类型元信息 (节点标题/图标; 未知类型回退 📌)。 */
export const TIMELINE_TYPE_META: Record<string, { label: string; icon: string }> = {
  user: { label: '用户输入', icon: '💬' },
  stage: { label: '阶段', icon: '🤖' },
  artifact: { label: '产物', icon: '📦' },
  review: { label: '审核', icon: '✅' },
  diff: { label: '代码变更', icon: '🔧' },
  error: { label: '失败', icon: '⛔' },
};

/** org role_id / agent_id → Design System 角色键 (未知名回退原值 → AgentAvatar 🤖)。 */
const AGENT_ID_ROLE_KEYS: Record<string, string> = {
  'product-manager': 'pm',
  pm: 'pm',
  'ui-designer': 'ux_ui',
  ux_ui: 'ux_ui',
  ui: 'ux_ui',
  architect: 'architecture',
  architecture: 'architecture',
  developer: 'developer',
  tester: 'tester',
  devops: 'release',
  release: 'release',
};

export function roleKeyFromAgentId(agentId: string | null): string {
  if (agentId == null) return 'agent';
  return AGENT_ID_ROLE_KEYS[agentId] ?? agentId;
}

/** Timeline 节点状态 (来自 event_type/type; 与 Design System statusTone 语义对齐)。 */
export function timelineNodeStatus(event: TimelineEventSummary): string {
  const eventType = event.event_type ?? '';
  switch (event.type) {
    case 'stage': {
      if (eventType.includes('stage_failed') || eventType.includes('failed')) return 'failed';
      if (eventType.includes('stage_completed') || eventType.includes('completed')) return 'success';
      if (eventType.includes('stage_started') || eventType.includes('started')) return 'running';
      const payloadStatus = event.payload?.status;
      return typeof payloadStatus === 'string' && payloadStatus.length > 0 ? payloadStatus : 'pending';
    }
    case 'user':
      return 'pending';
    case 'artifact':
      return 'success';
    case 'review':
      return 'approval_required';
    case 'diff':
      return 'success';
    case 'error':
      return 'failed';
    default:
      return 'pending';
  }
}

/** payload 字符串字段 (宽松读取, 缺 → null)。 */
function payloadString(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return typeof value === 'string' && value.length > 0 ? value : null;
}

/** payload 字符串数组字段 (宽松读取, 缺/形状不符 → null)。 */
export function payloadStringArray(payload: Record<string, unknown>, key: string): string[] | null {
  const value = payload[key];
  if (!Array.isArray(value)) return null;
  if (!value.every((item) => typeof item === 'string')) return null;
  return value as string[];
}

/** payload 数字字段 (宽松读取, 缺 → null)。 */
export function payloadNumber(payload: Record<string, unknown>, key: string): number | null {
  const value = payload[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/**
 * SSE 事件 → Timeline 节点 (订阅事件追加用; 非 Timeline 节点事件 → null 跳过)。
 *
 * 映射对齐 S10-002 SSE 事件表 (stage.started / stage.completed / artifact.created /
 * approval.required / error; approval.completed 与 runtime.* 不进 Timeline, KISS)。
 */
export function sseEventToTimelineNode(
  projectId: string,
  name: RuntimeEventName,
  data: Record<string, unknown>,
  seq: number,
): TimelineEventSummary | null {
  const str = (value: unknown): string | null =>
    typeof value === 'string' && value.length > 0 ? value : null;

  const build = (
    type: string,
    eventType: string,
    partial: Partial<TimelineEventSummary> = {},
  ): TimelineEventSummary => ({
    id: `sse-${name}-${seq}`,
    seq,
    project_id: projectId,
    type,
    event_type: eventType,
    stage_id: str(data.stage_id),
    agent_id: str(data.agent_id),
    artifact_id: str(data.artifact_id),
    gate_id: str(data.gate_id),
    message: '',
    status: null,
    payload: data,
    created_at: null,
    ...partial,
  });

  switch (name) {
    case 'stage.started': {
      const stageName = str(data.name);
      return build('stage', 'org.workflow.stage_started', {
        message: stageName != null ? `阶段开始: ${stageName}` : '阶段开始',
        status: 'running',
      });
    }
    case 'stage.completed': {
      const stageName = str(data.name);
      return build('stage', 'org.workflow.stage_completed', {
        message: stageName != null ? `阶段完成: ${stageName}` : '阶段完成',
        status: 'success',
      });
    }
    case 'artifact.created': {
      const artifactType = str(data.type);
      return build('artifact', 'org.artifact.created', {
        message: artifactType != null ? `生成 ${artifactTypeLabel(artifactType)} Artifact` : '产物生成',
        status: 'success',
      });
    }
    case 'approval.required':
      return build('review', 'org.approval.created', {
        message: '等待你审核',
        status: 'approval_required',
      });
    case 'error':
      return build('error', 'org.workflow.failed', {
        message: str(data.reason) ?? '任务失败',
        status: 'failed',
      });
    case 'approval.completed':
    case 'runtime.created':
    case 'runtime.status.changed':
      // 不进 Timeline (审批结果/Runtime 生命周期属 S10-004/S10-006 面板)
      return null;
  }
}

/** created_at → HH:MM 显示 (非法/缺失 → null, 不显示)。 */
export function formatEventTime(createdAt: string | null): string | null {
  if (createdAt == null) return null;
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

// ------------------------------------------------------------------ 节点渲染

function DetailBlock({ event }: { event: TimelineEventSummary }): JSX.Element {
  return (
    <div className="ws-tl-detail" data-testid="agent-timeline-detail">
      <pre className="ws-tl-detail-json">{JSON.stringify(event.payload, null, 2)}</pre>
    </div>
  );
}

function TimelineEventNode({
  event,
  expanded,
  onToggleDetail,
  onViewArtifact,
}: {
  event: TimelineEventSummary;
  expanded: boolean;
  onToggleDetail: (eventId: string) => void;
  /** S10-004 联动: artifact 节点查看 → 打开 Runtime (可选)。 */
  onViewArtifact?: (artifactId: string) => void;
}): JSX.Element {
  const meta = TIMELINE_TYPE_META[event.type] ?? { label: event.type, icon: '📌' };
  const status = timelineNodeStatus(event);
  const time = formatEventTime(event.created_at);

  switch (event.type) {
    case 'user':
      return (
        <TimelineNode status="pending" title={`${meta.icon} ${meta.label}`} time={time ?? undefined}>
          <div className="ws-tl-user-bubble" data-testid="agent-timeline-user">
            {event.message}
          </div>
        </TimelineNode>
      );
    case 'stage': {
      const stageName = payloadString(event.payload, 'name') ?? (event.message || meta.label);
      return (
        <TimelineNode status={status} title={`${meta.icon} ${meta.label}`} time={time ?? undefined}>
          <StageCard
            name={stageName}
            agent={roleKeyFromAgentId(event.agent_id)}
            status={status}
            input={payloadStringArray(event.payload, 'input_artifacts') ?? undefined}
            output={payloadStringArray(event.payload, 'output_artifacts') ?? undefined}
            durationSec={payloadNumber(event.payload, 'duration_s')}
            cost={payloadNumber(event.payload, 'cost_usd')}
            onViewDetails={() => onToggleDetail(event.id)}
          />
          {expanded ? <DetailBlock event={event} /> : null}
        </TimelineNode>
      );
    }
    case 'artifact':
      return (
        <TimelineNode status={status} title={`${meta.icon} ${meta.label}`} time={time ?? undefined}>
          <div className="ws-tl-artifact">
            <span className="ws-tl-artifact-name" data-testid="agent-timeline-artifact">
              {event.message}
            </span>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                // S10-004 联动: artifact_id 存在且提供回调 → 打开 Runtime Tab
                // (WorkspaceShell 定位绑定实例/提示创建); 否则维持展开详情
                if (
                  onViewArtifact != null &&
                  event.artifact_id != null &&
                  event.artifact_id.length > 0
                ) {
                  onViewArtifact(event.artifact_id);
                } else {
                  onToggleDetail(event.id);
                }
              }}
            >
              查看
            </Button>
          </div>
          {expanded ? <DetailBlock event={event} /> : null}
        </TimelineNode>
      );
    case 'review': {
      const artifactName = payloadString(event.payload, 'artifact_type') ?? event.message;
      return (
        <TimelineNode status={status} title={`${meta.icon} ${meta.label}`} time={time ?? undefined}>
          <div className="ws-tl-review">
            <span className="ws-tl-review-name" data-testid="agent-timeline-review">
              {artifactName}
            </span>
            <Button variant="primary" size="sm" onClick={() => onToggleDetail(event.id)}>
              去审核
            </Button>
          </div>
          {expanded ? <DetailBlock event={event} /> : null}
        </TimelineNode>
      );
    }
    case 'diff': {
      const files = payloadStringArray(event.payload, 'files') ?? payloadStringArray(event.payload, 'changed_files');
      return (
        <TimelineNode status={status} title={`${meta.icon} ${meta.label}`} time={time ?? undefined}>
          <div className="ws-tl-diff">
            {files != null && files.length > 0 ? (
              <div className="ws-tl-diff-files" data-testid="agent-timeline-diff-files">
                {files.map((file) => (
                  <span key={file} className="ws-tl-diff-file">
                    {file}
                  </span>
                ))}
              </div>
            ) : (
              <span className="ws-tl-diff-message">{event.message}</span>
            )}
            <Button variant="ghost" size="sm" onClick={() => onToggleDetail(event.id)}>
              展开 diff
            </Button>
          </div>
          {expanded ? <DetailBlock event={event} /> : null}
        </TimelineNode>
      );
    }
    case 'error':
      return (
        <TimelineNode status="failed" title={`${meta.icon} ${meta.label}`} time={time ?? undefined}>
          <div className="ws-tl-error" data-testid="agent-timeline-error">
            {event.message}
          </div>
          {expanded ? <DetailBlock event={event} /> : null}
        </TimelineNode>
      );
    default:
      return (
        <TimelineNode status={status} title={`${meta.icon} ${meta.label}`} time={time ?? undefined}>
          <span className="ws-tl-default">{event.message}</span>
        </TimelineNode>
      );
  }
}

// ------------------------------------------------------------------ 主组件

export function AgentTimeline({
  projectId,
  onViewArtifact,
}: {
  projectId: string;
  /** S10-004 联动: artifact "查看" → 打开对应 Runtime (WorkspaceShell 提供)。 */
  onViewArtifact?: (artifactId: string) => void;
}): JSX.Element {
  const [events, setEvents] = useState<TimelineEventSummary[]>([]);
  const [isMock, setIsMock] = useState(false);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [loadError, setLoadError] = useState<string>('');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  // S10-006.5 P1-A: 持续开发 chat (真实 POST /api/projects/{id}/chat)
  const [chatText, setChatText] = useState('');
  const [chatSending, setChatSending] = useState(false);
  const [chatHint, setChatHint] = useState<string | null>(null);

  /** 发送持续开发消息: POST /chat → 后端 (未启动 → 触发真实 Agent 链)。 */
  const handleChatSubmit = async (): Promise<void> => {
    const message = chatText.trim();
    if (message.length === 0) return;
    setChatSending(true);
    setChatHint(null);
    try {
      const result = await api.sendChat(projectId, message);
      setChatText('');
      setChatHint(
        result.started === true
          ? '已发送 — AI 开发已启动 (Timeline 将显示真实工作)'
          : '已发送给 AI 团队',
      );
    } catch (err) {
      setChatHint(err instanceof Error ? `发送失败: ${err.message}` : '发送失败, 请稍后重试');
    } finally {
      setChatSending(false);
    }
  };
  const scrollRef = useRef<HTMLDivElement>(null);
  const seqRef = useRef(0);

  // 初始历史事件 (S10-002 getTimeline; 无后端 → mock fallback, is_mock 诚实标注)
  useEffect(() => {
    let cancelled = false;
    setLoadState('loading');
    (async () => {
      try {
        const { data, is_mock: mock } = await runtimeClient.getTimeline(projectId);
        if (cancelled) return;
        setEvents(data);
        seqRef.current = data.reduce((max, event) => Math.max(max, event.seq), 0);
        setIsMock(mock);
        setLoadState('ready');
      } catch (err) {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : String(err));
        setLoadState('error');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId, retryToken]);

  // SSE 实时追加 (S10-002 subscribeEvents; 收到 mock error 事件 → 演示模式徽章)
  useEffect(() => {
    const subscription = runtimeClient.subscribeEvents(projectId, {
      onEvent: (name, data) => {
        if (data.mock === true) setIsMock(true);
        seqRef.current += 1;
        const node = sseEventToTimelineNode(projectId, name, data, seqRef.current);
        if (node == null) return;
        setEvents((prev) => [...prev, node]);
      },
    });
    return () => subscription.close();
  }, [projectId]);

  // 追加节点 → 滚动到底 (实时时间线跟随)
  useEffect(() => {
    const el = scrollRef.current;
    if (el != null) {
      el.scrollTop = el.scrollHeight - el.clientHeight;
    }
  }, [events]);

  const toggleDetail = (eventId: string): void => {
    setExpandedId((current) => (current === eventId ? null : eventId));
  };

  return (
    <section className="ws-timeline" data-testid="agent-timeline" aria-label="Agent Timeline">
      <div className="ws-timeline-head">
        <h2 className="ws-timeline-title">Agent Timeline</h2>
        {isMock ? (
          <span className="ws-timeline-mock" data-testid="agent-timeline-mock">
            演示数据
          </span>
        ) : null}
      </div>

      <div className="ws-timeline-scroll" data-testid="agent-timeline-scroll" ref={scrollRef}>
        {loadState === 'loading' ? (
          <div className="ws-timeline-empty" data-testid="agent-timeline-loading">
            <span className="ws-timeline-empty-icon" aria-hidden="true">
              ⏳
            </span>
            加载时间线…
          </div>
        ) : null}

        {loadState === 'error' ? (
          <div className="ws-timeline-empty" data-testid="agent-timeline-error-state">
            <span className="ws-timeline-empty-icon" aria-hidden="true">
              ⛔
            </span>
            <p className="ws-timeline-error-text">时间线加载失败: {loadError}</p>
            <Button variant="secondary" size="sm" onClick={() => setRetryToken((token) => token + 1)}>
              重试
            </Button>
          </div>
        ) : null}

        {loadState === 'ready' && events.length === 0 ? (
          <div className="ws-timeline-empty" data-testid="agent-timeline-empty">
            <span className="ws-timeline-empty-icon" aria-hidden="true">
              🤖
            </span>
            <p className="ws-timeline-empty-title">等待 AI 开始工作…</p>
            <p className="ws-timeline-empty-hint">AI Agent 的事件将实时出现在这里 (SSE 推送)</p>
          </div>
        ) : null}

        {loadState === 'ready' && events.length > 0 ? (
          <Timeline className="ws-tl-list">
            {events.map((event) => (
              <TimelineEventNode
                key={event.id}
                event={event}
                expanded={expandedId === event.id}
                onToggleDetail={toggleDetail}
                onViewArtifact={onViewArtifact}
              />
            ))}
          </Timeline>
        ) : null}
      </div>

      {/* 底部持续开发输入 (S10-006.5 P1-A: 真实 POST /chat — 已发送/触发开发) */}
      <form
        className="ws-tl-input"
        data-testid="agent-timeline-input"
        onSubmit={(e) => {
          e.preventDefault();
          void handleChatSubmit();
        }}
      >
        <input
          className="ws-tl-input-box"
          data-testid="agent-timeline-input-box"
          type="text"
          placeholder="继续提出需求或修改意见…"
          aria-label="持续开发输入"
          value={chatText}
          onChange={(e) => setChatText(e.target.value)}
        />
        <Button type="submit" variant="primary" size="sm" disabled={chatSending}>
          {chatSending ? '发送中…' : '发送'}
        </Button>
      </form>
      {chatHint != null ? (
        <p className="ws-tl-input-hint" data-testid="agent-timeline-input-hint">
          {chatHint}
        </p>
      ) : null}
    </section>
  );
}
