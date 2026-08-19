# 專案程式碼彙整

# GitHub Repo: a35085605/interaction_capability_kernel_adb_slice

---

## FILE: `adb\__init__.py`

```python
"""Host-side ADB native nouns and atomic read capabilities.

Canonical ownership is noun-first around the ADB server, pairing relationship, and transports.
Pairing commands live under ``adb.pairing``; transport inventory and observation are owned by
``adb.transport``; Android framework queries reached through ADB live under ``android.adb``.
"""

from adb.errors import (
    AdbError,
    AdbProtocolError,
    AdbRemoteCommandError,
    AdbServerConnectionError,
    AdbServiceError,
    AdbTimeoutError,
    AdbTransportAmbiguousError,
    AdbTransportNotFoundError,
    AdbTransportSelectionError,
    AdbTransportUnavailableError,
)
from adb.managed import AdbManagedRuntime, RegisteredTransport
from adb.server import AdbServerStatusReader
from adb.transport import (
    AdbConnectionState,
    AdbConnectionType,
    AdbDeviceSerial,
    AdbDevicesSnapshot,
    AdbDevicesSnapshotReader,
    AdbTrackedDevice,
    AdbTrackedDeviceLookup,
    AdbTransportById,
    AdbTransportBySerial,
    AdbTransportFeatures,
    AdbTransportFeaturesReader,
    AdbTransportId,
    AdbTransportSelector,
)

__all__ = [
    "AdbConnectionState",
    "AdbConnectionType",
    "AdbDeviceSerial",
    "AdbDevicesSnapshot",
    "AdbDevicesSnapshotReader",
    "AdbError",
    "AdbManagedRuntime",
    "AdbProtocolError",
    "AdbRemoteCommandError",
    "AdbServerConnectionError",
    "AdbServerStatusReader",
    "AdbServiceError",
    "AdbTimeoutError",
    "AdbTrackedDevice",
    "AdbTrackedDeviceLookup",
    "AdbTransportAmbiguousError",
    "AdbTransportById",
    "AdbTransportBySerial",
    "AdbTransportFeatures",
    "AdbTransportFeaturesReader",
    "AdbTransportId",
    "AdbTransportNotFoundError",
    "AdbTransportSelectionError",
    "AdbTransportSelector",
    "AdbTransportUnavailableError",
    "RegisteredTransport",
]

```

---

## FILE: `adb\errors.py`

```python
from __future__ import annotations


class AdbError(RuntimeError):
    """Base error for typed ADB protocol, query, and transport failures."""


class AdbServerConnectionError(AdbError):
    """The configured ADB server smart-socket session could not be established or used."""


class AdbTimeoutError(AdbServerConnectionError):
    """An ADB server smart-socket operation exceeded its configured timeout."""


class AdbProtocolError(AdbError):
    """ADB framing or payload data violated the expected protocol."""


class AdbServiceError(AdbError):
    """An ADB server or device service rejected a request."""

    def __init__(self, service: str, detail: str) -> None:
        self.service = service
        self.detail = detail
        super().__init__(f"ADB service {service!r} failed: {detail}")


class AdbTransportSelectionError(AdbServiceError):
    """Base error for deterministic transport selection failures."""


class AdbTransportNotFoundError(AdbTransportSelectionError):
    """The requested transport was not present in the selected ADB server."""


class AdbTransportAmbiguousError(AdbTransportSelectionError):
    """The requested transport selector matched more than one transport."""


class AdbTransportUnavailableError(AdbTransportSelectionError):
    """The selected transport exists but cannot currently serve the request."""


class AdbRemoteCommandError(AdbError):
    """A typed read-only remote command completed with a non-zero exit code."""

    def __init__(
        self,
        *,
        command_name: str,
        exit_code: int,
        stderr: bytes = b"",
    ) -> None:
        self.command_name = command_name
        self.exit_code = exit_code
        self.stderr = stderr
        detail = stderr.decode("utf-8", errors="replace").strip()
        suffix = f": {detail}" if detail else ""
        super().__init__(
            f"ADB remote command {command_name!r} exited with {exit_code}{suffix}"
        )


__all__ = [
    "AdbError",
    "AdbProtocolError",
    "AdbRemoteCommandError",
    "AdbServerConnectionError",
    "AdbServiceError",
    "AdbTimeoutError",
    "AdbTransportAmbiguousError",
    "AdbTransportNotFoundError",
    "AdbTransportSelectionError",
    "AdbTransportUnavailableError",
]

```

---

## FILE: `adb\managed.py`

```python
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

```

---

## FILE: `adb\_internal\__init__.py`

```python
"""Private ADB protocol implementation helpers."""

__all__: list[str] = []

```

---

## FILE: `adb\_internal\client.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Real
import socket
import struct
from typing import Callable

from adb.errors import (
    AdbProtocolError,
    AdbServerConnectionError,
    AdbServiceError,
    AdbTimeoutError,
    AdbTransportAmbiguousError,
    AdbTransportNotFoundError,
    AdbTransportUnavailableError,
)
from adb._internal.framing import encode_service, parse_hex_length
from adb.server.endpoint import AdbServerEndpoint
from adb.transport.selection import (
    AdbTransportById,
    AdbTransportBySerial,
    AdbTransportSelector,
)


_SHELL_STDOUT = 1
_SHELL_STDERR = 2
_SHELL_EXIT = 3


def _normalize_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError("ADB timeout must be a real number")
    timeout = float(value)
    if not isfinite(timeout) or timeout <= 0:
        raise ValueError("ADB timeout must be finite and greater than zero")
    return timeout


def _transport_service(selector: AdbTransportSelector) -> str:
    if isinstance(selector, AdbTransportBySerial):
        return f"host:transport:{selector.serial.value}"
    if isinstance(selector, AdbTransportById):
        return f"host:transport-id:{selector.transport_id.value}"
    raise TypeError("selector must be AdbTransportBySerial or AdbTransportById")


def _feature_service(selector: AdbTransportSelector) -> str:
    if isinstance(selector, AdbTransportBySerial):
        return f"host-serial:{selector.serial.value}:features"
    if isinstance(selector, AdbTransportById):
        return f"host-transport-id:{selector.transport_id.value}:features"
    raise TypeError("selector must be AdbTransportBySerial or AdbTransportById")


@dataclass(frozen=True, slots=True)
class ShellV2Result:
    stdout: bytes
    stderr: bytes
    exit_code: int


