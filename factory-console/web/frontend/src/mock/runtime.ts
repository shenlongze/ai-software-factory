/**
 * mock/runtime.ts — S10-002 Runtime API 的 mock 数据 (无后端可展示)。
 *
 * 约束: mock 仅作 fallback — 数据缺失/请求失败时由 client.withMockFallback
 * 注入, 全部携带 is_mock: true 标记 (诚实标注, 不冒充真实数据); 形状对齐
 * 后端 mock (service.build_mock_workflow) 与 mock/workspace.ts MOCK_PROJECTS
 * (Product→UX/UI→Architecture→Code→Test→Release, Architecture 待审核)。
 */

import type {
  ArtifactContent,
  ArtifactDetail,
  ArtifactSummary,
  RuntimeInstance,
  StageRunSummary,
  TimelineEventSummary,
  WorkflowDetail,
} from '../models/types';

/** mock 工作流详情 (与后端 build_mock_workflow 同形状; is_mock 恒 true)。 */
export function mockWorkflowDetail(projectId = 'ledger-app', projectName = '记账 App'): WorkflowDetail {
  const stage = (
    id: string,
    name: string,
    roleId: string,
    status: string,
    artifactType: string | null,
  ) => ({
    id,
    workflow_id: `mock-wf-${projectId}`,
    role_id: roleId,
    name,
    order: 0,
    status,
    depends_on: [],
    input_artifacts: [],
    output_artifacts: [],
    approval_required: status === 'waiting_review',
    artifact: artifactType
      ? {
          id: `mock-art-${id}`,
          stage_id: id,
          workflow_id: `mock-wf-${projectId}`,
          project_id: projectId,
          type: artifactType,
          ref: `mock://${artifactType}`,
          version: '1',
          status: 'validated',
          producer_role: roleId,
          producer_agent: '',
          location: '',
          created_at: '2026-08-10T00:00:00+00:00',
          updated_at: '2026-08-10T00:00:00+00:00',
        }
      : null,
    pending_approval: status === 'waiting_review'
      ? {
          id: 'mock-gate-arch',
          stage_id: id,
          workflow_id: `mock-wf-${projectId}`,
          project_id: projectId,
          status: 'pending',
          reviewer: '',
          comment: '',
          requested_at: '2026-08-10T00:00:00+00:00',
          approved_at: null,
          rejected_at: null,
        }
      : null,
  });

  return {
    id: `mock-wf-${projectId}`,
    project_id: projectId,
    project_name: projectName,
    name: 'Mock Workflow (演示数据)',
    status: 'active',
    failed_reason: '',
    created_at: '2026-08-10T00:00:00+00:00',
    started_at: '2026-08-10T00:00:00+00:00',
    completed_at: null,
    is_mock: true,
    stages: [
      { ...stage('mock-product', 'Product', 'product-manager', 'completed', 'product'), order: 1 },
      { ...stage('mock-ux_ui', 'UX/UI', 'ui-designer', 'completed', 'ux_ui'), order: 2 },
      { ...stage('mock-architect', 'Architecture', 'architect', 'waiting_review', 'design'), order: 3 },
      { ...stage('mock-developer', 'Code', 'developer', 'pending', null), order: 4 },
      { ...stage('mock-tester', 'Test', 'tester', 'pending', null), order: 5 },
      { ...stage('mock-release', 'Release', 'devops', 'pending', null), order: 6 },
    ],
    pending_approvals: [
      {
        id: 'mock-gate-arch',
        stage_id: 'mock-architect',
        workflow_id: `mock-wf-${projectId}`,
        project_id: projectId,
        status: 'pending',
        reviewer: '',
        comment: '',
        requested_at: '2026-08-10T00:00:00+00:00',
        approved_at: null,
        rejected_at: null,
      },
    ],
    template: ['Idea', 'PM', 'Product', 'UX/UI', 'Architecture', 'Development', 'Test', 'Release'],
  };
}

