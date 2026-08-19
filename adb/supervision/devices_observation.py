from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from random import random
from threading import Lock, Thread, current_thread

from adb.server.endpoint import AdbServerEndpoint
from adb.supervision.model import (
    AdbDevicesObservationEstablishmentCycleId,
    AdbDevicesObservationSupervisionPolicy,
)
from adb.supervision.signal import (
    AdbDevicesObservationEstablishmentExhausted,
    AdbDevicesObservationEstablishmentRetryDue,
)
from adb.transport.observation.establishment import (
    AdbDevicesObservationEstablishment,
    AdbDevicesObservationEstablishmentOrchestrator,
    AdbDevicesObservationEstablishmentPolicy,
    AdbDevicesObservationEstablishmentResult,
    AdbDevicesObservationEstablishmentStatus,
)
from adb.transport.observation.observer import AdbDevicesObservationController
from adb.transport.observation.signal import (
    AdbDevicesObservationFailed,
    AdbDevicesObservationFailure,
)
from eventing import EventBus, EventSubscriptionToken
from scheduling import ScheduleToken, TemporalScheduler


_RandomSource = Callable[[], float]
_ThreadFactory = Callable[..., Thread]


def _default_thread_factory(*args, **kwargs) -> Thread:
    thread = Thread(*args, **kwargs)
    thread.daemon = True
    return thread