class AdbServiceClient:
    """Private smart-socket client used by typed kernel adapters.

    This class deliberately stays under ``adb._internal``. Public kernel capabilities
    expose typed inspectors and commands rather than an unrestricted shell executor.
    """

    def __init__(
        self,
        endpoint: AdbServerEndpoint,
        timeout_seconds: float = 5.0,
        *,
        _socket_factory: Callable[..., socket.socket] = socket.create_connection,
    ) -> None:
        if not isinstance(endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        self.endpoint = endpoint
        self.timeout_seconds = _normalize_timeout(timeout_seconds)
        self._socket_factory = _socket_factory

    def host_query(self, service: str) -> bytes:
        """Run one length-prefixed host query and return its payload."""

        sock = self._connect()
        try:
            self._request(sock, service)
            return self._read_protocol_string(sock, context=service)
        finally:
            self._close(sock)

    def first_stream_frame(self, service: str) -> bytes:
        """Read the first length-prefixed frame from a host streaming service."""

        sock = self._connect()
        try:
            self._request(sock, service)
            return self._read_protocol_string(sock, context=service)
        finally:
            self._close(sock)

    def features(self, selector: AdbTransportSelector) -> frozenset[str]:
        payload = self.host_query(_feature_service(selector))
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AdbProtocolError("ADB feature list is not valid UTF-8") from exc
        return frozenset(part for part in text.split(",") if part)

    def raw_exec(self, selector: AdbTransportSelector, command: str) -> bytes:
        """Private raw ``exec:`` primitive for fixed typed adapter commands."""

        sock = self._connect()
        try:
            self._select_transport(sock, selector)
            self._request(sock, f"exec:{command}")
            return self._read_until_eof(sock)
        finally:
            self._close(sock)

    def shell_v2(self, selector: AdbTransportSelector, command: str) -> ShellV2Result:
        """Private shell-v2 primitive with stdout/stderr/exit-code separation."""

        sock = self._connect()
        try:
            self._select_transport(sock, selector)
            self._request(sock, f"shell,v2,raw:{command}")
            stdout = bytearray()
            stderr = bytearray()
            exit_code: int | None = None

            while True:
                first = self._recv_up_to(sock, 1)
                if not first:
                    break
                header = first + self._recv_exact(sock, 4)
                packet_id = header[0]
                size = struct.unpack("<I", header[1:])[0]
                payload = self._recv_exact(sock, size)
                if packet_id == _SHELL_STDOUT:
                    stdout.extend(payload)
                elif packet_id == _SHELL_STDERR:
                    stderr.extend(payload)
                elif packet_id == _SHELL_EXIT:
                    if len(payload) != 1:
                        raise AdbProtocolError("ADB shell-v2 exit packet must contain one byte")
                    if exit_code is not None:
                        raise AdbProtocolError("ADB shell-v2 emitted multiple exit packets")
                    exit_code = payload[0]

            if exit_code is None:
                raise AdbProtocolError("ADB shell-v2 stream ended without an exit packet")
            return ShellV2Result(bytes(stdout), bytes(stderr), exit_code)
        finally:
            self._close(sock)

    def _connect(self) -> socket.socket:
        try:
            sock = self._socket_factory(
                (self.endpoint.host, self.endpoint.port),
                timeout=self.timeout_seconds,
            )
            sock.settimeout(self.timeout_seconds)
            return sock
        except socket.timeout as exc:
            raise AdbTimeoutError("timed out connecting to the ADB server") from exc
        except OSError as exc:
            raise AdbServerConnectionError(
                f"failed to connect to ADB server {self.endpoint.host}:{self.endpoint.port}: {exc}"
            ) from exc

    def _select_transport(self, sock: socket.socket, selector: AdbTransportSelector) -> None:
        self._request(sock, _transport_service(selector), transport_selection=True)

    def _request(
        self,
        sock: socket.socket,
        service: str,
        *,
        transport_selection: bool = False,
    ) -> None:
        try:
            sock.sendall(encode_service(service))
        except socket.timeout as exc:
            raise AdbTimeoutError(f"timed out sending ADB service {service!r}") from exc
        except OSError as exc:
            raise AdbServerConnectionError(
                f"failed to send ADB service {service!r}: {exc}"
            ) from exc

        status = self._recv_exact(sock, 4)
        if status == b"OKAY":
            return
        if status != b"FAIL":
            raise AdbProtocolError(f"unexpected ADB service status: {status!r}")
        detail_raw = self._read_protocol_string(sock, context="service error")
        try:
            detail = detail_raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AdbProtocolError("ADB service error is not valid UTF-8") from exc
        if transport_selection:
            self._raise_transport_error(service, detail)
        raise AdbServiceError(service, detail or "request rejected")

    def _raise_transport_error(self, service: str, detail: str) -> None:
        lowered = detail.lower()
        if "more than one" in lowered or "multiple devices" in lowered:
            raise AdbTransportAmbiguousError(service, detail)
        if (
            "not found" in lowered
            or "no devices" in lowered
            or "no device" in lowered
            or "unknown transport" in lowered
        ):
            raise AdbTransportNotFoundError(service, detail)
        if (
            "offline" in lowered
            or "unauthorized" in lowered
            or "no permissions" in lowered
            or "permission" in lowered
        ):
            raise AdbTransportUnavailableError(service, detail)
        raise AdbTransportUnavailableError(service, detail or "transport unavailable")

    def _read_protocol_string(self, sock: socket.socket, *, context: str) -> bytes:
        length = parse_hex_length(self._recv_exact(sock, 4), context=context)
        return self._recv_exact(sock, length)

    def _recv_exact(self, sock: socket.socket, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            chunk = self._recv_up_to(sock, remaining)
            if not chunk:
                raise AdbServerConnectionError("unexpected EOF from ADB smart-socket")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _recv_up_to(self, sock: socket.socket, size: int) -> bytes:
        try:
            return sock.recv(size)
        except socket.timeout as exc:
            raise AdbTimeoutError("ADB smart-socket read timed out") from exc
        except OSError as exc:
            raise AdbServerConnectionError(f"ADB smart-socket read failed: {exc}") from exc

    def _read_until_eof(self, sock: socket.socket) -> bytes:
        chunks: list[bytes] = []
        while True:
            chunk = self._recv_up_to(sock, 65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)

    @staticmethod
    def _close(sock: socket.socket) -> None:
        try:
            sock.close()
        except OSError:
            pass


__all__ = ["AdbServiceClient", "ShellV2Result"]

```

---

## FILE: `adb\_internal\framing.py`

```python
from __future__ import annotations

from adb.errors import AdbProtocolError


_HEX_DIGITS = frozenset(b"0123456789abcdefABCDEF")


def encode_service(service: str) -> bytes:
    """Encode one ADB smart-socket service request with its 4-hex length prefix."""

    if not isinstance(service, str):
        raise TypeError("ADB service must be a string")
    encoded = service.encode("utf-8")
    if not encoded:
        raise ValueError("ADB service cannot be empty")
    if len(encoded) > 0xFFFF:
        raise ValueError("ADB service name is too long")
    return f"{len(encoded):04x}".encode("ascii") + encoded


def parse_hex_length(raw: bytes, *, context: str) -> int:
    """Parse one ADB 4-hex smart-socket length prefix."""

    if len(raw) != 4 or any(byte not in _HEX_DIGITS for byte in raw):
        raise AdbProtocolError(f"invalid {context} length prefix: {raw!r}")
    return int(raw, 16)


__all__ = ["encode_service", "parse_hex_length"]

```

---

## FILE: `adb\_internal\proto.py`

```python
from __future__ import annotations

from adb.transport.devices.domain import (
    AdbConnectionState,
    AdbConnectionType,
    AdbDevicesSnapshot,
    AdbTrackedDevice,
)
from adb.errors import AdbProtocolError
from adb.server.status.model import AdbMdnsBackend, AdbServerStatus, AdbUsbBackend
from adb.transport.selection import AdbTransportId


_DEVICE_STRING_FIELDS = {
    1: "serial",
    3: "bus_address",
    4: "product",
    5: "model",
    6: "device",
}
_DEVICE_INT64_FIELDS = {
    8: "negotiated_speed",
    9: "max_speed",
}
_SERVER_STRING_FIELDS = {
    5: "version",
    6: "build",
    7: "executable_absolute_path",
    8: "log_absolute_path",
    9: "os",
    10: "trace_level",
}


class ProtoReader:
    """Minimal protobuf wire reader for the AOSP adb_host.proto payloads we own."""

    def __init__(self, payload: bytes) -> None:
        if not isinstance(payload, bytes):
            raise TypeError("protobuf payload must be bytes")
        self.payload = payload
        self.offset = 0

    @property
    def done(self) -> bool:
        return self.offset == len(self.payload)

    def read_varint(self) -> int:
        result = 0
        for byte_index in range(10):
            if self.offset >= len(self.payload):
                raise AdbProtocolError("truncated protobuf varint")
            byte = self.payload[self.offset]
            self.offset += 1
            if byte_index == 9 and byte > 1:
                raise AdbProtocolError("protobuf varint exceeds 64 bits")
            result |= (byte & 0x7F) << (7 * byte_index)
            if byte < 0x80:
                return result
        raise AdbProtocolError("protobuf varint exceeds 64 bits")

    def read_key(self) -> tuple[int, int]:
        key = self.read_varint()
        field_number = key >> 3
        wire_type = key & 0x07
        if field_number == 0:
            raise AdbProtocolError("protobuf field number cannot be zero")
        return field_number, wire_type

    def read_bytes(self) -> bytes:
        size = self.read_varint()
        end = self.offset + size
        if end > len(self.payload):
            raise AdbProtocolError("truncated protobuf length-delimited field")
        value = self.payload[self.offset:end]
        self.offset = end
        return value

    def skip(self, wire_type: int) -> None:
        if wire_type == 0:
            self.read_varint()
            return
        if wire_type == 1:
            self._skip_fixed(8)
            return
        if wire_type == 2:
            self.read_bytes()
            return
        if wire_type == 5:
            self._skip_fixed(4)
            return
        raise AdbProtocolError(f"unsupported protobuf wire type {wire_type}")

    def _skip_fixed(self, size: int) -> None:
        end = self.offset + size
        if end > len(self.payload):
            raise AdbProtocolError("truncated protobuf fixed-width field")
        self.offset = end


def _decode_utf8(raw: bytes, *, field_name: str) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AdbProtocolError(f"ADB protobuf {field_name} is not valid UTF-8") from exc


def _decode_int64(raw: int) -> int:
    if raw >= (1 << 63):
        return raw - (1 << 64)
    return raw


def _decode_device(payload: bytes) -> AdbTrackedDevice:
    reader = ProtoReader(payload)
    values: dict[str, object] = {}

    while not reader.done:
        field_number, wire_type = reader.read_key()

        string_field = _DEVICE_STRING_FIELDS.get(field_number)
        if string_field is not None:
            if wire_type != 2:
                raise AdbProtocolError(
                    f"ADB Device field {field_number} has wire type {wire_type}, expected 2"
                )
            values[string_field] = _decode_utf8(
                reader.read_bytes(), field_name=string_field
            )
            continue

        if field_number == 2:
            if wire_type != 0:
                raise AdbProtocolError(
                    f"ADB Device state has wire type {wire_type}, expected 0"
                )
            raw_state = reader.read_varint()
            try:
                values["state"] = AdbConnectionState(raw_state)
            except ValueError:
                values["state"] = raw_state
            continue

        if field_number == 7:
            if wire_type != 0:
                raise AdbProtocolError(
                    "ADB Device connection_type has wire type "
                    f"{wire_type}, expected 0"
                )
            raw_type = reader.read_varint()
            try:
                values["connection_type"] = AdbConnectionType(raw_type)
            except ValueError:
                values["connection_type"] = raw_type
            continue

        int64_field = _DEVICE_INT64_FIELDS.get(field_number)
        if int64_field is not None:
            if wire_type != 0:
                raise AdbProtocolError(
                    f"ADB Device field {field_number} has wire type {wire_type}, expected 0"
                )
            values[int64_field] = _decode_int64(reader.read_varint())
            continue

        if field_number == 10:
            if wire_type != 0:
                raise AdbProtocolError(
                    f"ADB Device transport_id has wire type {wire_type}, expected 0"
                )
            raw_transport_id = _decode_int64(reader.read_varint())
            values["transport_id"] = (
                0 if raw_transport_id == 0 else AdbTransportId(raw_transport_id)
            )
            continue

        reader.skip(wire_type)

    return AdbTrackedDevice(**values)


def parse_devices_snapshot(payload: bytes) -> AdbDevicesSnapshot:
    reader = ProtoReader(payload)
    devices: list[AdbTrackedDevice] = []

    while not reader.done:
        field_number, wire_type = reader.read_key()
        if field_number == 1:
            if wire_type != 2:
                raise AdbProtocolError(
                    f"ADB Devices.device has wire type {wire_type}, expected 2"
                )
            devices.append(_decode_device(reader.read_bytes()))
            continue
        reader.skip(wire_type)

    return AdbDevicesSnapshot(tuple(devices))


def parse_server_status(payload: bytes) -> AdbServerStatus:
    reader = ProtoReader(payload)
    values: dict[str, object] = {}

    while not reader.done:
        field_number, wire_type = reader.read_key()

        if field_number in (1, 3):
            if wire_type != 0:
                raise AdbProtocolError(
                    f"ADB server enum field {field_number} has wire type {wire_type}, expected 0"
                )
            raw = reader.read_varint()
            enum_type = AdbUsbBackend if field_number == 1 else AdbMdnsBackend
            name = "usb_backend" if field_number == 1 else "mdns_backend"
            try:
                values[name] = enum_type(raw)
            except ValueError:
                values[name] = raw
            continue

        if field_number in (2, 4, 11, 12):
            if wire_type != 0:
                raise AdbProtocolError(
                    f"ADB server bool field {field_number} has wire type {wire_type}, expected 0"
                )
            name = {
                2: "usb_backend_forced",
                4: "mdns_backend_forced",
                11: "burst_mode",
                12: "mdns_enabled",
            }[field_number]
            values[name] = bool(reader.read_varint())
            continue

        string_field = _SERVER_STRING_FIELDS.get(field_number)
        if string_field is not None:
            if wire_type != 2:
                raise AdbProtocolError(
                    f"ADB server field {field_number} has wire type {wire_type}, expected 2"
                )
            values[string_field] = _decode_utf8(
                reader.read_bytes(), field_name=string_field
            )
            continue

        reader.skip(wire_type)

    return AdbServerStatus(**values)


__all__ = ["parse_devices_snapshot", "parse_server_status"]

```

---

## FILE: `adb\_internal\subprocess.py`

```python
from __future__ import annotations

from datetime import datetime, timezone
import math
import subprocess

from adb.server.endpoint import AdbServerEndpoint
from adb.transport.selection import AdbTransportById, AdbTransportBySerial, AdbTransportSelector
from native_attempt import NativeAttemptResult, NativeAttemptStatus, NativeCompletionScope


def normalize_executable(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("ADB executable must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("ADB executable cannot be empty")
    return normalized


def normalize_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("ADB subprocess timeout must be a number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0:
        raise ValueError("ADB subprocess timeout must be finite and greater than zero")
    return normalized


def selector_args(selector: AdbTransportSelector) -> list[str]:
    if isinstance(selector, AdbTransportBySerial):
        return ["-s", selector.serial.value]
    if isinstance(selector, AdbTransportById):
        return ["-t", str(selector.transport_id.value)]
    raise TypeError("selector must be an ADB transport selector")


def server_args(endpoint: AdbServerEndpoint) -> list[str]:
    if not isinstance(endpoint, AdbServerEndpoint):
        raise TypeError("endpoint must be AdbServerEndpoint")
    return ["-H", endpoint.host, "-P", str(endpoint.port)]


def run_adb(
    executable: str,
    timeout_seconds: float,
    args: list[str],
    *,
    input_text: str | None = None,
) -> NativeAttemptResult:
    started_at = datetime.now(timezone.utc)
    run_kwargs: dict[str, object] = {
        "capture_output": True,
        "text": True,
        "check": False,
        "timeout": timeout_seconds,
    }
    if input_text is not None:
        run_kwargs["input"] = input_text
    try:
        completed = subprocess.run([executable, *args], **run_kwargs)
    except subprocess.TimeoutExpired as exc:
        return NativeAttemptResult(
            status=NativeAttemptStatus.TIMED_OUT,
            completion_scope=None,
            backend_id="adb-subprocess",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            native_code=type(exc).__name__,
            diagnostic=str(exc),
        )
    except OSError as exc:
        return NativeAttemptResult(
            status=NativeAttemptStatus.FAILED,
            completion_scope=None,
            backend_id="adb-subprocess",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            native_code=type(exc).__name__,
            diagnostic=str(exc),
        )

    diagnostic = "\n".join(
        part
        for part in (completed.stdout.strip(), completed.stderr.strip())
        if part
    ) or None
    return NativeAttemptResult(
        status=(
            NativeAttemptStatus.SUCCEEDED
            if completed.returncode == 0
            else NativeAttemptStatus.FAILED
        ),
        completion_scope=NativeCompletionScope.PROCESS_EXIT,
        backend_id="adb-subprocess",
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        native_code=str(completed.returncode),
        diagnostic=diagnostic,
    )


__all__ = [
    "normalize_executable",
    "normalize_timeout",
    "run_adb",
    "selector_args",
    "server_args",
]

```

---

## FILE: `adb\pairing\__init__.py`

```python
"""ADB wireless-debugging pairing command ownership."""

__all__: list[str] = []

```

---

## FILE: `adb\pairing\adapters.py`

```python
from __future__ import annotations

from dataclasses import dataclass

from adb._internal.subprocess import (
    normalize_executable,
    normalize_timeout,
    run_adb,
    server_args,
)
from adb.server.endpoint import AdbServerEndpoint
from adb.pairing.command import AdbWirelessPair
from native_attempt import NativeAttemptResult


@dataclass(frozen=True, slots=True)
class SubprocessAdbPairing:
    """Execute one endpoint-bound ADB pairing command per bounded CLI attempt."""

    endpoint: AdbServerEndpoint
    executable: str = "adb"
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        object.__setattr__(self, "executable", normalize_executable(self.executable))
        object.__setattr__(self, "timeout_seconds", normalize_timeout(self.timeout_seconds))

    def pair(self, operation: AdbWirelessPair) -> NativeAttemptResult:
        if not isinstance(operation, AdbWirelessPair):
            raise TypeError("operation must be AdbWirelessPair")
        return run_adb(
            self.executable,
            self.timeout_seconds,
            [*server_args(self.endpoint), "pair", operation.address],
            input_text=f"{operation.pairing_code}\n",
        )


__all__ = ["SubprocessAdbPairing"]

```

---

## FILE: `adb\pairing\command.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from native_attempt import NativeAttemptResult


def _normalize_required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


@dataclass(frozen=True, slots=True)
class AdbWirelessPair:
    """Request one pairing attempt for an explicit wireless-debugging pairing endpoint."""

    address: str
    pairing_code: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "address",
            _normalize_required_text(self.address, field_name="ADB pairing address"),
        )
        object.__setattr__(
            self,
            "pairing_code",
            _normalize_required_text(self.pairing_code, field_name="ADB pairing code"),
        )


class AdbWirelessPairer(Protocol):
    def pair(self, operation: AdbWirelessPair) -> NativeAttemptResult: ...


__all__ = ["AdbWirelessPair", "AdbWirelessPairer"]

```

---

## FILE: `adb\pairing\signal.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from adb.pairing.command import AdbWirelessPair
from native_attempt import NativeAttemptResult


AdbPairingCommandOperation: TypeAlias = AdbWirelessPair


@dataclass(frozen=True, slots=True)
class AdbPairingCommandCompleted:
    """Signal carrying the result of one atomic ADB pairing command attempt."""

    operation: AdbPairingCommandOperation
    result: NativeAttemptResult

    def __post_init__(self) -> None:
        if not isinstance(self.operation, AdbWirelessPair):
            raise TypeError("operation must be an ADB pairing command operation")
        if not isinstance(self.result, NativeAttemptResult):
            raise TypeError("result must be NativeAttemptResult")


AdbPairingSignal: TypeAlias = AdbPairingCommandCompleted


__all__ = [
    "AdbPairingCommandCompleted",
    "AdbPairingCommandOperation",
    "AdbPairingSignal",
]

```

---

## FILE: `adb\server\__init__.py`

```python
"""ADB server endpoint and status ownership."""

from adb.server.endpoint import AdbServerEndpoint
from adb.server.status import AdbMdnsBackend, AdbServerStatus, AdbServerStatusReader, AdbUsbBackend

__all__ = ["AdbMdnsBackend", "AdbServerEndpoint", "AdbServerStatus", "AdbServerStatusReader", "AdbUsbBackend"]

```

---

## FILE: `adb\server\endpoint.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral


def _normalize_required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string, got {type(value).__name__}")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


@dataclass(frozen=True, slots=True, order=True)
class AdbServerEndpoint:
    """TCP address of one host-side ADB smart-socket server."""

    host: str = "localhost"
    port: int = 5037

    def __post_init__(self) -> None:
        host = _normalize_required_text(self.host, field_name="ADB server endpoint host")
        if isinstance(self.port, bool) or not isinstance(self.port, Integral):
            raise TypeError("ADB server endpoint port must be an integer")
        port = int(self.port)
        if not 1 <= port <= 65535:
            raise ValueError("ADB server endpoint port must be between 1 and 65535")
        object.__setattr__(self, "host", host)
        object.__setattr__(self, "port", port)


__all__ = ["AdbServerEndpoint"]

```

---

## FILE: `adb\server\provisioning.py`

```python
from __future__ import annotations

from threading import Lock
from typing import Protocol, runtime_checkable

from adb.server.endpoint import AdbServerEndpoint


class AdbServerProvisioningError(RuntimeError):
    """Base error for ADB server endpoint provisioning failures."""


class AdbServerEndpointConflictError(AdbServerProvisioningError):
    """An endpoint is already reserved in this provisioning scope."""


class AdbServerEndpointExhaustedError(AdbServerProvisioningError):
    """The endpoint allocator could not produce another unreserved endpoint."""


@runtime_checkable
class AdbServerEndpointAllocator(Protocol):
    """Allocate one endpoint not present in the supplied reservation set."""

    def allocate(
        self,
        reserved_endpoints: frozenset[AdbServerEndpoint],
    ) -> AdbServerEndpoint: ...


class SequentialLocalAdbServerEndpointAllocator:
    """Allocate registry-unique localhost endpoints from an increasing port range.

    The allocator does not probe operating-system socket availability. Provisioning
    owns only endpoint reservation; a caller-owned server id, if any, is associated
    with the returned endpoint by external composition.
    """

    def __init__(self, host: str = "localhost", first_port: int = 5037) -> None:
        first = AdbServerEndpoint(host=host, port=first_port)
        self.host = first.host
        self.first_port = first.port

    def allocate(
        self,
        reserved_endpoints: frozenset[AdbServerEndpoint],
    ) -> AdbServerEndpoint:
        if not isinstance(reserved_endpoints, frozenset):
            raise TypeError("reserved_endpoints must be a frozenset")
        for endpoint in reserved_endpoints:
            if not isinstance(endpoint, AdbServerEndpoint):
                raise TypeError("reserved_endpoints must contain AdbServerEndpoint values")

        for port in range(self.first_port, 65536):
            candidate = AdbServerEndpoint(self.host, port)
            if candidate not in reserved_endpoints:
                return candidate
        raise AdbServerEndpointExhaustedError(
            f"no unreserved ADB server endpoint remains for host {self.host!r} "
            f"starting at port {self.first_port}"
        )


@runtime_checkable
class AdbServerProvisioner(Protocol):
    """Reserve native ADB server endpoints without caller identity semantics."""

    def provision(
        self,
        *,
        endpoint: AdbServerEndpoint | None = None,
    ) -> AdbServerEndpoint: ...


class InMemoryAdbServerProvisioner:
    """Reserve distinct ADB server endpoints for one process-local scope.

    Caller-owned logical server identities and their endpoint bindings deliberately
    remain outside the ADB domain. A caller resolves or creates that association, then
    passes the resulting ``AdbServerEndpoint`` into ADB queries, commands, and
    orchestration.
    """

    def __init__(self, allocator: AdbServerEndpointAllocator | None = None) -> None:
        allocator = allocator or SequentialLocalAdbServerEndpointAllocator()
        if not callable(getattr(allocator, "allocate", None)):
            raise TypeError("allocator must provide allocate()")
        self._allocator = allocator
        self._reserved: set[AdbServerEndpoint] = set()
        self._lock = Lock()

    def provision(
        self,
        *,
        endpoint: AdbServerEndpoint | None = None,
    ) -> AdbServerEndpoint:
        if endpoint is not None and not isinstance(endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint or None")

        with self._lock:
            selected = endpoint
            if selected is None:
                selected = self._allocator.allocate(frozenset(self._reserved))
                if not isinstance(selected, AdbServerEndpoint):
                    raise TypeError("allocator.allocate() must return AdbServerEndpoint")

            if selected in self._reserved:
                raise AdbServerEndpointConflictError(
                    f"ADB server endpoint {selected.host}:{selected.port} is already reserved"
                )

            self._reserved.add(selected)
            return selected


__all__ = [
    "AdbServerEndpointAllocator",
    "AdbServerEndpointConflictError",
    "AdbServerEndpointExhaustedError",
    "AdbServerProvisioner",
    "AdbServerProvisioningError",
    "InMemoryAdbServerProvisioner",
    "SequentialLocalAdbServerEndpointAllocator",
]

```

---

## FILE: `adb\server\signal.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from adb.server.lifecycle.command import AdbServerStart, AdbServerStop
from adb.server.lifecycle.ensure import (
    AdbServerEnsureResult,
    AdbServerProbeResult,
)
from native_attempt import NativeAttemptResult


AdbServerCommandOperation: TypeAlias = AdbServerStart | AdbServerStop


@dataclass(frozen=True, slots=True)
class AdbServerCommandCompleted:
    """Signal carrying the result of one atomic ADB server command attempt."""

    operation: AdbServerCommandOperation
    result: NativeAttemptResult

    def __post_init__(self) -> None:
        if not isinstance(self.operation, (AdbServerStart, AdbServerStop)):
            raise TypeError("operation must be an ADB server command operation")
        if not isinstance(self.result, NativeAttemptResult):
            raise TypeError("result must be NativeAttemptResult")


@dataclass(frozen=True, slots=True)
class AdbServerProbeCompleted:
    """Signal carrying evidence from one fresh ADB server probe."""

    probe: AdbServerProbeResult

    def __post_init__(self) -> None:
        if not isinstance(self.probe, AdbServerProbeResult):
            raise TypeError("probe must be AdbServerProbeResult")


@dataclass(frozen=True, slots=True)
class AdbServerEnsureCompleted:
    """Signal carrying terminal evidence from one ADB server ensure operation."""

    result: AdbServerEnsureResult

    def __post_init__(self) -> None:
        if not isinstance(self.result, AdbServerEnsureResult):
            raise TypeError("result must be AdbServerEnsureResult")


AdbServerSignal: TypeAlias = (
    AdbServerCommandCompleted
    | AdbServerProbeCompleted
    | AdbServerEnsureCompleted
)


__all__ = [
    "AdbServerCommandCompleted",
    "AdbServerCommandOperation",
    "AdbServerEnsureCompleted",
    "AdbServerProbeCompleted",
    "AdbServerSignal",
]

```

---

## FILE: `adb\server\lifecycle\__init__.py`

```python
"""ADB server lifecycle atomic commands and bounded same-domain orchestration."""

from adb.server.lifecycle.command import (
    AdbServerStart,
    AdbServerStarter,
    AdbServerStop,
    AdbServerStopper,
)
from adb.server.lifecycle.ensure import (
    AdbServerAvailability,
    AdbServerEnsureAvailable,
    AdbServerEnsureOperation,
    AdbServerEnsureOrchestrator,
    AdbServerEnsurePolicy,
    AdbServerEnsureResult,
    AdbServerEnsureStatus,
    AdbServerEnsureUnavailable,
    AdbServerProbeResult,
    AdbServerSatisfaction,
)

__all__ = [
    "AdbServerAvailability",
    "AdbServerEnsureAvailable",
    "AdbServerEnsureOperation",
    "AdbServerEnsureOrchestrator",
    "AdbServerEnsurePolicy",
    "AdbServerEnsureResult",
    "AdbServerEnsureStatus",
    "AdbServerEnsureUnavailable",
    "AdbServerProbeResult",
    "AdbServerSatisfaction",
    "AdbServerStart",
    "AdbServerStarter",
    "AdbServerStop",
    "AdbServerStopper",
]

```

---

## FILE: `adb\server\lifecycle\adapters.py`

```python
from __future__ import annotations

from dataclasses import dataclass

from adb._internal.subprocess import normalize_executable, normalize_timeout, run_adb, server_args
from adb.server.endpoint import AdbServerEndpoint
from adb.server.lifecycle.command import AdbServerStart, AdbServerStop
from native_attempt import NativeAttemptResult


@dataclass(frozen=True, slots=True)
class SubprocessAdbServer:
    """Execute one endpoint-bound ADB server lifecycle command per bounded CLI attempt."""

    endpoint: AdbServerEndpoint
    executable: str = "adb"
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        object.__setattr__(self, "executable", normalize_executable(self.executable))
        object.__setattr__(self, "timeout_seconds", normalize_timeout(self.timeout_seconds))

    def start(self, operation: AdbServerStart) -> NativeAttemptResult:
        if not isinstance(operation, AdbServerStart):
            raise TypeError("operation must be AdbServerStart")
        if operation.endpoint != self.endpoint:
            raise ValueError("operation endpoint does not match configured ADB server endpoint")
        return run_adb(self.executable, self.timeout_seconds, [*server_args(self.endpoint), "start-server"])

    def stop(self, operation: AdbServerStop) -> NativeAttemptResult:
        if not isinstance(operation, AdbServerStop):
            raise TypeError("operation must be AdbServerStop")
        if operation.endpoint != self.endpoint:
            raise ValueError("operation endpoint does not match configured ADB server endpoint")
        return run_adb(self.executable, self.timeout_seconds, [*server_args(self.endpoint), "kill-server"])


__all__ = ["SubprocessAdbServer"]

```

---

## FILE: `adb\server\lifecycle\command.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adb.server.endpoint import AdbServerEndpoint
from native_attempt import NativeAttemptResult


@dataclass(frozen=True, slots=True)
class AdbServerStart:
    """Request one native attempt to start the ADB server at one endpoint."""

    endpoint: AdbServerEndpoint

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")


@dataclass(frozen=True, slots=True)
class AdbServerStop:
    """Request one native attempt to stop the ADB server at one endpoint."""

    endpoint: AdbServerEndpoint

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")


class AdbServerStarter(Protocol):
    def start(self, operation: AdbServerStart) -> NativeAttemptResult: ...


class AdbServerStopper(Protocol):
    def stop(self, operation: AdbServerStop) -> NativeAttemptResult: ...


__all__ = ["AdbServerStart", "AdbServerStarter", "AdbServerStop", "AdbServerStopper"]

```

---

## FILE: `adb\server\lifecycle\ensure.py`

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import math
from numbers import Real
from time import monotonic, sleep
from typing import TypeAlias

from adb.server.endpoint import AdbServerEndpoint
from adb.errors import AdbError, AdbServerConnectionError
from adb.server.lifecycle.command import (
    AdbServerStart,
    AdbServerStarter,
    AdbServerStop,
    AdbServerStopper,
)
from adb.server.status.model import AdbServerStatus
from adb.server.status.query import AdbServerStatusReader
from eventing import EventPublisher
from native_attempt import NativeAttemptResult, NativeAttemptStatus


_MonotonicClock = Callable[[], float]
_Sleeper = Callable[[float], None]


def _normalize_positive_seconds(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a real number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0.0:
        raise ValueError(f"{field_name} must be finite and greater than zero")
    return normalized


def _normalize_optional_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


class AdbServerAvailability(str, Enum):
    """Domain-local observation of one configured ADB server endpoint."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    INDETERMINATE = "indeterminate"


class AdbServerEnsureStatus(str, Enum):
    """Terminal status of ADB server availability orchestration."""

    SATISFIED = "satisfied"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class AdbServerSatisfaction(str, Enum):
    """How an ensure operation reached its requested observable condition."""

    ALREADY_SATISFIED = "already_satisfied"
    ACHIEVED = "achieved"


@dataclass(frozen=True, slots=True)
class AdbServerEnsurePolicy:
    """Explicit waiting policy for ADB server availability orchestration."""

    timeout_seconds: float
    probe_interval_seconds: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "timeout_seconds",
            _normalize_positive_seconds(
                self.timeout_seconds,
                field_name="ADB server ensure timeout",
            ),
        )
        object.__setattr__(
            self,
            "probe_interval_seconds",
            _normalize_positive_seconds(
                self.probe_interval_seconds,
                field_name="ADB server ensure probe interval",
            ),
        )


@dataclass(frozen=True, slots=True)
class AdbServerEnsureAvailable:
    """Request domain orchestration to establish and verify server availability."""

    endpoint: AdbServerEndpoint
    policy: AdbServerEnsurePolicy

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(self.policy, AdbServerEnsurePolicy):
            raise TypeError("policy must be AdbServerEnsurePolicy")


@dataclass(frozen=True, slots=True)
class AdbServerEnsureUnavailable:
    """Request domain orchestration to establish and verify server unavailability."""

    endpoint: AdbServerEndpoint
    policy: AdbServerEnsurePolicy

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(self.policy, AdbServerEnsurePolicy):
            raise TypeError("policy must be AdbServerEnsurePolicy")


AdbServerEnsureOperation: TypeAlias = AdbServerEnsureAvailable | AdbServerEnsureUnavailable


@dataclass(frozen=True, slots=True)
class AdbServerProbeResult:
    """Evidence from one fresh probe performed by ADB server orchestration."""

    endpoint: AdbServerEndpoint
    availability: AdbServerAvailability
    server_status: AdbServerStatus | None = None
    diagnostic: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(self.availability, AdbServerAvailability):
            raise TypeError("availability must be AdbServerAvailability")
        if self.availability is AdbServerAvailability.AVAILABLE:
            if not isinstance(self.server_status, AdbServerStatus):
                raise ValueError("available probe requires AdbServerStatus")
        elif self.server_status is not None:
            raise ValueError("non-available probe cannot carry AdbServerStatus")
        object.__setattr__(
            self,
            "diagnostic",
            _normalize_optional_text(
                self.diagnostic,
                field_name="ADB server probe diagnostic",
            ),
        )


@dataclass(frozen=True, slots=True)
class AdbServerEnsureResult:
    """Terminal evidence produced by ADB server availability orchestration."""

    operation: AdbServerEnsureOperation
    status: AdbServerEnsureStatus
    satisfaction: AdbServerSatisfaction | None
    attempts: tuple[NativeAttemptResult, ...]
    final_probe: AdbServerProbeResult

    def __post_init__(self) -> None:
        if not isinstance(
            self.operation,
            (AdbServerEnsureAvailable, AdbServerEnsureUnavailable),
        ):
            raise TypeError("operation must be an ADB server ensure operation")
        if not isinstance(self.status, AdbServerEnsureStatus):
            raise TypeError("status must be AdbServerEnsureStatus")
        if self.satisfaction is not None and not isinstance(
            self.satisfaction,
            AdbServerSatisfaction,
        ):
            raise TypeError("satisfaction must be AdbServerSatisfaction or None")
        if not isinstance(self.attempts, tuple) or not all(
            isinstance(attempt, NativeAttemptResult) for attempt in self.attempts
        ):
            raise TypeError("attempts must be a tuple of NativeAttemptResult")
        if not isinstance(self.final_probe, AdbServerProbeResult):
            raise TypeError("final_probe must be AdbServerProbeResult")
        if self.final_probe.endpoint != self.operation.endpoint:
            raise ValueError("final probe endpoint must match ensure operation")
        desired = (
            AdbServerAvailability.AVAILABLE
            if isinstance(self.operation, AdbServerEnsureAvailable)
            else AdbServerAvailability.UNAVAILABLE
        )
        condition_met = self.final_probe.availability is desired
        if self.status is AdbServerEnsureStatus.SATISFIED:
            if self.satisfaction is None:
                raise ValueError("satisfied ensure result requires satisfaction")
            if not condition_met:
                raise ValueError("satisfied ensure result requires matching final probe")
        else:
            if self.satisfaction is not None:
                raise ValueError("unsatisfied ensure result cannot carry satisfaction")
            if condition_met:
                raise ValueError("matching final probe requires satisfied ensure status")
        if (
            self.satisfaction is AdbServerSatisfaction.ALREADY_SATISFIED
            and self.attempts
        ):
            raise ValueError("already-satisfied ensure result cannot contain native attempts")


class AdbServerEnsureOrchestrator:
    """Concrete same-domain executor for probe/command/verification ensure operations."""

    def __init__(
        self,
        endpoint: AdbServerEndpoint,
        status_reader: AdbServerStatusReader,
        starter: AdbServerStarter,
        stopper: AdbServerStopper,
        publisher: EventPublisher,
        *,
        _monotonic: _MonotonicClock = monotonic,
        _sleep: _Sleeper = sleep,
    ) -> None:
        if not isinstance(endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not callable(getattr(status_reader, "read", None)):
            raise TypeError("status_reader must provide read()")
        if not callable(getattr(starter, "start", None)):
            raise TypeError("starter must provide start()")
        if not callable(getattr(stopper, "stop", None)):
            raise TypeError("stopper must provide stop()")
        if not isinstance(publisher, EventPublisher):
            raise TypeError("publisher must satisfy EventPublisher")
        self.endpoint = endpoint
        self._status_reader = status_reader
        self._starter = starter
        self._stopper = stopper
        self._publisher = publisher
        self._monotonic = _monotonic
        self._sleep = _sleep

    def probe(self) -> AdbServerProbeResult:
        from adb.server.signal import AdbServerProbeCompleted

        try:
            status = self._status_reader.read(self.endpoint)
        except AdbServerConnectionError as exc:
            result = AdbServerProbeResult(
                endpoint=self.endpoint,
                availability=AdbServerAvailability.UNAVAILABLE,
                diagnostic=str(exc),
            )
        except AdbError as exc:
            result = AdbServerProbeResult(
                endpoint=self.endpoint,
                availability=AdbServerAvailability.INDETERMINATE,
                diagnostic=str(exc),
            )
        else:
            result = AdbServerProbeResult(
                endpoint=self.endpoint,
                availability=AdbServerAvailability.AVAILABLE,
                server_status=status,
            )
        self._publisher.publish(AdbServerProbeCompleted(result))
        return result

    def ensure(self, operation: AdbServerEnsureOperation) -> AdbServerEnsureResult:
        from adb.server.signal import AdbServerCommandCompleted, AdbServerEnsureCompleted

        if not isinstance(operation, (AdbServerEnsureAvailable, AdbServerEnsureUnavailable)):
            raise TypeError("operation must be an ADB server ensure operation")
        if operation.endpoint != self.endpoint:
            raise ValueError("operation endpoint does not match configured ADB server endpoint")
        desired = (
            AdbServerAvailability.AVAILABLE
            if isinstance(operation, AdbServerEnsureAvailable)
            else AdbServerAvailability.UNAVAILABLE
        )
        first_probe = self.probe()
        if first_probe.availability is desired:
            result = AdbServerEnsureResult(
                operation=operation,
                status=AdbServerEnsureStatus.SATISFIED,
                satisfaction=AdbServerSatisfaction.ALREADY_SATISFIED,
                attempts=(),
                final_probe=first_probe,
            )
            self._publisher.publish(AdbServerEnsureCompleted(result))
            return result
        deadline = self._monotonic() + operation.policy.timeout_seconds
        command = (
            AdbServerStart(operation.endpoint)
            if isinstance(operation, AdbServerEnsureAvailable)
            else AdbServerStop(operation.endpoint)
        )
        attempt = (
            self._starter.start(command)
            if isinstance(command, AdbServerStart)
            else self._stopper.stop(command)
        )
        self._publisher.publish(AdbServerCommandCompleted(command, attempt))
        final_probe = self.probe()
        while final_probe.availability is not desired:
            remaining = deadline - self._monotonic()
            if remaining <= 0.0:
                terminal_status = (
                    AdbServerEnsureStatus.FAILED
                    if attempt.status is NativeAttemptStatus.FAILED
                    else AdbServerEnsureStatus.TIMED_OUT
                )
                result = AdbServerEnsureResult(
                    operation=operation,
                    status=terminal_status,
                    satisfaction=None,
                    attempts=(attempt,),
                    final_probe=final_probe,
                )
                self._publisher.publish(AdbServerEnsureCompleted(result))
                return result
            self._sleep(min(operation.policy.probe_interval_seconds, remaining))
            final_probe = self.probe()
        result = AdbServerEnsureResult(
            operation=operation,
            status=AdbServerEnsureStatus.SATISFIED,
            satisfaction=AdbServerSatisfaction.ACHIEVED,
            attempts=(attempt,),
            final_probe=final_probe,
        )
        self._publisher.publish(AdbServerEnsureCompleted(result))
        return result


__all__ = [
    "AdbServerAvailability",
    "AdbServerEnsureAvailable",
    "AdbServerEnsureOperation",
    "AdbServerEnsureOrchestrator",
    "AdbServerEnsurePolicy",
    "AdbServerEnsureResult",
    "AdbServerEnsureStatus",
    "AdbServerEnsureUnavailable",
    "AdbServerProbeResult",
    "AdbServerSatisfaction",
]

```

---

## FILE: `adb\server\status\__init__.py`

```python
"""ADB server status facts and atomic read contracts."""

from adb.server.status.model import (
    AdbMdnsBackend,
    AdbServerStatus,
    AdbUsbBackend,
)
from adb.server.status.query import AdbServerStatusReader

__all__ = [
    "AdbMdnsBackend",
    "AdbServerStatus",
    "AdbServerStatusReader",
    "AdbUsbBackend",
]

```

---

## FILE: `adb\server\status\adapters.py`

```python
from __future__ import annotations

from collections.abc import Callable

from adb._internal.client import AdbServiceClient
from adb._internal.proto import parse_server_status
from adb.server.endpoint import AdbServerEndpoint
from adb.server.status.model import AdbServerStatus


_ClientFactory = Callable[[AdbServerEndpoint], AdbServiceClient]


def _default_client_factory(endpoint: AdbServerEndpoint) -> AdbServiceClient:
    return AdbServiceClient(endpoint)


class SmartSocketAdbServerStatusReader:
    """One-shot reader for AOSP ``host:server-status``."""

    def __init__(self, *, _client_factory: _ClientFactory = _default_client_factory) -> None:
        self._client_factory = _client_factory

    def read(self, endpoint: AdbServerEndpoint) -> AdbServerStatus:
        if not isinstance(endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        payload = self._client_factory(endpoint).host_query("host:server-status")
        return parse_server_status(payload)


__all__ = ["SmartSocketAdbServerStatusReader"]

```

---

## FILE: `adb\server\status\model.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from numbers import Integral


def _require_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string, got {type(value).__name__}")
    return value


def _require_optional_string(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, field_name=field_name)


def _require_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{field_name} must be an integer")
    return int(value)


def _normalize_open_enum(
    value: object,
    enum_type: type[IntEnum],
    *,
    field_name: str,
) -> IntEnum | int:
    raw = _require_int(value, field_name=field_name)
    try:
        return enum_type(raw)
    except ValueError:
        return raw


class AdbUsbBackend(IntEnum):
    """AOSP ``adb_host.proto.UsbBackend`` values."""

    UNKNOWN_USB = 0
    NATIVE = 1
    LIBUSB = 2


class AdbMdnsBackend(IntEnum):
    """AOSP ``adb_host.proto.MdnsBackend`` values."""

    UNKNOWN_MDNS = 0
    BONJOUR = 1
    OPENSCREEN = 2


@dataclass(frozen=True, slots=True)
class AdbServerStatus:
    """AOSP ``adb_host.proto.AdbServerStatus`` payload."""

    usb_backend: AdbUsbBackend | int = AdbUsbBackend.UNKNOWN_USB
    usb_backend_forced: bool = False
    mdns_backend: AdbMdnsBackend | int = AdbMdnsBackend.UNKNOWN_MDNS
    mdns_backend_forced: bool = False
    version: str = ""
    build: str = ""
    executable_absolute_path: str = ""
    log_absolute_path: str = ""
    os: str = ""
    trace_level: str | None = None
    burst_mode: bool | None = None
    mdns_enabled: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "usb_backend",
            _normalize_open_enum(
                self.usb_backend,
                AdbUsbBackend,
                field_name="ADB USB backend",
            ),
        )
        object.__setattr__(
            self,
            "mdns_backend",
            _normalize_open_enum(
                self.mdns_backend,
                AdbMdnsBackend,
                field_name="ADB mDNS backend",
            ),
        )
        for field_name in ("usb_backend_forced", "mdns_backend_forced"):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"ADB server {field_name} must be bool")
        for field_name in (
            "version",
            "build",
            "executable_absolute_path",
            "log_absolute_path",
            "os",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_string(getattr(self, field_name), field_name=f"ADB server {field_name}"),
            )
        object.__setattr__(
            self,
            "trace_level",
            _require_optional_string(self.trace_level, field_name="ADB server trace_level"),
        )
        for field_name in ("burst_mode", "mdns_enabled"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, bool):
                raise TypeError(f"ADB server {field_name} must be bool or None")


__all__ = ["AdbMdnsBackend", "AdbServerStatus", "AdbUsbBackend"]

```

---

## FILE: `adb\server\status\query.py`

```python
from __future__ import annotations

from typing import Protocol

from adb.server.endpoint import AdbServerEndpoint
from adb.server.status.model import AdbServerStatus


class AdbServerStatusReader(Protocol):
    """Read the current AOSP host-side ADB server status."""

    def read(self, endpoint: AdbServerEndpoint) -> AdbServerStatus:
        ...


__all__ = ["AdbServerStatusReader"]

```

---

## FILE: `adb\supervision\__init__.py`

```python
"""Long-lived ADB server, transport, and observation supervision."""

from adb.supervision.model import (
    AdbDevicesObservationEstablishmentCycleId,
    AdbDevicesObservationSupervisionPolicy,
    AdbServerRecoveryCycleId,
    AdbServerSupervisionPolicy,
    AdbTransportBindingSupervisionPolicy,
)
from adb.supervision.signal import (
    AdbDevicesObservationEstablishmentExhausted,
    AdbDevicesObservationEstablishmentRetryDue,
    AdbServerRecoveryExhausted,
    AdbServerRecoveryRetryDue,
    AdbSupervisionSignal,
    AdbTransportBindingRecoveryExhausted,
    AdbTransportBindingResolutionChanged,
)
from adb.supervision.server import AdbServerSupervisor
from adb.supervision.transport_binding import (
    AdbTransportBindingSupervisor,
    AdbTransportPreparationExecutor,
)
from adb.supervision.devices_observation import AdbDevicesObservationSupervisor

__all__ = [
    "AdbDevicesObservationEstablishmentCycleId",
    "AdbDevicesObservationEstablishmentExhausted",
    "AdbDevicesObservationEstablishmentRetryDue",
    "AdbDevicesObservationSupervisionPolicy",
    "AdbDevicesObservationSupervisor",
    "AdbServerRecoveryCycleId",
    "AdbServerRecoveryExhausted",
    "AdbServerRecoveryRetryDue",
    "AdbServerSupervisionPolicy",
    "AdbServerSupervisor",
    "AdbSupervisionSignal",
    "AdbTransportBindingRecoveryExhausted",
    "AdbTransportBindingResolutionChanged",
    "AdbTransportBindingSupervisionPolicy",
    "AdbTransportBindingSupervisor",
    "AdbTransportPreparationExecutor",
]

```

---

## FILE: `adb\supervision\devices_observation.py`

```python
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

```

---

## FILE: `adb\supervision\model.py`

```python
from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from uuid import uuid4

from adb.server.lifecycle import AdbServerEnsurePolicy
from adb.transport.orchestration import AdbTransportPreparationPolicy


def _normalize_positive_seconds(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a real number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0.0:
        raise ValueError(f"{field_name} must be finite and greater than zero")
    return normalized


def _normalize_required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


def _normalize_retry_configuration(
    *,
    retry_initial_seconds: object,
    retry_max_seconds: object,
    retry_multiplier: object,
    retry_jitter_ratio: object,
    max_attempts: object,
    prefix: str,
) -> tuple[float, float, float, float, int | None]:
    initial = _normalize_positive_seconds(
        retry_initial_seconds,
        field_name=f"{prefix} initial retry",
    )
    maximum = _normalize_positive_seconds(
        retry_max_seconds,
        field_name=f"{prefix} maximum retry",
    )
    multiplier = _normalize_positive_seconds(
        retry_multiplier,
        field_name=f"{prefix} retry multiplier",
    )
    if multiplier < 1.0:
        raise ValueError(f"{prefix} retry multiplier must be at least one")
    if maximum < initial:
        raise ValueError(f"{prefix} maximum retry must be >= initial retry")
    if isinstance(retry_jitter_ratio, bool) or not isinstance(retry_jitter_ratio, Real):
        raise TypeError(f"{prefix} retry jitter ratio must be a real number")
    jitter = float(retry_jitter_ratio)
    if not math.isfinite(jitter) or not 0.0 <= jitter < 1.0:
        raise ValueError(f"{prefix} retry jitter ratio must be in [0, 1)")
    if max_attempts is not None:
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int):
            raise TypeError(f"{prefix} max_attempts must be an integer or None")
        if max_attempts <= 0:
            raise ValueError(f"{prefix} max_attempts must be greater than zero")
    return initial, maximum, multiplier, jitter, max_attempts


@dataclass(frozen=True, slots=True)
class AdbTransportBindingSupervisionPolicy:
    """Long-lived binding projection with optional one-shot recovery per absence episode."""

    preparation_policy: AdbTransportPreparationPolicy | None = None

    def __post_init__(self) -> None:
        if self.preparation_policy is not None and not isinstance(
            self.preparation_policy, AdbTransportPreparationPolicy
        ):
            raise TypeError(
                "preparation_policy must be AdbTransportPreparationPolicy or None"
            )


@dataclass(frozen=True, slots=True, order=True)
class AdbServerRecoveryCycleId:
    """Opaque identity for one server-running recovery cycle."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "value",
            _normalize_required_text(
                self.value,
                field_name="ADB server recovery cycle id",
            ),
        )

    @classmethod
    def new(cls) -> "AdbServerRecoveryCycleId":
        return cls(uuid4().hex)


@dataclass(frozen=True, slots=True)
class AdbServerSupervisionPolicy:
    """Retry policy for maintaining one ADB server's desired running condition."""

    ensure_policy: AdbServerEnsurePolicy
    retry_initial_seconds: float = 0.5
    retry_max_seconds: float = 30.0
    retry_multiplier: float = 2.0
    retry_jitter_ratio: float = 0.2
    max_attempts: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.ensure_policy, AdbServerEnsurePolicy):
            raise TypeError("ensure_policy must be AdbServerEnsurePolicy")
        initial, maximum, multiplier, jitter, max_attempts = _normalize_retry_configuration(
            retry_initial_seconds=self.retry_initial_seconds,
            retry_max_seconds=self.retry_max_seconds,
            retry_multiplier=self.retry_multiplier,
            retry_jitter_ratio=self.retry_jitter_ratio,
            max_attempts=self.max_attempts,
            prefix="ADB server supervision",
        )
        object.__setattr__(self, "retry_initial_seconds", initial)
        object.__setattr__(self, "retry_max_seconds", maximum)
        object.__setattr__(self, "retry_multiplier", multiplier)
        object.__setattr__(self, "retry_jitter_ratio", jitter)
        object.__setattr__(self, "max_attempts", max_attempts)


@dataclass(frozen=True, slots=True, order=True)
class AdbDevicesObservationEstablishmentCycleId:
    """Opaque identity for one supervision cycle spanning observation attempts."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "value",
            _normalize_required_text(
                self.value,
                field_name="ADB transport-inventory observation establishment cycle id",
            ),
        )

    @classmethod
    def new(cls) -> "AdbDevicesObservationEstablishmentCycleId":
        return cls(uuid4().hex)


@dataclass(frozen=True, slots=True)
class AdbDevicesObservationSupervisionPolicy:
    """Retry policy around bounded transport-inventory observation establishment episodes."""

    episode_timeout_seconds: float = 10.0
    retry_initial_seconds: float = 0.5
    retry_max_seconds: float = 30.0
    retry_multiplier: float = 2.0
    retry_jitter_ratio: float = 0.2
    max_attempts: int | None = None

    def __post_init__(self) -> None:
        episode_timeout = _normalize_positive_seconds(
            self.episode_timeout_seconds,
            field_name="ADB observation establishment episode timeout",
        )
        initial, maximum, multiplier, jitter, max_attempts = _normalize_retry_configuration(
            retry_initial_seconds=self.retry_initial_seconds,
            retry_max_seconds=self.retry_max_seconds,
            retry_multiplier=self.retry_multiplier,
            retry_jitter_ratio=self.retry_jitter_ratio,
            max_attempts=self.max_attempts,
            prefix="ADB observation supervision",
        )
        object.__setattr__(self, "episode_timeout_seconds", episode_timeout)
        object.__setattr__(self, "retry_initial_seconds", initial)
        object.__setattr__(self, "retry_max_seconds", maximum)
        object.__setattr__(self, "retry_multiplier", multiplier)
        object.__setattr__(self, "retry_jitter_ratio", jitter)
        object.__setattr__(self, "max_attempts", max_attempts)


__all__ = [
    "AdbDevicesObservationEstablishmentCycleId",
    "AdbDevicesObservationSupervisionPolicy",
    "AdbServerRecoveryCycleId",
    "AdbServerSupervisionPolicy",
    "AdbTransportBindingSupervisionPolicy",
]

```

---

## FILE: `adb\supervision\server.py`

```python
from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from random import random
from threading import Lock, Thread, current_thread

from adb.server.endpoint import AdbServerEndpoint
from adb.server.lifecycle import (
    AdbServerEnsureAvailable,
    AdbServerEnsureOrchestrator,
    AdbServerEnsureResult,
    AdbServerEnsureStatus,
    AdbServerEnsureUnavailable,
)
from adb.supervision.model import AdbServerRecoveryCycleId, AdbServerSupervisionPolicy
from adb.supervision.signal import AdbServerRecoveryExhausted, AdbServerRecoveryRetryDue
from eventing import EventBus, EventSubscriptionToken
from scheduling import ScheduleToken, TemporalScheduler


_RandomSource = Callable[[], float]
_ThreadFactory = Callable[..., Thread]


def _default_thread_factory(*args, **kwargs) -> Thread:
    thread = Thread(*args, **kwargs)
    thread.daemon = True
    return thread


def _require_bool(value: object, *, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


class AdbServerSupervisor:
    """Maintain the desired running condition of one configured ADB server endpoint.

    The bounded ``AdbServerEnsureOrchestrator`` remains the owner of one probe/command/
    verification episode. This supervisor owns durable running intent, the recovery-enabled
    gate, retry/backoff state, stale-cycle fencing, and serialization of managed start/stop
    mutations for the endpoint.

    Availability monitoring is intentionally not hidden here: callers may invoke ``reconcile``
    when fresh evidence or another supervised condition suggests the running condition should be
    checked again. The managed runtime can later decide which liveness sources should trigger that
    reconciliation.
    """

    def __init__(
        self,
        endpoint: AdbServerEndpoint,
        event_bus: EventBus,
        ensure_orchestrator: AdbServerEnsureOrchestrator,
        scheduler: TemporalScheduler[object],
        policy: AdbServerSupervisionPolicy,
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
        if not isinstance(ensure_orchestrator, AdbServerEnsureOrchestrator):
            raise TypeError("ensure_orchestrator must be AdbServerEnsureOrchestrator")
        if ensure_orchestrator.endpoint != endpoint:
            raise ValueError("ensure orchestrator endpoint does not match ADB server endpoint")
        if not isinstance(scheduler, TemporalScheduler):
            raise TypeError("scheduler must satisfy TemporalScheduler")
        if not isinstance(policy, AdbServerSupervisionPolicy):
            raise TypeError("policy must be AdbServerSupervisionPolicy")

        self.endpoint = endpoint
        self._bus = event_bus
        self._ensure = ensure_orchestrator
        self._scheduler = scheduler
        self._policy = policy
        self._random = _random
        self._thread_factory = _thread_factory

        self._lock = Lock()
        self._mutation_lock = Lock()
        self._subscriptions: tuple[EventSubscriptionToken, ...] = ()
        self._desired_running = False
        self._recovery_enabled = False
        self._recovery_epoch = 0
        self._cycle_id: AdbServerRecoveryCycleId | None = None
        self._retry_token: ScheduleToken | None = None
        self._attempt_threads: set[Thread] = set()
        self._closed = False

    @property
    def desired_running(self) -> bool:
        with self._lock:
            return self._desired_running

    @property
    def recovery_enabled(self) -> bool:
        with self._lock:
            return self._recovery_enabled

    @property
    def recovery_epoch(self) -> int:
        with self._lock:
            return self._recovery_epoch

    def start(self, *, recovery_enabled: bool) -> AdbServerEnsureResult:
        """Establish the running condition and optionally keep recovery armed afterwards."""

        enabled = _require_bool(recovery_enabled, field_name="recovery_enabled")
        with self._mutation_lock:
            with self._lock:
                self._require_open()
                old_token = self._invalidate_recovery_locked()
                self._desired_running = True
                self._recovery_enabled = enabled
                self._recovery_epoch += 1
                cycle_id = AdbServerRecoveryCycleId.new() if enabled else None
                self._cycle_id = cycle_id
                if cycle_id is not None:
                    self._ensure_retry_subscription_locked()
            if old_token is not None:
                self._scheduler.cancel(old_token)

            result = self._ensure.ensure(
                AdbServerEnsureAvailable(self.endpoint, self._policy.ensure_policy)
            )

        if cycle_id is not None:
            self._handle_recovery_result(cycle_id, 1, result)
        return result

    def stop(self) -> AdbServerEnsureResult:
        """Establish the stopped condition and invalidate automatic running recovery."""

        with self._mutation_lock:
            with self._lock:
                self._require_open()
                old_token = self._invalidate_recovery_locked()
                self._desired_running = False
                self._recovery_enabled = False
                self._recovery_epoch += 1
            if old_token is not None:
                self._scheduler.cancel(old_token)
            return self._ensure.ensure(
                AdbServerEnsureUnavailable(self.endpoint, self._policy.ensure_policy)
            )

    def set_recovery_enabled(self, enabled: bool) -> None:
        """Enable or disable maintenance of the server running condition without stopping it."""

        normalized = _require_bool(enabled, field_name="enabled")
        launch_cycle: AdbServerRecoveryCycleId | None = None
        with self._lock:
            self._require_open()
            if normalized and not self._desired_running:
                raise RuntimeError(
                    "cannot enable ADB server recovery without a desired running condition"
                )
            if self._recovery_enabled is normalized:
                return
            old_token = self._invalidate_recovery_locked()
            self._recovery_enabled = normalized
            self._recovery_epoch += 1
            if normalized:
                launch_cycle = AdbServerRecoveryCycleId.new()
                self._cycle_id = launch_cycle
                self._ensure_retry_subscription_locked()
        if old_token is not None:
            self._scheduler.cancel(old_token)
        if launch_cycle is not None:
            self._launch_recovery_attempt(launch_cycle, attempt_number=1)

    def reconcile(self) -> None:
        """Freshly reconcile the running condition when automatic recovery is currently allowed."""

        with self._lock:
            self._require_open()
            if not self._recovery_armed_locked():
                return
            if self._cycle_id is not None:
                return
            cycle_id = AdbServerRecoveryCycleId.new()
            self._cycle_id = cycle_id
            self._recovery_epoch += 1
            self._ensure_retry_subscription_locked()
        self._launch_recovery_attempt(cycle_id, attempt_number=1)

    def close(self) -> None:
        """Stop supervising without changing the native server state."""

        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._recovery_enabled = False
            subscriptions = self._subscriptions
            self._subscriptions = ()
            retry_token = self._invalidate_recovery_locked()
            attempt_threads = tuple(self._attempt_threads)
            self._recovery_epoch += 1
        for token in subscriptions:
            self._bus.unsubscribe(token)
        if retry_token is not None:
            self._scheduler.cancel(retry_token)
        for thread in attempt_threads:
            if thread is not current_thread():
                thread.join()

    def _launch_recovery_attempt(
        self,
        cycle_id: AdbServerRecoveryCycleId,
        attempt_number: int,
    ) -> None:
        thread = self._thread_factory(
            target=self._run_recovery_attempt,
            args=(cycle_id, attempt_number),
            name=(
                "adb-server-recovery-"
                f"{self.endpoint.host}-{self.endpoint.port}-{attempt_number}"
            ),
        )
        with self._lock:
            if not self._recovery_is_current_locked(cycle_id):
                return
            self._attempt_threads.add(thread)
        thread.start()

    def _run_recovery_attempt(
        self,
        cycle_id: AdbServerRecoveryCycleId,
        attempt_number: int,
    ) -> None:
        active = current_thread()
        try:
            with self._mutation_lock:
                with self._lock:
                    if not self._recovery_is_current_locked(cycle_id):
                        return
                result = self._ensure.ensure(
                    AdbServerEnsureAvailable(self.endpoint, self._policy.ensure_policy)
                )
            self._handle_recovery_result(cycle_id, attempt_number, result)
        finally:
            with self._lock:
                self._attempt_threads.discard(active)

    def _handle_recovery_result(
        self,
        cycle_id: AdbServerRecoveryCycleId,
        attempt_number: int,
        result: AdbServerEnsureResult,
    ) -> None:
        if result.status is AdbServerEnsureStatus.SATISFIED:
            self._end_recovery_cycle(cycle_id)
            return

        with self._lock:
            if not self._recovery_is_current_locked(cycle_id):
                return
        self._schedule_retry_or_exhaust(cycle_id, attempt_number)

    def _schedule_retry_or_exhaust(
        self,
        cycle_id: AdbServerRecoveryCycleId,
        attempt_number: int,
    ) -> None:
        max_attempts = self._policy.max_attempts
        if max_attempts is not None and attempt_number >= max_attempts:
            self._end_recovery_cycle(cycle_id)
            self._bus.publish(
                AdbServerRecoveryExhausted(
                    self.endpoint,
                    cycle_id,
                    attempt_number,
                )
            )
            return

        next_attempt = attempt_number + 1
        delay_seconds = self._retry_delay(attempt_number)
        retry_event = AdbServerRecoveryRetryDue(
            self.endpoint,
            cycle_id,
            next_attempt,
        )
        token = self._scheduler.schedule_after(
            timedelta(seconds=delay_seconds),
            retry_event,
        )
        with self._lock:
            if not self._recovery_is_current_locked(cycle_id):
                self._scheduler.cancel(token)
                return
            old_token = self._retry_token
            self._retry_token = token
        if old_token is not None:
            self._scheduler.cancel(old_token)

    def _ensure_retry_subscription_locked(self) -> None:
        if self._subscriptions:
            return
        retry_subscription = self._bus.subscribe(
            AdbServerRecoveryRetryDue,
            self._on_retry_due,
        )
        self._subscriptions = (retry_subscription,)

    def _on_retry_due(self, event: AdbServerRecoveryRetryDue) -> None:
        if event.endpoint != self.endpoint:
            return
        with self._lock:
            if not self._recovery_is_current_locked(event.cycle_id):
                return
            self._retry_token = None
        self._launch_recovery_attempt(event.cycle_id, event.attempt_number)

    def _end_recovery_cycle(
        self,
        cycle_id: AdbServerRecoveryCycleId,
    ) -> None:
        with self._lock:
            if self._cycle_id != cycle_id:
                return
            retry_token = self._retry_token
            self._retry_token = None
            self._cycle_id = None
        if retry_token is not None:
            self._scheduler.cancel(retry_token)

    def _invalidate_recovery_locked(self) -> ScheduleToken | None:
        retry_token = self._retry_token
        self._retry_token = None
        self._cycle_id = None
        return retry_token

    def _recovery_is_current_locked(self, cycle_id: AdbServerRecoveryCycleId) -> bool:
        return (
            not self._closed
            and self._recovery_armed_locked()
            and self._cycle_id == cycle_id
        )

    def _recovery_armed_locked(self) -> bool:
        return self._desired_running and self._recovery_enabled

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("ADB server supervisor is closed")

    def _retry_delay(self, attempt_number: int) -> float:
        base = min(
            self._policy.retry_initial_seconds
            * (self._policy.retry_multiplier ** max(0, attempt_number - 1)),
            self._policy.retry_max_seconds,
        )
        jitter = self._policy.retry_jitter_ratio
        sample = self._random()
        if not 0.0 <= sample <= 1.0:
            raise ValueError("server supervision random source must return a value in [0, 1]")
        factor = 1.0 + ((sample * 2.0) - 1.0) * jitter
        return max(base * factor, 1e-6)


__all__ = ["AdbServerSupervisor"]

```

---

## FILE: `adb\supervision\signal.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from adb.server.endpoint import AdbServerEndpoint
from adb.supervision.model import (
    AdbDevicesObservationEstablishmentCycleId,
    AdbServerRecoveryCycleId,
)
from adb.transport.binding import (
    AdbTransportBindingConfiguration,
    AdbTransportBindingResolution,
)
from adb.transport.observation.contracts import AdbObservationSessionId
from adb.transport.orchestration import (
    AdbTransportPreparationResult,
    AdbTransportPreparationStatus,
)


@dataclass(frozen=True, slots=True)
class AdbTransportBindingResolutionChanged:
    """Signal carrying one registered binding projection within an observation generation."""

    session_id: AdbObservationSessionId
    previous: AdbTransportBindingResolution | None
    current: AdbTransportBindingResolution

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, AdbObservationSessionId):
            raise TypeError("session_id must be AdbObservationSessionId")
        if self.previous is not None and not isinstance(
            self.previous, AdbTransportBindingResolution
        ):
            raise TypeError("previous must be AdbTransportBindingResolution or None")
        if not isinstance(self.current, AdbTransportBindingResolution):
            raise TypeError("current must be AdbTransportBindingResolution")
        if self.current.configuration.endpoint != self.session_id.endpoint:
            raise ValueError("binding resolution endpoint must match observation session")
        if self.previous is not None and (
            self.previous.configuration.serial
            != self.current.configuration.serial
        ):
            raise ValueError("binding resolution change must keep one serial")


@dataclass(frozen=True, slots=True)
class AdbTransportBindingRecoveryExhausted:
    """Signal that automatic recovery ended unsatisfied for one registered binding."""

    configuration: AdbTransportBindingConfiguration
    result: AdbTransportPreparationResult

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, AdbTransportBindingConfiguration):
            raise TypeError("configuration must be AdbTransportBindingConfiguration")
        if not isinstance(self.result, AdbTransportPreparationResult):
            raise TypeError("result must be AdbTransportPreparationResult")
        if self.result.operation.endpoint != self.configuration.endpoint:
            raise ValueError("recovery result endpoint must match binding configuration")
        if self.result.operation.serial != self.configuration.serial:
            raise ValueError("recovery result serial must match binding configuration")
        if self.result.status is AdbTransportPreparationStatus.SATISFIED:
            raise ValueError("recovery exhausted signal requires an unsatisfied result")


@dataclass(frozen=True, slots=True)
class AdbServerRecoveryRetryDue:
    """Signal delivered when one scheduled server-running recovery retry becomes due."""

    endpoint: AdbServerEndpoint
    cycle_id: AdbServerRecoveryCycleId
    attempt_number: int

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(self.cycle_id, AdbServerRecoveryCycleId):
            raise TypeError("cycle_id must be AdbServerRecoveryCycleId")
        if isinstance(self.attempt_number, bool) or not isinstance(self.attempt_number, int):
            raise TypeError("attempt_number must be an integer")
        if self.attempt_number <= 0:
            raise ValueError("attempt_number must be greater than zero")


@dataclass(frozen=True, slots=True)
class AdbServerRecoveryExhausted:
    """Signal that automatic maintenance of the server running condition exhausted its budget."""

    endpoint: AdbServerEndpoint
    cycle_id: AdbServerRecoveryCycleId
    attempts: int

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(self.cycle_id, AdbServerRecoveryCycleId):
            raise TypeError("cycle_id must be AdbServerRecoveryCycleId")
        if isinstance(self.attempts, bool) or not isinstance(self.attempts, int):
            raise TypeError("attempts must be an integer")
        if self.attempts <= 0:
            raise ValueError("attempts must be greater than zero")


@dataclass(frozen=True, slots=True)
class AdbDevicesObservationEstablishmentRetryDue:
    """Signal delivered when one scheduled observation-establishment retry becomes due."""

    endpoint: AdbServerEndpoint
    cycle_id: AdbDevicesObservationEstablishmentCycleId
    attempt_number: int

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(
            self.cycle_id,
            AdbDevicesObservationEstablishmentCycleId,
        ):
            raise TypeError(
                "cycle_id must be AdbDevicesObservationEstablishmentCycleId"
            )
        if isinstance(self.attempt_number, bool) or not isinstance(self.attempt_number, int):
            raise TypeError("attempt_number must be an integer")
        if self.attempt_number <= 0:
            raise ValueError("attempt_number must be greater than zero")


@dataclass(frozen=True, slots=True)
class AdbDevicesObservationEstablishmentExhausted:
    """Signal that an observation-establishment cycle exhausted its attempt budget."""

    endpoint: AdbServerEndpoint
    cycle_id: AdbDevicesObservationEstablishmentCycleId
    attempts: int

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(
            self.cycle_id,
            AdbDevicesObservationEstablishmentCycleId,
        ):
            raise TypeError(
                "cycle_id must be AdbDevicesObservationEstablishmentCycleId"
            )
        if isinstance(self.attempts, bool) or not isinstance(self.attempts, int):
            raise TypeError("attempts must be an integer")
        if self.attempts <= 0:
            raise ValueError("attempts must be greater than zero")


AdbSupervisionSignal: TypeAlias = (
    AdbTransportBindingResolutionChanged
    | AdbTransportBindingRecoveryExhausted
    | AdbServerRecoveryRetryDue
    | AdbServerRecoveryExhausted
    | AdbDevicesObservationEstablishmentRetryDue
    | AdbDevicesObservationEstablishmentExhausted
)


__all__ = [
    "AdbDevicesObservationEstablishmentExhausted",
    "AdbDevicesObservationEstablishmentRetryDue",
    "AdbServerRecoveryExhausted",
    "AdbServerRecoveryRetryDue",
    "AdbSupervisionSignal",
    "AdbTransportBindingRecoveryExhausted",
    "AdbTransportBindingResolutionChanged",
]

```

---

## FILE: `adb\supervision\transport_binding.py`

```python
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
    AdbTransportBindingConfiguration,
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
    [AdbTransportBindingConfiguration],
    AdbTransportPreparationExecutor,
]
_ThreadFactory = Callable[..., Thread]


def _default_thread_factory(*args, **kwargs) -> Thread:
    thread = Thread(*args, **kwargs)
    thread.daemon = True
    return thread


@dataclass(slots=True)
class _BindingRegistration:
    configuration: AdbTransportBindingConfiguration
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
        configuration: AdbTransportBindingConfiguration,
        policy: AdbTransportBindingSupervisionPolicy | None = None,
    ) -> None:
        if not isinstance(configuration, AdbTransportBindingConfiguration):
            raise TypeError("configuration must be AdbTransportBindingConfiguration")
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

```

---

## FILE: `adb\transport\__init__.py`

```python
"""ADB transport identity, selection, capabilities, inventory, and observation."""

from adb.transport.selection import (
    AdbDeviceSerial,
    AdbTransportById,
    AdbTransportBySerial,
    AdbTransportId,
    AdbTransportSelector,
)
from adb.transport.features import AdbTransportFeatures
from adb.transport.binding import (
    AdbTransportBindingConfiguration,
    AdbTransportBindingResolution,
    AdbTransportBindingResolutionStatus,
    resolve_transport_binding,
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
    "AdbTransportBindingConfiguration",
    "AdbTransportBindingResolution",
    "AdbTransportBindingResolutionStatus",
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
    "resolve_transport_binding",
]

```

---

## FILE: `adb\transport\adapters.py`

```python
from __future__ import annotations

from collections.abc import Callable

from adb._internal.client import AdbServiceClient
from adb.server.endpoint import AdbServerEndpoint
from adb.transport.features import AdbTransportFeatures
from adb.transport.selection import AdbTransportSelector


_ClientFactory = Callable[[AdbServerEndpoint], AdbServiceClient]


def _default_client_factory(endpoint: AdbServerEndpoint) -> AdbServiceClient:
    return AdbServiceClient(endpoint)


class SmartSocketAdbTransportFeaturesReader:
    """One-shot feature reader for one selected transport."""

    def __init__(self, *, _client_factory: _ClientFactory = _default_client_factory) -> None:
        self._client_factory = _client_factory

    def read(self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector) -> AdbTransportFeatures:
        if not isinstance(endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        return AdbTransportFeatures(self._client_factory(endpoint).features(selector))


__all__ = ["SmartSocketAdbTransportFeaturesReader"]

```

---

## FILE: `adb\transport\binding.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from adb.server.endpoint import AdbServerEndpoint
from adb.transport.devices.domain import AdbDevicesSnapshot, AdbTrackedDevice
from adb.transport.selection import AdbDeviceSerial


def _normalize_optional_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


@dataclass(frozen=True, slots=True)
class AdbTransportBindingConfiguration:
    """ADB-domain configuration for one endpoint and serial-selected transport.

    ``serial`` is the persistent native selection key and can be passed directly to ADB
    serial-selection mechanisms. Preparation separately uses the same serial to locate the
    matching row in fresh transport-inventory evidence; that lookup does not convert the
    configuration to a runtime ``transport_id`` selector.

    ``serial`` is deliberately independent from ``connect_address``. The address passed to
    ``adb connect`` does not have to be identical to the serial later reported by the ADB
    transport inventory. Runtime ``transport_id`` values remain fresh inventory facts rather
    than binding configuration or implicit preparation continuity state.
    """

    endpoint: AdbServerEndpoint
    serial: AdbDeviceSerial
    connect_address: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(self.serial, AdbDeviceSerial):
            raise TypeError("serial must be AdbDeviceSerial")
        object.__setattr__(
            self,
            "connect_address",
            _normalize_optional_text(
                self.connect_address,
                field_name="ADB transport connect address",
            ),
        )


class AdbTransportBindingResolutionStatus(str, Enum):
    """How one configured serial appears in one complete inventory snapshot."""

    ABSENT = "absent"
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class AdbTransportBindingResolution:
    """Pure projection of one configured serial into inventory evidence.

    The result identifies matching observed rows for presence/state evaluation. It does not
    construct an ``AdbTransportById`` selector or otherwise change how commands select the
    transport.
    """

    configuration: AdbTransportBindingConfiguration
    status: AdbTransportBindingResolutionStatus
    matches: tuple[AdbTrackedDevice, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, AdbTransportBindingConfiguration):
            raise TypeError("configuration must be AdbTransportBindingConfiguration")
        if not isinstance(self.status, AdbTransportBindingResolutionStatus):
            raise TypeError("status must be AdbTransportBindingResolutionStatus")
        if not isinstance(self.matches, tuple) or not all(
            isinstance(row, AdbTrackedDevice) for row in self.matches
        ):
            raise TypeError("matches must be a tuple of AdbTrackedDevice values")
        expected = (
            AdbTransportBindingResolutionStatus.ABSENT
            if not self.matches
            else AdbTransportBindingResolutionStatus.RESOLVED
            if len(self.matches) == 1
            else AdbTransportBindingResolutionStatus.AMBIGUOUS
        )
        if self.status is not expected:
            raise ValueError("resolution status does not match the number of matching rows")

    @property
    def row(self) -> AdbTrackedDevice | None:
        return self.matches[0] if self.status is AdbTransportBindingResolutionStatus.RESOLVED else None


def resolve_transport_binding(
    configuration: AdbTransportBindingConfiguration,
    snapshot: AdbDevicesSnapshot,
) -> AdbTransportBindingResolution:
    """Locate the configured serial in fresh inventory evidence.

    This lookup supports preparation presence/state evaluation only. It does not translate the
    serial into a transport-id selector and does not participate in native serial selection.
    """

    if not isinstance(configuration, AdbTransportBindingConfiguration):
        raise TypeError("configuration must be AdbTransportBindingConfiguration")
    if not isinstance(snapshot, AdbDevicesSnapshot):
        raise TypeError("snapshot must be AdbDevicesSnapshot")

    matches = tuple(
        row for row in snapshot.devices if row.serial == configuration.serial.value
    )
    status = (
        AdbTransportBindingResolutionStatus.ABSENT
        if not matches
        else AdbTransportBindingResolutionStatus.RESOLVED
        if len(matches) == 1
        else AdbTransportBindingResolutionStatus.AMBIGUOUS
    )
    return AdbTransportBindingResolution(configuration, status, matches)


__all__ = [
    "AdbTransportBindingConfiguration",
    "AdbTransportBindingResolution",
    "AdbTransportBindingResolutionStatus",
    "resolve_transport_binding",
]

```

---

## FILE: `adb\transport\features.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field


def _normalize_feature(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("ADB transport feature must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("ADB transport feature cannot be empty")
    if "," in normalized:
        raise ValueError("ADB transport feature cannot contain a comma")
    return normalized


@dataclass(frozen=True, slots=True)
class AdbTransportFeatures:
    """Open ADB transport feature set advertised by one selected transport."""

    features: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not isinstance(self.features, frozenset):
            raise TypeError("ADB transport features must be a frozenset")
        normalized = frozenset(_normalize_feature(feature) for feature in self.features)
        object.__setattr__(self, "features", normalized)

    def __contains__(self, feature: object) -> bool:
        return feature in self.features


__all__ = ["AdbTransportFeatures"]

```

---

## FILE: `adb\transport\orchestration.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from numbers import Integral, Real

from adb.server.endpoint import AdbServerEndpoint
from adb.transport.devices.domain import (
    AdbConnectionState,
    AdbDevicesSnapshot,
    AdbTrackedDevice,
)
from adb.transport.observation.contracts import AdbObservationSessionId
from adb.transport.selection import AdbDeviceSerial
from native_attempt import NativeAttemptResult


def _normalize_positive_seconds(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a real number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0.0:
        raise ValueError(f"{field_name} must be finite and greater than zero")
    return normalized


def _normalize_state(value: object, *, field_name: str) -> AdbConnectionState | int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{field_name} values must be integers")
    raw = int(value)
    try:
        return AdbConnectionState(raw)
    except ValueError:
        return raw


def _normalize_states(
    value: object,
    *,
    field_name: str,
    allow_empty: bool,
) -> frozenset[AdbConnectionState | int]:
    if not isinstance(value, frozenset):
        raise TypeError(f"{field_name} must be a frozenset")
    normalized = frozenset(
        _normalize_state(item, field_name=field_name)
        for item in value
    )
    if not allow_empty and not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


def _normalize_optional_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


@dataclass(frozen=True, slots=True)
class AdbTransportPreparation:
    """Request one bounded preparation episode for a configured serial-selected transport."""

    endpoint: AdbServerEndpoint
    serial: AdbDeviceSerial

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(self.serial, AdbDeviceSerial):
            raise TypeError("serial must be AdbDeviceSerial")


@dataclass(frozen=True, slots=True)
class AdbTransportRecovery:
    """Request domain-local orchestration to recover one configured serial-selected transport."""

    endpoint: AdbServerEndpoint
    serial: AdbDeviceSerial

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(self.serial, AdbDeviceSerial):
            raise TypeError("serial must be AdbDeviceSerial")


@dataclass(frozen=True, slots=True)
class AdbTransportPreparationPolicy:
    """One-deadline readiness policy for presence and state gates in one episode.

    States not listed as acceptable or blocked remain waiting states. This preserves future
    open-enum values without silently treating them as ready or permanently failed.
    """

    timeout_seconds: float
    acceptable_states: frozenset[AdbConnectionState | int]
    blocked_states: frozenset[AdbConnectionState | int] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "timeout_seconds",
            _normalize_positive_seconds(
                self.timeout_seconds,
                field_name="ADB transport preparation timeout",
            ),
        )
        acceptable = _normalize_states(
            self.acceptable_states,
            field_name="acceptable_states",
            allow_empty=False,
        )
        blocked = _normalize_states(
            self.blocked_states,
            field_name="blocked_states",
            allow_empty=True,
        )
        if acceptable & blocked:
            raise ValueError("acceptable_states and blocked_states must be disjoint")
        object.__setattr__(self, "acceptable_states", acceptable)
        object.__setattr__(self, "blocked_states", blocked)


class AdbTransportPreparationStatus(str, Enum):
    """Terminal status of one transport preparation episode."""

    SATISFIED = "satisfied"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    BLOCKED = "blocked"
    AMBIGUOUS = "ambiguous"
    OBSERVATION_FAILED = "observation_failed"
    OBSERVATION_STOPPED = "observation_stopped"
    OBSERVATION_REPLACED = "observation_replaced"


class AdbTransportPreparationSatisfaction(str, Enum):
    """How the final readiness condition became satisfied."""

    ALREADY_SATISFIED = "already_satisfied"
    ACHIEVED = "achieved"


class AdbTransportPresenceSatisfaction(str, Enum):
    """How the configured binding first became present during one episode."""

    ALREADY_PRESENT = "already_present"
    OBSERVED = "observed"


@dataclass(frozen=True, slots=True)
class AdbTransportPreparationResult:
    """Terminal preparation evidence without collapsing command success into readiness."""

    operation: AdbTransportPreparation
    policy: AdbTransportPreparationPolicy
    status: AdbTransportPreparationStatus
    satisfaction: AdbTransportPreparationSatisfaction | None
    presence_satisfaction: AdbTransportPresenceSatisfaction | None
    observation_session_id: AdbObservationSessionId
    attempts: tuple[NativeAttemptResult, ...]
    final_snapshot: AdbDevicesSnapshot | None = None
    final_row: AdbTrackedDevice | None = None
    diagnostic: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.operation, AdbTransportPreparation):
            raise TypeError("operation must be AdbTransportPreparation")
        if not isinstance(self.policy, AdbTransportPreparationPolicy):
            raise TypeError("policy must be AdbTransportPreparationPolicy")
        if not isinstance(self.status, AdbTransportPreparationStatus):
            raise TypeError("status must be AdbTransportPreparationStatus")
        if self.satisfaction is not None and not isinstance(
            self.satisfaction, AdbTransportPreparationSatisfaction
        ):
            raise TypeError("satisfaction must be AdbTransportPreparationSatisfaction or None")
        if self.presence_satisfaction is not None and not isinstance(
            self.presence_satisfaction, AdbTransportPresenceSatisfaction
        ):
            raise TypeError(
                "presence_satisfaction must be AdbTransportPresenceSatisfaction or None"
            )
        if not isinstance(self.observation_session_id, AdbObservationSessionId):
            raise TypeError("observation_session_id must be AdbObservationSessionId")
        if not isinstance(self.attempts, tuple) or not all(
            isinstance(attempt, NativeAttemptResult) for attempt in self.attempts
        ):
            raise TypeError("attempts must be a tuple of NativeAttemptResult values")
        if self.final_snapshot is not None and not isinstance(
            self.final_snapshot, AdbDevicesSnapshot
        ):
            raise TypeError("final_snapshot must be AdbDevicesSnapshot or None")
        if self.final_row is not None and not isinstance(self.final_row, AdbTrackedDevice):
            raise TypeError("final_row must be AdbTrackedDevice or None")
        object.__setattr__(
            self,
            "diagnostic",
            _normalize_optional_text(
                self.diagnostic,
                field_name="ADB transport preparation diagnostic",
            ),
        )

        if self.status is AdbTransportPreparationStatus.SATISFIED:
            if self.satisfaction is None or self.final_row is None:
                raise ValueError("satisfied preparation requires satisfaction and final_row")
            if self.final_row.state not in self.policy.acceptable_states:
                raise ValueError("satisfied preparation requires an acceptable final state")
        elif self.satisfaction is not None:
            raise ValueError("unsatisfied preparation cannot carry satisfaction")


__all__ = [
    "AdbTransportPreparation",
    "AdbTransportPreparationPolicy",
    "AdbTransportPreparationResult",
    "AdbTransportPreparationSatisfaction",
    "AdbTransportPreparationStatus",
    "AdbTransportPresenceSatisfaction",
    "AdbTransportRecovery",
]

```

---

## FILE: `adb\transport\preparation.py`

```python
from __future__ import annotations

from collections import deque
from collections.abc import Callable
from threading import Condition
from time import monotonic

from adb.server.endpoint import AdbServerEndpoint
from adb.errors import AdbError
from adb.transport.binding import (
    AdbTransportBindingConfiguration,
    AdbTransportBindingResolutionStatus,
    resolve_transport_binding,
)
from adb.transport.connection import AdbTcpConnect, AdbTcpConnector
from adb.transport.devices.domain import AdbDevicesSnapshot, AdbTrackedDevice
from adb.transport.devices.query import AdbDevicesSnapshotReader
from adb.transport.observation.contracts import AdbObservationSessionId
from adb.transport.observation.observer import AdbDevicesObservationController
from adb.transport.observation.signal import (
    AdbDevicesObservationFailed,
    AdbDevicesObservationStarted,
    AdbDevicesObservationStopped,
    AdbDevicesSnapshotObserved,
)
from adb.transport.orchestration import (
    AdbTransportPreparation,
    AdbTransportPreparationPolicy,
    AdbTransportPreparationResult,
    AdbTransportPreparationSatisfaction,
    AdbTransportPreparationStatus,
    AdbTransportPresenceSatisfaction,
)
from adb.transport.signal import (
    AdbTransportCommandCompleted,
    AdbTransportPreparationCompleted,
)
from eventing import EventBus, EventSubscriptionToken
from native_attempt import NativeAttemptResult, NativeAttemptStatus


_MonotonicClock = Callable[[], float]


class AdbTransportPreparationOrchestrator:
    """Run presence and state gates inside one generation-fenced preparation episode.

    The observation session is caller-owned and must already be active. The orchestrator
    subscribes before taking its one-shot inventory snapshot, so state updates arriving during
    the initial probe or atomic connect attempt remain part of the same episode.
    """

    def __init__(
        self,
        endpoint: AdbServerEndpoint,
        binding_configuration: AdbTransportBindingConfiguration,
        snapshot_reader: AdbDevicesSnapshotReader,
        connector: AdbTcpConnector,
        event_bus: EventBus,
        observation: AdbDevicesObservationController,
        *,
        _monotonic: _MonotonicClock = monotonic,
    ) -> None:
        if not isinstance(endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(binding_configuration, AdbTransportBindingConfiguration):
            raise TypeError("binding_configuration must be AdbTransportBindingConfiguration")
        if binding_configuration.endpoint != endpoint:
            raise ValueError("binding configuration endpoint does not match ADB server endpoint")
        if not callable(getattr(snapshot_reader, "read", None)):
            raise TypeError("snapshot_reader must provide read()")
        if not callable(getattr(connector, "connect", None)):
            raise TypeError("connector must provide connect()")
        if not callable(getattr(event_bus, "publish", None)) or not callable(
            getattr(event_bus, "subscribe", None)
        ) or not callable(getattr(event_bus, "unsubscribe", None)):
            raise TypeError("event_bus must satisfy EventBus")
        if not isinstance(observation, AdbDevicesObservationController):
            raise TypeError("observation must satisfy observation controller")
        self.endpoint = endpoint
        self.binding_configuration = binding_configuration
        self._snapshot_reader = snapshot_reader
        self._connector = connector
        self._bus = event_bus
        self._observation = observation
        self._monotonic = _monotonic

    def prepare(
        self,
        operation: AdbTransportPreparation,
        policy: AdbTransportPreparationPolicy,
    ) -> AdbTransportPreparationResult:
        if not isinstance(operation, AdbTransportPreparation):
            raise TypeError("operation must be AdbTransportPreparation")
        if not isinstance(policy, AdbTransportPreparationPolicy):
            raise TypeError("policy must be AdbTransportPreparationPolicy")
        if operation.endpoint != self.endpoint:
            raise ValueError("operation endpoint does not match configured ADB server endpoint")
        if operation.serial != self.binding_configuration.serial:
            raise ValueError("operation serial does not match configured ADB transport")

        session_id = self._observation.active_session_id
        if session_id is None:
            raise RuntimeError("transport preparation requires an active observation session")
        if session_id.endpoint != operation.endpoint:
            raise ValueError("active observation session belongs to another ADB server endpoint")

        deadline = self._monotonic() + policy.timeout_seconds
        condition = Condition()
        events: deque[object] = deque()

        def collect(event: object) -> None:
            with condition:
                events.append(event)
                condition.notify()

        subscriptions = self._subscribe(collect)
        try:
            return self._run_episode(
                operation,
                policy,
                session_id,
                deadline,
                condition,
                events,
            )
        finally:
            for token in subscriptions:
                self._bus.unsubscribe(token)

    def _subscribe(self, collect: Callable[[object], None]) -> tuple[EventSubscriptionToken, ...]:
        return (
            self._bus.subscribe(AdbDevicesSnapshotObserved, collect),
            self._bus.subscribe(AdbDevicesObservationFailed, collect),
            self._bus.subscribe(AdbDevicesObservationStopped, collect),
            self._bus.subscribe(AdbDevicesObservationStarted, collect),
        )

    def _run_episode(
        self,
        operation: AdbTransportPreparation,
        policy: AdbTransportPreparationPolicy,
        session_id: AdbObservationSessionId,
        deadline: float,
        condition: Condition,
        events: deque[object],
    ) -> AdbTransportPreparationResult:
        attempts: list[NativeAttemptResult] = []
        presence: AdbTransportPresenceSatisfaction | None = None
        final_snapshot: AdbDevicesSnapshot | None = None
        final_row: AdbTrackedDevice | None = None
        initial_snapshot_processed = False
        connect_attempted = False
        diagnostic: str | None = None

        try:
            snapshot = self._snapshot_reader.read(self.endpoint)
        except AdbError as exc:
            diagnostic = str(exc) or exc.__class__.__name__
        else:
            initial_snapshot_processed = True
            final_snapshot = snapshot
            outcome = self._evaluate_snapshot(
                snapshot,
                policy,
                presence,
                initial=True,
            )
            presence, final_row, terminal = outcome
            if terminal is not None:
                return self._complete(
                    operation,
                    policy,
                    session_id,
                    terminal,
                    attempts,
                    presence,
                    final_snapshot,
                    final_row,
                    diagnostic,
                    already_satisfied=(
                        terminal is AdbTransportPreparationStatus.SATISFIED
                    ),
                )
            if presence is None and self.binding_configuration.connect_address is not None:
                connect_attempted = True
                attempts.append(self._connect())

        while True:
            if not initial_snapshot_processed and not connect_attempted:
                # An indeterminate one-shot query does not prove absence, so wait for the
                # generation-fenced observation stream before deciding whether to connect.
                pass

            event = self._next_event(condition, events, deadline)
            if event is None:
                terminal = (
                    AdbTransportPreparationStatus.FAILED
                    if attempts and attempts[-1].status is NativeAttemptStatus.FAILED
                    else AdbTransportPreparationStatus.TIMED_OUT
                )
                return self._complete(
                    operation,
                    policy,
                    session_id,
                    terminal,
                    attempts,
                    presence,
                    final_snapshot,
                    final_row,
                    diagnostic,
                )

            event_session = getattr(event, "session_id", None)
            if isinstance(event_session, AdbObservationSessionId):
                if event_session.endpoint != session_id.endpoint:
                    continue
                if event_session.generation < session_id.generation:
                    continue
                if event_session.generation > session_id.generation:
                    return self._complete(
                        operation,
                        policy,
                        session_id,
                        AdbTransportPreparationStatus.OBSERVATION_REPLACED,
                        attempts,
                        presence,
                        final_snapshot,
                        final_row,
                        "transport inventory observation generation changed",
                    )

            if isinstance(event, AdbDevicesObservationFailed):
                return self._complete(
                    operation,
                    policy,
                    session_id,
                    AdbTransportPreparationStatus.OBSERVATION_FAILED,
                    attempts,
                    presence,
                    final_snapshot,
                    final_row,
                    event.diagnostic or f"observation failed: {event.failure.value}",
                )
            if isinstance(event, AdbDevicesObservationStopped):
                return self._complete(
                    operation,
                    policy,
                    session_id,
                    AdbTransportPreparationStatus.OBSERVATION_STOPPED,
                    attempts,
                    presence,
                    final_snapshot,
                    final_row,
                    "transport inventory observation stopped",
                )
            if isinstance(event, AdbDevicesObservationStarted):
                continue
            if not isinstance(event, AdbDevicesSnapshotObserved):
                continue

            final_snapshot = event.snapshot
            outcome = self._evaluate_snapshot(
                event.snapshot,
                policy,
                presence,
                initial=False,
            )
            presence, final_row, terminal = outcome
            initial_snapshot_processed = True
            if terminal is not None:
                return self._complete(
                    operation,
                    policy,
                    session_id,
                    terminal,
                    attempts,
                    presence,
                    final_snapshot,
                    final_row,
                    diagnostic,
                )
            if (
                presence is None
                and not connect_attempted
                and self.binding_configuration.connect_address is not None
            ):
                connect_attempted = True
                attempts.append(self._connect())

    def _evaluate_snapshot(
        self,
        snapshot: AdbDevicesSnapshot,
        policy: AdbTransportPreparationPolicy,
        presence: AdbTransportPresenceSatisfaction | None,
        *,
        initial: bool,
    ) -> tuple[
        AdbTransportPresenceSatisfaction | None,
        AdbTrackedDevice | None,
        AdbTransportPreparationStatus | None,
    ]:
        resolution = resolve_transport_binding(self.binding_configuration, snapshot)

        if resolution.status is AdbTransportBindingResolutionStatus.AMBIGUOUS:
            return presence, None, AdbTransportPreparationStatus.AMBIGUOUS
        if resolution.status is AdbTransportBindingResolutionStatus.ABSENT:
            return presence, None, None

        row = resolution.row
        assert row is not None
        if presence is None:
            presence = (
                AdbTransportPresenceSatisfaction.ALREADY_PRESENT
                if initial
                else AdbTransportPresenceSatisfaction.OBSERVED
            )

        if row.state in policy.acceptable_states:
            return presence, row, AdbTransportPreparationStatus.SATISFIED
        if row.state in policy.blocked_states:
            return presence, row, AdbTransportPreparationStatus.BLOCKED
        return presence, row, None

    def _connect(self) -> NativeAttemptResult:
        address = self.binding_configuration.connect_address
        assert address is not None
        command = AdbTcpConnect(address)
        attempt = self._connector.connect(command)
        self._bus.publish(AdbTransportCommandCompleted(command, attempt))
        return attempt

    def _next_event(
        self,
        condition: Condition,
        events: deque[object],
        deadline: float,
    ) -> object | None:
        with condition:
            while not events:
                remaining = deadline - self._monotonic()
                if remaining <= 0.0:
                    return None
                condition.wait(timeout=remaining)
            return events.popleft()

    def _complete(
        self,
        operation: AdbTransportPreparation,
        policy: AdbTransportPreparationPolicy,
        session_id: AdbObservationSessionId,
        status: AdbTransportPreparationStatus,
        attempts: list[NativeAttemptResult],
        presence: AdbTransportPresenceSatisfaction | None,
        final_snapshot: AdbDevicesSnapshot | None,
        final_row: AdbTrackedDevice | None,
        diagnostic: str | None,
        *,
        already_satisfied: bool = False,
    ) -> AdbTransportPreparationResult:
        satisfaction = None
        if status is AdbTransportPreparationStatus.SATISFIED:
            satisfaction = (
                AdbTransportPreparationSatisfaction.ALREADY_SATISFIED
                if already_satisfied
                else AdbTransportPreparationSatisfaction.ACHIEVED
            )
        result = AdbTransportPreparationResult(
            operation=operation,
            policy=policy,
            status=status,
            satisfaction=satisfaction,
            presence_satisfaction=presence,
            observation_session_id=session_id,
            attempts=tuple(attempts),
            final_snapshot=final_snapshot,
            final_row=final_row,
            diagnostic=diagnostic,
        )
        self._bus.publish(AdbTransportPreparationCompleted(result))
        return result


__all__ = ["AdbTransportPreparationOrchestrator"]

```

---

## FILE: `adb\transport\query.py`

```python
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

```

---

## FILE: `adb\transport\selection.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral
from typing import TypeAlias


def _normalize_required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string, got {type(value).__name__}")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


@dataclass(frozen=True, slots=True, order=True)
class AdbDeviceSerial:
    """Native ADB device serial used for deterministic transport selection."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "value",
            _normalize_required_text(self.value, field_name="ADB device serial"),
        )

    def __str__(self) -> str:
        return self.value


class AdbTransportId(int):
    """ADB-server-local native transport identity.

    Transport IDs are positive runtime identities allocated by one ADB server. They are
    integers on the native protocol, so the type intentionally subclasses ``int`` while
    preserving a distinct constructor for public APIs and selectors.
    """

    def __new__(cls, value: object) -> "AdbTransportId":
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise TypeError("ADB transport id must be an integer")
        normalized = int(value)
        if normalized <= 0:
            raise ValueError("ADB transport id must be greater than zero")
        return int.__new__(cls, normalized)

    @property
    def value(self) -> int:
        return int(self)


@dataclass(frozen=True, slots=True)
class AdbTransportBySerial:
    """Select the transport directly by its native ADB serial.

    This selector is passed through to native ADB serial-selection mechanisms. It does not
    require an inventory snapshot and does not imply conversion to ``AdbTransportById``.
    """

    serial: AdbDeviceSerial

    def __post_init__(self) -> None:
        if not isinstance(self.serial, AdbDeviceSerial):
            raise TypeError("serial must be AdbDeviceSerial")


@dataclass(frozen=True, slots=True)
class AdbTransportById:
    """Select one exact ADB-server-local runtime transport identity."""

    transport_id: AdbTransportId

    def __post_init__(self) -> None:
        if not isinstance(self.transport_id, AdbTransportId):
            raise TypeError("transport_id must be AdbTransportId")


AdbTransportSelector: TypeAlias = AdbTransportBySerial | AdbTransportById


__all__ = [
    "AdbDeviceSerial",
    "AdbTransportById",
    "AdbTransportBySerial",
    "AdbTransportId",
    "AdbTransportSelector",
]

```

---

## FILE: `adb\transport\signal.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from adb.transport.connection import (
    AdbDeviceSideReconnect,
    AdbOfflineTransportsReconnect,
    AdbTcpConnect,
    AdbTcpDisconnect,
    AdbTransportReconnect,
)
from adb.transport.orchestration import AdbTransportPreparationResult
from native_attempt import NativeAttemptResult


AdbTransportCommandOperation: TypeAlias = (
    AdbTcpConnect
    | AdbTcpDisconnect
    | AdbTransportReconnect
    | AdbDeviceSideReconnect
    | AdbOfflineTransportsReconnect
)


@dataclass(frozen=True, slots=True)
class AdbTransportCommandCompleted:
    """Signal carrying the result of one atomic ADB transport command attempt."""

    operation: AdbTransportCommandOperation
    result: NativeAttemptResult

    def __post_init__(self) -> None:
        if not isinstance(
            self.operation,
            (
                AdbTcpConnect,
                AdbTcpDisconnect,
                AdbTransportReconnect,
                AdbDeviceSideReconnect,
                AdbOfflineTransportsReconnect,
            ),
        ):
            raise TypeError("operation must be an ADB transport command operation")
        if not isinstance(self.result, NativeAttemptResult):
            raise TypeError("result must be NativeAttemptResult")


@dataclass(frozen=True, slots=True)
class AdbTransportPreparationCompleted:
    """Signal carrying terminal evidence from one transport preparation episode."""

    result: AdbTransportPreparationResult

    def __post_init__(self) -> None:
        if not isinstance(self.result, AdbTransportPreparationResult):
            raise TypeError("result must be AdbTransportPreparationResult")


AdbTransportSignal: TypeAlias = (
    AdbTransportCommandCompleted | AdbTransportPreparationCompleted
)


__all__ = [
    "AdbTransportCommandCompleted",
    "AdbTransportCommandOperation",
    "AdbTransportPreparationCompleted",
    "AdbTransportSignal",
]

```

---

## FILE: `adb\transport\connection\__init__.py`

```python
"""ADB transport connection atomic command contracts."""

from adb.transport.connection.command import (
    AdbDeviceSideReconnect,
    AdbDeviceSideReconnector,
    AdbOfflineTransportsReconnect,
    AdbOfflineTransportsReconnector,
    AdbTcpConnect,
    AdbTcpConnector,
    AdbTcpDisconnect,
    AdbTcpDisconnector,
    AdbTransportReconnect,
    AdbTransportReconnector,
)

__all__ = [
    "AdbDeviceSideReconnect",
    "AdbDeviceSideReconnector",
    "AdbOfflineTransportsReconnect",
    "AdbOfflineTransportsReconnector",
    "AdbTcpConnect",
    "AdbTcpConnector",
    "AdbTcpDisconnect",
    "AdbTcpDisconnector",
    "AdbTransportReconnect",
    "AdbTransportReconnector",
]

```

---

## FILE: `adb\transport\connection\adapters.py`

```python
from __future__ import annotations

from dataclasses import dataclass

from adb._internal.subprocess import normalize_executable, normalize_timeout, run_adb, selector_args, server_args
from adb.server.endpoint import AdbServerEndpoint
from adb.transport.connection.command import AdbDeviceSideReconnect, AdbOfflineTransportsReconnect, AdbTcpConnect, AdbTcpDisconnect, AdbTransportReconnect
from native_attempt import NativeAttemptResult


@dataclass(frozen=True, slots=True)
class SubprocessAdbTransport:
    """Execute one configured-server ADB transport connection command per bounded CLI attempt."""
    endpoint: AdbServerEndpoint
    executable: str = "adb"
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        object.__setattr__(self, "executable", normalize_executable(self.executable))
        object.__setattr__(self, "timeout_seconds", normalize_timeout(self.timeout_seconds))

    def connect(self, operation: AdbTcpConnect) -> NativeAttemptResult:
        if not isinstance(operation, AdbTcpConnect):
            raise TypeError("operation must be AdbTcpConnect")
        return run_adb(self.executable, self.timeout_seconds, [*server_args(self.endpoint), "connect", operation.address])

    def disconnect(self, operation: AdbTcpDisconnect) -> NativeAttemptResult:
        if not isinstance(operation, AdbTcpDisconnect):
            raise TypeError("operation must be AdbTcpDisconnect")
        return run_adb(self.executable, self.timeout_seconds, [*server_args(self.endpoint), "disconnect", operation.address])

    def reconnect(self, operation: AdbTransportReconnect) -> NativeAttemptResult:
        if not isinstance(operation, AdbTransportReconnect):
            raise TypeError("operation must be AdbTransportReconnect")
        return run_adb(self.executable, self.timeout_seconds, [*server_args(self.endpoint), *selector_args(operation.selector), "reconnect"])

    def reconnect_device(self, operation: AdbDeviceSideReconnect) -> NativeAttemptResult:
        if not isinstance(operation, AdbDeviceSideReconnect):
            raise TypeError("operation must be AdbDeviceSideReconnect")
        return run_adb(self.executable, self.timeout_seconds, [*server_args(self.endpoint), *selector_args(operation.selector), "reconnect", "device"])

    def reconnect_offline(self, operation: AdbOfflineTransportsReconnect) -> NativeAttemptResult:
        if not isinstance(operation, AdbOfflineTransportsReconnect):
            raise TypeError("operation must be AdbOfflineTransportsReconnect")
        return run_adb(self.executable, self.timeout_seconds, [*server_args(self.endpoint), "reconnect", "offline"])


__all__ = ["SubprocessAdbTransport"]

```

---

## FILE: `adb\transport\connection\command.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adb.transport.selection import AdbTransportById, AdbTransportBySerial, AdbTransportSelector
from native_attempt import NativeAttemptResult


def _normalize_required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


def _require_selector(value: object) -> AdbTransportSelector:
    if not isinstance(value, (AdbTransportBySerial, AdbTransportById)):
        raise TypeError("selector must be an ADB transport selector")
    return value


@dataclass(frozen=True, slots=True)
class AdbTcpConnect:
    """Request one native attempt to connect one explicit TCP ADB endpoint."""
    address: str
    def __post_init__(self) -> None:
        object.__setattr__(self, "address", _normalize_required_text(self.address, field_name="ADB TCP address"))


@dataclass(frozen=True, slots=True)
class AdbTcpDisconnect:
    """Request one native attempt to disconnect one explicit TCP ADB endpoint."""
    address: str
    def __post_init__(self) -> None:
        object.__setattr__(self, "address", _normalize_required_text(self.address, field_name="ADB TCP address"))


@dataclass(frozen=True, slots=True)
class AdbTransportReconnect:
    """Request one host-side reconnect attempt for one selected transport."""
    selector: AdbTransportSelector
    def __post_init__(self) -> None:
        _require_selector(self.selector)


@dataclass(frozen=True, slots=True)
class AdbDeviceSideReconnect:
    """Request one selected device-side adbd reconnect attempt."""
    selector: AdbTransportSelector
    def __post_init__(self) -> None:
        _require_selector(self.selector)


@dataclass(frozen=True, slots=True)
class AdbOfflineTransportsReconnect:
    """Request one ADB reconnect-offline native attempt."""


class AdbTcpConnector(Protocol):
    def connect(self, operation: AdbTcpConnect) -> NativeAttemptResult: ...
class AdbTcpDisconnector(Protocol):
    def disconnect(self, operation: AdbTcpDisconnect) -> NativeAttemptResult: ...
class AdbTransportReconnector(Protocol):
    def reconnect(self, operation: AdbTransportReconnect) -> NativeAttemptResult: ...
class AdbDeviceSideReconnector(Protocol):
    def reconnect_device(self, operation: AdbDeviceSideReconnect) -> NativeAttemptResult: ...
class AdbOfflineTransportsReconnector(Protocol):
    def reconnect_offline(self, operation: AdbOfflineTransportsReconnect) -> NativeAttemptResult: ...


__all__ = [
    "AdbDeviceSideReconnect", "AdbDeviceSideReconnector", "AdbOfflineTransportsReconnect",
    "AdbOfflineTransportsReconnector", "AdbTcpConnect", "AdbTcpConnector", "AdbTcpDisconnect",
    "AdbTcpDisconnector", "AdbTransportReconnect", "AdbTransportReconnector",
]

```

---

## FILE: `adb\transport\devices\__init__.py`

```python
"""ADB server-observed transport inventory facts and read-side contracts."""

from adb.transport.devices.domain import (
    AdbConnectionState,
    AdbConnectionType,
    AdbDevicesSnapshot,
    AdbTrackedDevice,
)
from adb.transport.devices.query import AdbDevicesSnapshotReader, AdbTrackedDeviceLookup

__all__ = [
    "AdbConnectionState",
    "AdbConnectionType",
    "AdbDevicesSnapshot",
    "AdbDevicesSnapshotReader",
    "AdbTrackedDevice",
    "AdbTrackedDeviceLookup",
]

```

---

## FILE: `adb\transport\devices\adapters.py`

```python
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

```

---

## FILE: `adb\transport\devices\domain.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from numbers import Integral
from typing import Literal

from adb.transport.selection import AdbTransportId


class AdbConnectionState(IntEnum):
    """AOSP ``adb_host.proto.ConnectionState`` values."""

    ANY = 0
    CONNECTING = 1
    AUTHORIZING = 2
    UNAUTHORIZED = 3
    NOPERMISSION = 4
    DETACHED = 5
    OFFLINE = 6
    BOOTLOADER = 7
    DEVICE = 8
    HOST = 9
    RECOVERY = 10
    SIDELOAD = 11
    RESCUE = 12


class AdbConnectionType(IntEnum):
    """AOSP ``adb_host.proto.ConnectionType`` values."""

    UNKNOWN = 0
    USB = 1
    SOCKET = 2


def _require_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string, got {type(value).__name__}")
    return value


def _require_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{field_name} must be an integer")
    return int(value)


def _normalize_open_enum(
    value: object,
    enum_type: type[IntEnum],
    *,
    field_name: str,
) -> IntEnum | int:
    raw = _require_int(value, field_name=field_name)
    try:
        return enum_type(raw)
    except ValueError:
        # Proto3 enums are open: preserve future AOSP values numerically instead
        # of inventing an UNKNOWN interpretation or rejecting the whole snapshot.
        return raw


@dataclass(frozen=True, slots=True)
class AdbTrackedDevice:
    """One observed row from AOSP ``adb_host.proto.Device``.

    This wire-aligned value describes one server-tracked ADB transport in an
    inventory snapshot. It is not an independently identified device entity and
    does not own a separate lifecycle or command surface. ``transport_id`` is the
    native server-local transport identity when non-zero; zero means that native
    identity is unavailable in the observed row.

    Known enum numbers are exposed as the matching ``IntEnum`` member. Unknown
    future proto3 enum numbers are preserved as raw integers.
    """

    serial: str = ""
    state: AdbConnectionState | int = AdbConnectionState.ANY
    bus_address: str = ""
    product: str = ""
    model: str = ""
    device: str = ""
    connection_type: AdbConnectionType | int = AdbConnectionType.UNKNOWN
    negotiated_speed: int = 0
    max_speed: int = 0
    transport_id: AdbTransportId | Literal[0] = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "state",
            _normalize_open_enum(
                self.state,
                AdbConnectionState,
                field_name="ADB connection state",
            ),
        )
        object.__setattr__(
            self,
            "connection_type",
            _normalize_open_enum(
                self.connection_type,
                AdbConnectionType,
                field_name="ADB connection type",
            ),
        )

        for field_name in ("serial", "bus_address", "product", "model", "device"):
            object.__setattr__(
                self,
                field_name,
                _require_string(
                    getattr(self, field_name),
                    field_name=f"ADB device {field_name}",
                ),
            )

        for field_name in ("negotiated_speed", "max_speed"):
            object.__setattr__(
                self,
                field_name,
                _require_int(
                    getattr(self, field_name),
                    field_name=f"ADB device {field_name}",
                ),
            )

        transport_id = self.transport_id
        if isinstance(transport_id, AdbTransportId):
            pass
        elif isinstance(transport_id, bool) or not isinstance(transport_id, Integral):
            raise TypeError(
                "ADB device transport_id must be AdbTransportId or integer zero"
            )
        else:
            raw_transport_id = int(transport_id)
            if raw_transport_id < 0:
                raise ValueError("ADB device transport_id cannot be negative")
            object.__setattr__(
                self,
                "transport_id",
                0 if raw_transport_id == 0 else AdbTransportId(raw_transport_id),
            )


