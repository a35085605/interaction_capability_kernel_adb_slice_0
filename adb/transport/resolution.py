from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from adb.transport.configuration import AdbConfiguredTransport
from adb.transport.devices.domain import AdbDevicesSnapshot, AdbTrackedDevice


class AdbConfiguredTransportResolutionStatus(str, Enum):
    """How one configured transport serial appears in one complete inventory snapshot."""

    ABSENT = "absent"
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class AdbConfiguredTransportResolution:
    """Pure projection of one configured transport into inventory evidence.

    The result identifies matching observed rows for presence/state evaluation. It does not
    construct an ``AdbTransportById`` selector or otherwise change how commands select the
    transport.
    """

    configuration: AdbConfiguredTransport
    status: AdbConfiguredTransportResolutionStatus
    matches: tuple[AdbTrackedDevice, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, AdbConfiguredTransport):
            raise TypeError("configuration must be AdbConfiguredTransport")
        if not isinstance(self.status, AdbConfiguredTransportResolutionStatus):
            raise TypeError("status must be AdbConfiguredTransportResolutionStatus")
        if not isinstance(self.matches, tuple) or not all(
            isinstance(row, AdbTrackedDevice) for row in self.matches
        ):
            raise TypeError("matches must be a tuple of AdbTrackedDevice values")
        expected = (
            AdbConfiguredTransportResolutionStatus.ABSENT
            if not self.matches
            else AdbConfiguredTransportResolutionStatus.RESOLVED
            if len(self.matches) == 1
            else AdbConfiguredTransportResolutionStatus.AMBIGUOUS
        )
        if self.status is not expected:
            raise ValueError("resolution status does not match the number of matching rows")

    @property
    def row(self) -> AdbTrackedDevice | None:
        return (
            self.matches[0]
            if self.status is AdbConfiguredTransportResolutionStatus.RESOLVED
            else None
        )


def resolve_configured_transport(
    configuration: AdbConfiguredTransport,
    snapshot: AdbDevicesSnapshot,
) -> AdbConfiguredTransportResolution:
    """Locate the configured serial in fresh inventory evidence.

    This lookup supports preparation presence/state evaluation only. It does not translate the
    serial into a transport-id selector and does not participate in native serial selection.
    """

    if not isinstance(configuration, AdbConfiguredTransport):
        raise TypeError("configuration must be AdbConfiguredTransport")
    if not isinstance(snapshot, AdbDevicesSnapshot):
        raise TypeError("snapshot must be AdbDevicesSnapshot")

    matches = tuple(
        row for row in snapshot.devices if row.serial == configuration.serial.value
    )
    status = (
        AdbConfiguredTransportResolutionStatus.ABSENT
        if not matches
        else AdbConfiguredTransportResolutionStatus.RESOLVED
        if len(matches) == 1
        else AdbConfiguredTransportResolutionStatus.AMBIGUOUS
    )
    return AdbConfiguredTransportResolution(configuration, status, matches)


__all__ = [
    "AdbConfiguredTransportResolution",
    "AdbConfiguredTransportResolutionStatus",
    "resolve_configured_transport",
]
