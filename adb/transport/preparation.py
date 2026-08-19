from __future__ import annotations

from collections import deque
from collections.abc import Callable
from threading import Condition
from time import monotonic

from adb.server.endpoint import AdbServerEndpoint
from adb.errors import AdbError
from adb.transport.configuration import AdbConfiguredTransport
from adb.transport.resolution import (
    AdbConfiguredTransportResolutionStatus,
    resolve_configured_transport,
)
from adb.transport.connection import AdbTcpConnect, AdbTcpConnector
from adb.transport.devices.domain import AdbDevicesSnapshot, AdbTrackedDevice
from adb.transport.devices.query import AdbDevicesSnapshotReader
from adb.transport.observation.contracts import AdbObservationSessionId
from adb.transport.observation.observer import AdbDevicesObservationController
from adb.transport.observation.signal import (
    AdbDevicesObservationFailed,
    AdbDevicesObservationStarted,
    AdbDevicesObservationStopped,
    AdbDevicesSnapshotObserved,
)
from adb.transport.orchestration import (
    AdbTransportPreparation,
    AdbTransportPreparationPolicy,
    AdbTransportPreparationResult,
    AdbTransportPreparationSatisfaction,
    AdbTransportPreparationStatus,
    AdbTransportPresenceSatisfaction,
)
from adb.transport.signal import (
    AdbTransportCommandCompleted,
    AdbTransportPreparationCompleted,
)
from eventing import EventBus, EventSubscriptionToken
from native_attempt import NativeAttemptResult, NativeAttemptStatus


_MonotonicClock = Callable[[], float]