@dataclass(frozen=True, slots=True)
class AdbDevicesSnapshot:
    """Complete AOSP ``adb_host.proto.Devices`` transport-inventory snapshot."""

    devices: tuple[AdbTrackedDevice, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.devices, tuple):
            raise TypeError("ADB devices must be a tuple")
        for index, device in enumerate(self.devices):
            if not isinstance(device, AdbTrackedDevice):
                raise TypeError(f"ADB devices[{index}] must be AdbTrackedDevice")


__all__ = [
    "AdbConnectionState",
    "AdbConnectionType",
    "AdbDevicesSnapshot",
    "AdbTrackedDevice",
]

```

---

## FILE: `adb\transport\devices\query.py`

```python
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

```

---

## FILE: `adb\transport\observation\__init__.py`

```python
"""Long-lived observation of the ADB server's transport inventory."""

from adb.transport.observation.contracts import (
    AdbObservationError,
    AdbObservationProtocolError,
    AdbObservationServerConnectionError,
    AdbObservationServiceError,
    AdbObservationSessionId,
)
from adb.transport.observation.establishment import (
    AdbDevicesObservationEstablishment,
    AdbDevicesObservationEstablishmentOrchestrator,
    AdbDevicesObservationEstablishmentPolicy,
    AdbDevicesObservationEstablishmentResult,
    AdbDevicesObservationEstablishmentStatus,
)
from adb.transport.observation.observer import (
    AdbDevicesObservationController,
    AdbDevicesObserver,
)

