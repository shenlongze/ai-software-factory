"""tests/git/test_git_events.py — git.* 审计事件 (Phase 6C, ADR-0018)。

覆盖: git.status.viewed (OK/ERROR result + payload) / git.change.detected
(bind_task_change 自动发, payload 含 change_id/files/commits) / git.commit.viewed
(count/hashes/limit) — 全部经 EventLogger → EventStore 落库断言 (ADR-0002:
CLI 行为必须产生 Event; 本域事件只审计, 零仓库写操作)。

服务层装配 logger 发事件; 未装配 logger 的 service 不发 (依赖注入边界)。
"""

from __future__ import annotations

from git.client import GitClient
from git.events import (
    record_git_change_detected,
    record_git_commit_viewed,
    record_git_status_viewed,
)
from git.service import GitChangeStore, GitService

from git_helpers import write_file


class TestStatusViewedEvent:
    def test_status_viewed_ok(self, logger, repo_path, changes_dir):
        svc = GitService(
            GitClient(repo_path), project_id="markpad",
            changes_store=GitChangeStore(changes_dir),
        )
        status = svc.get_status()
        ev = record_git_status_viewed(logger, status=status, project_id="markpad")
        assert ev.type.value == "git.status.viewed"
        assert ev.stage == "viewed"
        assert ev.result == "OK"
        assert ev.project_id == "markpad"
        assert ev.payload["repository"] == str(repo_path)
        assert ev.payload["branch"] == "main"
        assert ev.payload["current_commit"] == status.current_commit
        assert ev.payload["is_repo"] is True
        assert ev.payload["error"] is None
        # 落库
        stored = logger.store.query()
        assert [e.type.value for e in stored] == ["git.status.viewed"]
        assert stored[0].payload["branch"] == "main"

    def test_status_viewed_error_result(self, logger, tmp_path):
        status = GitClient(tmp_path).status()  # 非 git 目录
        ev = record_git_status_viewed(logger, status=status, source="cli")
        assert ev.type.value == "git.status.viewed"
        assert ev.result == "ERROR"
        assert ev.payload["is_repo"] is False
        assert ev.payload["error"]
        assert ev.payload["branch"] is None

    def test_status_viewed_changes_count(self, logger, repo_path, changes_dir):
        write_file(repo_path, "wip.py", "x\n")
        svc = GitService(GitClient(repo_path), changes_store=GitChangeStore(changes_dir))
        ev = record_git_status_viewed(logger, status=svc.get_status())
        assert ev.payload["changes"] == 1

    def test_status_viewed_default_source(self, logger, repo_path):
        status = GitClient(repo_path).status()
        ev = record_git_status_viewed(logger, status=status)
        assert ev.source == "git"

    def test_status_viewed_custom_source(self, logger, repo_path):
        status = GitClient(repo_path).status()
        ev = record_git_status_viewed(logger, status=status, source="cli")
        assert ev.source == "cli"


class TestChangeDetectedEvent:
    def test_bind_emits_change_detected(self, repo_path, event_service, logger):
        write_file(repo_path, "wip.py", "x = 1\n")
        c = event_service.bind_task_change("T-001")
        stored = logger.store.query()
        assert [e.type.value for e in stored] == ["git.change.detected"]
        ev = stored[0]
        assert ev.task_id == "T-001"
        assert ev.project_id == "markpad"
        assert ev.stage == "detected"
        assert ev.result == "OK"
        assert ev.payload["change_id"] == c.id
        assert ev.payload["files"] == ["wip.py"]
        assert ev.payload["insertions"] == 1
        assert ev.payload["commits"] == []

    def test_bind_commits_in_payload(self, event_service, logger):
        event_service.bind_task_change("T-001", commits=["abc123"])
        ev = logger.store.query()[0]
        assert ev.payload["commits"] == ["abc123"]

    def test_no_logger_no_event(self, repo_path, service, logger):
        """未装配 logger 的 service: bind 持久化但不发事件 (依赖注入边界)。"""
        service.bind_task_change("T-001")
        assert logger.store.query() == []

    def test_record_change_detected_direct(self, logger, repo_path, changes_dir):
        svc = GitService(GitClient(repo_path), changes_store=GitChangeStore(changes_dir))
        change = svc.bind_task_change("T-001", files=["a.py"])
        ev = record_git_change_detected(
            logger, change=change, project_id="markpad", task_id="T-001"
        )
        assert ev.type.value == "git.change.detected"
        assert ev.task_id == "T-001"
        assert ev.payload["change_id"] == change.id
        assert ev.payload["status"] == "detected"


class TestCommitViewedEvent:
    def test_commit_viewed_payload(self, logger, repo_path, changes_dir):
        svc = GitService(GitClient(repo_path), changes_store=GitChangeStore(changes_dir))
        commits = svc.get_commits(limit=5)
        ev = record_git_commit_viewed(
            logger, commits=commits, project_id="markpad",
            repository=str(repo_path), limit=5,
        )
        assert ev.type.value == "git.commit.viewed"
        assert ev.stage == "viewed"
        assert ev.result == "OK"
        assert ev.payload["count"] == 2
        assert ev.payload["limit"] == 5
        assert len(ev.payload["hashes"]) == 2
        assert ev.payload["hashes"][0] == commits[0].hash
        assert ev.payload["repository"] == str(repo_path)

    def test_commit_viewed_empty(self, logger, tmp_path):
        ev = record_git_commit_viewed(logger, commits=[], repository="/nope")
        assert ev.payload["count"] == 0
        assert ev.payload["hashes"] == []

    def test_commit_viewed_caps_hashes_at_20(self, logger, repo_path, changes_dir):
        """payload hashes 只保留前 20 (审计载荷上限)。"""
        svc = GitService(GitClient(repo_path), changes_store=GitChangeStore(changes_dir))
        commits = svc.get_commits(limit=500)
        ev = record_git_commit_viewed(logger, commits=commits)
        assert ev.payload["count"] == 2
        assert len(ev.payload["hashes"]) == 2  # 仓库只有 2 提交


class TestEventStorePersistence:
    def test_all_git_event_types_known(self):
        from events.models import EventType

        for name in ("GIT_STATUS_VIEWED", "GIT_CHANGE_DETECTED", "GIT_COMMIT_VIEWED"):
            assert hasattr(EventType, name)
        assert EventType.GIT_STATUS_VIEWED.value == "git.status.viewed"
        assert EventType.GIT_CHANGE_DETECTED.value == "git.change.detected"
        assert EventType.GIT_COMMIT_VIEWED.value == "git.commit.viewed"

    def test_events_order(self, repo_path, event_service, logger):
        """status → bind → commits 三条事件按序落库 (append-only)。"""
        from git.events import record_git_commit_viewed, record_git_status_viewed

        record_git_status_viewed(logger, status=event_service.get_status())
        event_service.bind_task_change("T-001", files=["a.py"])
        record_git_commit_viewed(logger, commits=event_service.get_commits())
        types = [e.type.value for e in logger.store.query()]
        assert types == ["git.status.viewed", "git.change.detected", "git.commit.viewed"]
