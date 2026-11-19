"""Unit tests for the shared LSM/PS-OCT state guards."""

from types import SimpleNamespace

import pytest

import opticstream.state.state_guards as state_guards
from opticstream.state.lsm_project_state import LSMChannelId, LSMStripId
from opticstream.state.oct_project_state import OCTBatchId, OCTMosaicId
from opticstream.state.project_state_core import ProcessingState
from opticstream.state.state_guards import (
    RunDecision,
    enter_flow_stage,
    enter_milestone_stage,
    force_rerun_from_payload,
    should_skip_run,
)


class _RecordingLogger:
    def __init__(self) -> None:
        self.info_messages: list[str] = []
        self.warning_messages: list[str] = []

    def info(self, message: str, *_args, **_kwargs) -> None:
        self.info_messages.append(message)

    def warning(self, message: str, *_args, **_kwargs) -> None:
        self.warning_messages.append(message)


@pytest.fixture(autouse=True)
def recording_logger(monkeypatch) -> _RecordingLogger:
    """Keep decision tests independent of a running Prefect flow context."""
    logger = _RecordingLogger()
    monkeypatch.setattr(state_guards, "get_run_logger", lambda: logger)
    return logger


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({}, False),
        ({"force_rerun": False}, False),
        ({"force_rerun": True}, True),
        ({"force_rerun": 1}, True),
        ({"force_rerun": 0}, False),
    ],
)
def test_force_rerun_from_payload(payload, expected):
    assert force_rerun_from_payload(payload) is expected


@pytest.mark.parametrize(
    (
        "processing_state",
        "force_rerun",
        "skip_if_running",
        "expected_decision",
        "expected_started_calls",
    ),
    [
        (None, False, False, RunDecision.STARTED, 1),
        (ProcessingState.PENDING, False, False, RunDecision.STARTED, 1),
        (ProcessingState.FAILED, False, False, RunDecision.STARTED, 1),
        (ProcessingState.COMPLETED, False, False, RunDecision.SKIPPED, 0),
        (ProcessingState.COMPLETED, True, False, RunDecision.RESTARTED, 1),
        (ProcessingState.RUNNING, False, True, RunDecision.SKIPPED, 0),
        (ProcessingState.RUNNING, True, True, RunDecision.RESTARTED, 1),
        (ProcessingState.RUNNING, False, False, RunDecision.STARTED, 1),
    ],
)
def test_enter_flow_stage_decisions(
    processing_state,
    force_rerun,
    skip_if_running,
    expected_decision,
    expected_started_calls,
):
    calls = {"started": 0}
    view = (
        None
        if processing_state is None
        else SimpleNamespace(processing_state=processing_state)
    )

    decision = enter_flow_stage(
        view,
        force_rerun=force_rerun,
        skip_if_running=skip_if_running,
        item_ident="item-1",
        mark_started=lambda: calls.__setitem__("started", calls["started"] + 1),
    )

    assert decision == expected_decision
    assert calls["started"] == expected_started_calls


def test_forced_running_flow_warns(recording_logger):
    decision = enter_flow_stage(
        SimpleNamespace(processing_state=ProcessingState.RUNNING),
        force_rerun=True,
        skip_if_running=True,
        item_ident="item-1",
        mark_started=lambda: None,
    )

    assert decision == RunDecision.RESTARTED
    assert any("duplicate processing" in msg for msg in recording_logger.warning_messages)


@pytest.mark.parametrize(
    (
        "item_state_view",
        "force_rerun",
        "expected_decision",
        "expected_reset_calls",
    ),
    [
        (None, False, RunDecision.STARTED, 1),
        (SimpleNamespace(), False, RunDecision.STARTED, 1),
        (SimpleNamespace(uploaded=False), False, RunDecision.STARTED, 1),
        (SimpleNamespace(uploaded=True), False, RunDecision.SKIPPED, 0),
        (SimpleNamespace(uploaded=True), True, RunDecision.RESTARTED, 1),
    ],
)
def test_enter_milestone_stage_decisions(
    item_state_view,
    force_rerun,
    expected_decision,
    expected_reset_calls,
):
    calls = {"reset": 0}

    decision = enter_milestone_stage(
        item_state_view=item_state_view,
        item_ident="item-1",
        field_name="uploaded",
        force_rerun=force_rerun,
        reset=lambda: calls.__setitem__("reset", calls["reset"] + 1),
    )

    assert decision == expected_decision
    assert calls["reset"] == expected_reset_calls


