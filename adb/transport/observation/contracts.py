from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral

from adb.server.endpoint import AdbServerEndpoint
from adb.errors import (
    AdbError,
    AdbProtocolError,
    AdbServerConnectionError,
    AdbServiceError,
)


@dataclass(frozen=True, slots=True, order=True)
class AdbObservationSessionId:
    """ADB-native identity for one endpoint-scoped transport-inventory observation generation."""

    endpoint: AdbServerEndpoint
    generation: int

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if isinstance(self.generation, bool) or not isinstance(self.generation, Integral):
            raise TypeError("generation must be an integer")
        generation = int(self.generation)
        if generation <= 0:
            raise ValueError("generation must be greater than zero")
        object.__setattr__(self, "generation", generation)


class AdbObservationError(AdbError):
    """Base error for failures while observing ADB state."""


class AdbObservationServerConnectionError(
    AdbObservationError,
    AdbServerConnectionError,
):
    """Observation failed because its smart-socket session to the ADB server was lost."""


class AdbObservationServiceError(AdbObservationError, AdbServiceError):
    """ADB server rejected the requested observation service."""

    def __init__(self, detail: str) -> None:
        AdbServiceError.__init__(self, "host:track-devices-proto-binary", detail)


class AdbObservationProtocolError(AdbObservationError, AdbProtocolError):
    """ADB observation data violated the expected smart-socket protocol."""


__all__ = [
    "AdbObservationError",
    "AdbObservationProtocolError",
    "AdbObservationServerConnectionError",
    "AdbObservationServiceError",
    "AdbObservationSessionId",
]
