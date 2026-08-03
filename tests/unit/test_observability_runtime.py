from __future__ import annotations

from pathlib import Path

from docfit.observability.benchmark import measure_operation
from docfit.observability.runtime import (
    BootstrapObservationRecorder,
    NullObservationRecorder,
    close_observation_safely,
    create_observation_recorder,
)


def test_disabled_recorder_has_no_filesystem_side_effect(tmp_path: Path) -> None:
    state_home = tmp_path / "state"

    recorder = create_observation_recorder(
        "off",
        environment={"XDG_STATE_HOME": str(state_home)},
        task_root=tmp_path / "task",
        repository_root=tmp_path / "repository",
    )

    assert isinstance(recorder, NullObservationRecorder)
    assert recorder.enabled is False
    assert recorder.state_root is None
    assert recorder.failure_code is None
    assert not state_home.exists()


def test_auto_recorder_bootstraps_external_store(tmp_path: Path) -> None:
    task = tmp_path / "task"
    repository = tmp_path / "repository"
    task.mkdir()
    repository.mkdir()

    recorder = create_observation_recorder(
        "auto",
        environment={"XDG_STATE_HOME": str(tmp_path / "state")},
        task_root=task,
        repository_root=repository,
    )

    assert isinstance(recorder, BootstrapObservationRecorder)
    assert recorder.enabled is True
    assert recorder.database.is_file()


def test_auto_setup_failure_degrades_to_null(tmp_path: Path) -> None:
    task = tmp_path / "task"
    task.mkdir()

    recorder = create_observation_recorder(
        "auto",
        environment={"XDG_STATE_HOME": str(task)},
        task_root=task,
        repository_root=tmp_path / "repository",
    )

    assert isinstance(recorder, NullObservationRecorder)
    assert recorder.failure_code == "observer_state_not_external"


def test_close_failure_never_escapes_conversion_boundary() -> None:
    class BrokenRecorder(NullObservationRecorder):
        def close(self) -> None:
            raise RuntimeError("sensitive close detail")

    close_observation_safely(BrokenRecorder())


def test_benchmark_helper_reports_wall_cpu_and_rss() -> None:
    calls: list[int] = []
    result = measure_operation(lambda: calls.append(1), iterations=3)

    assert calls == [1, 1, 1]
    assert result.iterations == 3
    assert result.wall_seconds >= 0
    assert result.cpu_seconds >= 0
    assert result.peak_rss_bytes > 0
