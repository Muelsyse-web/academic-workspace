"""Provider cancellation is exercised against a real loopback socket."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
import time

import httpx
import pytest

from workspace import providers


@contextmanager
def local_server(mode):
    entered = threading.Event()
    disconnected = threading.Event()
    failures = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                self.rfile.read(int(self.headers['Content-Length']))
                if mode == 'normal':
                    body = json.dumps({'choices': [{'message': {'content': 'Full answer'}}]}).encode()
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if mode == 'body':
                    self.send_response(200)
                    self.send_header('Content-Length', '1000')
                    self.end_headers()
                    self.wfile.write(b'{')
                    self.wfile.flush()
                entered.set()
                self.connection.settimeout(3)
                if self.connection.recv(1) == b'':
                    disconnected.set()
            except Exception as exc:
                failures.append(exc)

    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05))
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', entered, disconnected, failures
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=4)
        assert not thread.is_alive()


@pytest.mark.parametrize('mode', ['headers', 'body'])
def test_cancellation_closes_waiting_http_request_promptly(mode):
    assert callable(getattr(providers.LocalProvider, 'chat_cancellable', None))
    cancel = threading.Event()
    outcome = []
    with local_server(mode) as (url, entered, disconnected, failures):
        provider = providers.LocalProvider(base_url=url, model='local', timeout=30)

        def ask():
            try:
                outcome.append(provider.chat_cancellable([{'role': 'user', 'content': 'hello'}], cancel))
            except Exception as exc:
                outcome.append(exc)

        worker = threading.Thread(target=ask)
        worker.start()
        try:
            assert entered.wait(2), 'Provider never reached the local server'
            start = time.monotonic()
            cancel.set()
            worker.join(timeout=1)
            assert not worker.is_alive(), 'Cancellation left the HTTP worker running'
            assert time.monotonic() - start < 1
            assert disconnected.wait(1), 'Cancellation did not close the HTTP socket'
        finally:
            cancel.set()
            worker.join(timeout=4)
        assert not failures
    assert len(outcome) == 1
    assert isinstance(outcome[0], providers.ProviderCancelled)


def test_cancellable_chat_returns_complete_answer():
    assert callable(getattr(providers.LocalProvider, 'chat_cancellable', None))
    with local_server('normal') as (url, _, _, failures):
        provider = providers.LocalProvider(base_url=url, model='local')
        assert provider.chat_cancellable([{'role': 'user', 'content': 'hello'}], threading.Event()) == 'Full answer'
        assert not failures


def test_cancellable_chat_stops_reading_at_response_limit():
    assert callable(getattr(providers.LocalProvider, 'chat_cancellable', None))

    class LargeStream(httpx.AsyncByteStream):
        chunks_read = 0
        closed = False

        async def __aiter__(self):
            for _ in range(12):
                self.chunks_read += 1
                yield b'x' * (1024 * 1024)

        async def aclose(self):
            self.closed = True

    stream = LargeStream()
    provider = providers.LocalProvider(model='local', async_transport=httpx.MockTransport(
        lambda request: httpx.Response(200, stream=stream)))
    with pytest.raises(providers.ProviderError, match='8 MiB'):
        provider.chat_cancellable([], threading.Event())
    assert stream.chunks_read == 9
    assert stream.closed


def test_already_cancelled_request_does_not_connect():
    assert callable(getattr(providers.LocalProvider, 'chat_cancellable', None))
    cancel = threading.Event()
    cancel.set()

    def unexpected_request(request):
        pytest.fail('A cancelled request opened a connection')

    provider = providers.LocalProvider(model='local', async_transport=httpx.MockTransport(unexpected_request))
    with pytest.raises(providers.ProviderCancelled):
        provider.chat_cancellable([], cancel)


@pytest.mark.parametrize('failure, message', [
    ('redirect', 'redirects are not allowed'),
    ('status', 'HTTP 503'),
    ('json', 'invalid JSON'),
    ('timeout', 'timed out'),
    ('connection', 'Cannot connect'),
    ('empty', 'no usable answer'),
])
def test_cancellable_chat_preserves_safe_provider_errors(failure, message):
    seen = []

    def handle(request):
        seen.append(request)
        if failure == 'redirect':
            return httpx.Response(302, headers={'location': 'https://example.com/collect'})
        if failure == 'status':
            return httpx.Response(503, content='private server error')
        if failure == 'json':
            return httpx.Response(200, content='private malformed response')
        if failure == 'timeout':
            raise httpx.ReadTimeout('private transport details')
        if failure == 'connection':
            raise httpx.ConnectError('private transport details')
        return httpx.Response(200, json={'choices': []})

    provider = providers.LocalProvider(model='local', async_transport=httpx.MockTransport(handle))
    with pytest.raises(providers.ProviderError, match=message) as exc:
        provider.chat_cancellable([], threading.Event())
    assert 'private' not in str(exc.value)
    assert len(seen) == 1
    assert seen[0].url.host == '127.0.0.1'
