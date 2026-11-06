"""Scan quarantined attachments through a trusted loopback ClamAV sidecar."""

from __future__ import annotations

import datetime as dt
import re
import socket
import struct
import time

_REPLY_LIMIT = 2048


class ClamdScanner:
    def __init__(self, port=3310, *, timeout=10.0, clock=lambda: dt.datetime.now(dt.UTC)):
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("invalid clamd port")
        self._port = port
        self._timeout = timeout
        self._clock = clock

    def _exchange(self, deadline, command, data=None):
        def remaining():
            seconds = deadline - time.monotonic()
            if seconds <= 0:
                raise TimeoutError("clamd scan deadline exceeded")
            return seconds

        with socket.create_connection(("127.0.0.1", self._port), timeout=remaining()) as connection:
            connection.settimeout(remaining())
            connection.sendall(command)
            if data is not None:
                for offset in range(0, len(data), 65_536):
                    chunk = data[offset:offset + 65_536]
                    connection.settimeout(remaining())
                    connection.sendall(struct.pack("!I", len(chunk)) + chunk)
                connection.settimeout(remaining())
                connection.sendall(b"\x00" * 4)
            response = bytearray()
            while len(response) < _REPLY_LIMIT:
                connection.settimeout(remaining())
                chunk = connection.recv(_REPLY_LIMIT - len(response))
                if not chunk:
                    break
                response.extend(chunk)
                if b"\0" in response:
                    line, _, suffix = response.partition(b"\0")
                    if not suffix:
                        return bytes(line)
                    break
        raise OSError("clamd returned an invalid response")

    def __call__(self, data):
        deadline = time.monotonic() + self._timeout
        version = self._exchange(deadline, b"zVERSION\0")
        match = re.fullmatch(rb"ClamAV [^/\s]+/[0-9]+/(.+)", version)
        if match is None:
            raise OSError("clamd signature database is unavailable")
        try:
            database = dt.datetime.strptime(match[1].decode("ascii"), "%a %b %d %H:%M:%S %Y").replace(tzinfo=dt.UTC)
        except ValueError:
            raise OSError("clamd signature timestamp is invalid") from None
        age = self._clock() - database
        if not -dt.timedelta(minutes=5) <= age <= dt.timedelta(hours=72):
            raise OSError("clamd signature database is outside its freshness window")
        verdict = self._exchange(deadline, b"zINSTREAM\0", data)
        if verdict == b"stream: OK":
            return True
        if re.fullmatch(rb"stream: [^\r\n\x00]+ FOUND", verdict):
            return False
        raise OSError("clamd did not return an authoritative verdict")
