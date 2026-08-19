from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from adb.server.endpoint import AdbServerEndpoint
from adb.transport.devices.domain import AdbDevicesSnapshot
from adb.transport.observation.contracts import AdbObservationSessionId


def _require_endpoint(value: object) -> AdbServerEndpoint:
    if not isinstance(value, AdbServerEndpoint):
        raise TypeError("endpoint must be AdbServerEndpoint")
    return value


def _require_session_id(value: object) -> AdbObservationSessionId:
    if not isinstance(value, AdbObservationSessionId):
        raise TypeError("session_id must be AdbObservationSessionId")
    return value


def _normalize_optional_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


class AdbDevicesObservationFailure(str, Enum):
    """Typed reason one transport-inventory observation session terminated abnormally."""

    SERVER_CONNECTION = "server_connection"
    SERVICE = "service"
    PROTOCOL = "protocol"


@dataclass(frozen=True, slots=True)
class AdbDevicesObservationStarted:
    """Signal that one transport-inventory observation session entered stream mode."""

    endpoint: AdbServerEndpoint
    session_id: AdbObservationSessionId

    def __post_init__(self) -> None:
        _require_endpoint(self.endpoint)
        _require_session_id(self.session_id)
        if self.session_id.endpoint != self.endpoint:
            raise ValueError("session_id endpoint must match signal endpoint")


@dataclass(frozen=True, slots=True)
class AdbDevicesObservationStopped:
    """Signal that observation ended without implying transport disappearance."""

    endpoint: AdbServerEndpoint
    session_id: AdbObservationSessionId

    def __post_init__(self) -> None:
        _require_endpoint(self.endpoint)
        _require_session_id(self.session_id)
        if self.session_id.endpoint != self.endpoint:
            raise ValueError("session_id endpoint must match signal endpoint")


@dataclass(frozen=True, slots=True)
class AdbDevicesObservationFailed:
    """Signal that observation failed without synthesizing server or transport state."""

    endpoint: AdbServerEndpoint
    session_id: AdbObservationSessionId
    failure: AdbDevicesObservationFailure
    diagnostic: str | None = None

    def __post_init__(self) -> None:
        _require_endpoint(self.endpoint)
        _require_session_id(self.session_id)
        if self.session_id.endpoint != self.endpoint:
            raise ValueError("session_id endpoint must match signal endpoint")
        if not isinstance(self.failure, AdbDevicesObservationFailure):
            raise TypeError("failure must be AdbDevicesObservationFailure")
        object.__setattr__(
            self,
            "diagnostic",
            _normalize_optional_text(
                self.diagnostic,
                field_name="ADB transport-inventory observation diagnostic",
            ),
        )


@dataclass(frozen=True, slots=True)
class AdbDevicesSnapshotObserved:
    """Signal carrying one complete snapshot emitted by ADB track-devices."""

    endpoint: AdbServerEndpoint
    session_id: AdbObservationSessionId
    snapshot: AdbDevicesSnapshot

    def __post_init__(self) -> None:
        _require_endpoint(self.endpoint)
        _require_session_id(self.session_id)
        if self.session_id.endpoint != self.endpoint:
            raise ValueError("session_id endpoint must match signal endpoint")
        if not isinstance(self.snapshot, AdbDevicesSnapshot):
            raise TypeError("snapshot must be AdbDevicesSnapshot")


__all__ = [
    "AdbDevicesObservationFailed",
    "AdbDevicesObservationFailure",
    "AdbDevicesObservationStarted",
    "AdbDevicesObservationStopped",
    "AdbDevicesSnapshotObserved",
]