/** mock 阶段运行明细 (Task 面板数据源; is_mock 由调用方透传标记)。 */
export function mockStageRuns(projectId = 'ledger-app'): StageRunSummary[] {
  const run = (
    id: string,
    name: string,
    roleId: string,
    status: string,
    artifactType: string | null,
    durationS: number | null,
    costUsd: number | null,
  ): StageRunSummary => ({
    id,
    workflow_id: `mock-wf-${projectId}`,
    role_id: roleId,
    name,
    order: 0,
    status,
    agent_id: roleId,
    duration_s: durationS,
    cost_usd: costUsd,
    started_at: '2026-08-10T00:00:00+00:00',
    completed_at: status === 'completed' ? '2026-08-10T00:02:00+00:00' : null,
    depends_on: [],
    input_artifacts: [],
    output_artifacts: artifactType ? [`mock-art-${id}`] : [],
    artifacts: artifactType
      ? [
          {
            id: `mock-art-${id}`,
            stage_id: id,
            workflow_id: `mock-wf-${projectId}`,
            project_id: projectId,
            type: artifactType,
            ref: `mock://${artifactType}`,
            version: '1',
            status: 'validated',
            producer_role: roleId,
            producer_agent: '',
            location: '',
            created_at: '2026-08-10T00:02:00+00:00',
            updated_at: '2026-08-10T00:02:00+00:00',
          },
        ]
      : [],
  });

  return [
    { ...run('mock-product', 'Product', 'product-manager', 'completed', 'product', 120, 0.05), order: 1 },
    { ...run('mock-ux_ui', 'UX/UI', 'ui-designer', 'completed', 'ux_ui', 95, 0.04), order: 2 },
    { ...run('mock-architect', 'Architecture', 'architect', 'waiting_review', 'design', 60, 0.03), order: 3 },
    { ...run('mock-developer', 'Code', 'developer', 'pending', null, null, null), order: 4 },
    { ...run('mock-tester', 'Test', 'tester', 'pending', null, null, null), order: 5 },
    { ...run('mock-release', 'Release', 'devops', 'pending', null, null, null), order: 6 },
  ];
}

/** S10-004: mock Runtime 实例列表 (Runtime Panel 演示数据源; is_mock 由
 * runtimeClient.listRuntimes fallback 标记 — 形状对齐后端 create_runtime
 * 输出: browser (url 沙箱预览) + terminal (session 会话) 各一, 诚实演示)。 */
export function mockRuntimes(projectId = 'ledger-app'): RuntimeInstance[] {
  return [
    {
      id: 'mock-rt-browser-1',
      project_id: projectId,
      type: 'browser',
      status: 'running',
      artifact_id: 'mock-art-ux_ui',
      // data: URL 沙箱预览 (演示数据 — 真实 URL 由 Runtime 服务提供)
      url: 'data:text/html;charset=utf-8,' + encodeURIComponent(
        '<h1>Browser 沙箱预览</h1><p>演示数据 — 绑定产物 mock-art-ux_ui (UX/UI)</p>',
      ),
      session: null,
      created_at: '2026-08-10T00:05:00+00:00',
    },
    {
      id: 'mock-rt-terminal-1',
      project_id: projectId,
      type: 'terminal',
      status: 'running',
      artifact_id: 'mock-art-code',
      url: null,
      session: 'mock-session-1',
      created_at: '2026-08-10T00:06:00+00:00',
    },
  ];
}

