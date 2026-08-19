from __future__ import annotations

from typing import Protocol

from adb.server.endpoint import AdbServerEndpoint
from adb.transport.binding import AdbTransportBindingConfiguration


class RegisteredTransport(Protocol):
    """One transport binding managed by the ADB runtime."""

    def set_auto_recovery(self, enabled: bool) -> None:
        """Enable or disable automatic re-establishment of this binding."""
        ...


class AdbManagedRuntime:
    """Managed lifecycle for one ADB server endpoint and its registered transports."""

    def __init__(self, endpoint: AdbServerEndpoint) -> None:
        if not isinstance(endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        self.endpoint = endpoint

    # ------------------------------------------------------------------
    # Runtime lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the managed runtime infrastructure."""
        raise NotImplementedError

    def close(self) -> None:
        """Stop managing runtime state and release runtime resources."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    def start_server(self, *, auto_recovery: bool = True) -> None:
        """Establish the server running condition."""
        raise NotImplementedError

    def stop_server(self) -> None:
        """Establish the server stopped condition."""
        raise NotImplementedError

    def set_server_auto_recovery(self, enabled: bool) -> None:
        """Enable or disable maintenance of the server running condition."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Transport registration lifecycle
    # ------------------------------------------------------------------

    def add_transport(
        self,
        configuration: AdbTransportBindingConfiguration,
        *,
        auto_recovery: bool = True,
    ) -> RegisteredTransport:
        """Register one transport binding for managed observation/recovery."""
        raise NotImplementedError

    def remove_transport(self, transport: RegisteredTransport) -> None:
        """Release one managed transport registration."""
        raise NotImplementedError


__all__ = ["AdbManagedRuntime", "RegisteredTransport"]
