from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock, Thread, current_thread
from typing import Protocol, runtime_checkable

from adb.server.endpoint import AdbServerEndpoint
from adb.errors import AdbError
from adb.supervision.model import AdbTransportBindingSupervisionPolicy
from adb.supervision.signal import (
    AdbTransportBindingRecoveryExhausted,
    AdbTransportBindingResolutionChanged,
)
from adb.transport.binding import (
    AdbConfiguredTransport,
    AdbTransportBindingResolution,
    AdbTransportBindingResolutionStatus,
    resolve_transport_binding,
)
from adb.transport.devices.domain import AdbDevicesSnapshot
from adb.transport.devices.query import AdbDevicesSnapshotReader
from adb.transport.observation.contracts import AdbObservationSessionId
from adb.transport.observation.observer import AdbDevicesObservationController
from adb.transport.observation.signal import (
    AdbDevicesObservationStarted,
    AdbDevicesSnapshotObserved,
)
from adb.transport.selection import AdbDeviceSerial
from adb.transport.orchestration import (
    AdbTransportPreparation,
    AdbTransportPreparationResult,
    AdbTransportPreparationStatus,
)
from eventing import EventBus, EventSubscriptionToken


@runtime_checkable
class AdbTransportPreparationExecutor(Protocol):
    def prepare(self, operation, policy) -> AdbTransportPreparationResult: ...


_PreparationFactory = Callable[
    [AdbConfiguredTransport],
    AdbTransportPreparationExecutor,
]
_ThreadFactory = Callable[..., Thread]


def _default_thread_factory(*args, **kwargs) -> Thread:
    thread = Thread(*args, **kwargs)
    thread.daemon = True
    return thread


@dataclass(slots=True)
class _BindingRegistration:
    configuration: AdbConfiguredTransport
    policy: AdbTransportBindingSupervisionPolicy
    resolution: AdbTransportBindingResolution | None = None
    session_id: AdbObservationSessionId | None = None
    recovery_attempted_for_absence: bool = False
    recovery_thread: Thread | None = None


