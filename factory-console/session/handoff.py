"""factory-console/session/handoff.py — 跨会话交接协议 ProjectSpine (S10-127 M3.1).

对标 Project Continuity (MIT 设计借鉴, 非代码复用): Spine + 权威分层 + Closure over replay。

ProjectSpine 结构 (<data_dir>/project_spine/<project_id>.json):
{
  project_id, updated_at,
  current_goal: {text, source},              # 当前目标
  active_requirements: [{text, source}],     # 当前有效需求
  handoff_card: {progress, next_steps[], blockers[], source},  # 交接面
  resume_point: {task_id, note, exec_state_file, source},      # 半路暂停物理边界
  closure_memory: [{task_id, title, summary, closed_at, source}],  # 已关闭阶段压缩记忆
  source_pointers: [{path, note, source}]    # 需要时回源证据
}

权威分层 (source 等级, 高>低; 低等级不作事实, 注入时按阈值过滤):
  user_intent(5) > verified_state(4) > repo_evidence(3) > agent_claim(2) > summary(1)

Closure over replay: 接手读 closure_memory 摘要, 不重放旧聊天。

失败安全: 文件坏/缺失 → 空 Spine 不崩; 写入 OSError 静默 (同 project_memory)。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: 权威等级 (数字越大越可信)
AUTHORITY = {
    "user_intent": 5,
    "verified_state": 4,
    "repo_evidence": 3,
    "agent_claim": 2,
    "summary": 1,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _authority_rank(source: str | None) -> int:
    return AUTHORITY.get(str(source or ""), 2)


def _blank() -> dict[str, Any]:
    return {
        "project_id": "",
        "updated_at": _now_iso(),
        "current_goal": None,
        "active_requirements": [],
        "handoff_card": None,
        "resume_point": None,
        "closure_memory": [],
        "source_pointers": [],
    }


class ProjectSpine:
    """跨会话项目交接面 (Project Spine)。"""

    def __init__(self, project_id: str, data: dict[str, Any] | None = None):
        self.project_id = project_id
        d = _blank()
        d.update(data or {})
        d["project_id"] = project_id
        self.data = d

    # ------------------------------------------------------------ 持久化
    @classmethod
    def load(cls, data_dir: str | Path | None, project_id: str) -> "ProjectSpine":
        sp = cls(project_id)
        if not data_dir or not project_id:
            return sp
        try:
            d = json.loads(
                (Path(data_dir) / "project_spine" / f"{project_id}.json").read_text(encoding="utf-8"))
            if isinstance(d, dict):
                sp.data.update(d)
                sp.data["project_id"] = project_id
        except Exception:  # noqa: BLE001 — 坏/缺 → 空 Spine 不崩
            pass
        return sp

    def save(self, data_dir: str | Path | None) -> None:
        if not data_dir or not self.project_id:
            return
        try:
            self.data["updated_at"] = _now_iso()
            path = Path(data_dir) / "project_spine" / f"{self.project_id}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------ 写入 (带权威)
    def set_current_goal(self, text: str, *, source: str = "user_intent") -> None:
        text = str(text or "").strip()
        if text:
            self.data["current_goal"] = {"text": text[:200], "source": source}

    def set_requirement(self, text: str, *, source: str = "user_intent") -> None:
        text = str(text or "").strip()
        if not text:
            return
        reqs = self.data.get("active_requirements") or []
        # 同文本去重 (升级权威)
        for r in reqs:
            if r.get("text") == text:
                if _authority_rank(source) > _authority_rank(r.get("source")):
                    r["source"] = source
                return
        reqs.append({"text": text[:200], "source": source})
        self.data["active_requirements"] = reqs[-20:]

    def set_handoff(self, *, progress: str = "", next_steps: list[str] | None = None,
                    blockers: list[str] | None = None,
                    source: str = "agent_claim") -> None:
        """交接面 (压缩前/会话结束/任务推进时写)。"""
        self.data["handoff_card"] = {
            "progress": str(progress or "")[:300],
            "next_steps": [str(x)[:120] for x in (next_steps or [])][:10],
            "blockers": [str(x)[:120] for x in (blockers or [])][:10],
            "source": source,
        }

    def set_resume_point(self, *, task_id: str = "", note: str = "",
                         exec_state_file: str = "", source: str = "verified_state") -> None:
        self.data["resume_point"] = {
            "task_id": str(task_id)[:60],
            "note": str(note)[:200],
            "exec_state_file": str(exec_state_file)[:200],
            "source": source,
        }

    def add_closure(self, *, task_id: str, title: str, summary: str,
                    source: str = "verified_state") -> None:
        """归档任务 → closure memory (Closure over replay: 只留压缩记忆)。"""
        task_id = str(task_id or "")[:60]
        title = str(title or "")[:120]
        summary = str(summary or "")[:300]
        if not task_id:
            return
        mem = self.data.get("closure_memory") or []
        for m in mem:
            if m.get("task_id") == task_id:
                m.update({"title": title, "summary": summary, "source": source,
                          "closed_at": _now_iso()})
                return
        mem.append({"task_id": task_id, "title": title, "summary": summary,
                    "closed_at": _now_iso(), "source": source})
        self.data["closure_memory"] = mem[-50:]

    def add_source_pointer(self, path: str, note: str = "", source: str = "repo_evidence") -> None:
        path = str(path or "").strip()[:200]
        if not path:
            return
        pts = self.data.get("source_pointers") or []
        for p in pts:
            if p.get("path") == path:
                return
        pts.append({"path": path, "note": str(note)[:120], "source": source})
        self.data["source_pointers"] = pts[-20:]

    # ------------------------------------------------------------ 读取 (按权威过滤)
    def view(self, min_authority: int = 3) -> str:
        """注入文本块 (只含 ≥ min_authority 的内容; 默认 repo_evidence 及以上, 不含 agent_claim/summary)。

        Closure over replay: 只投影 closure_memory 摘要, 不重放旧聊天。
        """
        lines: list[str] = ["【项目交接 Spine】(跨会话, 新会话接手用)"]
        goal = self.data.get("current_goal")
        if goal and _authority_rank(goal.get("source")) >= min_authority:
            lines.append(f"- 当前目标: {goal.get('text')}")
        for r in self.data.get("active_requirements") or []:
            if _authority_rank(r.get("source")) >= min_authority:
                lines.append(f"- 有效需求: {r.get('text')}")
        hc = self.data.get("handoff_card")
        if hc and _authority_rank(hc.get("source")) >= min_authority:
            lines.append(f"- 上次进展: {hc.get('progress') or '—'}")
            for ns in (hc.get("next_steps") or [])[:5]:
                lines.append(f"  · 下一步: {ns}")
            for bl in (hc.get("blockers") or [])[:3]:
                lines.append(f"  · 阻塞: {bl}")
        rp = self.data.get("resume_point")
        if rp and _authority_rank(rp.get("source")) >= min_authority:
            lines.append(f"- 断点: 任务 {rp.get('task_id') or '—'} ({rp.get('note') or ''})")
        cls = self.data.get("closure_memory") or []
        if cls:
            lines.append("- 已归档(摘要):")
            for m in cls[-5:]:
                lines.append(f"  · {m.get('title')}: {m.get('summary')}")
        return "\n".join(lines) if len(lines) > 1 else ""

    def summary(self) -> dict[str, Any]:
        """结构化摘要 (审计/调试用)。"""
        return {
            "project_id": self.project_id,
            "has_goal": bool(self.data.get("current_goal")),
            "requirements": len(self.data.get("active_requirements") or []),
            "has_handoff": bool(self.data.get("handoff_card")),
            "has_resume": bool(self.data.get("resume_point")),
            "closures": len(self.data.get("closure_memory") or []),
        }
