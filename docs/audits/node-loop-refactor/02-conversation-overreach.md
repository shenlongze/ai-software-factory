# 02 Conversation Overreach
- Conversation 层承担: 阶段判断 (governor continue/domain)、下一步决策
  (resolver next_action)、执行语义 (exec 指令/克制)、状态 (conv_state
  active_work/next_action)、幂等引导 (guide 文本)
- 这些在 Hermes 模型 = LLM 自决 + 上下文; 在 Node 模型 = NodeRun checkpoint;
  Conversation 层模拟 = 拆东墙根因 (S47-S50 补丁面)
- 收敛: 保留 intent 识别 + 生产安全; 执行语义迁移 NodeRun; 不删 governor
  整体 (保留作 intent adapter), 删其"执行指导"职责
