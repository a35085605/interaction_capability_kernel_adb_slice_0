from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import math
from numbers import Real
from time import monotonic, sleep
from typing import TypeAlias

from adb.server.endpoint import AdbServerEndpoint
from adb.errors import AdbError, AdbServerConnectionError
from adb.server.lifecycle.command import (
    AdbServerStart,
    AdbServerStarter,
    AdbServerStop,
    AdbServerStopper,
)
from adb.server.status.model import AdbServerStatus
from adb.server.status.query import AdbServerStatusReader
from eventing import EventPublisher
from native_attempt import NativeAttemptResult, NativeAttemptStatus


_MonotonicClock = Callable[[], float]
_Sleeper = Callable[[float], None]


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


class AdbServerAvailability(str, Enum):
    """Domain-local observation of one configured ADB server endpoint."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    INDETERMINATE = "indeterminate"


class AdbServerEnsureStatus(str, Enum):
    """Terminal status of ADB server availability orchestration."""

    SATISFIED = "satisfied"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class AdbServerSatisfaction(str, Enum):
    """How an ensure operation reached its requested observable condition."""

    ALREADY_SATISFIED = "already_satisfied"
    ACHIEVED = "achieved"


@dataclass(frozen=True, slots=True)
class AdbServerEnsurePolicy:
    """Explicit waiting policy for ADB server availability orchestration."""

    timeout_seconds: float
    probe_interval_seconds: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "timeout_seconds",
            _normalize_positive_seconds(
                self.timeout_seconds,
                field_name="ADB server ensure timeout",
            ),
        )
        object.__setattr__(
            self,
            "probe_interval_seconds",
            _normalize_positive_seconds(
                self.probe_interval_seconds,
                field_name="ADB server ensure probe interval",
            ),
        )


@dataclass(frozen=True, slots=True)
class AdbServerEnsureAvailable:
    """Request domain orchestration to establish and verify server availability."""

    endpoint: AdbServerEndpoint
    policy: AdbServerEnsurePolicy

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(self.policy, AdbServerEnsurePolicy):
            raise TypeError("policy must be AdbServerEnsurePolicy")


@dataclass(frozen=True, slots=True)
class AdbServerEnsureUnavailable:
    """Request domain orchestration to establish and verify server unavailability."""

    endpoint: AdbServerEndpoint
    policy: AdbServerEnsurePolicy

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(self.policy, AdbServerEnsurePolicy):
            raise TypeError("policy must be AdbServerEnsurePolicy")


AdbServerEnsureOperation: TypeAlias = AdbServerEnsureAvailable | AdbServerEnsureUnavailable


@dataclass(frozen=True, slots=True)
class AdbServerProbeResult:
    """Evidence from one fresh probe performed by ADB server orchestration."""

    endpoint: AdbServerEndpoint
    availability: AdbServerAvailability
    server_status: AdbServerStatus | None = None
    diagnostic: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(self.availability, AdbServerAvailability):
            raise TypeError("availability must be AdbServerAvailability")
        if self.availability is AdbServerAvailability.AVAILABLE:
            if not isinstance(self.server_status, AdbServerStatus):
                raise ValueError("available probe requires AdbServerStatus")
        elif self.server_status is not None:
            raise ValueError("non-available probe cannot carry AdbServerStatus")
        object.__setattr__(
            self,
            "diagnostic",
            _normalize_optional_text(
                self.diagnostic,
                field_name="ADB server probe diagnostic",
            ),
        )


@dataclass(frozen=True, slots=True)
class AdbServerEnsureResult:
    """Terminal evidence produced by ADB server availability orchestration."""

    operation: AdbServerEnsureOperation
    status: AdbServerEnsureStatus
    satisfaction: AdbServerSatisfaction | None
    attempts: tuple[NativeAttemptResult, ...]
    final_probe: AdbServerProbeResult

    def __post_init__(self) -> None:
        if not isinstance(
            self.operation,
            (AdbServerEnsureAvailable, AdbServerEnsureUnavailable),
        ):
            raise TypeError("operation must be an ADB server ensure operation")
        if not isinstance(self.status, AdbServerEnsureStatus):
            raise TypeError("status must be AdbServerEnsureStatus")
        if self.satisfaction is not None and not isinstance(
            self.satisfaction,
            AdbServerSatisfaction,
        ):
            raise TypeError("satisfaction must be AdbServerSatisfaction or None")
        if not isinstance(self.attempts, tuple) or not all(
            isinstance(attempt, NativeAttemptResult) for attempt in self.attempts
        ):
            raise TypeError("attempts must be a tuple of NativeAttemptResult")
        if not isinstance(self.final_probe, AdbServerProbeResult):
            raise TypeError("final_probe must be AdbServerProbeResult")
        if self.final_probe.endpoint != self.operation.endpoint:
            raise ValueError("final probe endpoint must match ensure operation")
        desired = (
            AdbServerAvailability.AVAILABLE
            if isinstance(self.operation, AdbServerEnsureAvailable)
            else AdbServerAvailability.UNAVAILABLE
        )
        condition_met = self.final_probe.availability is desired
        if self.status is AdbServerEnsureStatus.SATISFIED:
            if self.satisfaction is None:
                raise ValueError("satisfied ensure result requires satisfaction")
            if not condition_met:
                raise ValueError("satisfied ensure result requires matching final probe")
        else:
            if self.satisfaction is not None:
                raise ValueError("unsatisfied ensure result cannot carry satisfaction")
            if condition_met:
                raise ValueError("matching final probe requires satisfied ensure status")
        if (
            self.satisfaction is AdbServerSatisfaction.ALREADY_SATISFIED
            and self.attempts
        ):
            raise ValueError("already-satisfied ensure result cannot contain native attempts")


class AdbServerEnsureOrchestrator:
    """Concrete same-domain executor for probe/command/verification ensure operations."""

    def __init__(
        self,
        endpoint: AdbServerEndpoint,
        status_reader: AdbServerStatusReader,
        starter: AdbServerStarter,
        stopper: AdbServerStopper,
        publisher: EventPublisher,
        *,
        _monotonic: _MonotonicClock = monotonic,
        _sleep: _Sleeper = sleep,
    ) -> None:
        if not isinstance(endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not callable(getattr(status_reader, "read", None)):
            raise TypeError("status_reader must provide read()")
        if not callable(getattr(starter, "start", None)):
            raise TypeError("starter must provide start()")
        if not callable(getattr(stopper, "stop", None)):
            raise TypeError("stopper must provide stop()")
        if not isinstance(publisher, EventPublisher):
            raise TypeError("publisher must satisfy EventPublisher")
        self.endpoint = endpoint
        self._status_reader = status_reader
        self._starter = starter
        self._stopper = stopper
        self._publisher = publisher
        self._monotonic = _monotonic
        self._sleep = _sleep

    def probe(self) -> AdbServerProbeResult:
        from adb.server.signal import AdbServerProbeCompleted

        try:
            status = self._status_reader.read(self.endpoint)
        except AdbServerConnectionError as exc:
            result = AdbServerProbeResult(
                endpoint=self.endpoint,
                availability=AdbServerAvailability.UNAVAILABLE,
                diagnostic=str(exc),
            )
        except AdbError as exc:
            result = AdbServerProbeResult(
                endpoint=self.endpoint,
                availability=AdbServerAvailability.INDETERMINATE,
                diagnostic=str(exc),
            )
        else:
            result = AdbServerProbeResult(
                endpoint=self.endpoint,
                availability=AdbServerAvailability.AVAILABLE,
                server_status=status,
            )
        self._publisher.publish(AdbServerProbeCompleted(result))
        return result

    def ensure(self, operation: AdbServerEnsureOperation) -> AdbServerEnsureResult:
        from adb.server.signal import AdbServerCommandCompleted, AdbServerEnsureCompleted

        if not isinstance(operation, (AdbServerEnsureAvailable, AdbServerEnsureUnavailable)):
            raise TypeError("operation must be an ADB server ensure operation")
        if operation.endpoint != self.endpoint:
            raise ValueError("operation endpoint does not match configured ADB server endpoint")
        desired = (
            AdbServerAvailability.AVAILABLE
            if isinstance(operation, AdbServerEnsureAvailable)
            else AdbServerAvailability.UNAVAILABLE
        )
        first_probe = self.probe()
        if first_probe.availability is desired:
            result = AdbServerEnsureResult(
                operation=operation,
                status=AdbServerEnsureStatus.SATISFIED,
                satisfaction=AdbServerSatisfaction.ALREADY_SATISFIED,
                attempts=(),
                final_probe=first_probe,
            )
            self._publisher.publish(AdbServerEnsureCompleted(result))
            return result
        deadline = self._monotonic() + operation.policy.timeout_seconds
        command = (
            AdbServerStart(operation.endpoint)
            if isinstance(operation, AdbServerEnsureAvailable)
            else AdbServerStop(operation.endpoint)
        )
        attempt = (
            self._starter.start(command)
            if isinstance(command, AdbServerStart)
            else self._stopper.stop(command)
        )
        self._publisher.publish(AdbServerCommandCompleted(command, attempt))
        final_probe = self.probe()
        while final_probe.availability is not desired:
            remaining = deadline - self._monotonic()
            if remaining <= 0.0:
                terminal_status = (
                    AdbServerEnsureStatus.FAILED
                    if attempt.status is NativeAttemptStatus.FAILED
                    else AdbServerEnsureStatus.TIMED_OUT
                )
                result = AdbServerEnsureResult(
                    operation=operation,
                    status=terminal_status,
                    satisfaction=None,
                    attempts=(attempt,),
                    final_probe=final_probe,
                )
                self._publisher.publish(AdbServerEnsureCompleted(result))
                return result
            self._sleep(min(operation.policy.probe_interval_seconds, remaining))
            final_probe = self.probe()
        result = AdbServerEnsureResult(
            operation=operation,
            status=AdbServerEnsureStatus.SATISFIED,
            satisfaction=AdbServerSatisfaction.ACHIEVED,
            attempts=(attempt,),
            final_probe=final_probe,
        )
        self._publisher.publish(AdbServerEnsureCompleted(result))
        return result


__all__ = [
    "AdbServerAvailability",
    "AdbServerEnsureAvailable",
    "AdbServerEnsureOperation",
    "AdbServerEnsureOrchestrator",
    "AdbServerEnsurePolicy",
    "AdbServerEnsureResult",
    "AdbServerEnsureStatus",
    "AdbServerEnsureUnavailable",
    "AdbServerProbeResult",
    "AdbServerSatisfaction",
]
