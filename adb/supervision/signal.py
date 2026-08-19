from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from adb.server.endpoint import AdbServerEndpoint
from adb.supervision.model import (
    AdbDevicesObservationEstablishmentCycleId,
    AdbServerRecoveryCycleId,
)
from adb.transport.configuration import AdbConfiguredTransport
from adb.transport.resolution import AdbConfiguredTransportResolution
from adb.transport.observation.contracts import AdbObservationSessionId
from adb.transport.orchestration import (
    AdbTransportPreparationResult,
    AdbTransportPreparationStatus,
)


@dataclass(frozen=True, slots=True)
class AdbConfiguredTransportResolutionChanged:
    """Signal carrying one configured-transport projection within an observation generation."""

    session_id: AdbObservationSessionId
    previous: AdbConfiguredTransportResolution | None
    current: AdbConfiguredTransportResolution

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, AdbObservationSessionId):
            raise TypeError("session_id must be AdbObservationSessionId")
        if self.previous is not None and not isinstance(
            self.previous, AdbConfiguredTransportResolution
        ):
            raise TypeError("previous must be AdbConfiguredTransportResolution or None")
        if not isinstance(self.current, AdbConfiguredTransportResolution):
            raise TypeError("current must be AdbConfiguredTransportResolution")
        if self.current.configuration.endpoint != self.session_id.endpoint:
            raise ValueError("configured transport resolution endpoint must match observation session")
        if self.previous is not None and (
            self.previous.configuration.serial
            != self.current.configuration.serial
        ):
            raise ValueError("configured transport resolution change must keep one serial")


@dataclass(frozen=True, slots=True)
class AdbConfiguredTransportRecoveryExhausted:
    """Signal that automatic recovery ended unsatisfied for one configured transport."""

    configuration: AdbConfiguredTransport
    result: AdbTransportPreparationResult

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, AdbConfiguredTransport):
            raise TypeError("configuration must be AdbConfiguredTransport")
        if not isinstance(self.result, AdbTransportPreparationResult):
            raise TypeError("result must be AdbTransportPreparationResult")
        if self.result.operation.endpoint != self.configuration.endpoint:
            raise ValueError("recovery result endpoint must match configured transport")
        if self.result.operation.serial != self.configuration.serial:
            raise ValueError("recovery result serial must match configured transport")
        if self.result.status is AdbTransportPreparationStatus.SATISFIED:
            raise ValueError("recovery exhausted signal requires an unsatisfied result")


@dataclass(frozen=True, slots=True)
class AdbServerRecoveryRetryDue:
    """Signal delivered when one scheduled server-running recovery retry becomes due."""

    endpoint: AdbServerEndpoint
    cycle_id: AdbServerRecoveryCycleId
    attempt_number: int

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(self.cycle_id, AdbServerRecoveryCycleId):
            raise TypeError("cycle_id must be AdbServerRecoveryCycleId")
        if isinstance(self.attempt_number, bool) or not isinstance(self.attempt_number, int):
            raise TypeError("attempt_number must be an integer")
        if self.attempt_number <= 0:
            raise ValueError("attempt_number must be greater than zero")


@dataclass(frozen=True, slots=True)
class AdbServerRecoveryExhausted:
    """Signal that automatic maintenance of the server running condition exhausted its budget."""

    endpoint: AdbServerEndpoint
    cycle_id: AdbServerRecoveryCycleId
    attempts: int

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(self.cycle_id, AdbServerRecoveryCycleId):
            raise TypeError("cycle_id must be AdbServerRecoveryCycleId")
        if isinstance(self.attempts, bool) or not isinstance(self.attempts, int):
            raise TypeError("attempts must be an integer")
        if self.attempts <= 0:
            raise ValueError("attempts must be greater than zero")


@dataclass(frozen=True, slots=True)
class AdbDevicesObservationEstablishmentRetryDue:
    """Signal delivered when one scheduled observation-establishment retry becomes due."""

    endpoint: AdbServerEndpoint
    cycle_id: AdbDevicesObservationEstablishmentCycleId
    attempt_number: int

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(
            self.cycle_id,
            AdbDevicesObservationEstablishmentCycleId,
        ):
            raise TypeError(
                "cycle_id must be AdbDevicesObservationEstablishmentCycleId"
            )
        if isinstance(self.attempt_number, bool) or not isinstance(self.attempt_number, int):
            raise TypeError("attempt_number must be an integer")
        if self.attempt_number <= 0:
            raise ValueError("attempt_number must be greater than zero")


@dataclass(frozen=True, slots=True)
class AdbDevicesObservationEstablishmentExhausted:
    """Signal that an observation-establishment cycle exhausted its attempt budget."""

    endpoint: AdbServerEndpoint
    cycle_id: AdbDevicesObservationEstablishmentCycleId
    attempts: int

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(
            self.cycle_id,
            AdbDevicesObservationEstablishmentCycleId,
        ):
            raise TypeError(
                "cycle_id must be AdbDevicesObservationEstablishmentCycleId"
            )
        if isinstance(self.attempts, bool) or not isinstance(self.attempts, int):
            raise TypeError("attempts must be an integer")
        if self.attempts <= 0:
            raise ValueError("attempts must be greater than zero")


AdbSupervisionSignal: TypeAlias = (
    AdbConfiguredTransportResolutionChanged
    | AdbConfiguredTransportRecoveryExhausted
    | AdbServerRecoveryRetryDue
    | AdbServerRecoveryExhausted
    | AdbDevicesObservationEstablishmentRetryDue
    | AdbDevicesObservationEstablishmentExhausted
)


__all__ = [
    "AdbConfiguredTransportRecoveryExhausted",
    "AdbConfiguredTransportResolutionChanged",
    "AdbDevicesObservationEstablishmentExhausted",
    "AdbDevicesObservationEstablishmentRetryDue",
    "AdbServerRecoveryExhausted",
    "AdbServerRecoveryRetryDue",
    "AdbSupervisionSignal",
]