/** mock Timeline 事件流 (Agent Timeline 数据源; user/stage/artifact/review 五类)。 */
export function mockTimeline(projectId = 'ledger-app'): TimelineEventSummary[] {  const node = (
    seq: number,
    type: TimelineEventSummary['type'],
    message: string,
    extra: Partial<TimelineEventSummary> = {},
  ): TimelineEventSummary => ({
    id: `evt-${seq}`,
    seq,
    project_id: projectId,
    type,
    event_type: '',
    stage_id: null,
    agent_id: null,
    artifact_id: null,
    gate_id: null,
    message,
    status: 'OK',
    payload: {},
    created_at: '2026-08-10T00:00:00+00:00',
    ...extra,
  });

  return [
    node(1, 'user', '项目创建: 记账 App', { event_type: 'org.project.created' }),
    node(2, 'stage', '工作流启动', { event_type: 'org.workflow.started', agent_id: 'pm' }),
    node(3, 'stage', '阶段开始 PM', {
      event_type: 'org.workflow.stage_started',
      stage_id: 'mock-product',
      agent_id: 'product-manager',
    }),
    node(4, 'artifact', '产物生成', {
      event_type: 'org.artifact.created',
      artifact_id: 'mock-art-product',
    }),
    node(5, 'stage', '阶段完成 Product', {
      event_type: 'org.workflow.stage_completed',
      stage_id: 'mock-product',
      agent_id: 'product-manager',
    }),
    node(6, 'review', '审批待处理 (需求/设计/发布门)', {
      event_type: 'org.approval.created',
      gate_id: 'mock-gate-arch',
      stage_id: 'mock-architect',
    }),
  ];
}

// ---------------------------------------------------------------- S10-005 Artifact Center mock

/** mock Artifact 清单 (Artifact Center 数据源; is_mock 由 runtimeClient
 * fallback 标记)。id 按阶段约定 (mock-art-product/ux_ui/architect/developer/
 * tester/release) — 与 mockTimeline (mock-art-product 节点) 共用, Timeline
 * artifact 节点 "查看" 才能经 artifactId 定位到列表/详情。状态覆盖三态:
 * validated (绿) / failed (红) / pending (黄) — 演示状态徽章。 */
export function mockArtifacts(
  projectId = 'ledger-app',
  type?: string,
): ArtifactSummary[] {
  const base = {
    project_id: projectId,
    workflow_id: `mock-wf-${projectId}`,
    ref: 'mock://artifact',
    producer_agent: '',
    location: '',
    created_at: '2026-08-10T00:02:00+00:00',
    updated_at: '2026-08-10T00:02:00+00:00',
  };
  const all: ArtifactSummary[] = [
    {
      ...base,
      id: 'mock-art-product',
      stage_id: 'mock-product',
      type: 'product',
      ref: 'org/artifacts/product.md',
      version: '3',
      status: 'validated',
      producer_role: 'product-manager',
      location: 'org/artifacts/product.md',
    },
    {
      ...base,
      id: 'mock-art-ux_ui',
      stage_id: 'mock-ux_ui',
      type: 'ux_ui',
      ref: 'org/artifacts/ux_ui.json',
      version: '2',
      status: 'validated',
      producer_role: 'ui-designer',
      location: 'org/artifacts/ux_ui.json',
    },
    {
      ...base,
      id: 'mock-art-architect',
      stage_id: 'mock-architect',
      type: 'design',
      ref: 'org/artifacts/architecture.md',
      version: '1',
      status: 'validated',
      producer_role: 'architect',
      location: 'org/artifacts/architecture.md',
    },
    {
      ...base,
      id: 'mock-art-developer',
      stage_id: 'mock-developer',
      type: 'code',
      ref: 'org/artifacts/code.diff',
      version: '1',
      status: 'validated',
      producer_role: 'developer',
      location: 'org/artifacts/code.diff',
    },
    {
      ...base,
      id: 'mock-art-tester',
      stage_id: 'mock-tester',
      type: 'test',
      ref: 'org/artifacts/test.json',
      version: '1',
      status: 'failed',
      producer_role: 'tester',
      location: 'org/artifacts/test.json',
    },
    {
      ...base,
      id: 'mock-art-release',
      stage_id: 'mock-release',
      type: 'release',
      ref: 'org/artifacts/release-0.1.0.tar.gz',
      version: '0.1.0',
      status: 'pending',
      producer_role: 'devops',
      location: 'org/artifacts/release-0.1.0.tar.gz',
    },
  ];
  return type != null && type.length > 0 ? all.filter((a) => a.type === type) : all;
}

