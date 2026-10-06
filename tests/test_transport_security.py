import http.server
import io
import socket
import threading
import time
import unittest
import urllib.error
from unittest.mock import patch

from clearparcel.datawatch import watch
from clearparcel.datawatch.dashboard import _BoundedThreadingHTTPServer


class TransportSecurityTests(unittest.TestCase):
    def test_fallback_429_preserves_stop_signal(self):
        for invoke in (lambda: watch._request('https://example.invalid/', 2),
                       lambda: watch._post_json('https://example.invalid/', {}, 2)):
            with patch.object(watch, '_urllib_request_once', side_effect=urllib.error.URLError('network')), patch.object(watch, '_curl_request', side_effect=watch.ProviderRateLimitError('60')):
                with self.assertRaises(watch.ProviderRateLimitError):
                    invoke()

    def test_optional_quality_429_stops_remaining_queries(self):
        layer = {'fields': [{'name': 'PARCEL_ID', 'type': 'esriFieldTypeString'}], 'geometryType': 'esriGeometryPolygon'}
        with patch.object(watch, '_json_request', return_value=(layer, {'status': 200})), patch.object(watch, '_arcgis_count_query', side_effect=watch.ProviderRateLimitError('60')) as query, patch.object(watch, '_arcgis_duplicate_id_summary') as duplicates:
            with self.assertRaises(watch.ProviderRateLimitError):
                watch._arcgis_layer({'url': 'https://example.invalid/0', 'parcel_quality': True}, 2)
            self.assertEqual(query.call_count, 1)
            duplicates.assert_not_called()

    def test_http_error_response_is_closed(self):
        body = io.BytesIO(b'error')
        error = urllib.error.HTTPError('https://example.invalid', 429, 'rate', {}, body)
        with patch.object(watch.urllib.request, 'build_opener') as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(watch.ProviderRateLimitError):
                watch._urllib_request_once('https://example.invalid', 1)
        self.assertTrue(body.closed)

    def test_absolute_deadline_bounds_trickling_headers_and_body(self):
        for mode in ('headers', 'body'):
            with self.subTest(mode=mode):
                stop = threading.Event()
                class Handler(http.server.BaseHTTPRequestHandler):
                    def do_GET(self):
                        try:
                            if mode == 'body':
                                self.send_response(200)
                                self.send_header('Content-Length', '30')
                                self.end_headers()
                                data = b'x' * 30
                            else:
                                data = b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n'
                            for byte in data:
                                if stop.wait(.035):
                                    break
                                self.connection.sendall(bytes([byte]))
                        except OSError:
                            pass
                    def log_message(self, *args):
                        pass
                server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                started = time.monotonic()
                try:
                    with self.assertRaises((TimeoutError, OSError, urllib.error.URLError)):
                        watch._urllib_request_once(f'http://127.0.0.1:{server.server_port}/', .2)
                    self.assertLess(time.monotonic() - started, .7)
                finally:
                    stop.set()
                    server.shutdown()
                    server.server_close()
                    thread.join()

    def test_public_deadline_releases_slot_despite_header_progress(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
            def log_message(self, *args):
                pass
        server = _BoundedThreadingHTTPServer(('127.0.0.1', 0), Handler, max_connections=1, request_timeout=.2)
        server.handle_error = lambda *args: None
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with socket.create_connection(server.server_address) as client:
                for byte in b'GET / HTTP/1.1\r\nX-Test: ':
                    try:
                        client.sendall(bytes([byte]))
                    except OSError:
                        break
                    time.sleep(.035)
                client.settimeout(.5)
                try:
                    self.assertEqual(client.recv(100), b'')
                except (ConnectionAbortedError, ConnectionResetError):
                    pass
            self.assertTrue(server._connection_slots.acquire(timeout=.5))
            server._connection_slots.release()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_redirect_carries_validated_dns_snapshot(self):
        public = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]
        with patch.object(watch.socket, 'getaddrinfo', return_value=public), patch.object(watch, '_destination_publicity', return_value=True):
            target = watch._validated_redirect('https://provider.example/a', 'https://cdn.example/b', 'https://provider.example/a')
        self.assertEqual(target.addresses, tuple(public))

    def test_pinned_redirect_rejects_proxy_before_post_dispatch(self):
        from clearparcel.datawatch.transport import PinnedURL
        target = PinnedURL('https://cdn.example/b', [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))])
        with patch('clearparcel.datawatch.transport.effective_proxy', return_value=True), patch.object(watch.urllib.request, 'build_opener') as opener:
            opener.return_value.open.side_effect = AssertionError('protected POST dispatched')
            with self.assertRaisesRegex(RuntimeError, 'proxy'):
                watch._urllib_request_once(target, 1, data=b'private-body', content_type='application/json')
            opener.assert_not_called()


    def test_pinned_urllib_get_head_post_preserve_host_tls_and_addresses(self):
        import ssl
        from unittest.mock import Mock
        from clearparcel.datawatch import transport
        addresses = ((socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443)),)
        target = transport.PinnedURL('https://cdn.example/resource', addresses)
        for method in ('GET', 'HEAD', 'POST'):
            with self.subTest(method=method):
                sock = Mock()
                sock.makefile.return_value = io.BytesIO(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}')
                context = ssl.create_default_context()
                with patch.object(transport, 'effective_proxy', return_value=False), patch.object(transport.socket, 'socket', return_value=sock), patch.object(transport, 'resolve_addresses', side_effect=AssertionError('second DNS lookup')), patch.object(context, 'wrap_socket', return_value=sock) as wrap, patch('ssl._create_default_https_context', return_value=context):
                    body, meta = watch._urllib_request_once(target, 1, data=b'{}' if method == 'POST' else None, method=method)
                sock.connect.assert_called_once_with(('93.184.216.34', 443))
                self.assertEqual(wrap.call_args.kwargs['server_hostname'], 'cdn.example')
                self.assertFalse(wrap.call_args.kwargs['do_handshake_on_connect'])
                self.assertTrue(context.check_hostname)
                self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
                sock.do_handshake.assert_called_once()
                sent = b''.join(call.args[0] for call in sock.sendall.call_args_list)
                self.assertIn(b'Host: cdn.example\r\n', sent)
                self.assertEqual(body, b'' if method == 'HEAD' else b'{}')

    def test_pinned_curl_preferred_and_fallback_use_resolve(self):
        from pathlib import Path
        from types import SimpleNamespace
        from clearparcel.datawatch import transport
        target = transport.PinnedURL('https://cdn.example/resource', ((socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443)),))
        commands = []
        def run(command, **kwargs):
            commands.append(command)
            Path(command[command.index('-o') + 1]).write_bytes(b'{}')
            Path(command[command.index('-D') + 1]).write_text('', encoding='utf-8')
            return SimpleNamespace(returncode=0, stdout=b'__CP_HTTP__200\n__CP_REDIRECT__\n', stderr=b'')
        with patch.object(watch, 'effective_proxy', return_value=False), patch.object(watch.shutil, 'which', return_value='curl'), patch.object(watch.subprocess, 'run', side_effect=run):
            watch._request(target, 1, prefer_curl=True)
            with patch.object(watch, '_urllib_request_once', side_effect=urllib.error.URLError('network')):
                watch._request(target, 1)
                watch._post_json(target, {}, 1)
        self.assertEqual(len(commands), 3)
        for command in commands:
            self.assertEqual(command[1], '--disable')
            self.assertEqual(command[command.index('--resolve') + 1], 'cdn.example:443:93.184.216.34')
            self.assertEqual(command[-1], target)
            self.assertNotIn('--insecure', command)

    def test_dns_wait_is_bounded_and_worker_retains_capacity(self):
        from clearparcel.datawatch import transport
        release = threading.Event()
        started = threading.Event()
        def resolve(*args, **kwargs):
            started.set()
            release.wait(2)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]
        slots = threading.BoundedSemaphore(1)
        try:
            with patch.object(transport, '_RESOLVER_SLOTS', slots), patch.object(transport.socket, 'getaddrinfo', side_effect=resolve):
                with transport.RequestDeadline(.05) as deadline:
                    with self.assertRaises(TimeoutError):
                        transport.resolve_addresses('example.invalid', 443, deadline)
                self.assertTrue(started.is_set())
                self.assertFalse(slots.acquire(blocking=False))
                with transport.RequestDeadline(.1) as deadline:
                    with self.assertRaisesRegex(RuntimeError, 'capacity'):
                        transport.resolve_addresses('example.invalid', 443, deadline)
                release.set()
                self.assertTrue(slots.acquire(timeout=1))
                slots.release()
        finally:
            release.set()

    def test_public_timeout_configuration_is_bounded(self):
        from clearparcel.datawatch.public_dashboard import _public_request_timeout_seconds
        import os
        for value, expected in [('bad', 10), ('-1', 2), ('90', 60), ('20', 20)]:
            with patch.dict(os.environ, {'WATCHTOWER_PUBLIC_REQUEST_TIMEOUT_SECONDS': value}):
                self.assertEqual(_public_request_timeout_seconds(), expected)

    def test_every_optional_check_preserves_429(self):
        layer = {'fields': [{'name': 'PARCEL_ID', 'type': 'esriFieldTypeString'}, {'name': 'OWNER', 'type': 'esriFieldTypeString'}], 'geometryType': 'esriGeometryPolygon'}
        optional = ('_arcgis_mngac_completeness', '_arcgis_count_query', '_field_completeness', '_arcgis_geometry_sample', '_arcgis_duplicate_id_summary')
        for failed in optional:
            with self.subTest(failed=failed):
                from contextlib import ExitStack
                with ExitStack() as stack:
                    stack.enter_context(patch.object(watch, '_json_request', return_value=(layer, {'status': 200})))
                    mocks = {}
                    for name in optional:
                        mocks[name] = stack.enter_context(patch.object(watch, name, return_value=0 if name == '_arcgis_count_query' else {}))
                    mocks[failed].side_effect = watch.ProviderRateLimitError('60')
                    with self.assertRaises(watch.ProviderRateLimitError):
                        watch._arcgis_layer({'url': 'https://example.invalid/0', 'mngac_completeness': True, 'parcel_quality': True, 'geometry_sample': True}, 2)
                    self.assertEqual(mocks[failed].call_count, 1)
                    for later in optional[optional.index(failed) + 1:]:
                        mocks[later].assert_not_called()

    def test_private_same_host_redirect_requires_explicit_allowlist(self):
        import os
        addresses = ((socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 80)),)
        with patch.object(watch, 'resolve_addresses', return_value=addresses), patch.dict(os.environ, {'WATCHTOWER_REDIRECT_ALLOW_HOSTS': ''}):
            with self.assertRaisesRegex(RuntimeError, 'redirect rejected'):
                watch._validated_redirect('http://provider.example/a', '/b', 'http://provider.example/a')
        with patch.object(watch, 'resolve_addresses', return_value=addresses), patch.dict(os.environ, {'WATCHTOWER_REDIRECT_ALLOW_HOSTS': 'provider.example'}):
            target = watch._validated_redirect('http://provider.example/a', '/b', 'http://provider.example/a')
            self.assertEqual(target.addresses, addresses)

    def test_redirect_snapshot_survives_urllib_to_curl_fallback(self):
        import os
        addresses = ((socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443)),)
        def primary(url, *args, **kwargs):
            if url == 'https://provider.example/a':
                return b'', {'status': 302, 'location': 'https://cdn.example/b'}
            raise urllib.error.URLError('network')
        with patch.dict(os.environ, {'WATCHTOWER_MAX_REDIRECTS': '1'}), patch.object(watch, 'resolve_addresses', return_value=addresses) as resolve, patch.object(watch, '_urllib_request_once', side_effect=primary), patch.object(watch, '_curl_request', return_value=(b'{}', {'status': 200})) as curl:
            watch._request('https://provider.example/a', 1)
        self.assertEqual(resolve.call_count, 1)
        self.assertEqual(curl.call_args.args[0].addresses, addresses)

    def test_public_idle_connection_and_watchdog_cleanup(self):
        from clearparcel.datawatch.transport import RequestDeadline
        with RequestDeadline(.05) as deadline:
            timer = deadline._timer
        self.assertFalse(timer.is_alive())
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
        server = _BoundedThreadingHTTPServer(('127.0.0.1', 0), Handler, max_connections=1, request_timeout=.15)
        server.handle_error = lambda *args: None
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with socket.create_connection(server.server_address) as client:
                client.settimeout(.7)
                try:
                    self.assertEqual(client.recv(1), b'')
                except (ConnectionAbortedError, ConnectionResetError):
                    pass
            self.assertTrue(server._connection_slots.acquire(timeout=.5))
            server._connection_slots.release()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_head_allows_large_content_length_without_body(self):
        from unittest.mock import Mock
        response = Mock()
        response.headers = {'Content-Length': str(256 * 1024 * 1024)}
        response.status = 200
        response.geturl.return_value = 'https://example.invalid/'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch.object(watch.urllib.request, 'build_opener') as opener:
            opener.return_value.open.return_value = response
            result = watch._head_request('https://example.invalid/', 1)
        self.assertEqual(result['status'], 200)
        response.read.assert_not_called()

    def test_deadline_interrupts_blocked_tls_handshake(self):
        import socketserver
        stop = threading.Event()
        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                stop.wait(1)
        server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        started = time.monotonic()
        try:
            with self.assertRaises((TimeoutError, OSError, urllib.error.URLError)):
                watch._urllib_request_once(f'https://127.0.0.1:{server.server_address[1]}/', .15)
            self.assertLess(time.monotonic() - started, .6)
        finally:
            stop.set()
            server.shutdown()
            server.server_close()
            thread.join()

    def test_pinned_curl_proxy_refusal_precedes_dispatch(self):
        from clearparcel.datawatch.transport import PinnedURL
        target = PinnedURL('https://cdn.example/post', ((socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443)),))
        with patch.object(watch, 'effective_proxy', return_value=True), patch.object(watch.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'proxy'):
                watch._curl_request_once(target, 1, transport='curl', data=b'private-payload')
            run.assert_not_called()

    def test_redirect_count_is_shared_with_fallback(self):
        import os
        addresses = ((socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443)),)
        def primary(url, *args, **kwargs):
            if url == 'https://provider.example/a':
                return b'', {'status': 302, 'location': 'https://cdn.example/b'}
            raise urllib.error.URLError('network')
        with patch.dict(os.environ, {'WATCHTOWER_MAX_REDIRECTS': '1'}), patch.object(watch, 'resolve_addresses', return_value=addresses), patch.object(watch, '_urllib_request_once', side_effect=primary), patch.object(watch, '_curl_request_once', return_value=(b'', {'status': 302, 'location': '/c'})) as curl:
            with self.assertRaises(RuntimeError):
                watch._request('https://provider.example/a', 1)
            self.assertEqual(curl.call_count, 1)

    def test_late_socket_registration_interrupts_without_leaking_timer(self):
        from unittest.mock import Mock
        from clearparcel.datawatch.transport import RequestDeadline
        with RequestDeadline(.02) as deadline:
            time.sleep(.04)
            sock = Mock()
            with self.assertRaises(TimeoutError):
                deadline.attach(sock)
            sock.shutdown.assert_called_once_with(socket.SHUT_RDWR)
        self.assertFalse(deadline._timer.is_alive())

    def test_http_error_resources_close_on_head_post_and_redirect(self):
        for method in ('HEAD', 'POST'):
            for status in (302, 403, 429):
                with self.subTest(method=method, status=status):
                    body = io.BytesIO(b'error')
                    error = urllib.error.HTTPError('https://example.invalid', status, 'error', {'Location': '/next'}, body)
                    with patch.object(watch.urllib.request, 'build_opener') as opener:
                        opener.return_value.open.side_effect = error
                        if status == 302:
                            _, meta = watch._urllib_request_once('https://example.invalid', 1, method=method, data=b'{}' if method == 'POST' else None)
                            self.assertEqual(meta['status'], 302)
                        else:
                            with self.assertRaises(RuntimeError):
                                watch._urllib_request_once('https://example.invalid', 1, method=method, data=b'{}' if method == 'POST' else None)
                    self.assertTrue(body.closed)

    def test_curl_timeout_diagnostic_excludes_command_and_url_secrets(self):
        import subprocess
        with patch.object(watch.shutil, 'which', return_value='curl'), patch.object(watch.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['curl', 'https://example.invalid/?token=PRIVATE'], 1)):
            with self.assertRaises(TimeoutError) as failure:
                watch._curl_request_once('https://example.invalid/?token=PRIVATE', 1, transport='curl')
        self.assertNotIn('PRIVATE', str(failure.exception))