__all__ = [
    "AdbObservationError",
    "AdbObservationProtocolError",
    "AdbObservationServerConnectionError",
    "AdbObservationServiceError",
    "AdbObservationSessionId",
    "AdbDevicesObservationController",
    "AdbDevicesObservationEstablishment",
    "AdbDevicesObservationEstablishmentOrchestrator",
    "AdbDevicesObservationEstablishmentPolicy",
    "AdbDevicesObservationEstablishmentResult",
    "AdbDevicesObservationEstablishmentStatus",
    "AdbDevicesObserver",
]

```

---

## FILE: `adb\transport\observation\contracts.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral

from adb.server.endpoint import AdbServerEndpoint
from adb.errors import (
    AdbError,
    AdbProtocolError,
    AdbServerConnectionError,
    AdbServiceError,
)


@dataclass(frozen=True, slots=True, order=True)
class AdbObservationSessionId:
    """ADB-native identity for one endpoint-scoped transport-inventory observation generation."""

    endpoint: AdbServerEndpoint
    generation: int

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if isinstance(self.generation, bool) or not isinstance(self.generation, Integral):
            raise TypeError("generation must be an integer")
        generation = int(self.generation)
        if generation <= 0:
            raise ValueError("generation must be greater than zero")
        object.__setattr__(self, "generation", generation)


