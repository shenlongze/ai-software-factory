"""operations — 运维域（8 环的第 8 环）。

域归属依据（2026-09-15，Founder 裁决）:
  运维在老系统里是**完整一环** —— 有独立命令域（factory ops / doctor）、
  14 个模块 4,399 行（健康/恢复/回滚/自愈/备份/监控/存活/调度/投影），
  不是 execution 或 metrics 的附属 ⇒ 独立成 services/ 的第 10 个域。

  SSoT 服务域清单同步为 10 个:
    conversation · execution · governance · learning · metrics · organization ·
    operations · resource · validation · work

边界: 运维关注「系统持续健康运行」（监控/健康/恢复/回滚/备份/自愈）;
      执行（execution）关注「把活干完」; 度量（metrics）关注「看指标」。
"""