class AdbTransportPreparationOrchestrator:
    """Run presence and state gates inside one generation-fenced preparation episode.

    The observation session is caller-owned and must already be active. The orchestrator
    subscribes before taking its one-shot inventory snapshot, so state updates arriving during
    the initial probe or atomic connect attempt remain part of the same episode.
    """

    def __init__(
        self,
        endpoint: AdbServerEndpoint,
        configuration: AdbConfiguredTransport,
        snapshot_reader: AdbDevicesSnapshotReader,
        connector: AdbTcpConnector,
        event_bus: EventBus,
        observation: AdbDevicesObservationController,
        *,
        _monotonic: _MonotonicClock = monotonic,
    ) -> None:
        if not isinstance(endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(configuration, AdbConfiguredTransport):
            raise TypeError("configuration must be AdbConfiguredTransport")
        if configuration.endpoint != endpoint:
            raise ValueError("configured transport endpoint does not match ADB server endpoint")
        if not callable(getattr(snapshot_reader, "read", None)):
            raise TypeError("snapshot_reader must provide read()")
        if not callable(getattr(connector, "connect", None)):
            raise TypeError("connector must provide connect()")
        if not callable(getattr(event_bus, "publish", None)) or not callable(
            getattr(event_bus, "subscribe", None)
        ) or not callable(getattr(event_bus, "unsubscribe", None)):
            raise TypeError("event_bus must satisfy EventBus")
        if not isinstance(observation, AdbDevicesObservationController):
            raise TypeError("observation must satisfy observation controller")
        self.endpoint = endpoint
        self.configuration = configuration
        self._snapshot_reader = snapshot_reader
        self._connector = connector
        self._bus = event_bus
        self._observation = observation
        self._monotonic = _monotonic

    def prepare(
        self,
        operation: AdbTransportPreparation,
        policy: AdbTransportPreparationPolicy,
    ) -> AdbTransportPreparationResult:
        if not isinstance(operation, AdbTransportPreparation):
            raise TypeError("operation must be AdbTransportPreparation")
        if not isinstance(policy, AdbTransportPreparationPolicy):
            raise TypeError("policy must be AdbTransportPreparationPolicy")
        if operation.endpoint != self.endpoint:
            raise ValueError("operation endpoint does not match configured ADB server endpoint")
        if operation.serial != self.configuration.serial:
            raise ValueError("operation serial does not match configured ADB transport")

        session_id = self._observation.active_session_id
        if session_id is None:
            raise RuntimeError("transport preparation requires an active observation session")
        if session_id.endpoint != operation.endpoint:
            raise ValueError("active observation session belongs to another ADB server endpoint")

        deadline = self._monotonic() + policy.timeout_seconds
        condition = Condition()
        events: deque[object] = deque()

        def collect(event: object) -> None:
            with condition:
                events.append(event)
                condition.notify()

        subscriptions = self._subscribe(collect)
        try:
            return self._run_episode(
                operation,
                policy,
                session_id,
                deadline,
                condition,
                events,
            )
        finally:
            for token in subscriptions:
                self._bus.unsubscribe(token)

    def _subscribe(self, collect: Callable[[object], None]) -> tuple[EventSubscriptionToken, ...]:
        return (
            self._bus.subscribe(AdbDevicesSnapshotObserved, collect),
            self._bus.subscribe(AdbDevicesObservationFailed, collect),
            self._bus.subscribe(AdbDevicesObservationStopped, collect),
            self._bus.subscribe(AdbDevicesObservationStarted, collect),
        )

    def _run_episode(
        self,
        operation: AdbTransportPreparation,
        policy: AdbTransportPreparationPolicy,
        session_id: AdbObservationSessionId,
        deadline: float,
        condition: Condition,
        events: deque[object],
    ) -> AdbTransportPreparationResult:
        attempts: list[NativeAttemptResult] = []
        presence: AdbTransportPresenceSatisfaction | None = None
        final_snapshot: AdbDevicesSnapshot | None = None
        final_row: AdbTrackedDevice | None = None
        initial_snapshot_processed = False
        connect_attempted = False
        diagnostic: str | None = None

        try:
            snapshot = self._snapshot_reader.read(self.endpoint)
        except AdbError as exc:
            diagnostic = str(exc) or exc.__class__.__name__
        else:
            initial_snapshot_processed = True
            final_snapshot = snapshot
            outcome = self._evaluate_snapshot(
                snapshot,
                policy,
                presence,
                initial=True,
            )
            presence, final_row, terminal = outcome
            if terminal is not None:
                return self._complete(
                    operation,
                    policy,
                    session_id,
                    terminal,
                    attempts,
                    presence,
                    final_snapshot,
                    final_row,
                    diagnostic,
                    already_satisfied=(
                        terminal is AdbTransportPreparationStatus.SATISFIED
                    ),
                )
            if presence is None and self.configuration.connect_address is not None:
                connect_attempted = True
                attempts.append(self._connect())

        while True:
            if not initial_snapshot_processed and not connect_attempted:
                # An indeterminate one-shot query does not prove absence, so wait for the
                # generation-fenced observation stream before deciding whether to connect.
                pass

            event = self._next_event(condition, events, deadline)
            if event is None:
                terminal = (
                    AdbTransportPreparationStatus.FAILED
                    if attempts and attempts[-1].status is NativeAttemptStatus.FAILED
                    else AdbTransportPreparationStatus.TIMED_OUT
                )
                return self._complete(
                    operation,
                    policy,
                    session_id,
                    terminal,
                    attempts,
                    presence,
                    final_snapshot,
                    final_row,
                    diagnostic,
                )

            event_session = getattr(event, "session_id", None)
            if isinstance(event_session, AdbObservationSessionId):
                if event_session.endpoint != session_id.endpoint:
                    continue
                if event_session.generation < session_id.generation:
                    continue
                if event_session.generation > session_id.generation:
                    return self._complete(
                        operation,
                        policy,
                        session_id,
                        AdbTransportPreparationStatus.OBSERVATION_REPLACED,
                        attempts,
                        presence,
                        final_snapshot,
                        final_row,
                        "transport inventory observation generation changed",
                    )

            if isinstance(event, AdbDevicesObservationFailed):
                return self._complete(
                    operation,
                    policy,
                    session_id,
                    AdbTransportPreparationStatus.OBSERVATION_FAILED,
                    attempts,
                    presence,
                    final_snapshot,
                    final_row,
                    event.diagnostic or f"observation failed: {event.failure.value}",
                )
            if isinstance(event, AdbDevicesObservationStopped):
                return self._complete(
                    operation,
                    policy,
                    session_id,
                    AdbTransportPreparationStatus.OBSERVATION_STOPPED,
                    attempts,
                    presence,
                    final_snapshot,
                    final_row,
                    "transport inventory observation stopped",
                )
            if isinstance(event, AdbDevicesObservationStarted):
                continue
            if not isinstance(event, AdbDevicesSnapshotObserved):
                continue

            final_snapshot = event.snapshot
            outcome = self._evaluate_snapshot(
                event.snapshot,
                policy,
                presence,
                initial=False,
            )
            presence, final_row, terminal = outcome
            initial_snapshot_processed = True
            if terminal is not None:
                return self._complete(
                    operation,
                    policy,
                    session_id,
                    terminal,
                    attempts,
                    presence,
                    final_snapshot,
                    final_row,
                    diagnostic,
                )
            if (
                presence is None
                and not connect_attempted
                and self.configuration.connect_address is not None
            ):
                connect_attempted = True
                attempts.append(self._connect())

    def _evaluate_snapshot(
        self,
        snapshot: AdbDevicesSnapshot,
        policy: AdbTransportPreparationPolicy,
        presence: AdbTransportPresenceSatisfaction | None,
        *,
        initial: bool,
    ) -> tuple[
        AdbTransportPresenceSatisfaction | None,
        AdbTrackedDevice | None,
        AdbTransportPreparationStatus | None,
    ]:
        resolution = resolve_configured_transport(self.configuration, snapshot)

        if resolution.status is AdbConfiguredTransportResolutionStatus.AMBIGUOUS:
            return presence, None, AdbTransportPreparationStatus.AMBIGUOUS
        if resolution.status is AdbConfiguredTransportResolutionStatus.ABSENT:
            return presence, None, None

        row = resolution.row
        assert row is not None
        if presence is None:
            presence = (
                AdbTransportPresenceSatisfaction.ALREADY_PRESENT
                if initial
                else AdbTransportPresenceSatisfaction.OBSERVED
            )

        if row.state in policy.acceptable_states:
            return presence, row, AdbTransportPreparationStatus.SATISFIED
        if row.state in policy.blocked_states:
            return presence, row, AdbTransportPreparationStatus.BLOCKED
        return presence, row, None

    def _connect(self) -> NativeAttemptResult:
        address = self.configuration.connect_address
        assert address is not None
        command = AdbTcpConnect(address)
        attempt = self._connector.connect(command)
        self._bus.publish(AdbTransportCommandCompleted(command, attempt))
        return attempt

    def _next_event(
        self,
        condition: Condition,
        events: deque[object],
        deadline: float,
    ) -> object | None:
        with condition:
            while not events:
                remaining = deadline - self._monotonic()
                if remaining <= 0.0:
                    return None
                condition.wait(timeout=remaining)
            return events.popleft()

    def _complete(
        self,
        operation: AdbTransportPreparation,
        policy: AdbTransportPreparationPolicy,
        session_id: AdbObservationSessionId,
        status: AdbTransportPreparationStatus,
        attempts: list[NativeAttemptResult],
        presence: AdbTransportPresenceSatisfaction | None,
        final_snapshot: AdbDevicesSnapshot | None,
        final_row: AdbTrackedDevice | None,
        diagnostic: str | None,
        *,
        already_satisfied: bool = False,
    ) -> AdbTransportPreparationResult:
        satisfaction = None
        if status is AdbTransportPreparationStatus.SATISFIED:
            satisfaction = (
                AdbTransportPreparationSatisfaction.ALREADY_SATISFIED
                if already_satisfied
                else AdbTransportPreparationSatisfaction.ACHIEVED
            )
        result = AdbTransportPreparationResult(
            operation=operation,
            policy=policy,
            status=status,
            satisfaction=satisfaction,
            presence_satisfaction=presence,
            observation_session_id=session_id,
            attempts=tuple(attempts),
            final_snapshot=final_snapshot,
            final_row=final_row,
            diagnostic=diagnostic,
        )
        self._bus.publish(AdbTransportPreparationCompleted(result))
        return result


__all__ = ["AdbTransportPreparationOrchestrator"]
