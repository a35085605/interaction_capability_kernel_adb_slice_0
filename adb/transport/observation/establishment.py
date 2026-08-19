from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import math
from numbers import Real
from threading import Condition
from time import monotonic

from adb.server.endpoint import AdbServerEndpoint
from adb.transport.observation.contracts import AdbObservationSessionId
from adb.transport.observation.observer import AdbDevicesObservationController
from adb.transport.observation.signal import (
    AdbDevicesObservationFailed,
    AdbDevicesObservationFailure,
    AdbDevicesObservationStarted,
    AdbDevicesObservationStopped,
)
from eventing import EventBus, EventSubscriptionToken
from native_attempt import NativeAttemptResult


_MonotonicClock = Callable[[], float]


def _normalize_positive_seconds(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a real number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0.0:
        raise ValueError(f"{field_name} must be finite and greater than zero")
    return normalized


def _normalize_optional_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


class AdbDevicesObservationEstablishmentStatus(str, Enum):
    """Terminal status of one bounded transport-inventory observation establishment episode."""

    SATISFIED = "satisfied"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True, slots=True)
class AdbDevicesObservationEstablishmentPolicy:
    """Bound one transport-inventory observation establishment episode."""

    timeout_seconds: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "timeout_seconds",
            _normalize_positive_seconds(
                self.timeout_seconds,
                field_name="ADB transport-inventory observation establishment timeout",
            ),
        )


@dataclass(frozen=True, slots=True)
class AdbDevicesObservationEstablishment:
    """Request establishment of one configured server's transport-inventory observation."""

    endpoint: AdbServerEndpoint
    policy: AdbDevicesObservationEstablishmentPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(
            self.policy,
            AdbDevicesObservationEstablishmentPolicy,
        ):
            raise TypeError(
                "policy must be AdbDevicesObservationEstablishmentPolicy"
            )


@dataclass(frozen=True, slots=True)
class AdbDevicesObservationEstablishmentResult:
    """Evidence from one bounded transport-inventory observation establishment episode."""

    operation: AdbDevicesObservationEstablishment
    status: AdbDevicesObservationEstablishmentStatus
    observation_session_id: AdbObservationSessionId | None = None
    observation_failure: AdbDevicesObservationFailure | None = None
    diagnostic: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(
            self.operation,
            AdbDevicesObservationEstablishment,
        ):
            raise TypeError(
                "operation must be AdbDevicesObservationEstablishment"
            )
        if not isinstance(
            self.status,
            AdbDevicesObservationEstablishmentStatus,
        ):
            raise TypeError(
                "status must be AdbDevicesObservationEstablishmentStatus"
            )
        if self.observation_session_id is not None:
            if not isinstance(self.observation_session_id, AdbObservationSessionId):
                raise TypeError("observation_session_id must be AdbObservationSessionId or None")
            if self.observation_session_id.endpoint != self.operation.endpoint:
                raise ValueError(
                    "observation session endpoint must match establishment operation"
                )
        if self.observation_failure is not None and not isinstance(
            self.observation_failure,
            AdbDevicesObservationFailure,
        ):
            raise TypeError(
                "observation_failure must be AdbDevicesObservationFailure or None"
            )
        if self.status is AdbDevicesObservationEstablishmentStatus.SATISFIED:
            if self.observation_session_id is None:
                raise ValueError(
                    "satisfied establishment result requires observation_session_id"
                )
            if self.observation_failure is not None:
                raise ValueError(
                    "satisfied establishment result cannot carry observation_failure"
                )
        object.__setattr__(
            self,
            "diagnostic",
            _normalize_optional_text(
                self.diagnostic,
                field_name="ADB transport-inventory observation establishment diagnostic",
            ),
        )

    @property
    def attempts(self) -> tuple[NativeAttemptResult, ...]:
        """Observation establishment performs no native server mutation attempts."""

        return ()


