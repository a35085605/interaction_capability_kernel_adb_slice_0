from __future__ import annotations

from typing import Protocol

from adb.server.endpoint import AdbServerEndpoint
from adb.server.status.model import AdbServerStatus


class AdbServerStatusReader(Protocol):
    """Read the current AOSP host-side ADB server status."""

    def read(self, endpoint: AdbServerEndpoint) -> AdbServerStatus:
        ...


__all__ = ["AdbServerStatusReader"]
