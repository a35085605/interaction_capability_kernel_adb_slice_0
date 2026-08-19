from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from adb.server.endpoint import AdbServerEndpoint
from adb.transport.connection import AdbTcpAddress
from adb.transport.devices.domain import AdbDevicesSnapshot, AdbTrackedDevice
from adb.transport.selection import AdbDeviceSerial


@dataclass(frozen=True, slots=True)
class AdbUsbTransportConfiguration:
    """Configuration for one serial-selected USB ADB transport."""

    serial: AdbDeviceSerial

    def __post_init__(self) -> None:
        if not isinstance(self.serial, AdbDeviceSerial):
            raise TypeError("serial must be AdbDeviceSerial")


@dataclass(frozen=True, slots=True)
class AdbTcpTransportConfiguration:
    """Configuration for one serial-selected TCP ADB transport.

    ``serial`` remains the persistent selection and inventory-resolution identity. ``address``
    is only the explicit endpoint supplied to ``adb connect`` when preparation observes the
    configured serial as absent; the address need not equal the serial later reported by ADB.
    """

    serial: AdbDeviceSerial
    address: AdbTcpAddress

    def __post_init__(self) -> None:
        if not isinstance(self.serial, AdbDeviceSerial):
            raise TypeError("serial must be AdbDeviceSerial")
        if not isinstance(self.address, AdbTcpAddress):
            raise TypeError("address must be AdbTcpAddress")


AdbTransportConfiguration: TypeAlias = (
    AdbUsbTransportConfiguration | AdbTcpTransportConfiguration
)


@dataclass(frozen=True, slots=True)
class AdbConfiguredTransport:
    """ADB-domain configuration for one endpoint-bound transport.

    The nested transport configuration makes USB and TCP establishment semantics explicit while
    keeping ``serial`` as the stable native selection key. Runtime ``transport_id`` values remain
    fresh inventory facts rather than configured identity or implicit preparation continuity state.
    """

    endpoint: AdbServerEndpoint
    transport: AdbTransportConfiguration

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(
            self.transport,
            (AdbUsbTransportConfiguration, AdbTcpTransportConfiguration),
        ):
            raise TypeError("transport must be an ADB transport configuration")

    @property
    def serial(self) -> AdbDeviceSerial:
        """Persistent selection and inventory-resolution identity for this transport."""

        return self.transport.serial

    @property
    def connect_address(self) -> AdbTcpAddress | None:
        """Compatibility view for preparation code while connection kind lives in the variant."""

        if isinstance(self.transport, AdbTcpTransportConfiguration):
            return self.transport.address
        return None


# Private compatibility alias for preparation internals during the model migration.
AdbTransportBindingConfiguration = AdbConfiguredTransport


class AdbTransportBindingResolutionStatus(str, Enum):
    """How one configured transport serial appears in one complete inventory snapshot."""

    ABSENT = "absent"
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class AdbTransportBindingResolution:
    """Pure projection of one configured transport into inventory evidence.

    The result identifies matching observed rows for presence/state evaluation. It does not
    construct an ``AdbTransportById`` selector or otherwise change how commands select the
    transport.
    """

    configuration: AdbConfiguredTransport
    status: AdbTransportBindingResolutionStatus
    matches: tuple[AdbTrackedDevice, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, AdbConfiguredTransport):
            raise TypeError("configuration must be AdbConfiguredTransport")
        if not isinstance(self.status, AdbTransportBindingResolutionStatus):
            raise TypeError("status must be AdbTransportBindingResolutionStatus")
        if not isinstance(self.matches, tuple) or not all(
            isinstance(row, AdbTrackedDevice) for row in self.matches
        ):
            raise TypeError("matches must be a tuple of AdbTrackedDevice values")
        expected = (
            AdbTransportBindingResolutionStatus.ABSENT
            if not self.matches
            else AdbTransportBindingResolutionStatus.RESOLVED
            if len(self.matches) == 1
            else AdbTransportBindingResolutionStatus.AMBIGUOUS
        )
        if self.status is not expected:
            raise ValueError("resolution status does not match the number of matching rows")

    @property
    def row(self) -> AdbTrackedDevice | None:
        return self.matches[0] if self.status is AdbTransportBindingResolutionStatus.RESOLVED else None


def resolve_transport_binding(
    configuration: AdbConfiguredTransport,
    snapshot: AdbDevicesSnapshot,
) -> AdbTransportBindingResolution:
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
        AdbTransportBindingResolutionStatus.ABSENT
        if not matches
        else AdbTransportBindingResolutionStatus.RESOLVED
        if len(matches) == 1
        else AdbTransportBindingResolutionStatus.AMBIGUOUS
    )
    return AdbTransportBindingResolution(configuration, status, matches)


__all__ = [
    "AdbConfiguredTransport",
    "AdbTcpTransportConfiguration",
    "AdbTransportBindingResolution",
    "AdbTransportBindingResolutionStatus",
    "AdbTransportConfiguration",
    "AdbUsbTransportConfiguration",
    "resolve_transport_binding",
]
