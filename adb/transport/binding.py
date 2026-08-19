from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from adb.server.endpoint import AdbServerEndpoint
from adb.transport.devices.domain import AdbDevicesSnapshot, AdbTrackedDevice
from adb.transport.selection import AdbDeviceSerial


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
class AdbTransportBindingConfiguration:
    """ADB-domain configuration for one endpoint and serial-selected transport.

    ``serial`` is the persistent native selection key and can be passed directly to ADB
    serial-selection mechanisms. Preparation separately uses the same serial to locate the
    matching row in fresh transport-inventory evidence; that lookup does not convert the
    configuration to a runtime ``transport_id`` selector.

    ``serial`` is deliberately independent from ``connect_address``. The address passed to
    ``adb connect`` does not have to be identical to the serial later reported by the ADB
    transport inventory. Runtime ``transport_id`` values remain fresh inventory facts rather
    than binding configuration or implicit preparation continuity state.
    """

    endpoint: AdbServerEndpoint
    serial: AdbDeviceSerial
    connect_address: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(self.serial, AdbDeviceSerial):
            raise TypeError("serial must be AdbDeviceSerial")
        object.__setattr__(
            self,
            "connect_address",
            _normalize_optional_text(
                self.connect_address,
                field_name="ADB transport connect address",
            ),
        )


class AdbTransportBindingResolutionStatus(str, Enum):
    """How one configured serial appears in one complete inventory snapshot."""

    ABSENT = "absent"
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class AdbTransportBindingResolution:
    """Pure projection of one configured serial into inventory evidence.

    The result identifies matching observed rows for presence/state evaluation. It does not
    construct an ``AdbTransportById`` selector or otherwise change how commands select the
    transport.
    """

    configuration: AdbTransportBindingConfiguration
    status: AdbTransportBindingResolutionStatus
    matches: tuple[AdbTrackedDevice, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, AdbTransportBindingConfiguration):
            raise TypeError("configuration must be AdbTransportBindingConfiguration")
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
    configuration: AdbTransportBindingConfiguration,
    snapshot: AdbDevicesSnapshot,
) -> AdbTransportBindingResolution:
    """Locate the configured serial in fresh inventory evidence.

    This lookup supports preparation presence/state evaluation only. It does not translate the
    serial into a transport-id selector and does not participate in native serial selection.
    """

    if not isinstance(configuration, AdbTransportBindingConfiguration):
        raise TypeError("configuration must be AdbTransportBindingConfiguration")
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
    "AdbTransportBindingConfiguration",
    "AdbTransportBindingResolution",
    "AdbTransportBindingResolutionStatus",
    "resolve_transport_binding",
]
