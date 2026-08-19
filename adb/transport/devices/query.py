from __future__ import annotations

from typing import Protocol

from adb.server.endpoint import AdbServerEndpoint
from adb.transport.devices.domain import AdbDevicesSnapshot, AdbTrackedDevice
from adb.transport.selection import AdbTransportSelector


class AdbDevicesSnapshotReader(Protocol):
    """Read the current complete ADB transport-inventory snapshot."""

    def read(self, endpoint: AdbServerEndpoint) -> AdbDevicesSnapshot:
        ...


class AdbTrackedDeviceLookup(Protocol):
    """Find one observed transport row from a fresh complete inventory snapshot."""

    def find(
        self,
        endpoint: AdbServerEndpoint,
        selector: AdbTransportSelector,
    ) -> AdbTrackedDevice | None:
        ...


__all__ = ["AdbDevicesSnapshotReader", "AdbTrackedDeviceLookup"]