class AdbDevicesObservationEstablishmentOrchestrator:
    """Establish one track-devices observation generation inside a bounded episode.

    The episode owns no retry/backoff or server-lifecycle policy. Satisfaction requires matching
    ``AdbDevicesObservationStarted`` evidence, not merely acceptance of ``observation.start()``.
    Server condition maintenance belongs to ``AdbServerSupervisor``.
    """

    def __init__(
        self,
        endpoint: AdbServerEndpoint,
        event_bus: EventBus,
        observation: AdbDevicesObservationController,
        *,
        _monotonic: _MonotonicClock = monotonic,
    ) -> None:
        if not isinstance(endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not callable(getattr(event_bus, "subscribe", None)) or not callable(
            getattr(event_bus, "unsubscribe", None)
        ):
            raise TypeError("event_bus must satisfy EventBus")
        if not isinstance(observation, AdbDevicesObservationController):
            raise TypeError("observation must satisfy observation controller")
        self.endpoint = endpoint
        self._bus = event_bus
        self._observation = observation
        self._monotonic = _monotonic

    def establish(
        self,
        operation: AdbDevicesObservationEstablishment,
    ) -> AdbDevicesObservationEstablishmentResult:
        if not isinstance(
            operation,
            AdbDevicesObservationEstablishment,
        ):
            raise TypeError(
                "operation must be AdbDevicesObservationEstablishment"
            )
        if operation.endpoint != self.endpoint:
            raise ValueError("operation endpoint does not match configured ADB server endpoint")

        deadline = self._monotonic() + operation.policy.timeout_seconds
        condition = Condition()
        events: deque[object] = deque()

        def collect(event: object) -> None:
            with condition:
                events.append(event)
                condition.notify()

        subscriptions = self._subscribe(collect)
        try:
            return self._run_episode(operation, deadline, condition, events)
        finally:
            for token in subscriptions:
                self._bus.unsubscribe(token)

    def _run_episode(
        self,
        operation: AdbDevicesObservationEstablishment,
        deadline: float,
        condition: Condition,
        events: deque[object],
    ) -> AdbDevicesObservationEstablishmentResult:
        if deadline - self._monotonic() <= 0.0:
            return self._complete(
                operation,
                AdbDevicesObservationEstablishmentStatus.TIMED_OUT,
                diagnostic="establishment deadline expired before observation start",
            )

        try:
            session_id = self._observation.start()
        except RuntimeError as exc:
            return self._complete(
                operation,
                AdbDevicesObservationEstablishmentStatus.FAILED,
                diagnostic=str(exc),
            )
        if session_id.endpoint != operation.endpoint:
            raise ValueError("started observation belongs to another ADB server endpoint")

        while True:
            event = self._next_event(condition, events, deadline)
            if event is None:
                return self._complete(
                    operation,
                    AdbDevicesObservationEstablishmentStatus.TIMED_OUT,
                    observation_session_id=session_id,
                    diagnostic="timed out waiting for observation establishment evidence",
                )

            event_session = getattr(event, "session_id", None)
            if event_session != session_id:
                continue
            if isinstance(event, AdbDevicesObservationStarted):
                return self._complete(
                    operation,
                    AdbDevicesObservationEstablishmentStatus.SATISFIED,
                    observation_session_id=session_id,
                )
            if isinstance(event, AdbDevicesObservationFailed):
                return self._complete(
                    operation,
                    AdbDevicesObservationEstablishmentStatus.FAILED,
                    observation_session_id=session_id,
                    observation_failure=event.failure,
                    diagnostic=(
                        event.diagnostic or f"observation failed: {event.failure.value}"
                    ),
                )
            if isinstance(event, AdbDevicesObservationStopped):
                return self._complete(
                    operation,
                    AdbDevicesObservationEstablishmentStatus.FAILED,
                    observation_session_id=session_id,
                    diagnostic="observation stopped before establishment",
                )

    def _subscribe(
        self,
        collect: Callable[[object], None],
    ) -> tuple[EventSubscriptionToken, ...]:
        return (
            self._bus.subscribe(AdbDevicesObservationStarted, collect),
            self._bus.subscribe(AdbDevicesObservationFailed, collect),
            self._bus.subscribe(AdbDevicesObservationStopped, collect),
        )

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

    @staticmethod
    def _complete(
        operation: AdbDevicesObservationEstablishment,
        status: AdbDevicesObservationEstablishmentStatus,
        *,
        observation_session_id: AdbObservationSessionId | None = None,
        observation_failure: AdbDevicesObservationFailure | None = None,
        diagnostic: str | None = None,
    ) -> AdbDevicesObservationEstablishmentResult:
        return AdbDevicesObservationEstablishmentResult(
            operation=operation,
            status=status,
            observation_session_id=observation_session_id,
            observation_failure=observation_failure,
            diagnostic=diagnostic,
        )


__all__ = [
    "AdbDevicesObservationEstablishment",
    "AdbDevicesObservationEstablishmentOrchestrator",
    "AdbDevicesObservationEstablishmentPolicy",
    "AdbDevicesObservationEstablishmentResult",
    "AdbDevicesObservationEstablishmentStatus",
]
