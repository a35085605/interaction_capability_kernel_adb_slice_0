from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from adb.server.endpoint import AdbServerEndpoint
from adb.transport.connection import AdbTcpAddress
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
        """Explicit TCP connect address when this configured transport uses TCP."""

        if isinstance(self.transport, AdbTcpTransportConfiguration):
            return self.transport.address
        return None


__all__ = [
    "AdbConfiguredTransport",
    "AdbTcpTransportConfiguration",
    "AdbTransportConfiguration",
    "AdbUsbTransportConfiguration",
]