class AdbTransportBindingSupervisor:
    """Long-lived projection and bounded recovery for caller-registered ADB bindings.

    The transport-inventory observer remains server-wide and binding-agnostic. This supervisor
    holds binding configuration only for the explicit registration lifetime, projects complete
    inventory snapshots into binding resolutions, and may run one bounded preparation episode
    for each observed absence episode. It does not infer physical-device availability and does
    not retry indefinitely after a failed preparation.
    """

    def __init__(
        self,
        endpoint: AdbServerEndpoint,
        event_bus: EventBus,
        observation: AdbDevicesObservationController,
        snapshot_reader: AdbDevicesSnapshotReader,
        preparation_factory: _PreparationFactory,
        *,
        _thread_factory: _ThreadFactory = _default_thread_factory,
    ) -> None:
        if not isinstance(endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not callable(getattr(event_bus, "publish", None)) or not callable(
            getattr(event_bus, "subscribe", None)
        ) or not callable(getattr(event_bus, "unsubscribe", None)):
            raise TypeError("event_bus must satisfy EventBus")
        if not isinstance(observation, AdbDevicesObservationController):
            raise TypeError("observation must satisfy AdbDevicesObservationController")
        if not callable(getattr(snapshot_reader, "read", None)):
            raise TypeError("snapshot_reader must provide read()")
        if not callable(preparation_factory):
            raise TypeError("preparation_factory must be callable")
        self.endpoint = endpoint
        self._bus = event_bus
        self._observation = observation
        self._snapshot_reader = snapshot_reader
        self._preparation_factory = preparation_factory
        self._thread_factory = _thread_factory
        self._lock = Lock()
        self._registrations: dict[AdbDeviceSerial, _BindingRegistration] = {}
        self._subscriptions: tuple[EventSubscriptionToken, ...] = ()
        self._closed = False

    def start(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("transport binding supervisor is closed")
            if self._subscriptions:
                raise RuntimeError("transport binding supervisor is already started")
            started = self._bus.subscribe(
                AdbDevicesObservationStarted,
                self._on_observation_started,
            )
            snapshots = self._bus.subscribe(
                AdbDevicesSnapshotObserved,
                self._on_snapshot_observed,
            )
            self._subscriptions = (started, snapshots)

    def register(
        self,
        configuration: AdbConfiguredTransport,
        policy: AdbTransportBindingSupervisionPolicy | None = None,
    ) -> None:
        if not isinstance(configuration, AdbConfiguredTransport):
            raise TypeError("configuration must be AdbConfiguredTransport")
        if configuration.endpoint != self.endpoint:
            raise ValueError("binding configuration endpoint does not match ADB server endpoint")
        if policy is None:
            policy = AdbTransportBindingSupervisionPolicy()
        if not isinstance(policy, AdbTransportBindingSupervisionPolicy):
            raise TypeError("policy must be AdbTransportBindingSupervisionPolicy")

        with self._lock:
            if self._closed:
                raise RuntimeError("transport binding supervisor is closed")
            if not self._subscriptions:
                raise RuntimeError("transport binding supervisor must be started before register")
            if configuration.serial in self._registrations:
                raise ValueError("ADB transport binding is already registered")
            self._registrations[configuration.serial] = _BindingRegistration(
                configuration,
                policy,
            )

        self._project_fresh_snapshot(configuration.serial)

    def unregister(self, serial: AdbDeviceSerial) -> bool:
        if not isinstance(serial, AdbDeviceSerial):
            raise TypeError("serial must be AdbDeviceSerial")
        with self._lock:
            registration = self._registrations.pop(serial, None)
        return registration is not None

    def resolution(
        self,
        serial: AdbDeviceSerial,
    ) -> AdbTransportBindingResolution | None:
        if not isinstance(serial, AdbDeviceSerial):
            raise TypeError("serial must be AdbDeviceSerial")
        with self._lock:
            registration = self._registrations.get(serial)
            return None if registration is None else registration.resolution

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            subscriptions = self._subscriptions
            self._subscriptions = ()
            threads = tuple(
                registration.recovery_thread
                for registration in self._registrations.values()
                if registration.recovery_thread is not None
            )
            self._registrations.clear()
        for token in subscriptions:
            self._bus.unsubscribe(token)
        for thread in threads:
            if thread is not current_thread():
                thread.join()

    def _project_fresh_snapshot(self, serial: AdbDeviceSerial) -> None:
        session_id = self._observation.active_session_id
        if session_id is None or session_id.endpoint != self.endpoint:
            return
        try:
            snapshot = self._snapshot_reader.read(self.endpoint)
        except AdbError:
            return
        if self._observation.active_session_id != session_id:
            return
        self._apply_snapshot(session_id, snapshot, serial=serial)

    def _on_observation_started(self, event: AdbDevicesObservationStarted) -> None:
        if event.session_id.endpoint != self.endpoint:
            return
        with self._lock:
            if self._closed:
                return
            for registration in self._registrations.values():
                registration.resolution = None
                registration.session_id = event.session_id
                registration.recovery_attempted_for_absence = False

    def _on_snapshot_observed(self, event: AdbDevicesSnapshotObserved) -> None:
        if event.session_id.endpoint != self.endpoint:
            return
        self._apply_snapshot(event.session_id, event.snapshot)

    def _apply_snapshot(
        self,
        session_id: AdbObservationSessionId,
        snapshot: AdbDevicesSnapshot,
        *,
        serial: AdbDeviceSerial | None = None,
    ) -> None:
        publications: list[object] = []
        recoveries: list[AdbDeviceSerial] = []
        with self._lock:
            if self._closed:
                return
            registrations = (
                [self._registrations[serial]]
                if serial in self._registrations
                else []
                if serial is not None
                else list(self._registrations.values())
            )
            for registration in registrations:
                previous = registration.resolution
                current = resolve_transport_binding(registration.configuration, snapshot)
                baseline_changed = registration.session_id != session_id
                changed = baseline_changed or previous != current
                registration.session_id = session_id
                registration.resolution = current

                if current.status is not AdbTransportBindingResolutionStatus.ABSENT:
                    registration.recovery_attempted_for_absence = False

                if changed:
                    publications.append(
                        AdbTransportBindingResolutionChanged(
                            session_id,
                            previous if not baseline_changed else None,
                            current,
                        )
                    )

                should_recover = (
                    current.status is AdbTransportBindingResolutionStatus.ABSENT
                    and registration.policy.preparation_policy is not None
                    and not registration.recovery_attempted_for_absence
                    and registration.recovery_thread is None
                )
                if should_recover:
                    registration.recovery_attempted_for_absence = True
                    recoveries.append(registration.configuration.serial)

        for publication in publications:
            self._bus.publish(publication)
        for recovery_serial in recoveries:
            self._launch_recovery(recovery_serial)

    def _launch_recovery(self, serial: AdbDeviceSerial) -> None:
        thread = self._thread_factory(
            target=self._run_recovery,
            args=(serial,),
            name=f"adb-transport-recovery-{serial.value}",
        )
        with self._lock:
            registration = self._registrations.get(serial)
            if registration is None or self._closed:
                return
            if registration.recovery_thread is not None:
                return
            registration.recovery_thread = thread
        thread.start()

    def _run_recovery(self, serial: AdbDeviceSerial) -> None:
        try:
            with self._lock:
                registration = self._registrations.get(serial)
                if registration is None or self._closed:
                    return
                configuration = registration.configuration
                preparation_policy = registration.policy.preparation_policy
            if preparation_policy is None:
                return
            orchestrator = self._preparation_factory(configuration)
            if not isinstance(orchestrator, AdbTransportPreparationExecutor):
                raise TypeError(
                    "preparation_factory must return an ADB transport preparation executor"
                )
            result = orchestrator.prepare(
                AdbTransportPreparation(configuration.endpoint, configuration.serial),
                preparation_policy,
            )
            with self._lock:
                registration = self._registrations.get(serial)
                result_is_current = (
                    registration is not None
                    and not self._closed
                    and registration.configuration == configuration
                    and registration.session_id == result.observation_session_id
                )
            if not result_is_current:
                return
            if result.status is AdbTransportPreparationStatus.SATISFIED:
                if result.final_snapshot is not None:
                    self._apply_snapshot(
                        result.observation_session_id,
                        result.final_snapshot,
                        serial=serial,
                    )
            else:
                self._bus.publish(
                    AdbTransportBindingRecoveryExhausted(configuration, result)
                )
        finally:
            relaunch = False
            with self._lock:
                registration = self._registrations.get(serial)
                if registration is not None and registration.recovery_thread is current_thread():
                    registration.recovery_thread = None
                    relaunch = (
                        not self._closed
                        and registration.resolution is not None
                        and registration.resolution.status
                        is AdbTransportBindingResolutionStatus.ABSENT
                        and registration.policy.preparation_policy is not None
                        and not registration.recovery_attempted_for_absence
                    )
                    if relaunch:
                        registration.recovery_attempted_for_absence = True
            if relaunch:
                self._launch_recovery(serial)


__all__ = ["AdbTransportBindingSupervisor", "AdbTransportPreparationExecutor"]
