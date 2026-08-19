"""ADB transport identity, selection, capabilities, inventory, and observation."""

from adb.transport.selection import (
    AdbDeviceSerial,
    AdbTransportById,
    AdbTransportBySerial,
    AdbTransportId,
    AdbTransportSelector,
)
from adb.transport.features import AdbTransportFeatures
from adb.transport.configuration import (
    AdbConfiguredTransport,
    AdbTcpTransportConfiguration,
    AdbTransportConfiguration,
    AdbUsbTransportConfiguration,
)
from adb.transport.resolution import (
    AdbConfiguredTransportResolution,
    AdbConfiguredTransportResolutionStatus,
    resolve_configured_transport,
)
from adb.transport.query import AdbTransportFeaturesReader
from adb.transport.orchestration import (
    AdbTransportPreparation,
    AdbTransportPreparationPolicy,
    AdbTransportPreparationResult,
    AdbTransportPreparationSatisfaction,
    AdbTransportPreparationStatus,
    AdbTransportPresenceSatisfaction,
    AdbTransportRecovery,
)
from adb.transport.preparation import AdbTransportPreparationOrchestrator
from adb.transport.devices import (
    AdbConnectionState,
    AdbConnectionType,
    AdbDevicesSnapshot,
    AdbDevicesSnapshotReader,
    AdbTrackedDevice,
    AdbTrackedDeviceLookup,
)
from adb.transport.observation import (
    AdbObservationError,
    AdbObservationProtocolError,
    AdbObservationServerConnectionError,
    AdbObservationServiceError,
    AdbObservationSessionId,
    AdbDevicesObservationController,
    AdbDevicesObserver,
)

__all__ = [
    "AdbConnectionState",
    "AdbConnectionType",
    "AdbDeviceSerial",
    "AdbDevicesSnapshot",
    "AdbDevicesSnapshotReader",
    "AdbObservationError",
    "AdbObservationProtocolError",
    "AdbObservationServerConnectionError",
    "AdbObservationServiceError",
    "AdbObservationSessionId",
    "AdbTrackedDevice",
    "AdbTrackedDeviceLookup",
    "AdbConfiguredTransport",
    "AdbConfiguredTransportResolution",
    "AdbConfiguredTransportResolutionStatus",
    "AdbTcpTransportConfiguration",
    "AdbTransportConfiguration",
    "AdbUsbTransportConfiguration",
    "AdbTransportPreparation",
    "AdbTransportPreparationOrchestrator",
    "AdbTransportPreparationPolicy",
    "AdbTransportPreparationResult",
    "AdbTransportPreparationSatisfaction",
    "AdbTransportPreparationStatus",
    "AdbTransportPresenceSatisfaction",
    "AdbTransportRecovery",
    "AdbDevicesObservationController",
    "AdbDevicesObserver",
    "AdbTransportById",
    "AdbTransportBySerial",
    "AdbTransportFeatures",
    "AdbTransportFeaturesReader",
    "AdbTransportId",
    "AdbTransportSelector",
    "resolve_configured_transport",
]
