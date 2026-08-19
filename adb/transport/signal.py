from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from adb.transport.connection import (
    AdbDeviceSideReconnect,
    AdbOfflineTransportsReconnect,
    AdbTcpConnect,
    AdbTcpDisconnect,
    AdbTransportReconnect,
)
from adb.transport.orchestration import AdbTransportPreparationResult
from native_attempt import NativeAttemptResult


AdbTransportCommandOperation: TypeAlias = (
    AdbTcpConnect
    | AdbTcpDisconnect
    | AdbTransportReconnect
    | AdbDeviceSideReconnect
    | AdbOfflineTransportsReconnect
)


@dataclass(frozen=True, slots=True)
class AdbTransportCommandCompleted:
    """Signal carrying the result of one atomic ADB transport command attempt."""

    operation: AdbTransportCommandOperation
    result: NativeAttemptResult

    def __post_init__(self) -> None:
        if not isinstance(
            self.operation,
            (
                AdbTcpConnect,
                AdbTcpDisconnect,
                AdbTransportReconnect,
                AdbDeviceSideReconnect,
                AdbOfflineTransportsReconnect,
            ),
        ):
            raise TypeError("operation must be an ADB transport command operation")
        if not isinstance(self.result, NativeAttemptResult):
            raise TypeError("result must be NativeAttemptResult")


@dataclass(frozen=True, slots=True)
class AdbTransportPreparationCompleted:
    """Signal carrying terminal evidence from one transport preparation episode."""

    result: AdbTransportPreparationResult

    def __post_init__(self) -> None:
        if not isinstance(self.result, AdbTransportPreparationResult):
            raise TypeError("result must be AdbTransportPreparationResult")


AdbTransportSignal: TypeAlias = (
    AdbTransportCommandCompleted | AdbTransportPreparationCompleted
)


__all__ = [
    "AdbTransportCommandCompleted",
    "AdbTransportCommandOperation",
    "AdbTransportPreparationCompleted",
    "AdbTransportSignal",
]
