"""Request-scoped address binding and deadlines for the standard HTTP transports."""
from __future__ import annotations

import http.client
import socket
import threading
import time
import urllib.parse
import urllib.request

_RESOLVER_SLOTS = threading.BoundedSemaphore(8)


class RequestDeadline:
    """Interrupt socket I/O at an absolute deadline, including trickling responses."""
    def __init__(self, seconds: float):
        self.end = time.monotonic() + max(.001, float(seconds))
        self._lock = threading.Lock()
        self._socket = None
        self._expired = False
        self._timer = threading.Timer(max(.001, float(seconds)), self._expire)
        self._timer.daemon = True
        self._timer.start()

    def remaining(self) -> float:
        remaining = self.end - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('provider request wall-clock deadline exceeded')
        return remaining

    @staticmethod
    def _interrupt(sock):
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _expire(self):
        with self._lock:
            self._expired = True
            self._interrupt(self._socket)

    def attach(self, sock):
        with self._lock:
            if self._expired or time.monotonic() >= self.end:
                self._interrupt(sock)
                raise TimeoutError('provider request wall-clock deadline exceeded')
            self._socket = sock
        sock.settimeout(self.remaining())

    def close(self):
        self._timer.cancel()
        self._timer.join()
        with self._lock:
            self._socket = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def resolve_addresses(host: str, port: int, deadline: RequestDeadline):
    """Bound caller wait; uninterruptible native DNS retains its bounded slot."""
    slots = _RESOLVER_SLOTS
    if not slots.acquire(blocking=False):
        raise RuntimeError('provider DNS resolver capacity exhausted')
    result = []
    done = threading.Event()
    def resolve():
        try:
            result.append(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
        except Exception as exc:
            result.append(exc)
        finally:
            slots.release()
            done.set()
    worker = threading.Thread(target=resolve, daemon=True, name='watchtower-dns')
    try:
        worker.start()
    except Exception:
        slots.release()
        raise
    if not done.wait(deadline.remaining()):
        raise TimeoutError('provider DNS resolution deadline exceeded')
    deadline.remaining()
    if isinstance(result[0], Exception):
        raise result[0]
    if not result[0]:
        raise RuntimeError('provider DNS returned no addresses')
    return tuple(result[0])


class PinnedURL(str):
    def __new__(cls, url: str, addresses):
        value = super().__new__(cls, url)
        value.addresses = tuple(addresses)
        return value


def effective_proxy(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    proxies = urllib.request.getproxies()
    return bool(proxies.get(parsed.scheme) or proxies.get('all')) and not urllib.request.proxy_bypass(parsed.hostname or '')


def guarded_opener(url: str, deadline: RequestDeadline, redirect_handler):
    pinned = getattr(url, 'addresses', None)
    if pinned and effective_proxy(url):
        raise RuntimeError('redirect rejected: configured proxy cannot enforce validated destination')

    def connect(address, timeout=None, source_address=None):
        host, port = address
        addresses = pinned or resolve_addresses(host, port, deadline)
        last_error = None
        for family, kind, protocol, _, sockaddr in addresses:
            sock = socket.socket(family, kind, protocol)
            try:
                deadline.attach(sock)
                if source_address:
                    sock.bind(source_address)
                sock.connect(sockaddr)
                deadline.remaining()
                return sock
            except OSError as exc:
                last_error = exc
                sock.close()
                deadline.remaining()
        raise last_error or OSError('no usable provider destination')

    class HTTPConnection(http.client.HTTPConnection):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._create_connection = connect

    class HTTPSConnection(http.client.HTTPSConnection):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._create_connection = connect

        def connect(self):
            http.client.HTTPConnection.connect(self)
            server_hostname = self._tunnel_host or self.host
            self.sock = self._context.wrap_socket(self.sock, server_hostname=server_hostname, do_handshake_on_connect=False)
            deadline.attach(self.sock)
            self.sock.do_handshake()
            deadline.remaining()

    class HTTPHandler(urllib.request.HTTPHandler):
        def http_open(self, req):
            return self.do_open(HTTPConnection, req)

    class HTTPSHandler(urllib.request.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(HTTPSConnection, req, context=self._context)

    handlers = [redirect_handler, HTTPHandler(), HTTPSHandler()]
    if pinned:
        handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)
