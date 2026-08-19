from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from numbers import Integral, Real

from adb.server.endpoint import AdbServerEndpoint
from adb.transport.devices.domain import (
    AdbConnectionState,
    AdbDevicesSnapshot,
    AdbTrackedDevice,
)
from adb.transport.observation.contracts import AdbObservationSessionId
from adb.transport.selection import AdbDeviceSerial
from native_attempt import NativeAttemptResult


def _normalize_positive_seconds(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a real number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0.0:
        raise ValueError(f"{field_name} must be finite and greater than zero")
    return normalized


def _normalize_state(value: object, *, field_name: str) -> AdbConnectionState | int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{field_name} values must be integers")
    raw = int(value)
    try:
        return AdbConnectionState(raw)
    except ValueError:
        return raw


def _normalize_states(
    value: object,
    *,
    field_name: str,
    allow_empty: bool,
) -> frozenset[AdbConnectionState | int]:
    if not isinstance(value, frozenset):
        raise TypeError(f"{field_name} must be a frozenset")
    normalized = frozenset(
        _normalize_state(item, field_name=field_name)
        for item in value
    )
    if not allow_empty and not normalized:
        raise ValueError(f"{field_name} cannot be empty")
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


@dataclass(frozen=True, slots=True)
class AdbTransportPreparation:
    """Request one bounded preparation episode for a configured serial-selected transport."""

    endpoint: AdbServerEndpoint
    serial: AdbDeviceSerial

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(self.serial, AdbDeviceSerial):
            raise TypeError("serial must be AdbDeviceSerial")


@dataclass(frozen=True, slots=True)
class AdbTransportRecovery:
    """Request domain-local orchestration to recover one configured serial-selected transport."""

    endpoint: AdbServerEndpoint
    serial: AdbDeviceSerial

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(self.serial, AdbDeviceSerial):
            raise TypeError("serial must be AdbDeviceSerial")


@dataclass(frozen=True, slots=True)
class AdbTransportPreparationPolicy:
    """One-deadline readiness policy for presence and state gates in one episode.

    States not listed as acceptable or blocked remain waiting states. This preserves future
    open-enum values without silently treating them as ready or permanently failed.
    """

    timeout_seconds: float
    acceptable_states: frozenset[AdbConnectionState | int]
    blocked_states: frozenset[AdbConnectionState | int] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "timeout_seconds",
            _normalize_positive_seconds(
                self.timeout_seconds,
                field_name="ADB transport preparation timeout",
            ),
        )
        acceptable = _normalize_states(
            self.acceptable_states,
            field_name="acceptable_states",
            allow_empty=False,
        )
        blocked = _normalize_states(
            self.blocked_states,
            field_name="blocked_states",
            allow_empty=True,
        )
        if acceptable & blocked:
            raise ValueError("acceptable_states and blocked_states must be disjoint")
        object.__setattr__(self, "acceptable_states", acceptable)
        object.__setattr__(self, "blocked_states", blocked)


class AdbTransportPreparationStatus(str, Enum):
    """Terminal status of one transport preparation episode."""

    SATISFIED = "satisfied"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    BLOCKED = "blocked"
    AMBIGUOUS = "ambiguous"
    OBSERVATION_FAILED = "observation_failed"
    OBSERVATION_STOPPED = "observation_stopped"
    OBSERVATION_REPLACED = "observation_replaced"


class AdbTransportPreparationSatisfaction(str, Enum):
    """How the final readiness condition became satisfied."""

    ALREADY_SATISFIED = "already_satisfied"
    ACHIEVED = "achieved"


class AdbTransportPresenceSatisfaction(str, Enum):
    """How the configured binding first became present during one episode."""

    ALREADY_PRESENT = "already_present"
    OBSERVED = "observed"


@dataclass(frozen=True, slots=True)
class AdbTransportPreparationResult:
    """Terminal preparation evidence without collapsing command success into readiness."""

    operation: AdbTransportPreparation
    policy: AdbTransportPreparationPolicy
    status: AdbTransportPreparationStatus
    satisfaction: AdbTransportPreparationSatisfaction | None
    presence_satisfaction: AdbTransportPresenceSatisfaction | None
    observation_session_id: AdbObservationSessionId
    attempts: tuple[NativeAttemptResult, ...]
    final_snapshot: AdbDevicesSnapshot | None = None
    final_row: AdbTrackedDevice | None = None
    diagnostic: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.operation, AdbTransportPreparation):
            raise TypeError("operation must be AdbTransportPreparation")
        if not isinstance(self.policy, AdbTransportPreparationPolicy):
            raise TypeError("policy must be AdbTransportPreparationPolicy")
        if not isinstance(self.status, AdbTransportPreparationStatus):
            raise TypeError("status must be AdbTransportPreparationStatus")
        if self.satisfaction is not None and not isinstance(
            self.satisfaction, AdbTransportPreparationSatisfaction
        ):
            raise TypeError("satisfaction must be AdbTransportPreparationSatisfaction or None")
        if self.presence_satisfaction is not None and not isinstance(
            self.presence_satisfaction, AdbTransportPresenceSatisfaction
        ):
            raise TypeError(
                "presence_satisfaction must be AdbTransportPresenceSatisfaction or None"
            )
        if not isinstance(self.observation_session_id, AdbObservationSessionId):
            raise TypeError("observation_session_id must be AdbObservationSessionId")
        if not isinstance(self.attempts, tuple) or not all(
            isinstance(attempt, NativeAttemptResult) for attempt in self.attempts
        ):
            raise TypeError("attempts must be a tuple of NativeAttemptResult values")
        if self.final_snapshot is not None and not isinstance(
            self.final_snapshot, AdbDevicesSnapshot
        ):
            raise TypeError("final_snapshot must be AdbDevicesSnapshot or None")
        if self.final_row is not None and not isinstance(self.final_row, AdbTrackedDevice):
            raise TypeError("final_row must be AdbTrackedDevice or None")
        object.__setattr__(
            self,
            "diagnostic",
            _normalize_optional_text(
                self.diagnostic,
                field_name="ADB transport preparation diagnostic",
            ),
        )

        if self.status is AdbTransportPreparationStatus.SATISFIED:
            if self.satisfaction is None or self.final_row is None:
                raise ValueError("satisfied preparation requires satisfaction and final_row")
            if self.final_row.state not in self.policy.acceptable_states:
                raise ValueError("satisfied preparation requires an acceptable final state")
        elif self.satisfaction is not None:
            raise ValueError("unsatisfied preparation cannot carry satisfaction")


__all__ = [
    "AdbTransportPreparation",
    "AdbTransportPreparationPolicy",
    "AdbTransportPreparationResult",
    "AdbTransportPreparationSatisfaction",
    "AdbTransportPreparationStatus",
    "AdbTransportPresenceSatisfaction",
    "AdbTransportRecovery",
]
