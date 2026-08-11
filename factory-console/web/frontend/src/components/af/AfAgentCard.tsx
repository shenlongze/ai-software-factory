/**
 * components/af/AfAgentCard.tsx — AI Factory 员工卡片 (S10-014 Task 003, §4.3)。
 *
 * 规格 (S10-013 §6.2): 🤖 头像 + 名称 + 状态 (可用/停用/废弃) + 擅长标签 (skills)
 * + 版本 + 统计 (成功率/耗时)。
 * 降级 (§6.3): 缺失统计 → '—'; 空 skills → 无标签区; 未知状态 → 原样显示。
 * 纯展示组件: 不 fetch, 数据由父层传入 (AgentSummary 来自 models/domain.ts)。
 */

import type { AgentSummary } from '../../models/domain';
import {
  agentStatusLabel,
  formatDuration,
  formatSuccessRate,
} from './afTokens';

export interface AfAgentCardProps {
  agent: AgentSummary;
}

export function AfAgentCard({ agent }: AfAgentCardProps): JSX.Element {
  return (
    <div className="af-agent-card" data-testid="af-agent-card">
      <div className="af-agent-head">
        <span className="af-agent-avatar" aria-hidden="true">
          🤖
        </span>
        <div className="af-agent-id">
          <span className="af-agent-name">{agent.name}</span>
          <span className="af-agent-role">{agent.role}</span>
        </div>
        <span className="af-agent-status">{agentStatusLabel(agent.status)}</span>
      </div>
      {agent.skills.length > 0 ? (
        <div className="af-agent-skills">
          {agent.skills.map((skill) => (
            <span key={skill} className="af-chip" data-testid="af-agent-skill">
              {skill}
            </span>
          ))}
        </div>
      ) : null}
      <div className="af-agent-foot">
        <span className="af-agent-version">v{agent.version}</span>
        <div className="af-agent-stats">
          <span className="af-agent-stat">成功率 {formatSuccessRate(agent.successRate)}</span>
          <span className="af-agent-stat">耗时 {formatDuration(agent.avgDuration)}</span>
        </div>
      </div>
    </div>
  );
}
