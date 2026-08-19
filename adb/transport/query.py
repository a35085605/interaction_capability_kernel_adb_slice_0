from __future__ import annotations

from typing import Protocol

from adb.server.endpoint import AdbServerEndpoint
from adb.transport.features import AdbTransportFeatures
from adb.transport.selection import AdbTransportSelector


class AdbTransportFeaturesReader(Protocol):
    """Read feature facts for one deterministically selected ADB transport."""

    def read(
        self,
        endpoint: AdbServerEndpoint,
        selector: AdbTransportSelector,
    ) -> AdbTransportFeatures:
        ...


__all__ = ["AdbTransportFeaturesReader"]
