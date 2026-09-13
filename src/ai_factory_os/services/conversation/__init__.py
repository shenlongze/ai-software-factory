"""services.conversation — 会话（唯一人类入口）。

拥有契约：contracts/conversation.py
会话只承载"用户表达目标"，不承载流程状态、不规定步骤。
不负责：目标的结构化（由 Project/Work/Task 承接）、调度与执行。
"""