class CurlReviewRegressionTests(unittest.TestCase):
    def _run_result(self, status, exit_code, body=b'{}'):
        from pathlib import Path
        from types import SimpleNamespace
        def run(command, **kwargs):
            Path(command[command.index('-o') + 1]).write_bytes(body)
            Path(command[command.index('-D') + 1]).write_text(f'HTTP/1.1 {status} result\nRetry-After: 60\n\n', encoding='utf-8')
            return SimpleNamespace(returncode=exit_code, stdout=f'\n__CP_HTTP__{status}\n__CP_REDIRECT__\n'.encode(), stderr=b'transfer aborted')
        return run

    def test_initial_curl_commands_disable_configuration_without_disabling_proxy(self):
        invokes = (lambda: watch._request('https://provider.example/', 1, prefer_curl=True),
                   lambda: watch._request('https://provider.example/', 1),
                   lambda: watch._post_json('https://provider.example/', {}, 1))
        for invoke in invokes:
            with self.subTest(invoke=invoke), patch.object(watch.shutil, 'which', return_value='curl'), patch.object(watch.subprocess, 'run', side_effect=self._run_result(200, 0)) as run, patch.object(watch, '_urllib_request_once', side_effect=urllib.error.URLError('network')):
                invoke()
                command = run.call_args.args[0]
                self.assertEqual(command[1], '--disable')
                self.assertNotIn('--noproxy', command)
                self.assertNotIn('--location', command)
                self.assertNotIn('--insecure', command)

    def test_observed_429_overrides_nonzero_curl_transfer_exit(self):
        invokes = (lambda: watch._request('https://provider.example/', 1, prefer_curl=True),
                   lambda: watch._request('https://provider.example/', 1),
                   lambda: watch._post_json('https://provider.example/', {}, 1))
        for code in (63, 18, 28):
            for invoke in invokes:
                with self.subTest(code=code, invoke=invoke), patch.object(watch.shutil, 'which', return_value='curl'), patch.object(watch.subprocess, 'run', side_effect=self._run_result(429, code)), patch.object(watch, '_urllib_request_once', side_effect=urllib.error.URLError('network')):
                    with self.assertRaises(watch.ProviderRateLimitError) as failure:
                        invoke()
                    self.assertEqual(failure.exception.retry_after, '60')

    def test_429_body_failure_stops_optional_checks_and_source_retries(self):
        from pathlib import Path
        import json
        layer = {'fields': [{'name': 'PARCEL_ID', 'type': 'esriFieldTypeString'}], 'geometryType': 'esriGeometryPolygon'}
        def run(command, **kwargs):
            if '/query' in command[-1]:
                return self._run_result(429, 63)(command, **kwargs)
            return self._run_result(200, 0, json.dumps(layer).encode())(command, **kwargs)
        config = {'state_file': 'unused-state.json', 'history_file': 'unused-history.jsonl', 'retries': 3,
                  'sources': [{'id': 'rate', 'name': 'Rate', 'kind': 'arcgis_layer', 'url': 'https://provider.example/0', 'prefer_curl': True, 'parcel_quality': True}]}
        with patch.object(watch, 'load_state', return_value={'sources': {}}), patch.object(watch.shutil, 'which', return_value='curl'), patch.object(watch.subprocess, 'run', side_effect=run) as requests, patch.object(watch.time, 'sleep'), patch.object(watch, '_arcgis_duplicate_id_summary') as duplicates:
            result = watch.check_sources(config, save=False)
        self.assertEqual(requests.call_count, 2)
        self.assertEqual(result['sources']['rate']['attempts'], 1)
        duplicates.assert_not_called()

    def test_partial_timeout_output_with_429_preserves_rate_limit(self):
        import subprocess
        from pathlib import Path
        def run(command, **kwargs):
            Path(command[command.index('-D') + 1]).write_text('HTTP/1.1 429 rate\nRetry-After: 60\n\n', encoding='utf-8')
            raise subprocess.TimeoutExpired(command, 1, output=b'\n__CP_HTTP__429\n')
        with patch.object(watch.shutil, 'which', return_value='curl'), patch.object(watch.subprocess, 'run', side_effect=run):
            with self.assertRaises(watch.ProviderRateLimitError) as failure:
                watch._curl_request_once('https://provider.example/', 1, transport='curl')
            self.assertEqual(failure.exception.retry_after, '60')

    def test_non429_transfer_errors_and_invalid_markers_keep_original_errors(self):
        from types import SimpleNamespace
        for code, output, error in ((63, b'__CP_HTTP__200\n', watch.ProviderResponseTooLargeError),
                                     (18, b'__CP_HTTP__200\n', RuntimeError),
                                     (0, b'', RuntimeError),
                                     (0, b'__CP_HTTP__429junk\n', RuntimeError),
                                     (0, b'__CP_HTTP__000\n', RuntimeError)):
            with self.subTest(code=code, output=output), patch.object(watch.shutil, 'which', return_value='curl'), patch.object(watch.subprocess, 'run', return_value=SimpleNamespace(returncode=code, stdout=output, stderr=b'failed')):
                with self.assertRaises(error) as failure:
                    watch._curl_request_once('https://provider.example/', 1, transport='curl')
                self.assertNotIsInstance(failure.exception, watch.ProviderRateLimitError)

    def test_only_final_status_and_final_retry_after_are_used(self):
        from pathlib import Path
        from types import SimpleNamespace
        def run(command, **kwargs):
            Path(command[command.index('-D') + 1]).write_text('HTTP/1.1 200 proxy\r\nRetry-After: wrong\r\n\r\nHTTP/1.1 429 provider\r\nRetry-After: 60\r\n\r\n', encoding='utf-8')
            return SimpleNamespace(returncode=18, stdout=b'__CP_HTTP__200\n__CP_HTTP__429\n', stderr=b'failed')
        with patch.object(watch.shutil, 'which', return_value='curl'), patch.object(watch.subprocess, 'run', side_effect=run):
            with self.assertRaises(watch.ProviderRateLimitError) as failure:
                watch._curl_request_once('https://provider.example/', 1, transport='curl')
        self.assertEqual(failure.exception.retry_after, '60')
        with patch.object(watch.shutil, 'which', return_value='curl'), patch.object(watch.subprocess, 'run', return_value=SimpleNamespace(returncode=18, stdout=b'__CP_HTTP__429\n__CP_HTTP__200\n', stderr=b'failed')):
            with self.assertRaises(RuntimeError) as failure:
                watch._curl_request_once('https://provider.example/', 1, transport='curl')
            self.assertNotIsInstance(failure.exception, watch.ProviderRateLimitError)

    def test_observed_429_survives_unavailable_retry_after_file(self):
        from pathlib import Path
        with patch.object(watch.shutil, 'which', return_value='curl'), patch.object(watch.subprocess, 'run', side_effect=self._run_result(429, 63)), patch.object(Path, 'read_text', side_effect=OSError('header file unavailable')):
            with self.assertRaises(watch.ProviderRateLimitError) as failure:
                watch._curl_request_once('https://provider.example/', 1, transport='curl')
        self.assertIsNone(failure.exception.retry_after)
