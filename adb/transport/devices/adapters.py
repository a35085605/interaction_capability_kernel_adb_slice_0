from __future__ import annotations

from collections.abc import Callable

from adb._internal.client import AdbServiceClient
from adb._internal.proto import parse_devices_snapshot
from adb.server.endpoint import AdbServerEndpoint
from adb.transport.devices.domain import AdbDevicesSnapshot, AdbTrackedDevice
from adb.transport.selection import (
    AdbTransportById,
    AdbTransportBySerial,
    AdbTransportSelector,
)


_ClientFactory = Callable[[AdbServerEndpoint], AdbServiceClient]


def _default_client_factory(endpoint: AdbServerEndpoint) -> AdbServiceClient:
    return AdbServiceClient(endpoint)


def find_tracked_device(
    snapshot: AdbDevicesSnapshot,
    selector: AdbTransportSelector,
) -> AdbTrackedDevice | None:
    """Derive one observed transport row from a complete ADB inventory snapshot."""

    if not isinstance(snapshot, AdbDevicesSnapshot):
        raise TypeError("snapshot must be AdbDevicesSnapshot")
    if isinstance(selector, AdbTransportBySerial):
        matches = [device for device in snapshot.devices if device.serial == selector.serial.value]
    elif isinstance(selector, AdbTransportById):
        matches = [
            device
            for device in snapshot.devices
            if device.transport_id == selector.transport_id
        ]
    else:
        raise TypeError("selector must be AdbTransportBySerial or AdbTransportById")

    if len(matches) > 1:
        raise ValueError("ADB transport selector matched multiple inventory rows")
    return matches[0] if matches else None


class SmartSocketAdbDevicesSnapshotReader:
    """One-shot inventory snapshot reader from the first protobuf tracker frame."""

    _SERVICE = "host:track-devices-proto-binary"

    def __init__(self, *, _client_factory: _ClientFactory = _default_client_factory) -> None:
        self._client_factory = _client_factory

    def read(self, endpoint: AdbServerEndpoint) -> AdbDevicesSnapshot:
        if not isinstance(endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        payload = self._client_factory(endpoint).first_stream_frame(self._SERVICE)
        return parse_devices_snapshot(payload)


class SnapshotAdbTrackedDeviceLookup:
    """Derived single-row lookup over a fresh complete transport-inventory snapshot."""

    def __init__(self, snapshot_reader: object | None = None) -> None:
        self.snapshot_reader = snapshot_reader or SmartSocketAdbDevicesSnapshotReader()
        if not hasattr(self.snapshot_reader, "read"):
            raise TypeError("snapshot_reader must provide read()")

    def find(
        self,
        endpoint: AdbServerEndpoint,
        selector: AdbTransportSelector,
    ) -> AdbTrackedDevice | None:
        snapshot = self.snapshot_reader.read(endpoint)
        if not isinstance(snapshot, AdbDevicesSnapshot):
            raise TypeError("snapshot reader must return AdbDevicesSnapshot")
        return find_tracked_device(snapshot, selector)


__all__ = [
    "SmartSocketAdbDevicesSnapshotReader",
    "SnapshotAdbTrackedDeviceLookup",
    "find_tracked_device",
]
