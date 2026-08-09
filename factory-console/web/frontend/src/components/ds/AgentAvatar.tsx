/**
 * ds/AgentAvatar.tsx — Agent 头像 (6 Agent: PM/UX-UI/Arch/Dev/Tester/Release,
 * 每角色专属图标色; 未知角色回退中性灰 🤖)。
 */

import { agentMeta } from '../../design/tokens';

export type AvatarSize = 'sm' | 'md' | 'lg';

export function AgentAvatar({ role, size = 'md' }: { role: string; size?: AvatarSize }): JSX.Element {
  const meta = agentMeta(role);
  return (
    <span
      className={`ds-avatar ds-avatar-${size}`}
      data-role={role.toLowerCase()}
      style={{ background: meta.color }}
      role="img"
      aria-label={meta.label}
      title={meta.label}
    >
      <span aria-hidden="true">{meta.icon}</span>
    </span>
  );
}
