"""SSH plumbing shared by envstat, SMART status, and df, plus the combined fetch.

Everything in here is blocking (paramiko has no asyncio API) and must be run
via `hass.async_add_executor_job`, never awaited directly.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass

import paramiko

from .const import (
    BASE_STATION_NAME_COMMAND,
    CONNECT_TIMEOUT,
    DF_COMMAND,
    ENVSTAT_COMMAND,
    SMART_COMMAND,
    SSH_HOST_KEY_ALGORITHM,
    SSH_KEX_ALGORITHMS,
)
from .df import DiskUsage, parse_df
from .envstat import EnvstatReading, parse_envstat
from .smart import SmartStatus, parse_smart_status


class TimeCapsuleConnectionError(Exception):
    """Raised when the SSH connection or a remote command fails."""


class TimeCapsuleAuthError(TimeCapsuleConnectionError):
    """Raised when the SSH server rejects the username/password."""


@dataclass(frozen=True)
class TimeCapsuleData:
    """Sensor readings and optional base station name from one SSH session."""

    envstat: dict[str, EnvstatReading]
    smart: SmartStatus
    disk: DiskUsage | None
    base_station_name: str | None = None


def _connect(host: str, port: int, username: str, password: str) -> paramiko.Transport:
    """Open and authenticate an SSH transport to the Time Capsule."""
    try:
        sock = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT)
    except OSError as err:
        raise TimeCapsuleConnectionError(f"Could not reach {host}:{port}: {err}") from err

    transport = paramiko.Transport(sock)
    try:
        # This device's SSH server only offers a legacy kex algorithm and
        # signs its host key with plain ssh-rsa, neither of which Paramiko
        # offers by default any more. Ask for them explicitly, same as
        # `-o KexAlgorithms=... -o HostKeyAlgorithms=+ssh-rsa` on the CLI.
        options = transport.get_security_options()
        options.kex = SSH_KEX_ALGORITHMS
        options.key_types = tuple(dict.fromkeys((*options.key_types, SSH_HOST_KEY_ALGORITHM)))
        transport.connect(hostkey=None, username=username, password=password)
    except paramiko.AuthenticationException as err:
        transport.close()
        raise TimeCapsuleAuthError(f"Authentication to {host} failed: {err}") from err
    except (paramiko.SSHException, OSError, EOFError) as err:
        transport.close()
        raise TimeCapsuleConnectionError(f"SSH handshake with {host} failed: {err}") from err

    return transport


def _run_command(transport: paramiko.Transport, command: str) -> str:
    """Run one command over an already-authenticated transport."""
    try:
        with transport.open_session(timeout=CONNECT_TIMEOUT) as channel:
            channel.settimeout(CONNECT_TIMEOUT)
            channel.exec_command(command)

            chunks: list[bytes] = []
            while True:
                chunk = channel.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
            exit_status = channel.recv_exit_status()
    except (paramiko.SSHException, OSError, EOFError) as err:
        raise TimeCapsuleConnectionError(f"'{command}' failed: {err}") from err

    if exit_status != 0:
        raise TimeCapsuleConnectionError(f"'{command}' exited with status {exit_status}")

    return b"".join(chunks).decode("utf-8", errors="replace")


def fetch_time_capsule_data(
    host: str, port: int, username: str, password: str, *, include_name: bool = False
) -> TimeCapsuleData:
    """Fetch sensor readings and optionally the base station name over one SSH connection.

    Blocking; run in an executor.
    """
    base_station_name = None
    transport = _connect(host, port, username, password)
    try:
        envstat_output = _run_command(transport, ENVSTAT_COMMAND)
        smart_output = _run_command(transport, SMART_COMMAND)
        df_output = _run_command(transport, DF_COMMAND)
        if include_name:
            try:
                name = _run_command(transport, BASE_STATION_NAME_COMMAND).strip()
            except TimeCapsuleConnectionError:
                # The name is optional on firmware where ACP is unavailable.
                pass
            else:
                if len(name.splitlines()) == 1 and "\x00" not in name:
                    base_station_name = name
    finally:
        transport.close()

    envstat = {reading.key: reading for reading in parse_envstat(envstat_output)}
    smart = parse_smart_status(smart_output)
    disk = parse_df(df_output)
    return TimeCapsuleData(
        envstat=envstat, smart=smart, disk=disk, base_station_name=base_station_name
    )
