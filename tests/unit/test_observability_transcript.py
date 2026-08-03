from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

import pytest

from docfit.observability.transcript import (
    SDKTranscriptManager,
    SDKTranscriptRuntimeError,
    isolated_sdk_environment,
)


def _mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def test_attempt_is_private_unique_and_removed_without_reading_payload(tmp_path: Path) -> None:
    parent = tmp_path / "runtime" / "sdk-transcripts"
    manager = SDKTranscriptManager(parent=parent)
    seen: list[Path] = []

    for _ in range(2):
        with manager.attempt() as attempt:
            seen.append(attempt)
            assert _mode(parent) == 0o700
            assert _mode(attempt) == 0o700
            assert _mode(attempt / ".owner.json") == 0o600
            assert _mode(attempt / ".active.lock") == 0o600
            (attempt / "session-canary.jsonl").write_text(
                "PRIVATE_TRANSCRIPT_CANARY", encoding="utf-8"
            )
            assert manager.summary().status == "active"
        assert not attempt.exists()

    assert seen[0] != seen[1]
    summary = manager.summary()
    assert summary.status == "cleaned"
    assert summary.residual_count == 0
    assert "PRIVATE_TRANSCRIPT_CANARY" not in json.dumps(asdict(summary))


def test_preflight_preserves_an_active_attempt(tmp_path: Path) -> None:
    parent = tmp_path / "transcripts"
    owner = SDKTranscriptManager(parent=parent)

    with owner.attempt() as attempt:
        observer = SDKTranscriptManager(parent=parent)
        assert attempt.is_dir()
        assert observer.summary().status == "residual"
        assert observer.summary().residual_count == 1

    cleanup = SDKTranscriptManager(parent=parent)
    assert cleanup.summary().residual_count == 0


def test_preflight_reclaims_force_terminated_owned_attempt(tmp_path: Path) -> None:
    parent = tmp_path / "transcripts"
    script = """
import sys
import time
from pathlib import Path
from docfit.observability.transcript import SDKTranscriptManager

manager = SDKTranscriptManager(parent=Path(sys.argv[1]))
with manager.attempt():
    print("READY", flush=True)
    time.sleep(120)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(parent)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "READY"
    process.kill()
    process.wait(timeout=10)
    assert any(parent.iterdir())

    manager = SDKTranscriptManager(parent=parent)

    assert not tuple(parent.iterdir())
    assert manager.summary().residual_count == 0


def test_preflight_never_follows_attempt_symlink(tmp_path: Path) -> None:
    parent = tmp_path / "transcripts"
    manager = SDKTranscriptManager(parent=parent)
    target = tmp_path / "outside"
    target.mkdir()
    canary = target / "keep.txt"
    canary.write_text("keep", encoding="utf-8")
    link = parent / "attempt-malicious"
    link.symlink_to(target, target_is_directory=True)

    manager.preflight()

    assert link.is_symlink()
    assert canary.read_text(encoding="utf-8") == "keep"
    assert "sdk_transcript_residual_symlink" in manager.summary().failure_codes


def test_preflight_removes_old_uncertain_current_user_directory(tmp_path: Path) -> None:
    now = time.time()
    parent = tmp_path / "transcripts"
    manager = SDKTranscriptManager(parent=parent, now=lambda: now)
    uncertain = parent / "attempt-uncertain"
    uncertain.mkdir(mode=0o700)
    old = now - (25 * 60 * 60)
    os.utime(uncertain, (old, old))

    manager.preflight()

    assert not uncertain.exists()


def test_recent_uncertain_directory_is_retained_with_age_bucket(tmp_path: Path) -> None:
    now = time.time()
    parent = tmp_path / "transcripts"
    manager = SDKTranscriptManager(parent=parent, now=lambda: now)
    uncertain = parent / "attempt-uncertain"
    uncertain.mkdir(mode=0o700)

    manager.preflight()

    summary = manager.summary()
    assert uncertain.is_dir()
    assert summary.status == "residual"
    assert summary.residual_count == 1
    assert summary.oldest_age_bucket == "under_1h"


def test_unsafe_parent_never_falls_back_to_global_sdk_config(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    parent = tmp_path / "transcripts"
    parent.symlink_to(outside, target_is_directory=True)
    manager = SDKTranscriptManager(parent=parent)

    with pytest.raises(SDKTranscriptRuntimeError) as failure, manager.attempt():
        raise AssertionError("attempt must not start")

    assert failure.value.code == "sdk_transcript_parent_unsafe"
    assert not tuple(outside.iterdir())
    assert manager.summary().status == "unknown"


def test_cleanup_failure_is_summarized_without_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "transcripts"
    manager = SDKTranscriptManager(parent=parent)
    original = __import__("shutil").rmtree

    def fail_cleanup(path: Path) -> None:
        raise OSError("PRIVATE_TRANSCRIPT_PATH_CANARY")

    monkeypatch.setattr("docfit.observability.transcript.shutil.rmtree", fail_cleanup)
    with manager.attempt():
        pass

    summary = manager.summary()
    assert summary.status == "cleanup_failed"
    assert summary.residual_count == 1
    assert summary.failure_codes == ("sdk_transcript_cleanup_failed",)
    assert "PRIVATE_TRANSCRIPT_PATH_CANARY" not in str(summary)

    monkeypatch.setattr("docfit.observability.transcript.shutil.rmtree", original)
    recovered = SDKTranscriptManager(parent=parent)
    assert recovered.summary().residual_count == 0


def test_inherited_global_config_is_always_overridden(tmp_path: Path) -> None:
    attempt = tmp_path / "attempt"

    environment = isolated_sdk_environment(
        {
            "CLAUDE_CONFIG_DIR": "/user/global/config",
            "ANTHROPIC_API_KEY": "secret",
        },
        attempt,
    )

    assert environment["CLAUDE_CONFIG_DIR"] == str(attempt)
    assert environment["ANTHROPIC_API_KEY"] == "secret"


def test_parent_inside_task_or_repository_is_rejected(tmp_path: Path) -> None:
    task = tmp_path / "task"
    manager = SDKTranscriptManager(
        parent=task / "runtime",
        forbidden_roots=(task,),
    )

    with pytest.raises(SDKTranscriptRuntimeError) as failure, manager.attempt():
        raise AssertionError("attempt must not start")

    assert failure.value.code == "sdk_transcript_parent_forbidden"
    assert not task.exists()


def test_preflight_reclaims_marker_written_before_lock_after_owner_exit(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "transcripts"
    manager = SDKTranscriptManager(parent=parent)
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    owner_pid = process.pid
    process.wait(timeout=10)
    nonce = "ab" * 16
    attempt = parent / f"attempt-{nonce}"
    attempt.mkdir(mode=0o700)
    marker = attempt / ".owner.json"
    marker.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "owner_pid": owner_pid,
                "created_at_epoch": int(time.time()),
                "nonce": nonce,
            }
        ),
        encoding="utf-8",
    )
    marker.chmod(0o600)

    manager.preflight()

    assert not attempt.exists()
