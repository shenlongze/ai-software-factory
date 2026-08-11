/**
 * api/domain.ts — Domain Adapter (S10-014-plan §2.5 + §6)。
 *
 * 职责 (S10-014 Task 007 实现):
 *   - 字段映射 (后端 snake_case → 前端 domain 字段)
 *   - 派生计算 (完成度/状态人话/耗时/风险)
 *   - 聚合 (Todo Tree 从 backlog+runtime 投影)
 *   - 降级 (后端字段缺失 → 默认值, 不崩溃, §6.3)
 *
 * 数据流: Component → Domain Hook → Domain Adapter → API Layer → FastAPI (8011)
 *
 * S10-014 Task 001 状态: 仅建签名 + 返回默认值 (空/未实现占位), 不写转换逻辑;
 * 调用方在页面骨架期消费占位数据, Task 007 替换为真实转换。
 */

import type {
  AgentSummary,
  RuntimeActivity,
  TaskDetail,
  TodoTree,
  WorkflowPipeline,
  WorkspaceProject,
} from '../models/domain';

/** S10-014 Task 007 实现: GET /api/projects + /api/dashboard → WorkspaceProject。 */
export function toWorkspaceProject(_raw?: unknown): WorkspaceProject {
  return {
    id: '',
    name: '',
    lifecycleStage: 'draft',
    lifecycleLabel: '',
    progress: 0,
    pendingApprovals: 0,
    riskCount: 0,
  };
}

/** S10-014 Task 007 实现: backlog + workflow + timeline 聚合 → TodoTree (单根空树)。 */
export function toTodoTree(_raw?: unknown): TodoTree {
  return {
    root: {
      id: '',
      title: '',
      type: 'phase',
      status: 'pending',
      statusLabel: '',
      progress: 0,
      children: [],
    },
  };
}

/** S10-014 Task 007 实现: GET /api/projects/{id}/workflow + stages → WorkflowPipeline。 */
export function toWorkflowPipeline(_raw?: unknown): WorkflowPipeline {
  return {
    templateId: '',
    templateName: '',
    stages: [],
  };
}

/** S10-014 Task 007 实现: backlog/task/{id} + timeline → TaskDetail。 */
export function toTaskDetail(_raw?: unknown): TaskDetail {
  return {
    id: '',
    title: '',
    status: 'pending',
    statusLabel: '',
    history: [],
    artifacts: [],
  };
}

/** S10-014 Task 007 实现: timeline + events/stream → RuntimeActivity。 */
export function toRuntimeActivity(_raw?: unknown): RuntimeActivity {
  return {
    time: '',
    actor: '',
    action: '',
    result: '',
  };
}

/** S10-014 Task 007 实现: workflows/agents + registry 门面 → AgentSummary。 */
export function toAgentSummary(_raw?: unknown): AgentSummary {
  return {
    id: '',
    name: '',
    role: '',
    status: 'available',
    skills: [],
    version: '',
  };
}
