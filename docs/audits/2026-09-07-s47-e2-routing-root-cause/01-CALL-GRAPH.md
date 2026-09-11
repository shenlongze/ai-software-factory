# 01 — CALL GRAPH (真实会话 sess-59ae61e824)

WebUI msg → POST /api/sessions/{sid}/messages?stream=1
 → fastapi_adapter.api_session_send (line ~7307)
 → run_agent_native(question=body.message, history=list_messages, data_dir)
   → messages 构建: system 各引导块 + 【最近对话】(4轮) + continuation
      guide (仅当 _PROPOSAL_PATTERN 命中上轮 assistant 尾) [FACT: 本轮漏]
   → intent = understand_intent(LLM 软参考)
   → tools = _initial_tools(question): CORE 5 + discover top-k + tool_search
   → LLM function calling 自主选工具 (全 FC, 无 forced)

接受建议 (msg[4]):
  raw "接受建议，" → guide: [3]尾句号 → _PROPOSAL_PATTERN 不中 → 无 guide
  → LLM FC: project_status + project_lifecycle + project_tasks + code_scan
  → 后端 AI 文本 code_scan 说明 → 前端 S35 模板 (tool_calls 含 project_tasks)
  → UI 显示 "当前项目共有 20 个任务…" [FACT]

继续分析需求 (msg[6]):
  guide: 上轮 assistant = 工具说明文本 (非提议) → 无 guide
  → LLM FC: project_lifecycle + project_status + bash_exec + project_tasks
  → 前端 S35 模板 again → "20 个任务"

你什么情况 (未入store, 用户转述):
  → CORE 工具面 (project_status/scan/code_scan/bash 常驻) + 无 complaint
    语义 → LLM 选 4 诊断工具 [FACT by CORE 面]

谁决定 Tool: LLM (FC) [FACT]
第一次出现 project_tasks 位置: msg[5] LLM 工具选择 (FACT trace)