@pytest.mark.parametrize(
    "decision,expected",
    [
        (RunDecision.SKIPPED, True),
        (RunDecision.STARTED, False),
        (RunDecision.RESTARTED, False),
    ],
)
def test_should_skip_run(decision, expected):
    assert should_skip_run(decision) is expected


class _StateContext:
    def __init__(self, state) -> None:
        self.state = state

    def __enter__(self):
        return self.state

    def __exit__(self, *_args) -> None:
        return None


class _RecordingState:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def mark_started(self) -> None:
        self.calls.append("mark_started")

    def reset_uploaded(self) -> None:
        self.calls.append("reset_uploaded")


class _RecordingService:
    def __init__(self, state) -> None:
        self.state = state
        self.calls: list[str] = []

    def _open(self, name: str) -> _StateContext:
        self.calls.append(name)
        return _StateContext(self.state)

    def open_strip(self, *, strip_ident) -> _StateContext:
        return self._open("open_strip")

    def open_channel(self, *, channel_ident) -> _StateContext:
        return self._open("open_channel")

    def open_batch(self, *, batch_ident) -> _StateContext:
        return self._open("open_batch")

    def open_mosaic(self, *, mosaic_ident) -> _StateContext:
        return self._open("open_mosaic")


@pytest.mark.parametrize(
    "item_ident,service_name,open_method",
    [
        (
            LSMStripId(project_name="p", slice_id=1, channel_id=2, strip_id=3),
            "LSM_STATE_SERVICE",
            "open_strip",
        ),
        (
            LSMChannelId(project_name="p", slice_id=1, channel_id=2),
            "LSM_STATE_SERVICE",
            "open_channel",
        ),
        (
            OCTBatchId(
                project_name="p", slice_id=1, mosaic_id=2, batch_id=3
            ),
            "OCT_STATE_SERVICE",
            "open_batch",
        ),
        (
            OCTMosaicId(project_name="p", slice_id=1, mosaic_id=2),
            "OCT_STATE_SERVICE",
            "open_mosaic",
        ),
    ],
)
def test_default_state_service_routing(
    monkeypatch,
    item_ident,
    service_name,
    open_method,
):
    state = _RecordingState()
    service = _RecordingService(state)
    monkeypatch.setattr(state_guards, service_name, service)

    decision = enter_flow_stage(
        None,
        force_rerun=False,
        skip_if_running=False,
        item_ident=item_ident,
    )

    assert decision == RunDecision.STARTED
    assert service.calls == [open_method]
    assert state.calls == ["mark_started"]


def test_default_milestone_reset(monkeypatch):
    state = _RecordingState()
    service = _RecordingService(state)
    monkeypatch.setattr(state_guards, "LSM_STATE_SERVICE", service)

    decision = enter_milestone_stage(
        item_state_view=SimpleNamespace(uploaded=False),
        item_ident=LSMStripId(
            project_name="p", slice_id=1, channel_id=2, strip_id=3
        ),
        field_name="uploaded",
        force_rerun=False,
    )

    assert decision == RunDecision.STARTED
    assert service.calls == ["open_strip"]
    assert state.calls == ["reset_uploaded"]


def test_default_state_service_rejects_unsupported_identifier():
    with pytest.raises(TypeError, match="unsupported item_ident type"):
        enter_flow_stage(
            None,
            force_rerun=False,
            skip_if_running=False,
            item_ident="unsupported",
        )


@pytest.mark.parametrize(
    "entrypoint,missing_method",
    [
        ("flow", "mark_started"),
        ("milestone", "reset_uploaded"),
    ],
)
def test_default_state_mutation_requires_expected_method(
    monkeypatch,
    entrypoint,
    missing_method,
):
    service = _RecordingService(SimpleNamespace())
    monkeypatch.setattr(state_guards, "LSM_STATE_SERVICE", service)
    item_ident = LSMStripId(
        project_name="p", slice_id=1, channel_id=2, strip_id=3
    )

    with pytest.raises(AttributeError, match=missing_method):
        if entrypoint == "flow":
            enter_flow_stage(
                None,
                force_rerun=False,
                skip_if_running=False,
                item_ident=item_ident,
            )
        else:
            enter_milestone_stage(
                item_state_view=SimpleNamespace(uploaded=False),
                item_ident=item_ident,
                field_name="uploaded",
                force_rerun=False,
            )