class AdbDevicesObservationSupervisor:
    """Long-lived supervisor for one configured server's transport-inventory observation.

    The supervisor owns observation-generation establishment, retry/backoff, current-generation
    filtering, and close behavior. It deliberately does not establish or mutate the ADB server;
    server desired state and recovery belong to ``AdbServerSupervisor``.
    """

    def __init__(
        self,
        endpoint: AdbServerEndpoint,
        event_bus: EventBus,
        observation: AdbDevicesObservationController,
        scheduler: TemporalScheduler[object],
        policy: AdbDevicesObservationSupervisionPolicy,
        *,
        _random: _RandomSource = random,
        _thread_factory: _ThreadFactory = _default_thread_factory,
    ) -> None:
        if not isinstance(endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not callable(getattr(event_bus, "publish", None)) or not callable(
            getattr(event_bus, "subscribe", None)
        ):
            raise TypeError("event_bus must satisfy EventBus")
        if not isinstance(observation, AdbDevicesObservationController):
            raise TypeError("observation must satisfy AdbDevicesObservationController")
        if not isinstance(scheduler, TemporalScheduler):
            raise TypeError("scheduler must satisfy TemporalScheduler")
        if not isinstance(policy, AdbDevicesObservationSupervisionPolicy):
            raise TypeError(
                "policy must be AdbDevicesObservationSupervisionPolicy"
            )
        self.endpoint = endpoint
        self._bus = event_bus
        self._observation = observation
        self._establishment = AdbDevicesObservationEstablishmentOrchestrator(
            endpoint,
            event_bus,
            observation,
        )
        self._scheduler = scheduler
        self._policy = policy
        self._random = _random
        self._thread_factory = _thread_factory
        self._lock = Lock()
        self._subscriptions: tuple[EventSubscriptionToken, ...] = ()
        self._current_session_id = observation.active_session_id
        self._cycle_id: AdbDevicesObservationEstablishmentCycleId | None = None
        self._retry_token: ScheduleToken | None = None
        self._attempt_thread: Thread | None = None
        self._closed = False

    def start(self):
        """Subscribe and establish an initial transport-inventory observation generation."""

        with self._lock:
            if self._closed:
                raise RuntimeError("transport-inventory observation supervisor is closed")
            if self._subscriptions:
                raise RuntimeError("transport-inventory observation supervisor is already started")
            failure_token = self._bus.subscribe(
                AdbDevicesObservationFailed,
                self._on_observation_failed,
            )
            retry_token = self._bus.subscribe(
                AdbDevicesObservationEstablishmentRetryDue,
                self._on_retry_due,
            )
            self._subscriptions = (failure_token, retry_token)
            cycle_id = AdbDevicesObservationEstablishmentCycleId.new()
            self._cycle_id = cycle_id

        result = self._establish_once()
        self._handle_establishment_result(cycle_id, 1, result)
        if result.status is AdbDevicesObservationEstablishmentStatus.SATISFIED:
            return result.observation_session_id
        return None

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            subscriptions = self._subscriptions
            self._subscriptions = ()
            retry_token = self._retry_token
            self._retry_token = None
            attempt_thread = self._attempt_thread
            self._cycle_id = None
        for token in subscriptions:
            self._bus.unsubscribe(token)
        if retry_token is not None:
            self._scheduler.cancel(retry_token)
        self._observation.close()
        if attempt_thread is not None and attempt_thread is not current_thread():
            attempt_thread.join()

    def _on_observation_failed(self, event: AdbDevicesObservationFailed) -> None:
        if event.failure is not AdbDevicesObservationFailure.SERVER_CONNECTION:
            return
        if event.session_id.endpoint != self.endpoint:
            return

        with self._lock:
            if self._closed or event.session_id != self._current_session_id:
                return
            if self._cycle_id is not None:
                return
            cycle_id = AdbDevicesObservationEstablishmentCycleId.new()
            self._cycle_id = cycle_id
        self._launch_establishment_attempt(cycle_id, attempt_number=1)

    def _on_retry_due(
        self,
        event: AdbDevicesObservationEstablishmentRetryDue,
    ) -> None:
        if event.endpoint != self.endpoint:
            return
        with self._lock:
            if self._closed or event.cycle_id != self._cycle_id:
                return
            self._retry_token = None
        self._launch_establishment_attempt(event.cycle_id, event.attempt_number)

    def _launch_establishment_attempt(
        self,
        cycle_id: AdbDevicesObservationEstablishmentCycleId,
        attempt_number: int,
    ) -> None:
        thread = self._thread_factory(
            target=self._run_establishment_attempt,
            args=(cycle_id, attempt_number),
            name=(
                "adb-observation-establishment-"
                f"{self.endpoint.host}-{self.endpoint.port}-{attempt_number}"
            ),
        )
        with self._lock:
            if self._closed or self._cycle_id != cycle_id:
                return
            if self._attempt_thread is not None:
                return
            self._attempt_thread = thread
        thread.start()

    def _run_establishment_attempt(
        self,
        cycle_id: AdbDevicesObservationEstablishmentCycleId,
        attempt_number: int,
    ) -> None:
        active = current_thread()
        try:
            result = self._establish_once()
        except BaseException:
            with self._lock:
                if self._attempt_thread is active:
                    self._attempt_thread = None
            raise
        self._handle_establishment_result(
            cycle_id,
            attempt_number,
            result,
            active_thread=active,
        )

    def _establish_once(self) -> AdbDevicesObservationEstablishmentResult:
        return self._establishment.establish(
            AdbDevicesObservationEstablishment(
                self.endpoint,
                AdbDevicesObservationEstablishmentPolicy(
                    self._policy.episode_timeout_seconds,
                ),
            )
        )

    def _handle_establishment_result(
        self,
        cycle_id: AdbDevicesObservationEstablishmentCycleId,
        attempt_number: int,
        result: AdbDevicesObservationEstablishmentResult,
        *,
        active_thread: Thread | None = None,
    ) -> None:
        if result.status is AdbDevicesObservationEstablishmentStatus.SATISFIED:
            session_id = result.observation_session_id
            assert session_id is not None
            self._complete_establishment_cycle(
                cycle_id,
                session_id,
                active_thread=active_thread,
            )
            return

        if active_thread is not None:
            with self._lock:
                if self._attempt_thread is active_thread:
                    self._attempt_thread = None
                if self._closed or self._cycle_id != cycle_id:
                    return

        if self._should_retry(result):
            self._schedule_retry_or_exhaust(cycle_id, attempt_number)
        else:
            self._end_establishment_cycle(cycle_id)

    @staticmethod
    def _should_retry(
        result: AdbDevicesObservationEstablishmentResult,
    ) -> bool:
        failure = result.observation_failure
        return failure in (
            None,
            AdbDevicesObservationFailure.SERVER_CONNECTION,
        )

    def _schedule_retry_or_exhaust(
        self,
        cycle_id: AdbDevicesObservationEstablishmentCycleId,
        attempt_number: int,
    ) -> None:
        max_attempts = self._policy.max_attempts
        if max_attempts is not None and attempt_number >= max_attempts:
            self._end_establishment_cycle(cycle_id)
            self._bus.publish(
                AdbDevicesObservationEstablishmentExhausted(
                    self.endpoint,
                    cycle_id,
                    attempt_number,
                )
            )
            return

        next_attempt = attempt_number + 1
        delay_seconds = self._retry_delay(attempt_number)
        retry_event = AdbDevicesObservationEstablishmentRetryDue(
            self.endpoint,
            cycle_id,
            next_attempt,
        )
        token = self._scheduler.schedule_after(
            timedelta(seconds=delay_seconds),
            retry_event,
        )
        with self._lock:
            if self._closed or self._cycle_id != cycle_id:
                self._scheduler.cancel(token)
                return
            old_token = self._retry_token
            self._retry_token = token
        if old_token is not None:
            self._scheduler.cancel(old_token)

    def _complete_establishment_cycle(
        self,
        cycle_id: AdbDevicesObservationEstablishmentCycleId,
        session_id,
        *,
        active_thread: Thread | None = None,
    ) -> None:
        with self._lock:
            if active_thread is not None and self._attempt_thread is active_thread:
                self._attempt_thread = None
            if self._closed or self._cycle_id != cycle_id:
                return
            retry_token = self._retry_token
            self._retry_token = None
            self._current_session_id = session_id
            self._cycle_id = None
        if retry_token is not None:
            self._scheduler.cancel(retry_token)

    def _end_establishment_cycle(
        self,
        cycle_id: AdbDevicesObservationEstablishmentCycleId,
    ) -> None:
        with self._lock:
            if self._cycle_id != cycle_id:
                return
            retry_token = self._retry_token
            self._retry_token = None
            self._cycle_id = None
        if retry_token is not None:
            self._scheduler.cancel(retry_token)

    def _retry_delay(self, attempt_number: int) -> float:
        base = min(
            self._policy.retry_initial_seconds
            * (self._policy.retry_multiplier ** max(0, attempt_number - 1)),
            self._policy.retry_max_seconds,
        )
        jitter = self._policy.retry_jitter_ratio
        sample = self._random()
        if not 0.0 <= sample <= 1.0:
            raise ValueError(
                "observation supervision random source must return a value in [0, 1]"
            )
        factor = 1.0 + ((sample * 2.0) - 1.0) * jitter
        return max(base * factor, 1e-6)


__all__ = ["AdbDevicesObservationSupervisor"]