class AdbObservationError(AdbError):
    """Base error for failures while observing ADB state."""


class AdbObservationServerConnectionError(
    AdbObservationError,
    AdbServerConnectionError,
):
    """Observation failed because its smart-socket session to the ADB server was lost."""


class AdbObservationServiceError(AdbObservationError, AdbServiceError):
    """ADB server rejected the requested observation service."""

    def __init__(self, detail: str) -> None:
        AdbServiceError.__init__(self, "host:track-devices-proto-binary", detail)


class AdbObservationProtocolError(AdbObservationError, AdbProtocolError):
    """ADB observation data violated the expected smart-socket protocol."""


__all__ = [
    "AdbObservationError",
    "AdbObservationProtocolError",
    "AdbObservationServerConnectionError",
    "AdbObservationServiceError",
    "AdbObservationSessionId",
]

```

---

## FILE: `adb\transport\observation\establishment.py`

```python
from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import math
from numbers import Real
from threading import Condition
from time import monotonic

from adb.server.endpoint import AdbServerEndpoint
from adb.transport.observation.contracts import AdbObservationSessionId
from adb.transport.observation.observer import AdbDevicesObservationController
from adb.transport.observation.signal import (
    AdbDevicesObservationFailed,
    AdbDevicesObservationFailure,
    AdbDevicesObservationStarted,
    AdbDevicesObservationStopped,
)
from eventing import EventBus, EventSubscriptionToken
from native_attempt import NativeAttemptResult


_MonotonicClock = Callable[[], float]


def _normalize_positive_seconds(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a real number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0.0:
        raise ValueError(f"{field_name} must be finite and greater than zero")
    return normalized


def _normalize_optional_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


class AdbDevicesObservationEstablishmentStatus(str, Enum):
    """Terminal status of one bounded transport-inventory observation establishment episode."""

    SATISFIED = "satisfied"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True, slots=True)
class AdbDevicesObservationEstablishmentPolicy:
    """Bound one transport-inventory observation establishment episode."""

    timeout_seconds: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "timeout_seconds",
            _normalize_positive_seconds(
                self.timeout_seconds,
                field_name="ADB transport-inventory observation establishment timeout",
            ),
        )


@dataclass(frozen=True, slots=True)
class AdbDevicesObservationEstablishment:
    """Request establishment of one configured server's transport-inventory observation."""

    endpoint: AdbServerEndpoint
    policy: AdbDevicesObservationEstablishmentPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(
            self.policy,
            AdbDevicesObservationEstablishmentPolicy,
        ):
            raise TypeError(
                "policy must be AdbDevicesObservationEstablishmentPolicy"
            )


@dataclass(frozen=True, slots=True)
class AdbDevicesObservationEstablishmentResult:
    """Evidence from one bounded transport-inventory observation establishment episode."""

    operation: AdbDevicesObservationEstablishment
    status: AdbDevicesObservationEstablishmentStatus
    observation_session_id: AdbObservationSessionId | None = None
    observation_failure: AdbDevicesObservationFailure | None = None
    diagnostic: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(
            self.operation,
            AdbDevicesObservationEstablishment,
        ):
            raise TypeError(
                "operation must be AdbDevicesObservationEstablishment"
            )
        if not isinstance(
            self.status,
            AdbDevicesObservationEstablishmentStatus,
        ):
            raise TypeError(
                "status must be AdbDevicesObservationEstablishmentStatus"
            )
        if self.observation_session_id is not None:
            if not isinstance(self.observation_session_id, AdbObservationSessionId):
                raise TypeError("observation_session_id must be AdbObservationSessionId or None")
            if self.observation_session_id.endpoint != self.operation.endpoint:
                raise ValueError(
                    "observation session endpoint must match establishment operation"
                )
        if self.observation_failure is not None and not isinstance(
            self.observation_failure,
            AdbDevicesObservationFailure,
        ):
            raise TypeError(
                "observation_failure must be AdbDevicesObservationFailure or None"
            )
        if self.status is AdbDevicesObservationEstablishmentStatus.SATISFIED:
            if self.observation_session_id is None:
                raise ValueError(
                    "satisfied establishment result requires observation_session_id"
                )
            if self.observation_failure is not None:
                raise ValueError(
                    "satisfied establishment result cannot carry observation_failure"
                )
        object.__setattr__(
            self,
            "diagnostic",
            _normalize_optional_text(
                self.diagnostic,
                field_name="ADB transport-inventory observation establishment diagnostic",
            ),
        )

    @property
    def attempts(self) -> tuple[NativeAttemptResult, ...]:
        """Observation establishment performs no native server mutation attempts."""

        return ()


