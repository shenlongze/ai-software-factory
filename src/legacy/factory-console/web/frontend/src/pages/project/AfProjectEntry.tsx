/**
 * pages/project/AfProjectEntry.tsx — AI Factory 项目真实入口 (S10-014 Task 005 升级)。
 *
 * #/project/:id[/subpage] 打开后渲染 AI OS 项目层壳 (AfProjectShell):
 *   Browser → Router → AfProjectShell (Project Header + Sidebar 11 导航 + Main)
 *   → overview 页真实 Project Entity (GET /api/projects 按 id 定位 + 四态 + 404)
 *   → 其他 10 页 AfModulePlaceholder (禁空白; Todo Tree 明确占位)
 *
 * 入口兼容: 保持导出名与 data-testid="af-project-entry" (根节点在 Shell 上),
 * App.tsx 路由分发无需改动。Task 002b 的详情逻辑迁入 AfProjectShell.ProjectDetailView。
 */

import type { ParsedRoute } from '../../router';
import { AfProjectShell } from '../../components/af/AfProjectShell';

export function AfProjectEntry({ route }: { route: ParsedRoute }): JSX.Element {
  return <AfProjectShell route={route} />;
}