/** mock 单产物详情 (Detail Viewer 数据源; 6 类契约载荷 — org CONTRACTS 同源)。
 * 未知 id → 空 metadata 详情 (GenericReview 空态, 诚实不虚构)。 */
export function mockArtifactDetail(artifactId: string): ArtifactDetail {
  const summary = mockArtifacts('ledger-app').find((a) => a.id === artifactId);
  if (summary == null) {
    return {
      id: artifactId,
      stage_id: '',
      workflow_id: '',
      project_id: 'ledger-app',
      type: 'unknown',
      ref: '',
      version: '1',
      status: 'generated',
      producer_role: '',
      producer_agent: '',
      location: '',
      created_at: null,
      updated_at: null,
      metadata: {},
      review: null,
    };
  }
  const review = null;
  switch (summary.type) {
    case 'product':
      return {
        ...summary,
        review,
        metadata: {
          market_analysis: '目标市场: 个人记账用户; 竞争: 手工表格/同类记账 App',
          user_persona: '25-40 岁上班族, 需要简单记账与月度报表',
          user_journey: '记录一笔支出 → 查看分类统计 → 月底生成报表',
          feature_list: ['支出记录', '分类统计', '月度报表', '预算提醒'],
          mvp_scope: { in: ['支出记录', '分类统计'], out: ['多人协作', '资产报表'] },
          user_stories: [
            { 'as-a': '用户', 'i-want': '快速记录支出', 'so-that': '不遗漏' },
            { 'as-a': '用户', 'i-want': '查看月度分类统计', 'so-that': '控制预算' },
          ],
        },
      };
    case 'ux_ui':
      return {
        ...summary,
        review,
        metadata: {
          information_architecture: {
            screens: ['screen_home', 'screen_record', 'screen_report'],
            navigation: '底部 Tab 导航: 首页/记录/报表',
          },
          user_flow: [
            { step: '打开应用', screen: 'screen_home' },
            { step: '记录一笔支出', screen: 'screen_record' },
            { step: '查看月度报表', screen: 'screen_report' },
          ],
          wireframe: {
            screens: [
              {
                name: 'screen_home',
                ascii:
                  '+--------------------+\n|  💰 余额卡片  ¥12,400 |\n|  本月支出 ¥3,280     |\n+--------------------+\n| 近期流水            |\n|  - 早餐     ¥12.00  |\n|  - 地铁     ¥4.00   |\n|  - 咖啡     ¥28.00  |\n+--------------------+\n| [首页] [记录] [报表] |\n+--------------------+',
                components: ['BalanceCard', 'TransactionList', 'TabBar'],
                actions: ['下拉刷新', '点击流水进入详情'],
              },
              {
                name: 'screen_record',
                ascii:
                  '+--------------------+\n|  记录支出            |\n|  金额 [  ¥   ]       |\n|  分类 [ 餐饮  ▼ ]    |\n|  备注 [            ] |\n+--------------------+\n|      [ 保存 ]       |\n+--------------------+',
                components: ['AmountInput', 'CategorySelect', 'SaveButton'],
                actions: ['提交后返回首页并刷新余额'],
              },
            ],
          },
          screen_specifications: [
            {
              screen: 'screen_home',
              elements: ['余额卡片', '近期流水', '底部 Tab'],
              behaviors: ['下拉刷新流水'],
              acceptance: ['余额展示正确'],
            },
          ],
          component_definition: [
            { name: 'BalanceCard', description: '余额展示卡片', usage: '首页顶部' },
            { name: 'TabBar', description: '底部三 Tab 导航', usage: '全局' },
          ],
          design_tokens: {
            colors: { primary: '#1A73E8', background: '#FFFFFF' },
            typography: { title: '18px/600', body: '14px/400' },
            spacing: { xs: 4, sm: 8, md: 16 },
          },
          prototype: '点击底部 Tab 切换; 记录页提交后返回首页并刷新余额; 纯文本描述。',
        },
      };
    case 'design':
      return {
        ...summary,
        review,
        metadata: {
          system_architecture:
            '前端 React SPA + 后端 FastAPI + SQLite 本地存储; 单机部署, 前后端同仓',
          technical_stack: {
            frontend: ['React 18', 'TypeScript', 'Vite'],
            backend: ['Python', 'FastAPI'],
            storage: ['SQLite'],
          },
          database_design: {
            tables: ['transactions', 'categories', 'budgets'],
            note: 'transactions 主表: id/amount/category_id/note/created_at',
          },
          api_design: {
            endpoints: [
              { method: 'POST', path: '/api/transactions', desc: '新增支出记录' },
              { method: 'GET', path: '/api/reports/monthly', desc: '月度分类统计' },
            ],
          },
          frontend_architecture: '页面级组件: Home/Record/Report; 状态用轻量 Context',
          backend_architecture: '路由层 → service 层 → SQLite 仓储; 只读投影给 Console',
          task_breakdown: [
            { id: 'T1', title: '数据模型与建表', assignee: 'developer', est: '2h' },
            { id: 'T2', title: '支出记录 API', assignee: 'developer', est: '3h' },
            { id: 'T3', title: '首页与记录页 UI', assignee: 'developer', est: '4h' },
          ],
        },
      };
    case 'code':
      return {
        ...summary,
        review,
        metadata: {
          files: ['src/app.py', 'src/main.py'],
          changes:
            '--- a/src/app.py\n+++ b/src/app.py\n@@ -1,2 +1,3 @@\n def add(a, b):\n     return a + b\n+print(add(1, 2))\n',
        },
      };
    case 'test':
      return {
        ...summary,
        review,
        metadata: {
          results: {
            passed: 18,
            failed: 2,
            skipped: 1,
            duration_s: 42,
            command: 'pytest -q',
          },
          bugs: [
            { id: 'BUG-1', severity: 'high', title: '余额卡片负数显示异常', status: 'open' },
            { id: 'BUG-2', severity: 'low', title: '报表页空白态文案缺失', status: 'open' },
          ],
        },
      };
    case 'release':
      return {
        ...summary,
        review,
        metadata: {
          build_result: { status: 'success', command: 'npm run build' },
          version: '0.1.0',
          package: {
            name: 'ledger-app-0.1.0',
            type: 'tar.gz',
            files: ['dist/app.js', 'dist/index.html', 'README.md'],
          },
          release_notes: '首个可用版本: 支出记录 + 分类统计 + 月度报表。',
          deployment: {
            target: '本地沙箱 (static preview)',
            status: 'ready',
            steps: ['解压 dist 到静态目录', 'nginx 指向 index.html'],
          },
        },
      };
    default:
      return { ...summary, review, metadata: {} };
  }
}

/** mock 产物渲染内容 (GET /content 兜底; code → diff 文本, release → 包文本;
 * 其余 → null — 诚实: 无 location 文件不虚构)。 */
export function mockArtifactContent(artifactId: string): ArtifactContent {
  const base = { artifact_id: artifactId };
  if (artifactId === 'mock-art-developer') {
    return {
      ...base,
      type: 'code',
      location: 'org/artifacts/code.diff',
      content:
        '--- a/src/app.py\n+++ b/src/app.py\n@@ -1,2 +1,3 @@\n def add(a, b):\n     return a + b\n+print(add(1, 2))\n',
    };
  }
  if (artifactId === 'mock-art-release') {
    return {
      ...base,
      type: 'release',
      location: 'org/artifacts/release-0.1.0.tar.gz',
      content: 'ledger-app-0.1.0/\n  dist/app.js\n  dist/index.html\n  README.md\n',
    };
  }
  return { ...base, type: 'unknown', location: '', content: null };
}
