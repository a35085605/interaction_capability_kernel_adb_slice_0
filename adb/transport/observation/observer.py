from __future__ import annotations

from collections.abc import Callable
from threading import Lock, Thread, current_thread
from typing import Protocol, runtime_checkable

from adb.server.endpoint import AdbServerEndpoint
from adb.transport.observation.contracts import (
    AdbObservationProtocolError,
    AdbObservationServerConnectionError,
    AdbObservationServiceError,
    AdbObservationSessionId,
)
from adb.transport.observation.signal import (
    AdbDevicesSnapshotObserved,
    AdbDevicesObservationFailed,
    AdbDevicesObservationFailure,
    AdbDevicesObservationStarted,
    AdbDevicesObservationStopped,
)
from adb.transport.observation.source import AdbTrackDevicesSession, AdbTrackDevicesSource
from eventing import EventPublisher


_SourceFactory = Callable[[AdbServerEndpoint], AdbTrackDevicesSource]
_ThreadFactory = Callable[..., Thread]


def _default_source_factory(endpoint: AdbServerEndpoint) -> AdbTrackDevicesSource:
    return AdbTrackDevicesSource(endpoint)


def _default_thread_factory(*args, **kwargs) -> Thread:
    thread = Thread(*args, **kwargs)
    thread.daemon = True
    return thread


@runtime_checkable
class AdbDevicesObservationController(Protocol):
    @property
    def active_session_id(self) -> AdbObservationSessionId | None: ...

    def start(self) -> AdbObservationSessionId: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...


class AdbDevicesObserver:
    """Observe generation-fenced transport inventory and publish lifecycle signals."""

    def __init__(
        self,
        endpoint: AdbServerEndpoint,
        publisher: EventPublisher,
        *,
        _source_factory: _SourceFactory = _default_source_factory,
        _thread_factory: _ThreadFactory = _default_thread_factory,
    ) -> None:
        if not isinstance(endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(publisher, EventPublisher):
            raise TypeError("publisher must satisfy EventPublisher")
        self.endpoint = endpoint
        self._publisher = publisher
        self._source_factory = _source_factory
        self._thread_factory = _thread_factory
        self._lock = Lock()
        self._generation = 0
        self._active_session_id: AdbObservationSessionId | None = None
        self._active_source: AdbTrackDevicesSource | None = None
        self._active_thread: Thread | None = None
        self._closed = False

    @property
    def active_session_id(self) -> AdbObservationSessionId | None:
        """Return the allocated non-terminal observation generation, if any."""

        with self._lock:
            return self._active_session_id

    def start(self) -> AdbObservationSessionId:
        """Allocate and start one new observation generation in a background thread."""

        with self._lock:
            if self._closed:
                raise RuntimeError("ADB devices observer is closed")
            if self._active_thread is not None:
                raise RuntimeError("an ADB observation session is already active")
            self._generation += 1
            session_id = AdbObservationSessionId(
                self.endpoint,
                self._generation,
            )
            source = self._source_factory(self.endpoint)
            if not isinstance(source, AdbTrackDevicesSource):
                raise TypeError("source factory must return AdbTrackDevicesSource")
            thread = self._thread_factory(
                target=self._run_session,
                args=(session_id, source),
                name=(
                    "adb-track-devices-"
                    f"{self.endpoint.host}-{self.endpoint.port}-{session_id.generation}"
                ),
            )
            self._active_session_id = session_id
            self._active_source = source
            self._active_thread = thread
            thread.start()
            return session_id

    def stop(self) -> None:
        """Stop the active session without closing the observer for future generations."""

        with self._lock:
            source = self._active_source
            thread = self._active_thread
        if source is not None:
            source.close()
        if thread is not None and thread is not current_thread():
            thread.join()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self.stop()

    def _run_session(
        self,
        session_id: AdbObservationSessionId,
        source: AdbTrackDevicesSource,
    ) -> None:
        endpoint = self.endpoint
        session: AdbTrackDevicesSession | None = None
        terminal: object | None = None
        try:
            session = source.open()
            if session is None:
                terminal = AdbDevicesObservationStopped(endpoint, session_id)
            else:
                self._publisher.publish(
                    AdbDevicesObservationStarted(endpoint, session_id)
                )
                for snapshot in session.snapshots():
                    self._publisher.publish(
                        AdbDevicesSnapshotObserved(endpoint, session_id, snapshot)
                    )
                terminal = AdbDevicesObservationStopped(endpoint, session_id)
        except AdbObservationServerConnectionError as exc:
            terminal = AdbDevicesObservationFailed(
                endpoint,
                session_id,
                AdbDevicesObservationFailure.SERVER_CONNECTION,
                str(exc),
            )
        except AdbObservationServiceError as exc:
            terminal = AdbDevicesObservationFailed(
                endpoint,
                session_id,
                AdbDevicesObservationFailure.SERVICE,
                str(exc),
            )
        except AdbObservationProtocolError as exc:
            terminal = AdbDevicesObservationFailed(
                endpoint,
                session_id,
                AdbDevicesObservationFailure.PROTOCOL,
                str(exc),
            )
        finally:
            if session is not None:
                session.close()
            else:
                source.close()
            self._mark_inactive(session_id, source)

        if terminal is not None:
            self._publisher.publish(terminal)

    def _mark_inactive(
        self,
        session_id: AdbObservationSessionId,
        source: AdbTrackDevicesSource,
    ) -> None:
        with self._lock:
            if self._active_session_id == session_id and self._active_source is source:
                self._active_session_id = None
                self._active_source = None
                self._active_thread = None


__all__ = [
    "AdbDevicesObservationController",
    "AdbDevicesObserver",
]