class AdbDevicesObservationEstablishmentOrchestrator:
    """Establish one track-devices observation generation inside a bounded episode.

    The episode owns no retry/backoff or server-lifecycle policy. Satisfaction requires matching
    ``AdbDevicesObservationStarted`` evidence, not merely acceptance of ``observation.start()``.
    Server condition maintenance belongs to ``AdbServerSupervisor``.
    """

    def __init__(
        self,
        endpoint: AdbServerEndpoint,
        event_bus: EventBus,
        observation: AdbDevicesObservationController,
        *,
        _monotonic: _MonotonicClock = monotonic,
    ) -> None:
        if not isinstance(endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not callable(getattr(event_bus, "subscribe", None)) or not callable(
            getattr(event_bus, "unsubscribe", None)
        ):
            raise TypeError("event_bus must satisfy EventBus")
        if not isinstance(observation, AdbDevicesObservationController):
            raise TypeError("observation must satisfy observation controller")
        self.endpoint = endpoint
        self._bus = event_bus
        self._observation = observation
        self._monotonic = _monotonic

    def establish(
        self,
        operation: AdbDevicesObservationEstablishment,
    ) -> AdbDevicesObservationEstablishmentResult:
        if not isinstance(
            operation,
            AdbDevicesObservationEstablishment,
        ):
            raise TypeError(
                "operation must be AdbDevicesObservationEstablishment"
            )
        if operation.endpoint != self.endpoint:
            raise ValueError("operation endpoint does not match configured ADB server endpoint")

        deadline = self._monotonic() + operation.policy.timeout_seconds
        condition = Condition()
        events: deque[object] = deque()

        def collect(event: object) -> None:
            with condition:
                events.append(event)
                condition.notify()

        subscriptions = self._subscribe(collect)
        try:
            return self._run_episode(operation, deadline, condition, events)
        finally:
            for token in subscriptions:
                self._bus.unsubscribe(token)

    def _run_episode(
        self,
        operation: AdbDevicesObservationEstablishment,
        deadline: float,
        condition: Condition,
        events: deque[object],
    ) -> AdbDevicesObservationEstablishmentResult:
        if deadline - self._monotonic() <= 0.0:
            return self._complete(
                operation,
                AdbDevicesObservationEstablishmentStatus.TIMED_OUT,
                diagnostic="establishment deadline expired before observation start",
            )

        try:
            session_id = self._observation.start()
        except RuntimeError as exc:
            return self._complete(
                operation,
                AdbDevicesObservationEstablishmentStatus.FAILED,
                diagnostic=str(exc),
            )
        if session_id.endpoint != operation.endpoint:
            raise ValueError("started observation belongs to another ADB server endpoint")

        while True:
            event = self._next_event(condition, events, deadline)
            if event is None:
                return self._complete(
                    operation,
                    AdbDevicesObservationEstablishmentStatus.TIMED_OUT,
                    observation_session_id=session_id,
                    diagnostic="timed out waiting for observation establishment evidence",
                )

            event_session = getattr(event, "session_id", None)
            if event_session != session_id:
                continue
            if isinstance(event, AdbDevicesObservationStarted):
                return self._complete(
                    operation,
                    AdbDevicesObservationEstablishmentStatus.SATISFIED,
                    observation_session_id=session_id,
                )
            if isinstance(event, AdbDevicesObservationFailed):
                return self._complete(
                    operation,
                    AdbDevicesObservationEstablishmentStatus.FAILED,
                    observation_session_id=session_id,
                    observation_failure=event.failure,
                    diagnostic=(
                        event.diagnostic or f"observation failed: {event.failure.value}"
                    ),
                )
            if isinstance(event, AdbDevicesObservationStopped):
                return self._complete(
                    operation,
                    AdbDevicesObservationEstablishmentStatus.FAILED,
                    observation_session_id=session_id,
                    diagnostic="observation stopped before establishment",
                )

    def _subscribe(
        self,
        collect: Callable[[object], None],
    ) -> tuple[EventSubscriptionToken, ...]:
        return (
            self._bus.subscribe(AdbDevicesObservationStarted, collect),
            self._bus.subscribe(AdbDevicesObservationFailed, collect),
            self._bus.subscribe(AdbDevicesObservationStopped, collect),
        )

    def _next_event(
        self,
        condition: Condition,
        events: deque[object],
        deadline: float,
    ) -> object | None:
        with condition:
            while not events:
                remaining = deadline - self._monotonic()
                if remaining <= 0.0:
                    return None
                condition.wait(timeout=remaining)
            return events.popleft()

    @staticmethod
    def _complete(
        operation: AdbDevicesObservationEstablishment,
        status: AdbDevicesObservationEstablishmentStatus,
        *,
        observation_session_id: AdbObservationSessionId | None = None,
        observation_failure: AdbDevicesObservationFailure | None = None,
        diagnostic: str | None = None,
    ) -> AdbDevicesObservationEstablishmentResult:
        return AdbDevicesObservationEstablishmentResult(
            operation=operation,
            status=status,
            observation_session_id=observation_session_id,
            observation_failure=observation_failure,
            diagnostic=diagnostic,
        )


__all__ = [
    "AdbDevicesObservationEstablishment",
    "AdbDevicesObservationEstablishmentOrchestrator",
    "AdbDevicesObservationEstablishmentPolicy",
    "AdbDevicesObservationEstablishmentResult",
    "AdbDevicesObservationEstablishmentStatus",
]

```

---

## FILE: `adb\transport\observation\observer.py`

```python
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

```

---

## FILE: `adb\transport\observation\signal.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from adb.server.endpoint import AdbServerEndpoint
from adb.transport.devices.domain import AdbDevicesSnapshot
from adb.transport.observation.contracts import AdbObservationSessionId


def _require_endpoint(value: object) -> AdbServerEndpoint:
    if not isinstance(value, AdbServerEndpoint):
        raise TypeError("endpoint must be AdbServerEndpoint")
    return value


def _require_session_id(value: object) -> AdbObservationSessionId:
    if not isinstance(value, AdbObservationSessionId):
        raise TypeError("session_id must be AdbObservationSessionId")
    return value


def _normalize_optional_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


class AdbDevicesObservationFailure(str, Enum):
    """Typed reason one transport-inventory observation session terminated abnormally."""

    SERVER_CONNECTION = "server_connection"
    SERVICE = "service"
    PROTOCOL = "protocol"


@dataclass(frozen=True, slots=True)
class AdbDevicesObservationStarted:
    """Signal that one transport-inventory observation session entered stream mode."""

    endpoint: AdbServerEndpoint
    session_id: AdbObservationSessionId

    def __post_init__(self) -> None:
        _require_endpoint(self.endpoint)
        _require_session_id(self.session_id)
        if self.session_id.endpoint != self.endpoint:
            raise ValueError("session_id endpoint must match signal endpoint")


@dataclass(frozen=True, slots=True)
class AdbDevicesObservationStopped:
    """Signal that observation ended without implying transport disappearance."""

    endpoint: AdbServerEndpoint
    session_id: AdbObservationSessionId

    def __post_init__(self) -> None:
        _require_endpoint(self.endpoint)
        _require_session_id(self.session_id)
        if self.session_id.endpoint != self.endpoint:
            raise ValueError("session_id endpoint must match signal endpoint")


@dataclass(frozen=True, slots=True)
class AdbDevicesObservationFailed:
    """Signal that observation failed without synthesizing server or transport state."""

    endpoint: AdbServerEndpoint
    session_id: AdbObservationSessionId
    failure: AdbDevicesObservationFailure
    diagnostic: str | None = None

    def __post_init__(self) -> None:
        _require_endpoint(self.endpoint)
        _require_session_id(self.session_id)
        if self.session_id.endpoint != self.endpoint:
            raise ValueError("session_id endpoint must match signal endpoint")
        if not isinstance(self.failure, AdbDevicesObservationFailure):
            raise TypeError("failure must be AdbDevicesObservationFailure")
        object.__setattr__(
            self,
            "diagnostic",
            _normalize_optional_text(
                self.diagnostic,
                field_name="ADB transport-inventory observation diagnostic",
            ),
        )


@dataclass(frozen=True, slots=True)
class AdbDevicesSnapshotObserved:
    """Signal carrying one complete snapshot emitted by ADB track-devices."""

    endpoint: AdbServerEndpoint
    session_id: AdbObservationSessionId
    snapshot: AdbDevicesSnapshot

    def __post_init__(self) -> None:
        _require_endpoint(self.endpoint)
        _require_session_id(self.session_id)
        if self.session_id.endpoint != self.endpoint:
            raise ValueError("session_id endpoint must match signal endpoint")
        if not isinstance(self.snapshot, AdbDevicesSnapshot):
            raise TypeError("snapshot must be AdbDevicesSnapshot")


__all__ = [
    "AdbDevicesObservationFailed",
    "AdbDevicesObservationFailure",
    "AdbDevicesObservationStarted",
    "AdbDevicesObservationStopped",
    "AdbDevicesSnapshotObserved",
]

```

---

## FILE: `adb\transport\observation\source.py`

```python
from __future__ import annotations

from collections.abc import Iterator
from math import isfinite
from numbers import Real
import socket
from threading import Lock
from time import monotonic

from adb.transport.devices.domain import AdbDevicesSnapshot
from adb._internal.framing import encode_service, parse_hex_length
from adb._internal.proto import parse_devices_snapshot
from adb.errors import AdbProtocolError
from adb.transport.observation.contracts import (
    AdbObservationProtocolError,
    AdbObservationServerConnectionError,
    AdbObservationServiceError,
)
from adb.server.endpoint import AdbServerEndpoint


_SERVICE = "host:track-devices-proto-binary"


class _SourceClosed(Exception):
    pass


def _normalize_startup_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError("startup_timeout_seconds must be a real number")
    timeout = float(value)
    if not isfinite(timeout) or timeout <= 0:
        raise ValueError("startup_timeout_seconds must be finite and greater than zero")
    return timeout


def _parse_snapshot(payload: bytes) -> AdbDevicesSnapshot:
    try:
        return parse_devices_snapshot(payload)
    except AdbProtocolError as exc:
        raise AdbObservationProtocolError(str(exc)) from exc


class AdbTrackDevicesSession:
    """One established blocking track-devices stream session."""

    def __init__(self, source: "AdbTrackDevicesSource", session_socket: socket.socket) -> None:
        self._source = source
        self._socket = session_socket
        self._closed = False

    def snapshots(self) -> Iterator[AdbDevicesSnapshot]:
        """Yield complete snapshots until the session closes or observation fails."""

        if self._closed:
            return
        try:
            while True:
                yield _parse_snapshot(self._source._read_frame(self._socket))
        except _SourceClosed:
            return

    def close(self) -> None:
        """Close this stream session without introducing retry or recovery policy."""

        if self._closed:
            return
        self._closed = True
        self._source._release_session(self._socket)


class AdbTrackDevicesSource:
    """Blocking ``host:track-devices-proto-binary`` transport-inventory source.

    Each payload is the binary serialization of AOSP ``adb.proto.Devices``.
    The source does not retry or reconnect automatically.
    """

    def __init__(
        self,
        endpoint: AdbServerEndpoint = AdbServerEndpoint(),
        startup_timeout_seconds: float = 5.0,
    ) -> None:
        if not isinstance(endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        self.endpoint = endpoint
        self.startup_timeout_seconds = _normalize_startup_timeout(
            startup_timeout_seconds
        )
        self._lock = Lock()
        self._closed = False
        self._session_active = False
        self._active_socket: socket.socket | None = None

    def close(self) -> None:
        """Permanently close the source and interrupt an active socket read."""

        active_socket: socket.socket | None
        with self._lock:
            if self._closed:
                return
            self._closed = True
            active_socket = self._active_socket

        if active_socket is not None:
            try:
                active_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                active_socket.close()
            except OSError:
                pass

    def open(self) -> AdbTrackDevicesSession | None:
        """Establish one tracker stream and return after stream mode is entered."""

        if not self._acquire_session():
            return None

        session_socket: socket.socket | None = None
        try:
            session_socket, deadline = self._connect()
            self._handshake(session_socket, deadline)
            self._enter_stream_mode(session_socket)
            return AdbTrackDevicesSession(self, session_socket)
        except _SourceClosed:
            self._release_session(session_socket)
            return None
        except BaseException:
            self._release_session(session_socket)
            raise

    def _acquire_session(self) -> bool:
        with self._lock:
            if self._closed:
                return False
            if self._session_active:
                raise RuntimeError("an ADB observation session is already active")
            self._session_active = True
            return True

    def _release_session(self, session_socket: socket.socket | None) -> None:
        if session_socket is not None:
            try:
                session_socket.close()
            except OSError:
                pass
        with self._lock:
            if self._active_socket is session_socket:
                self._active_socket = None
            self._session_active = False

    def _is_closed(self) -> bool:
        with self._lock:
            return self._closed

    def _register_socket(self, candidate: socket.socket) -> None:
        with self._lock:
            if self._closed:
                raise _SourceClosed
            self._active_socket = candidate

    def _unregister_socket(self, candidate: socket.socket) -> None:
        with self._lock:
            if self._active_socket is candidate:
                self._active_socket = None

    def _remaining_timeout(self, deadline: float) -> float:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise AdbObservationServerConnectionError(
                "ADB track-devices startup timed out"
            )
        return remaining

    def _connect(self) -> tuple[socket.socket, float]:
        try:
            addresses = socket.getaddrinfo(
                self.endpoint.host,
                self.endpoint.port,
                type=socket.SOCK_STREAM,
            )
        except OSError as exc:
            if self._is_closed():
                raise _SourceClosed from exc
            raise AdbObservationServerConnectionError(
                f"failed to resolve ADB server endpoint {self.endpoint.host!r}"
            ) from exc

        if self._is_closed():
            raise _SourceClosed

        # Synchronous hostname resolution above cannot be interrupted by a socket
        # timeout. The startup deadline begins after resolution and is shared by
        # all connect attempts plus the ADB service handshake.
        deadline = monotonic() + self.startup_timeout_seconds
        last_error: OSError | None = None
        for family, socktype, proto, _, sockaddr in addresses:
            try:
                candidate = socket.socket(family, socktype, proto)
            except OSError as exc:
                if self._is_closed():
                    raise _SourceClosed from exc
                last_error = exc
                continue
            try:
                self._register_socket(candidate)
                self._set_deadline_timeout(candidate, deadline)
                candidate.connect(sockaddr)
                return candidate, deadline
            except _SourceClosed:
                try:
                    candidate.close()
                except OSError:
                    pass
                raise
            except (OSError, AdbObservationServerConnectionError) as exc:
                if self._is_closed():
                    self._unregister_socket(candidate)
                    try:
                        candidate.close()
                    except OSError:
                        pass
                    raise _SourceClosed from exc
                if isinstance(exc, OSError):
                    last_error = exc
                self._unregister_socket(candidate)
                try:
                    candidate.close()
                except OSError:
                    pass
                if isinstance(exc, AdbObservationServerConnectionError):
                    raise

        detail = str(last_error) if last_error is not None else "no address candidates"
        raise AdbObservationServerConnectionError(
            f"failed to connect to ADB server endpoint: {detail}"
        )

    def _set_deadline_timeout(self, sock: socket.socket, deadline: float) -> None:
        timeout = self._remaining_timeout(deadline)
        try:
            sock.settimeout(timeout)
        except OSError as exc:
            if self._is_closed():
                raise _SourceClosed from exc
            raise AdbObservationServerConnectionError(
                "failed to configure ADB track-devices startup timeout"
            ) from exc

    def _enter_stream_mode(self, sock: socket.socket) -> None:
        try:
            sock.settimeout(None)
        except OSError as exc:
            if self._is_closed():
                raise _SourceClosed from exc
            raise AdbObservationServerConnectionError(
                "failed to enter blocking ADB track-devices stream mode"
            ) from exc

    def _handshake(self, sock: socket.socket, deadline: float) -> None:
        request = encode_service(_SERVICE)
        self._send_all(sock, request, deadline)
        status = self._recv_exact(sock, 4, deadline=deadline)
        if status == b"OKAY":
            return
        if status == b"FAIL":
            length_raw = self._recv_exact(sock, 4, deadline=deadline)
            try:
                length = parse_hex_length(length_raw, context="service error")
            except AdbProtocolError as exc:
                raise AdbObservationProtocolError(str(exc)) from exc
            detail_raw = self._recv_exact(sock, length, deadline=deadline)
            try:
                detail = detail_raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise AdbObservationProtocolError(
                    "ADB service error is not valid UTF-8"
                ) from exc
            raise AdbObservationServiceError(detail or "ADB server rejected track-devices")
        raise AdbObservationProtocolError(
            f"unexpected ADB service status: {status!r}"
        )

    def _read_frame(self, sock: socket.socket) -> bytes:
        length_raw = self._recv_exact(sock, 4, deadline=None)
        try:
            length = parse_hex_length(length_raw, context="snapshot")
        except AdbProtocolError as exc:
            raise AdbObservationProtocolError(str(exc)) from exc
        return self._recv_exact(sock, length, deadline=None)

    def _send_all(self, sock: socket.socket, data: bytes, deadline: float) -> None:
        self._set_deadline_timeout(sock, deadline)
        try:
            sock.sendall(data)
        except socket.timeout as exc:
            if self._is_closed():
                raise _SourceClosed from exc
            raise AdbObservationServerConnectionError(
                "ADB track-devices startup timed out"
            ) from exc
        except OSError as exc:
            if self._is_closed():
                raise _SourceClosed from exc
            raise AdbObservationServerConnectionError(
                "failed to send ADB track-devices service request"
            ) from exc

    def _recv_exact(
        self,
        sock: socket.socket,
        size: int,
        *,
        deadline: float | None,
    ) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            if deadline is not None:
                self._set_deadline_timeout(sock, deadline)
            try:
                chunk = sock.recv(remaining)
            except socket.timeout as exc:
                if self._is_closed():
                    raise _SourceClosed from exc
                raise AdbObservationServerConnectionError(
                    "ADB track-devices startup timed out"
                ) from exc
            except OSError as exc:
                if self._is_closed():
                    raise _SourceClosed from exc
                raise AdbObservationServerConnectionError(
                    "ADB track-devices socket read failed"
                ) from exc
            if not chunk:
                if self._is_closed():
                    raise _SourceClosed
                raise AdbObservationServerConnectionError(
                    "unexpected EOF from ADB track-devices stream"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

```

---

## FILE: `android\adb\query.py`

```python
from __future__ import annotations

from typing import Protocol

from adb.server import AdbServerEndpoint
from adb.transport import AdbTransportSelector
from android.application import AndroidPackageState, AndroidResumedActivitiesSnapshot
from android.display import (
    AndroidDisplayId,
    AndroidDisplayState,
    AndroidDisplaysSnapshot,
    AndroidPhysicalDisplaysSnapshot,
)
from android.identity import AndroidComponentName, AndroidPackageName, AndroidUserId
from android.platform import AndroidBuildInfo
from android.runtime import (
    AndroidBootState,
    AndroidKeyguardState,
    AndroidPowerState,
    AndroidUsersSnapshot,
    AndroidUserState,
)
from android.window import (
    AndroidDisplayOcclusionsSnapshot,
    AndroidWindowId,
    AndroidWindowState,
    AndroidWindowsSnapshot,
)


class AdbBootStateInspector(Protocol):
    """Read-only Android boot readiness query reached through ADB."""

    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidBootState: ...


class AdbBuildInfoInspector(Protocol):
    """Read-only Android build/version facts reached through ADB."""

    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidBuildInfo: ...


class AdbDisplaysInspector(Protocol):
    """Read-only listing query for logical displays on one Android device via ADB."""

    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidDisplaysSnapshot: ...


class AdbDisplayInspector(Protocol):
    """Read-only Android display query reached through an ADB server."""

    def inspect(
        self,
        endpoint: AdbServerEndpoint,
        selector: AdbTransportSelector,
        display_id: AndroidDisplayId,
    ) -> AndroidDisplayState | None:
        """Return display facts, or ``None`` when the display is not observed."""
        ...


class AdbPhysicalDisplaysInspector(Protocol):
    """SurfaceFlinger physical-display identities available for deterministic capture."""

    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidPhysicalDisplaysSnapshot: ...


class AdbCurrentUserInspector(Protocol):
    """Read the Android framework's current user identity."""

    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidUserId: ...


class AdbUsersInspector(Protocol):
    """Read the current complete verbose user/profile listing."""

    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidUsersSnapshot: ...


class AdbUserStateInspector(Protocol):
    """Per-user Android started-user state."""

    def inspect(
        self,
        endpoint: AdbServerEndpoint,
        selector: AdbTransportSelector,
        user_id: AndroidUserId,
    ) -> AndroidUserState | None: ...


class AdbPackageStateInspector(Protocol):
    """Per-user PackageManager installation/availability facts."""

    def inspect(
        self,
        endpoint: AdbServerEndpoint,
        selector: AdbTransportSelector,
        user_id: AndroidUserId,
        package_name: AndroidPackageName,
    ) -> AndroidPackageState: ...


class AdbLauncherActivityInspector(Protocol):
    """Resolve the launcher activity for one package and user, when one exists."""

    def inspect(
        self,
        endpoint: AdbServerEndpoint,
        selector: AdbTransportSelector,
        user_id: AndroidUserId,
        package_name: AndroidPackageName,
    ) -> AndroidComponentName | None: ...


class AdbResumedActivitiesInspector(Protocol):
    """Current resumed activities scoped by user, logical display, and task."""

    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidResumedActivitiesSnapshot: ...


class AdbWindowsInspector(Protocol):
    """Current WindowManager windows in the supported native dump format."""

    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidWindowsSnapshot: ...


class AdbWindowInspector(Protocol):
    """Single native Android window lookup derived from a fresh window snapshot."""

    def inspect(
        self,
        endpoint: AdbServerEndpoint,
        selector: AdbTransportSelector,
        window_id: AndroidWindowId,
    ) -> AndroidWindowState | None: ...


class AdbDisplayOcclusionsInspector(Protocol):
    """Status/navigation/cutout/IME inset sources for one logical display."""

    def inspect(
        self,
        endpoint: AdbServerEndpoint,
        selector: AdbTransportSelector,
        display_id: AndroidDisplayId,
    ) -> AndroidDisplayOcclusionsSnapshot | None: ...


class AdbPowerStateInspector(Protocol):
    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidPowerState: ...


class AdbKeyguardStateInspector(Protocol):
    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidKeyguardState: ...


__all__ = [
    "AdbBootStateInspector",
    "AdbBuildInfoInspector",
    "AdbCurrentUserInspector",
    "AdbDisplayInspector",
    "AdbDisplayOcclusionsInspector",
    "AdbDisplaysInspector",
    "AdbKeyguardStateInspector",
    "AdbLauncherActivityInspector",
    "AdbPackageStateInspector",
    "AdbPhysicalDisplaysInspector",
    "AdbPowerStateInspector",
    "AdbResumedActivitiesInspector",
    "AdbUsersInspector",
    "AdbUserStateInspector",
    "AdbWindowInspector",
    "AdbWindowsInspector",
]

```

---

## FILE: `android\adb\adapters\__init__.py`

```python
from android.adb.adapters.input import (
    AdbBackNavigator,
    AdbKeyChordController,
    AdbKeyPresser,
    AdbTextController,
    AdbTouchController,
)
from android.adb.adapters.command import AdbActivityLauncher, AdbPackageForceStopper
from android.adb.adapters.query import (
    SmartSocketAdbBootStateInspector,
    SmartSocketAdbBuildInfoInspector,
    SmartSocketAdbCurrentUserInspector,
    SmartSocketAdbDisplayInspector,
    SmartSocketAdbDisplayOcclusionsInspector,
    SmartSocketAdbDisplaysInspector,
    SmartSocketAdbKeyguardStateInspector,
    SmartSocketAdbLauncherActivityInspector,
    SmartSocketAdbPackageStateInspector,
    SmartSocketAdbPhysicalDisplaysInspector,
    SmartSocketAdbPowerStateInspector,
    SmartSocketAdbResumedActivitiesInspector,
    SmartSocketAdbUsersInspector,
    SmartSocketAdbUserStateInspector,
    SmartSocketAdbWindowInspector,
    SmartSocketAdbWindowsInspector,
)

__all__ = [
    "AdbActivityLauncher",
    "AdbBackNavigator",
    "AdbKeyChordController",
    "AdbKeyPresser",
    "AdbPackageForceStopper",
    "AdbTextController",
    "AdbTouchController",
    "SmartSocketAdbBootStateInspector",
    "SmartSocketAdbBuildInfoInspector",
    "SmartSocketAdbCurrentUserInspector",
    "SmartSocketAdbDisplayInspector",
    "SmartSocketAdbDisplayOcclusionsInspector",
    "SmartSocketAdbDisplaysInspector",
    "SmartSocketAdbKeyguardStateInspector",
    "SmartSocketAdbLauncherActivityInspector",
    "SmartSocketAdbPackageStateInspector",
    "SmartSocketAdbPhysicalDisplaysInspector",
    "SmartSocketAdbPowerStateInspector",
    "SmartSocketAdbResumedActivitiesInspector",
    "SmartSocketAdbUsersInspector",
    "SmartSocketAdbUserStateInspector",
    "SmartSocketAdbWindowInspector",
    "SmartSocketAdbWindowsInspector",
]

```

---

## FILE: `android\adb\adapters\_attempt.py`

```python
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from adb._internal.client import AdbServiceClient, ShellV2Result
from adb.errors import AdbError, AdbTimeoutError
from adb.server import AdbServerEndpoint
from adb.transport import AdbTransportSelector
from native_attempt import NativeAttemptResult, NativeAttemptStatus, NativeCompletionScope


ClientFactory = Callable[[AdbServerEndpoint], AdbServiceClient]


def default_client_factory(endpoint: AdbServerEndpoint) -> AdbServiceClient:
    return AdbServiceClient(endpoint)


def shell_v2_attempt(
    endpoint: AdbServerEndpoint,
    selector: AdbTransportSelector,
    command: str,
    *,
    backend_id: str,
    client_factory: ClientFactory = default_client_factory,
) -> NativeAttemptResult:
    started_at = datetime.now(timezone.utc)
    try:
        result = client_factory(endpoint).shell_v2(selector, command)
    except AdbTimeoutError as exc:
        return NativeAttemptResult(
            status=NativeAttemptStatus.TIMED_OUT,
            completion_scope=None,
            backend_id=backend_id,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            native_code=type(exc).__name__,
            diagnostic=str(exc),
        )
    except AdbError as exc:
        return NativeAttemptResult(
            status=NativeAttemptStatus.FAILED,
            completion_scope=None,
            backend_id=backend_id,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            native_code=type(exc).__name__,
            diagnostic=str(exc),
        )
    return native_result(backend_id, started_at, result)


def native_result(
    backend_id: str,
    started_at: datetime,
    result: ShellV2Result,
) -> NativeAttemptResult:
    diagnostic = result.stderr.decode("utf-8", errors="replace").strip() or None
    return NativeAttemptResult(
        status=(
            NativeAttemptStatus.SUCCEEDED
            if result.exit_code == 0
            else NativeAttemptStatus.FAILED
        ),
        completion_scope=NativeCompletionScope.PROCESS_EXIT,
        backend_id=backend_id,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        native_code=str(result.exit_code),
        diagnostic=diagnostic,
    )


__all__ = ["ClientFactory", "default_client_factory", "native_result", "shell_v2_attempt"]

```

---

## FILE: `android\adb\adapters\_display_parsers.py`

```python
from __future__ import annotations

import re

from adb.errors import AdbProtocolError
from android.display import (
    AndroidDisplayId,
    AndroidDisplayRotation,
    AndroidDisplayState,
    AndroidDisplaysSnapshot,
    AndroidPhysicalDisplayId,
    AndroidPhysicalDisplayState,
    AndroidPhysicalDisplaysSnapshot,
)
from geometry import Rect


_DISPLAY_SECTION_RE = re.compile(r"^\s*Display\s+(\d+):\s*$")
_DISPLAY_ID_RE = re.compile(r"\bdisplayId\s+(\d+)\b")
_LEGACY_DISPLAY_ID_RE = re.compile(r"\bmDisplayId=(\d+)\b")
_REAL_SIZE_RE = re.compile(r"\breal\s+(\d+)\s*x\s*(\d+)\b")
_ROTATION_RE = re.compile(r"\brotation\s*(\d+)\b")
_DENSITY_RE = re.compile(r"\bdensity\s+(\d+)\b")
_LOCAL_UNIQUE_ID_RE = re.compile(r'\buniqueId\s+"local:(\d+)"')
_PHYSICAL_DISPLAY_RE = re.compile(
    r'^\s*Display\s+(\d+)(?:\s+\(HWC display\s+(\d+)\))?(?::\s*(.*))?$'
)
_PORT_RE = re.compile(r"\bport=(\d+)\b")
_PNP_RE = re.compile(r"\bpnpId=([^\s]+)")
_DISPLAY_NAME_RE = re.compile(r'\bdisplayName="([^"]*)"')


def parse_dumpsys_display(text: str) -> AndroidDisplaysSnapshot:
    """Parse supported AOSP logical ``DisplayInfo`` rows and reject partial parses."""
    if not isinstance(text, str):
        raise TypeError("display dump must be a string")

    current_display_id: int | None = None
    by_id: dict[int, AndroidDisplayState] = {}
    priority: dict[int, int] = {}
    candidate_rows = 0

    for line in text.splitlines():
        section = _DISPLAY_SECTION_RE.match(line)
        if section is not None:
            current_display_id = int(section.group(1))
            continue

        legacy_id = _LEGACY_DISPLAY_ID_RE.search(line)
        if legacy_id is not None:
            current_display_id = int(legacy_id.group(1))

        if "DisplayInfo{" not in line or "mOverrideDisplayInfo=null" in line:
            continue
        candidate_rows += 1

        embedded_id = _DISPLAY_ID_RE.search(line)
        display_id = int(embedded_id.group(1)) if embedded_id else current_display_id
        size = _REAL_SIZE_RE.search(line)
        rotation = _ROTATION_RE.search(line)
        density = _DENSITY_RE.search(line)
        missing = [
            name
            for name, value in (
                ("display id", display_id),
                ("real size", size),
                ("rotation", rotation),
                ("density", density),
            )
            if value is None
        ]
        if missing:
            raise AdbProtocolError(
                "unsupported dumpsys display candidate row did not match the supported "
                "Android display format: missing " + ", ".join(missing)
            )
        assert display_id is not None
        assert size is not None
        assert rotation is not None
        assert density is not None

        try:
            normalized_rotation = AndroidDisplayRotation.from_surface_rotation(
                int(rotation.group(1))
            )
        except ValueError as exc:
            raise AdbProtocolError(
                f"Android display {display_id} has unsupported rotation {rotation.group(1)}"
            ) from exc

        local_id = _LOCAL_UNIQUE_ID_RE.search(line)
        state = AndroidDisplayState(
            display_id=AndroidDisplayId(display_id),
            bounds=Rect(
                x=0,
                y=0,
                width=int(size.group(1)),
                height=int(size.group(2)),
            ),
            rotation=normalized_rotation,
            density_dpi=int(density.group(1)),
            physical_display_id=(
                AndroidPhysicalDisplayId(int(local_id.group(1))) if local_id else None
            ),
        )
        row_priority = 2 if "mOverrideDisplayInfo=" in line else 1
        if display_id not in by_id or row_priority >= priority[display_id]:
            by_id[display_id] = state
            priority[display_id] = row_priority

    if candidate_rows == 0:
        raise AdbProtocolError(
            "unsupported dumpsys display format: no DisplayInfo rows were present"
        )
    if not by_id:
        raise AdbProtocolError("unsupported dumpsys display format")
    return AndroidDisplaysSnapshot(tuple(by_id[key] for key in sorted(by_id)))


def parse_surfaceflinger_display_ids(text: str) -> AndroidPhysicalDisplaysSnapshot:
    if not isinstance(text, str):
        raise TypeError("SurfaceFlinger display dump must be a string")

    displays: list[AndroidPhysicalDisplayState] = []
    for line in text.splitlines():
        match = _PHYSICAL_DISPLAY_RE.match(line)
        if match is None:
            continue
        suffix = match.group(3) or ""
        port = _PORT_RE.search(suffix)
        pnp = _PNP_RE.search(suffix)
        name = _DISPLAY_NAME_RE.search(suffix)
        displays.append(
            AndroidPhysicalDisplayState(
                display_id=AndroidPhysicalDisplayId(int(match.group(1))),
                hwc_display_id=(
                    int(match.group(2)) if match.group(2) is not None else None
                ),
                port=int(port.group(1)) if port else None,
                pnp_id=pnp.group(1) if pnp else None,
                display_name=name.group(1) if name else None,
            )
        )

    if not displays:
        raise AdbProtocolError(
            "unsupported SurfaceFlinger --display-id format: no physical display rows"
        )
    return AndroidPhysicalDisplaysSnapshot(tuple(displays))


__all__ = ["parse_dumpsys_display", "parse_surfaceflinger_display_ids"]

```

---

## FILE: `android\adb\adapters\_runtime_parsers.py`

```python
from __future__ import annotations

import re

from adb.errors import AdbProtocolError
from android.application import (
    AndroidPackageEnabledState,
    AndroidPackageState,
    AndroidResumedActivitiesSnapshot,
    AndroidResumedActivity,
)
from android.display import AndroidDisplayId
from android.identity import AndroidComponentName, AndroidPackageName, AndroidUserId
from android.platform import AndroidBuildInfo
from android.runtime import (
    AndroidBootState,
    AndroidKeyguardState,
    AndroidPowerState,
    AndroidPowerWakefulness,
    AndroidUserInfo,
    AndroidUserPhase,
    AndroidUsersSnapshot,
    AndroidUserState,
)


_USER_STATE_RE = re.compile(r"\bid=(\d+),\s*state=([A-Z_]+)\b")
_USER_NOT_STARTED_RE = re.compile(r"^\s*User is not started:\s*(\d+)\s*$")
_ACTIVITY_DISPLAY_RE = re.compile(r"^\s*Display\s+#(\d+)\b")
_RESUMED_ACTIVITY_RE = re.compile(
    r"(?:mResumedActivity:\s*|topResumedActivity=)"
    r"ActivityRecord\{[^}]*?\bu(\d+)\s+"
    r"([A-Za-z][A-Za-z0-9_.]*)/(\.?[A-Za-z_$][A-Za-z0-9_.$]*)\s+t(\d+)\b"
)
_WAKEFULNESS_RE = re.compile(r"\bmWakefulness=(Awake|Asleep|Dozing|Dreaming)\b")
_WAKEFULNESS_ALT_RE = re.compile(
    r"\bWakefulness:\s*(Awake|Asleep|Dozing|Dreaming)\b"
)
_KEYGUARD_SHOWING_RE = re.compile(
    r"\bmKeyguardShowing=(true|false)\b", re.IGNORECASE
)
_USERS_HEADER_RE = re.compile(r"^\s*(\d+)\s+users?:\s*$")
_USER_ROW_RE = re.compile(
    r"^\s*\d+:\s+id=(\d+),\s*name=(.*?),\s*type=([^,]+),\s*flags=([^\s(]*)(.*)$"
)
_PARENT_ID_RE = re.compile(r"\(parentId=(\d+)\)")
_PACKAGE_USER_RE = re.compile(r"^\s*User\s+(\d+):\s*(.*)$")
_PACKAGE_BOOL_RE = re.compile(r"\b(installed|hidden|suspended)=(true|false)\b")
_PACKAGE_ENABLED_RE = re.compile(r"\benabled=(\d+)\b")


def parse_boot_completed(text: str) -> AndroidBootState:
    if not isinstance(text, str):
        raise TypeError("boot-completed value must be a string")
    value = text.strip()
    if value == "1":
        return AndroidBootState.BOOTED
    if value in {"", "0"}:
        return AndroidBootState.BOOTING
    raise AdbProtocolError(f"unsupported sys.boot_completed value {value!r}")


def parse_build_info(text: str) -> AndroidBuildInfo:
    if not isinstance(text, str):
        raise TypeError("Android build-info output must be a string")
    lines = [line.strip() for line in text.splitlines()]
    if len(lines) != 3 or any(not line for line in lines):
        raise AdbProtocolError("unsupported Android build-info output")
    try:
        return AndroidBuildInfo(
            sdk_int=int(lines[0]), release=lines[1], fingerprint=lines[2]
        )
    except (TypeError, ValueError) as exc:
        raise AdbProtocolError("unsupported Android build-info output") from exc


def parse_current_user(text: str) -> AndroidUserId:
    if not isinstance(text, str):
        raise TypeError("current-user output must be a string")
    value = text.strip()
    if re.fullmatch(r"\d+", value) is None:
        raise AdbProtocolError("unsupported current-user output")
    return AndroidUserId(int(value))


def parse_users(text: str) -> AndroidUsersSnapshot:
    if not isinstance(text, str):
        raise TypeError("user-list output must be a string")
    declared: int | None = None
    users: list[AndroidUserInfo] = []
    candidate_rows = 0

    for line in text.splitlines():
        header = _USERS_HEADER_RE.match(line)
        if header:
            declared = int(header.group(1))
            continue
        if "id=" not in line:
            continue
        candidate_rows += 1
        match = _USER_ROW_RE.match(line)
        if match is None:
            raise AdbProtocolError("unsupported verbose Android user row")
        tail = match.group(5)
        parent = _PARENT_ID_RE.search(tail)
        users.append(
            AndroidUserInfo(
                user_id=AndroidUserId(int(match.group(1))),
                name=match.group(2),
                user_type=match.group(3),
                flags=frozenset(
                    part for part in match.group(4).split("|") if part
                ),
                profile_group_id=(
                    AndroidUserId(int(parent.group(1))) if parent else None
                ),
                running="(running)" in tail,
                current="(current)" in tail,
                visible="(visible)" in tail,
            )
        )

    if declared is None:
        raise AdbProtocolError("unsupported verbose Android user-list format")
    if candidate_rows != declared or len(users) != declared:
        raise AdbProtocolError("Android user-list snapshot is incomplete")
    return AndroidUsersSnapshot(tuple(users))


def parse_android_user_state(
    text: str, user_id: AndroidUserId
) -> AndroidUserState | None:
    if not isinstance(user_id, AndroidUserId):
        raise TypeError("user_id must be AndroidUserId")
    not_started = _USER_NOT_STARTED_RE.match(text.strip())
    if not_started is not None:
        if int(not_started.group(1)) != user_id.value:
            raise AdbProtocolError(
                "Android user-state response referenced a different user"
            )
        return None

    match = _USER_STATE_RE.search(text)
    if match is None or int(match.group(1)) != user_id.value:
        raise AdbProtocolError("unsupported Android started-user state format")
    try:
        return AndroidUserState(
            user_id=user_id, phase=AndroidUserPhase[match.group(2)]
        )
    except KeyError as exc:
        raise AdbProtocolError(
            f"unsupported Android user phase {match.group(2)!r}"
        ) from exc


def parse_package_state(
    text: str,
    user_id: AndroidUserId,
    package_name: AndroidPackageName,
) -> AndroidPackageState:
    if not isinstance(user_id, AndroidUserId):
        raise TypeError("user_id must be AndroidUserId")
    if not isinstance(package_name, AndroidPackageName):
        raise TypeError("package_name must be AndroidPackageName")
    if "Unable to find package" in text or "was not found" in text:
        return AndroidPackageState(
            user_id=user_id, package_name=package_name, installed=False
        )

    for line in text.splitlines():
        match = _PACKAGE_USER_RE.match(line)
        if not match or int(match.group(1)) != user_id.value:
            continue
        fields = {
            key: value.lower() == "true"
            for key, value in _PACKAGE_BOOL_RE.findall(match.group(2))
        }
        enabled = _PACKAGE_ENABLED_RE.search(match.group(2))
        if not {"installed", "hidden", "suspended"}.issubset(fields) or enabled is None:
            raise AdbProtocolError(
                "unsupported PackageManager per-user package state"
            )
        try:
            enabled_state = AndroidPackageEnabledState(int(enabled.group(1)))
        except ValueError as exc:
            raise AdbProtocolError("unsupported PackageManager enabled state") from exc
        return AndroidPackageState(
            user_id=user_id,
            package_name=package_name,
            installed=fields["installed"],
            hidden=fields["hidden"],
            suspended=fields["suspended"],
            enabled_state=enabled_state,
        )
    raise AdbProtocolError("package dump did not contain requested user state")


def parse_launcher_component(
    text: str, package_name: AndroidPackageName
) -> AndroidComponentName | None:
    if not isinstance(package_name, AndroidPackageName):
        raise TypeError("package_name must be AndroidPackageName")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or all("No activity found" in line for line in lines):
        return None
    candidates = [
        line
        for line in lines
        if re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_.]*/\.?[A-Za-z_$][A-Za-z0-9_.$]*", line
        )
    ]
    if len(candidates) != 1:
        raise AdbProtocolError("unsupported launcher-activity resolution output")
    package, class_name = candidates[0].split("/", 1)
    if package != package_name.value:
        raise AdbProtocolError("launcher resolution returned a different package")
    return AndroidComponentName(package_name, class_name)


def parse_resumed_activities(text: str) -> AndroidResumedActivitiesSnapshot:
    if not isinstance(text, str):
        raise TypeError("activity dump must be a string")
    display_id: AndroidDisplayId | None = None
    activities: list[AndroidResumedActivity] = []
    recognized_structure = "ACTIVITY MANAGER ACTIVITIES" in text
    candidate_rows = 0

    for line in text.splitlines():
        display_match = _ACTIVITY_DISPLAY_RE.match(line)
        if display_match is not None:
            display_id = AndroidDisplayId(int(display_match.group(1)))
            recognized_structure = True
            continue
        if "mResumedActivity:" not in line and "topResumedActivity=" not in line:
            continue
        candidate_rows += 1
        resumed = _RESUMED_ACTIVITY_RE.search(line)
        if resumed is None:
            raise AdbProtocolError("unsupported resumed-activity row format")
        if display_id is None:
            raise AdbProtocolError(
                "resumed activity row was not scoped by a logical display section"
            )
        package = AndroidPackageName(resumed.group(2))
        activities.append(
            AndroidResumedActivity(
                user_id=AndroidUserId(int(resumed.group(1))),
                display_id=display_id,
                component=AndroidComponentName(package, resumed.group(3)),
                task_id=int(resumed.group(4)),
            )
        )

    if not recognized_structure:
        raise AdbProtocolError("unsupported dumpsys activity activities format")
    if candidate_rows != len(activities):
        raise AdbProtocolError("resumed-activity snapshot is incomplete")
    return AndroidResumedActivitiesSnapshot(tuple(activities))


def parse_power_state(text: str) -> AndroidPowerState:
    match = _WAKEFULNESS_RE.search(text) or _WAKEFULNESS_ALT_RE.search(text)
    if match is None:
        raise AdbProtocolError("unsupported dumpsys power wakefulness format")
    mapping = {
        "Awake": AndroidPowerWakefulness.AWAKE,
        "Asleep": AndroidPowerWakefulness.ASLEEP,
        "Dozing": AndroidPowerWakefulness.DOZING,
        "Dreaming": AndroidPowerWakefulness.DREAMING,
    }
    return AndroidPowerState(mapping[match.group(1)])


def parse_keyguard_state(text: str) -> AndroidKeyguardState:
    match = _KEYGUARD_SHOWING_RE.search(text)
    if match is None:
        raise AdbProtocolError("unsupported dumpsys window policy keyguard format")
    return AndroidKeyguardState(showing=match.group(1).lower() == "true")


__all__ = [
    "parse_android_user_state",
    "parse_boot_completed",
    "parse_build_info",
    "parse_current_user",
    "parse_keyguard_state",
    "parse_launcher_component",
    "parse_package_state",
    "parse_power_state",
    "parse_resumed_activities",
    "parse_users",
]

```

---

## FILE: `android\adb\adapters\_window_parsers.py`

```python
from __future__ import annotations

import re

from adb.errors import AdbProtocolError
from android.display import AndroidDisplayId
from android.identity import AndroidComponentName, AndroidPackageName, AndroidUserId
from android.window import (
    AndroidDisplayOcclusion,
    AndroidDisplayOcclusionKind,
    AndroidDisplayOcclusionsSnapshot,
    AndroidWindowId,
    AndroidWindowState,
    AndroidWindowsSnapshot,
    AndroidWindowViewVisibility,
)
from geometry import Rect


_WINDOW_HEADER_RE = re.compile(
    r"^\s*Window #\d+ Window\{([0-9A-Fa-f]+)\s+u(\d+)\s+([^}]+)\}:\s*$"
)
_CURRENT_FOCUS_RE = re.compile(r"\bmCurrentFocus=Window\{([0-9A-Fa-f]+)\b")
_WINDOW_DISPLAY_RE = re.compile(r"\bmDisplayId=(\d+)\b")
_WINDOW_FRAME_RE = re.compile(
    r"\b(?:frame|mFrame)=\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]"
)
_WINDOW_VIS_RE = re.compile(r"\bmViewVisibility=(0x[0-9A-Fa-f]+|\d+)\b")
_WINDOW_SURFACE_RE = re.compile(r"\bmHasSurface=(true|false)\b", re.IGNORECASE)
_WINDOW_PACKAGE_RE = re.compile(r"\bpackage=([A-Za-z][A-Za-z0-9_.]*)\b")
_WINDOW_MODE_RE = re.compile(r"\b(?:mWindowingMode|windowingMode)=([^\s,}]+)")
_WM_DISPLAY_SECTION_RES = (
    re.compile(r"^\s*Display\s+#(\d+)\b"),
    re.compile(r"^\s*Display:\s*mDisplayId=(\d+)\b"),
    re.compile(r"^\s*DisplayContent\{[^}]*\bdisplayId=(\d+)\b"),
)
_INSETS_SOURCE_CANDIDATE_RE = re.compile(r"\bInsetsSource\b")
_INSETS_TYPE_RE = re.compile(r"\b(?:type|mType)=([^\s,}]+)")
_INSETS_FRAME_RE = re.compile(
    r"\b(?:frame|mFrame)=\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]"
)
_INSETS_VISIBLE_RE = re.compile(
    r"\b(?:visible|mVisible)=(true|false)\b", re.IGNORECASE
)


def _rect_from_match(match: re.Match[str], *, context: str) -> Rect:
    try:
        return Rect.from_ltrb(
            left=int(match.group(1)),
            top=int(match.group(2)),
            right=int(match.group(3)),
            bottom=int(match.group(4)),
        )
    except ValueError as exc:
        raise AdbProtocolError(f"invalid {context} rectangle") from exc


def parse_windows(text: str) -> AndroidWindowsSnapshot:
    if not isinstance(text, str):
        raise TypeError("window dump must be a string")
    focus_match = _CURRENT_FOCUS_RE.search(text)
    focused_id = focus_match.group(1) if focus_match else None
    lines = text.splitlines()
    windows: list[AndroidWindowState] = []
    i = 0

    while i < len(lines):
        header = _WINDOW_HEADER_RE.match(lines[i])
        if header is None:
            i += 1
            continue
        candidate_id = header.group(1)
        user = int(header.group(2))
        title = header.group(3).strip()
        block = [lines[i]]
        i += 1
        while i < len(lines) and _WINDOW_HEADER_RE.match(lines[i]) is None:
            block.append(lines[i])
            i += 1
        body = "\n".join(block)

        display = _WINDOW_DISPLAY_RE.search(body)
        frame = _WINDOW_FRAME_RE.search(body)
        visibility = _WINDOW_VIS_RE.search(body)
        surface = _WINDOW_SURFACE_RE.search(body)
        if None in (display, frame, visibility, surface):
            raise AdbProtocolError(
                f"unsupported WindowState row for {candidate_id}: required facts missing"
            )
        assert display is not None
        assert frame is not None
        assert visibility is not None
        assert surface is not None

        raw_visibility = int(visibility.group(1), 0)
        try:
            view_visibility = AndroidWindowViewVisibility(raw_visibility)
        except ValueError as exc:
            raise AdbProtocolError(
                f"unsupported Android window visibility {raw_visibility}"
            ) from exc

        package_match = _WINDOW_PACKAGE_RE.search(body)
        package_name: AndroidPackageName | None = None
        component: AndroidComponentName | None = None
        component_match = re.search(
            r"([A-Za-z][A-Za-z0-9_.]*)/(\.?[A-Za-z_$][A-Za-z0-9_.$]*)",
            title,
        )
        if component_match:
            package_name = AndroidPackageName(component_match.group(1))
            component = AndroidComponentName(package_name, component_match.group(2))
        elif package_match:
            package_name = AndroidPackageName(package_match.group(1))

        mode = _WINDOW_MODE_RE.search(body)
        windows.append(
            AndroidWindowState(
                window_id=AndroidWindowId(candidate_id),
                user_id=AndroidUserId(user),
                display_id=AndroidDisplayId(int(display.group(1))),
                bounds=_rect_from_match(frame, context="Android window"),
                view_visibility=view_visibility,
                has_surface=surface.group(1).lower() == "true",
                focused=candidate_id == focused_id,
                package_name=package_name,
                component=component,
                windowing_mode=mode.group(1) if mode else None,
            )
        )

    if not windows:
        raise AdbProtocolError(
            "unsupported dumpsys window windows format: no WindowState rows"
        )
    if focused_id is not None and all(
        window.window_id.value != focused_id for window in windows
    ):
        raise AdbProtocolError(
            "focused window was not present in parsed window snapshot"
        )
    return AndroidWindowsSnapshot(tuple(windows))


def _occlusion_kind(raw_type: str) -> AndroidDisplayOcclusionKind | None:
    normalized = raw_type.lower().replace("_", "").replace("-", "")
    if "statusbar" in normalized:
        return AndroidDisplayOcclusionKind.STATUS_BAR
    if "navigationbar" in normalized or "navbar" in normalized:
        return AndroidDisplayOcclusionKind.NAVIGATION_BAR
    if "displaycutout" in normalized or "cutout" in normalized:
        return AndroidDisplayOcclusionKind.DISPLAY_CUTOUT
    if normalized in {"ime", "itypeime"} or normalized.endswith("ime"):
        return AndroidDisplayOcclusionKind.IME
    return None


def parse_display_occlusions(
    text: str, display_id: AndroidDisplayId
) -> AndroidDisplayOcclusionsSnapshot | None:
    if not isinstance(display_id, AndroidDisplayId):
        raise TypeError("display_id must be AndroidDisplayId")
    if not isinstance(text, str):
        raise TypeError("window-display dump must be a string")

    current_display: int | None = None
    seen_displays: set[int] = set()
    occlusions: list[AndroidDisplayOcclusion] = []

    for line in text.splitlines():
        section = next(
            (
                match
                for pattern in _WM_DISPLAY_SECTION_RES
                if (match := pattern.match(line)) is not None
            ),
            None,
        )
        if section is not None:
            current_display = int(section.group(1))
            seen_displays.add(current_display)
            continue
        if (
            current_display != display_id.value
            or _INSETS_SOURCE_CANDIDATE_RE.search(line) is None
        ):
            continue

        type_match = _INSETS_TYPE_RE.search(line)
        if type_match is None:
            raise AdbProtocolError("InsetsSource row did not expose a type")
        kind = _occlusion_kind(type_match.group(1))
        if kind is None:
            continue
        frame = _INSETS_FRAME_RE.search(line)
        visible = _INSETS_VISIBLE_RE.search(line)
        if frame is None or visible is None:
            raise AdbProtocolError(
                "supported InsetsSource row is missing frame/visibility"
            )
        occlusions.append(
            AndroidDisplayOcclusion(
                kind=kind,
                bounds=_rect_from_match(frame, context="Android inset"),
                visible=visible.group(1).lower() == "true",
            )
        )

    if not seen_displays:
        raise AdbProtocolError("unsupported dumpsys window displays format")
    if display_id.value not in seen_displays:
        return None
    return AndroidDisplayOcclusionsSnapshot(
        display_id=display_id, occlusions=tuple(occlusions)
    )


__all__ = ["parse_display_occlusions", "parse_windows"]

```

---

## FILE: `android\adb\adapters\command.py`

```python
from __future__ import annotations

from adb.server import AdbServerEndpoint
from adb.transport import AdbTransportSelector
from android.adb.adapters._attempt import ClientFactory, default_client_factory, shell_v2_attempt
from android.command import AndroidActivityLaunch, AndroidPackageForceStop
from native_attempt import NativeAttemptResult


class _AndroidAdbCommandAdapter:
    backend_id = "android-adb-command"

    def __init__(
        self,
        endpoint: AdbServerEndpoint,
        selector: AdbTransportSelector,
        *,
        _client_factory: ClientFactory = default_client_factory,
    ) -> None:
        if not isinstance(endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        self.endpoint = endpoint
        self.selector = selector
        self._client_factory = _client_factory

    def _attempt(self, command: str) -> NativeAttemptResult:
        return shell_v2_attempt(
            self.endpoint,
            self.selector,
            command,
            backend_id=self.backend_id,
            client_factory=self._client_factory,
        )


class AdbActivityLauncher(_AndroidAdbCommandAdapter):
    """Typed ``am start`` attempt with explicit Android user/component identity."""

    def launch(self, operation: AndroidActivityLaunch) -> NativeAttemptResult:
        if not isinstance(operation, AndroidActivityLaunch):
            raise TypeError("operation must be AndroidActivityLaunch")
        return self._attempt(
            "am start --user "
            f"{operation.user_id.value} -n {operation.component.flattened}"
        )


class AdbPackageForceStopper(_AndroidAdbCommandAdapter):
    """Typed ``am force-stop`` attempt with explicit Android user/package identity."""

    def force_stop(self, operation: AndroidPackageForceStop) -> NativeAttemptResult:
        if not isinstance(operation, AndroidPackageForceStop):
            raise TypeError("operation must be AndroidPackageForceStop")
        return self._attempt(
            "am force-stop --user "
            f"{operation.user_id.value} {operation.package_name.value}"
        )


__all__ = ["AdbActivityLauncher", "AdbPackageForceStopper"]

```

---

## FILE: `android\adb\adapters\input.py`

```python
from __future__ import annotations

from datetime import timedelta
import re

from adb.server import AdbServerEndpoint
from adb.transport import AdbTransportSelector
from android.adb.adapters._attempt import ClientFactory, default_client_factory, shell_v2_attempt
from android.display import AndroidDisplayId
from android.spatial import AndroidDisplayPoint
from execution.input import KeyChord, KeyPress, TextEntry
from execution.touch import TouchDragAndDrop, TouchLongPress, TouchSwipe, TouchTap
from native_attempt import NativeAttemptResult, NativeAttemptStatus


_SAFE_KEY_RE = re.compile(r"^(?:KEYCODE_)?[A-Z0-9_]+$")
_PORTABLE_TEXT_RE = re.compile(r"^[A-Za-z0-9 .,_@+\-]+$")


def _duration_ms(value: timedelta) -> int:
    return max(1, int(round(value.total_seconds() * 1000)))


def _keycode(key_value: str) -> str:
    raw = key_value.upper()
    if _SAFE_KEY_RE.fullmatch(raw) is None:
        raise ValueError("Android key name contains unsupported characters")
    return raw if raw.startswith("KEYCODE_") else f"KEYCODE_{raw}"


class _AndroidAdbCommandAdapter:
    backend_id = "android-adb-input"

    def __init__(
        self,
        endpoint: AdbServerEndpoint,
        selector: AdbTransportSelector,
        display_id: AndroidDisplayId,
        *,
        _client_factory: ClientFactory = default_client_factory,
    ) -> None:
        if not isinstance(endpoint, AdbServerEndpoint):
            raise TypeError("endpoint must be AdbServerEndpoint")
        if not isinstance(display_id, AndroidDisplayId):
            raise TypeError("display_id must be AndroidDisplayId")
        self.endpoint = endpoint
        self.selector = selector
        self.display_id = display_id
        self._client_factory = _client_factory

    def _attempt(self, command: str) -> NativeAttemptResult:
        return shell_v2_attempt(
            self.endpoint,
            self.selector,
            command,
            backend_id=self.backend_id,
            client_factory=self._client_factory,
        )


class AdbTouchController(_AndroidAdbCommandAdapter):
    """Single-pointer Android touch commands in one logical display surface."""

    def tap(self, operation: TouchTap[AndroidDisplayPoint]) -> NativeAttemptResult:
        if not isinstance(operation, TouchTap):
            raise TypeError("operation must be TouchTap")
        point = _require_display_point(operation.point)
        return self._attempt(
            f"input -d {self.display_id.value} tap {point.x} {point.y}"
        )

    def long_press(
        self,
        operation: TouchLongPress[AndroidDisplayPoint],
    ) -> NativeAttemptResult:
        if not isinstance(operation, TouchLongPress):
            raise TypeError("operation must be TouchLongPress")
        point = _require_display_point(operation.point)
        duration = _duration_ms(operation.duration)
        return self._attempt(
            "input -d "
            f"{self.display_id.value} swipe "
            f"{point.x} {point.y} {point.x} {point.y} {duration}"
        )

    def swipe(self, operation: TouchSwipe[AndroidDisplayPoint]) -> NativeAttemptResult:
        if not isinstance(operation, TouchSwipe):
            raise TypeError("operation must be TouchSwipe")
        start = _require_display_point(operation.start)
        end = _require_display_point(operation.end)
        duration = _duration_ms(operation.duration)
        return self._attempt(
            "input -d "
            f"{self.display_id.value} swipe "
            f"{start.x} {start.y} {end.x} {end.y} {duration}"
        )

    def drag_and_drop(
        self,
        operation: TouchDragAndDrop[AndroidDisplayPoint],
    ) -> NativeAttemptResult:
        if not isinstance(operation, TouchDragAndDrop):
            raise TypeError("operation must be TouchDragAndDrop")
        start = _require_display_point(operation.start)
        end = _require_display_point(operation.end)
        duration = _duration_ms(operation.duration)
        return self._attempt(
            "input -d "
            f"{self.display_id.value} draganddrop "
            f"{start.x} {start.y} {end.x} {end.y} {duration}"
        )


class AdbKeyPresser(_AndroidAdbCommandAdapter):
    """Basic Android key-event adapter for one logical display."""

    def press(self, operation: KeyPress) -> NativeAttemptResult:
        if not isinstance(operation, KeyPress):
            raise TypeError("operation must be KeyPress")
        if operation.repeat != 1 or operation.interval.total_seconds() != 0:
            return self._unsupported_repeat_result()
        return self._attempt(
            f"input -d {self.display_id.value} keyevent {_keycode(operation.key.value)}"
        )

    def _unsupported_repeat_result(self) -> NativeAttemptResult:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        return NativeAttemptResult(
            status=NativeAttemptStatus.FAILED,
            completion_scope=None,
            backend_id=self.backend_id,
            started_at=now,
            finished_at=now,
            native_code="unsupported_semantics",
            diagnostic="Android ADB key adapter currently requires repeat=1 and interval=0",
        )


class AdbKeyChordController(_AndroidAdbCommandAdapter):
    """One AOSP ``input keycombination`` native attempt."""

    def chord(self, operation: KeyChord) -> NativeAttemptResult:
        if not isinstance(operation, KeyChord):
            raise TypeError("operation must be KeyChord")
        keycodes = " ".join(_keycode(key.value) for key in operation.keys)
        return self._attempt(
            f"input -d {self.display_id.value} keycombination {keycodes}"
        )


class AdbTextController(_AndroidAdbCommandAdapter):
    """Limited portable ASCII text via AOSP virtual-keyboard ``input text`` semantics."""

    def type_text(self, operation: TextEntry) -> NativeAttemptResult:
        if not isinstance(operation, TextEntry):
            raise TypeError("operation must be TextEntry")
        if _PORTABLE_TEXT_RE.fullmatch(operation.text) is None:
            now_result = self._unsupported_text_result()
            return now_result
        encoded = operation.text.replace(" ", "%s")
        return self._attempt(f"input -d {self.display_id.value} text {encoded}")

    def _unsupported_text_result(self) -> NativeAttemptResult:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        return NativeAttemptResult(
            status=NativeAttemptStatus.FAILED,
            completion_scope=None,
            backend_id=self.backend_id,
            started_at=now,
            finished_at=now,
            native_code="unsupported_text_semantics",
            diagnostic=(
                "Android ADB text adapter supports only portable ASCII letters, digits, "
                "space, and .,_@+-. Use an IME/clipboard/instrumentation adapter for "
                "general Unicode"
            ),
        )


class AdbBackNavigator(_AndroidAdbCommandAdapter):
    def back(self) -> NativeAttemptResult:
        return self._attempt(
            f"input -d {self.display_id.value} keyevent KEYCODE_BACK"
        )


def _require_display_point(value: object) -> AndroidDisplayPoint:
    if not isinstance(value, AndroidDisplayPoint):
        raise TypeError("Android touch point must be AndroidDisplayPoint")
    return value


__all__ = [
    "AdbBackNavigator",
    "AdbKeyChordController",
    "AdbKeyPresser",
    "AdbTextController",
    "AdbTouchController",
]

```

---

## FILE: `android\adb\adapters\query.py`

```python
from __future__ import annotations

from collections.abc import Callable

from adb._internal.client import AdbServiceClient
from adb.errors import AdbProtocolError, AdbRemoteCommandError
from adb.server import AdbServerEndpoint
from adb.transport import AdbTransportSelector
from android.adb.adapters._display_parsers import (
    parse_dumpsys_display,
    parse_surfaceflinger_display_ids,
)
from android.adb.adapters._runtime_parsers import (
    parse_android_user_state,
    parse_boot_completed,
    parse_build_info,
    parse_current_user,
    parse_keyguard_state,
    parse_launcher_component,
    parse_package_state,
    parse_power_state,
    parse_resumed_activities,
    parse_users,
)
from android.adb.adapters._window_parsers import (
    parse_display_occlusions,
    parse_windows,
)
from android.application import AndroidPackageState, AndroidResumedActivitiesSnapshot
from android.display import (
    AndroidDisplayId,
    AndroidDisplayState,
    AndroidDisplaysSnapshot,
    AndroidPhysicalDisplaysSnapshot,
)
from android.identity import AndroidComponentName, AndroidPackageName, AndroidUserId
from android.platform import AndroidBuildInfo
from android.runtime import (
    AndroidBootState,
    AndroidKeyguardState,
    AndroidPowerState,
    AndroidUsersSnapshot,
    AndroidUserState,
)
from android.window import (
    AndroidDisplayOcclusionsSnapshot,
    AndroidWindowId,
    AndroidWindowState,
    AndroidWindowsSnapshot,
)


_ClientFactory = Callable[[AdbServerEndpoint], AdbServiceClient]


def _default_client_factory(endpoint: AdbServerEndpoint) -> AdbServiceClient:
    return AdbServiceClient(endpoint)


def _run_text_query(
    endpoint: AdbServerEndpoint,
    selector: AdbTransportSelector,
    *,
    command_name: str,
    command: str,
    client_factory: _ClientFactory,
) -> str:
    result = client_factory(endpoint).shell_v2(selector, command)
    if result.exit_code != 0:
        raise AdbRemoteCommandError(
            command_name=command_name,
            exit_code=result.exit_code,
            stderr=result.stderr,
        )
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AdbProtocolError(f"{command_name} output is not valid UTF-8") from exc


class _BaseInspector:
    def __init__(
        self, *, _client_factory: _ClientFactory = _default_client_factory
    ) -> None:
        self._client_factory = _client_factory

    def _query(
        self,
        endpoint: AdbServerEndpoint,
        selector: AdbTransportSelector,
        command: str,
    ) -> str:
        return _run_text_query(
            endpoint,
            selector,
            command_name=command,
            command=command,
            client_factory=self._client_factory,
        )


class SmartSocketAdbBootStateInspector(_BaseInspector):
    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidBootState:
        return parse_boot_completed(
            self._query(endpoint, selector, "getprop sys.boot_completed")
        )


class SmartSocketAdbBuildInfoInspector(_BaseInspector):
    _COMMAND = (
        "getprop ro.build.version.sdk; getprop ro.build.version.release; "
        "getprop ro.build.fingerprint"
    )

    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidBuildInfo:
        return parse_build_info(self._query(endpoint, selector, self._COMMAND))


class SmartSocketAdbDisplaysInspector(_BaseInspector):
    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidDisplaysSnapshot:
        return parse_dumpsys_display(self._query(endpoint, selector, "dumpsys display"))


class SmartSocketAdbDisplayInspector:
    def __init__(self, displays_inspector: object | None = None) -> None:
        self.displays_inspector = displays_inspector or SmartSocketAdbDisplaysInspector()
        if not hasattr(self.displays_inspector, "inspect"):
            raise TypeError("displays_inspector must provide inspect()")

    def inspect(
        self,
        endpoint: AdbServerEndpoint,
        selector: AdbTransportSelector,
        display_id: AndroidDisplayId,
    ) -> AndroidDisplayState | None:
        if not isinstance(display_id, AndroidDisplayId):
            raise TypeError("display_id must be AndroidDisplayId")
        snapshot = self.displays_inspector.inspect(endpoint, selector)
        if not isinstance(snapshot, AndroidDisplaysSnapshot):
            raise TypeError("displays inspector must return AndroidDisplaysSnapshot")
        return next(
            (display for display in snapshot.displays if display.display_id == display_id),
            None,
        )


class SmartSocketAdbPhysicalDisplaysInspector(_BaseInspector):
    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidPhysicalDisplaysSnapshot:
        return parse_surfaceflinger_display_ids(
            self._query(endpoint, selector, "dumpsys SurfaceFlinger --display-id")
        )


class SmartSocketAdbCurrentUserInspector(_BaseInspector):
    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidUserId:
        return parse_current_user(self._query(endpoint, selector, "am get-current-user"))


class SmartSocketAdbUsersInspector(_BaseInspector):
    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidUsersSnapshot:
        return parse_users(self._query(endpoint, selector, "cmd user list -v"))


class SmartSocketAdbUserStateInspector(_BaseInspector):
    def inspect(
        self,
        endpoint: AdbServerEndpoint,
        selector: AdbTransportSelector,
        user_id: AndroidUserId,
    ) -> AndroidUserState | None:
        if not isinstance(user_id, AndroidUserId):
            raise TypeError("user_id must be AndroidUserId")
        return parse_android_user_state(
            self._query(endpoint, selector, f"am get-started-user-state {user_id.value}"),
            user_id,
        )


class SmartSocketAdbPackageStateInspector(_BaseInspector):
    def inspect(
        self,
        endpoint: AdbServerEndpoint,
        selector: AdbTransportSelector,
        user_id: AndroidUserId,
        package_name: AndroidPackageName,
    ) -> AndroidPackageState:
        if not isinstance(user_id, AndroidUserId):
            raise TypeError("user_id must be AndroidUserId")
        if not isinstance(package_name, AndroidPackageName):
            raise TypeError("package_name must be AndroidPackageName")
        return parse_package_state(
            self._query(endpoint, selector, f"dumpsys package {package_name.value}"),
            user_id,
            package_name,
        )


class SmartSocketAdbLauncherActivityInspector(_BaseInspector):
    def inspect(
        self,
        endpoint: AdbServerEndpoint,
        selector: AdbTransportSelector,
        user_id: AndroidUserId,
        package_name: AndroidPackageName,
    ) -> AndroidComponentName | None:
        if not isinstance(user_id, AndroidUserId):
            raise TypeError("user_id must be AndroidUserId")
        if not isinstance(package_name, AndroidPackageName):
            raise TypeError("package_name must be AndroidPackageName")
        command = (
            "cmd package resolve-activity --brief "
            f"--user {user_id.value} -a android.intent.action.MAIN "
            "-c android.intent.category.LAUNCHER "
            f"-p {package_name.value}"
        )
        return parse_launcher_component(
            self._query(endpoint, selector, command), package_name
        )


class SmartSocketAdbResumedActivitiesInspector(_BaseInspector):
    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidResumedActivitiesSnapshot:
        return parse_resumed_activities(
            self._query(endpoint, selector, "dumpsys activity activities")
        )


class SmartSocketAdbWindowsInspector(_BaseInspector):
    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidWindowsSnapshot:
        return parse_windows(self._query(endpoint, selector, "dumpsys window windows"))


class SmartSocketAdbWindowInspector:
    def __init__(self, windows_inspector: object | None = None) -> None:
        self.windows_inspector = windows_inspector or SmartSocketAdbWindowsInspector()
        if not hasattr(self.windows_inspector, "inspect"):
            raise TypeError("windows_inspector must provide inspect()")

    def inspect(
        self,
        endpoint: AdbServerEndpoint,
        selector: AdbTransportSelector,
        window_id: AndroidWindowId,
    ) -> AndroidWindowState | None:
        if not isinstance(window_id, AndroidWindowId):
            raise TypeError("window_id must be AndroidWindowId")
        snapshot = self.windows_inspector.inspect(endpoint, selector)
        if not isinstance(snapshot, AndroidWindowsSnapshot):
            raise TypeError("windows inspector must return AndroidWindowsSnapshot")
        return next(
            (window for window in snapshot.windows if window.window_id == window_id),
            None,
        )


class SmartSocketAdbDisplayOcclusionsInspector(_BaseInspector):
    def inspect(
        self,
        endpoint: AdbServerEndpoint,
        selector: AdbTransportSelector,
        display_id: AndroidDisplayId,
    ) -> AndroidDisplayOcclusionsSnapshot | None:
        if not isinstance(display_id, AndroidDisplayId):
            raise TypeError("display_id must be AndroidDisplayId")
        return parse_display_occlusions(
            self._query(endpoint, selector, "dumpsys window displays"), display_id
        )


class SmartSocketAdbPowerStateInspector(_BaseInspector):
    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidPowerState:
        return parse_power_state(self._query(endpoint, selector, "dumpsys power"))


class SmartSocketAdbKeyguardStateInspector(_BaseInspector):
    def inspect(
        self, endpoint: AdbServerEndpoint, selector: AdbTransportSelector
    ) -> AndroidKeyguardState:
        return parse_keyguard_state(
            self._query(endpoint, selector, "dumpsys window policy")
        )


__all__ = [
    "SmartSocketAdbBootStateInspector",
    "SmartSocketAdbBuildInfoInspector",
    "SmartSocketAdbCurrentUserInspector",
    "SmartSocketAdbDisplayInspector",
    "SmartSocketAdbDisplayOcclusionsInspector",
    "SmartSocketAdbDisplaysInspector",
    "SmartSocketAdbKeyguardStateInspector",
    "SmartSocketAdbLauncherActivityInspector",
    "SmartSocketAdbPackageStateInspector",
    "SmartSocketAdbPhysicalDisplaysInspector",
    "SmartSocketAdbPowerStateInspector",
    "SmartSocketAdbResumedActivitiesInspector",
    "SmartSocketAdbUsersInspector",
    "SmartSocketAdbUserStateInspector",
    "SmartSocketAdbWindowInspector",
    "SmartSocketAdbWindowsInspector",
    "parse_android_user_state",
    "parse_boot_completed",
    "parse_build_info",
    "parse_current_user",
    "parse_display_occlusions",
    "parse_dumpsys_display",
    "parse_keyguard_state",
    "parse_launcher_component",
    "parse_package_state",
    "parse_power_state",
    "parse_resumed_activities",
    "parse_surfaceflinger_display_ids",
    "parse_users",
    "parse_windows",
]

```

---

## FILE: `eventing\__init__.py`

```python
"""Infrastructure-neutral event delivery contracts and in-process adapter."""

from eventing.models import (
    EventDispatchError,
    EventHandlerFailure,
    EventSubscriptionToken,
)
from eventing.ports import EventBus, EventPublisher, EventSubscriber

__all__ = [
    "EventBus",
    "EventDispatchError",
    "EventHandlerFailure",
    "EventPublisher",
    "EventSubscriber",
    "EventSubscriptionToken",
]

```

---

## FILE: `eventing\models.py`

```python
from __future__ import annotations

from dataclasses import dataclass


def _normalize_required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


@dataclass(frozen=True, slots=True, order=True)
class EventSubscriptionToken:
    """Opaque identity for one event-bus subscription registration."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "value",
            _normalize_required_text(self.value, field_name="event subscription token"),
        )


@dataclass(frozen=True, slots=True)
class EventHandlerFailure:
    """One subscriber failure captured while dispatching an event."""

    event: object
    handler: object
    error: BaseException

    def __post_init__(self) -> None:
        if not callable(self.handler):
            raise TypeError("handler must be callable")
        if not isinstance(self.error, BaseException):
            raise TypeError("error must be BaseException")


class EventDispatchError(RuntimeError):
    """Raised after queued delivery completes when one or more handlers failed."""

    def __init__(self, failures: tuple[EventHandlerFailure, ...]) -> None:
        if not failures:
            raise ValueError("EventDispatchError requires at least one failure")
        if not all(isinstance(failure, EventHandlerFailure) for failure in failures):
            raise TypeError("failures must contain EventHandlerFailure values")
        self.failures = failures
        super().__init__(f"{len(failures)} event handler failure(s) occurred")


__all__ = [
    "EventDispatchError",
    "EventHandlerFailure",
    "EventSubscriptionToken",
]

```

---

## FILE: `eventing\ports.py`

```python
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypeVar, runtime_checkable

from eventing.models import EventSubscriptionToken


EventT = TypeVar("EventT")


@runtime_checkable
class EventPublisher(Protocol):
    """Publish immutable data events without owning their behavioral semantics."""

    def publish(self, event: object) -> None: ...


@runtime_checkable
class EventSubscriber(Protocol):
    """Register ordered handlers for event payload types."""

    def subscribe(
        self,
        event_type: type[EventT],
        handler: Callable[[EventT], None],
    ) -> EventSubscriptionToken: ...

    def unsubscribe(self, token: EventSubscriptionToken) -> bool: ...


class EventBus(EventPublisher, EventSubscriber, Protocol):
    """Combined event publication and subscription contract."""


__all__ = ["EventBus", "EventPublisher", "EventSubscriber"]

```

---

## FILE: `native_attempt\__init__.py`

```python
"""Terminal native-attempt evidence contracts."""

from native_attempt.domain import (
    NativeAttemptResult,
    NativeAttemptStatus,
    NativeCompletionScope,
)

__all__ = [
    "NativeAttemptResult",
    "NativeAttemptStatus",
    "NativeCompletionScope",
]

```

---

## FILE: `native_attempt\domain.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


def _normalize_non_empty_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"{field_name} must be a string, got {type(value).__name__}"
        )
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


def _normalize_optional_text(
    value: object,
    *,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    return _normalize_non_empty_text(value, field_name=field_name)


def _require_timezone_aware(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


class NativeAttemptStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class NativeCompletionScope(str, Enum):
    """Strongest native boundary known to have completed for an attempt."""

    SUBMISSION = "submission"
    SYNCHRONOUS_RETURN = "synchronous_return"
    PROCESS_EXIT = "process_exit"


@dataclass(frozen=True, slots=True)
class NativeAttemptResult:
    """Terminal evidence from one native attempt.

    Application-level effects are evaluated separately.
    """

    status: NativeAttemptStatus
    completion_scope: NativeCompletionScope | None
    backend_id: str
    started_at: datetime
    finished_at: datetime
    native_code: str | None = None
    diagnostic: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, NativeAttemptStatus):
            raise TypeError("native attempt status must be NativeAttemptStatus")
        if self.completion_scope is not None and not isinstance(
            self.completion_scope,
            NativeCompletionScope,
        ):
            raise TypeError(
                "native completion_scope must be NativeCompletionScope or None"
            )
        if (
            self.status is NativeAttemptStatus.SUCCEEDED
            and self.completion_scope is None
        ):
            raise ValueError(
                "a successful native attempt requires completion_scope"
            )
        started_at = _require_timezone_aware(
            self.started_at,
            field_name="native attempt started_at",
        )
        finished_at = _require_timezone_aware(
            self.finished_at,
            field_name="native attempt finished_at",
        )
        if finished_at < started_at:
            raise ValueError("native attempt cannot finish before it starts")
        object.__setattr__(
            self,
            "backend_id",
            _normalize_non_empty_text(
                self.backend_id,
                field_name="native attempt backend id",
            ),
        )
        object.__setattr__(
            self,
            "native_code",
            _normalize_optional_text(
                self.native_code,
                field_name="native attempt code",
            ),
        )
        object.__setattr__(
            self,
            "diagnostic",
            _normalize_optional_text(
                self.diagnostic,
                field_name="native attempt diagnostic",
            ),
        )


__all__ = [
    "NativeAttemptResult",
    "NativeAttemptStatus",
    "NativeCompletionScope",
]

```

---

## FILE: `scheduling\__init__.py`

```python
from scheduling.models import MisfirePolicy, ScheduleToken
from scheduling.ports import CalendarSchedule, TemporalScheduler

__all__ = [
    "CalendarSchedule",
    "MisfirePolicy",
    "ScheduleToken",
    "TemporalScheduler",
]

```

---

## FILE: `scheduling\models.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


def _normalize_non_empty_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"{field_name} must be a string, got {type(value).__name__}"
        )
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


class MisfirePolicy(Enum):
    """How a scheduler handles occurrences that became due while unavailable."""

    SKIP = "skip"
    FIRE_ONCE = "fire_once"
    CATCH_UP_ALL = "catch_up_all"


@dataclass(frozen=True, slots=True)
class ScheduleToken:
    """Opaque identity returned for one scheduler registration."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "value",
            _normalize_non_empty_text(
                self.value,
                field_name="schedule token",
            ),
        )


__all__ = ["MisfirePolicy", "ScheduleToken"]

```

---

## FILE: `scheduling\ports.py`

```python
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol, TypeVar, runtime_checkable

from scheduling.models import MisfirePolicy, ScheduleToken


ScheduledEventT = TypeVar("ScheduledEventT", contravariant=True)


@runtime_checkable
class CalendarSchedule(Protocol):
    """Caller-owned rule for timezone-aware recurring occurrences."""

    def next_after(self, instant: datetime) -> datetime | None:
        """Return the next timezone-aware occurrence strictly after ``instant``."""
        ...


@runtime_checkable
class TemporalScheduler(Protocol[ScheduledEventT]):
    """Register data events for non-polling temporal delivery.

    Implementations wait efficiently and deliver events through configured
    orchestration or event-queue infrastructure. They must not invoke domain
    control effects directly.
    """

    def schedule_at(
        self,
        deadline: datetime,
        event: ScheduledEventT,
        *,
        misfire_policy: MisfirePolicy = MisfirePolicy.FIRE_ONCE,
    ) -> ScheduleToken:
        """Register a one-shot event for a timezone-aware wall-clock deadline."""
        ...

    def schedule_after(
        self,
        delay: timedelta,
        event: ScheduledEventT,
    ) -> ScheduleToken:
        """Register a one-shot event after a positive monotonic duration."""
        ...

    def schedule_recurring(
        self,
        schedule: CalendarSchedule,
        event: ScheduledEventT,
        *,
        misfire_policy: MisfirePolicy = MisfirePolicy.FIRE_ONCE,
    ) -> ScheduleToken:
        """Register an event for each occurrence produced by ``schedule``."""
        ...

    def cancel(self, token: ScheduleToken) -> bool:
        """Cancel a registration, returning whether it was still active."""
        ...


__all__ = ["CalendarSchedule", "TemporalScheduler"]

```

