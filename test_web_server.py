import pytest

from web_server import (
    UpstreamWebSocket,
    _call_preview_control_ws,
    _check_ws_handshake,
    _check_ws_handshakes,
    _parse_http_headers,
    _parse_preview_control_payload,
    _preview_upstream_handshake_headers,
    _output_from_payload,
    _preview_output_from_query,
    _preview_event_needs_port_check,
    _preview_event_summary,
    _protocol_requested_by_client,
    _preview_stream_for_output,
    _websocket_accept_key,
)


def test_preview_event_summary_includes_key_fields():
    summary = _preview_event_summary({
        "output": 1,
        "event": "first_frame",
        "control_ws_url": (
            "ws://192.168.130.101:8001/?display_wall=%E6%98%BE%E7%A4%BA%E5%99%A81"
        ),
        "ws_url": "ws://192.168.130.101:12997/play",
        "connect_url": "ws://127.0.0.1:8080/api/preview/ws?output=1",
        "channel": "6c-df-fb-01-5e-80-00-01/v1",
        "codec": "H.264",
        "width": 1920,
        "height": 1080,
        "bytes": 4096,
        "frames": 1,
    })

    assert "output=1" in summary
    assert "event=first_frame" in summary
    assert "control_ws_url=ws://192.168.130.101:8001/?display_wall=" in summary
    assert "ws_url=ws://192.168.130.101:12997/play" in summary
    assert "connect_url=ws://127.0.0.1:8080/api/preview/ws?output=1" in summary
    assert "channel=6c-df-fb-01-5e-80-00-01/v1" in summary
    assert "codec=H.264" in summary
    assert "frames=1" in summary


def test_preview_event_needs_port_check_for_zero_frame_connection_failure():
    assert _preview_event_needs_port_check({
        "event": "candidate_failed",
        "reason": "连接超时",
        "frames": 0,
    })

    assert not _preview_event_needs_port_check({
        "event": "candidate_failed",
        "reason": "H.264 解码失败",
        "frames": 1,
    })


def test_check_ws_handshake_reports_invalid_url():
    assert _check_ws_handshake("").endswith("status=invalid_url")


def test_check_ws_handshakes_checks_with_and_without_origin(monkeypatch):
    calls = []

    def fake_check(ws_url, origin="", protocol=""):
        calls.append((ws_url, origin, protocol))
        return f"origin={origin or '-'}, protocol={protocol or '-'}"

    monkeypatch.setattr("web_server._check_ws_handshake", fake_check)

    results = _check_ws_handshakes(
        "ws://example.test:8003",
        origin="http://127.0.0.1:8080",
        protocol="fake-token",
    )

    assert results == [
        "origin=http://127.0.0.1:8080, protocol=fake-token",
        "origin=http://192.168.130.101:8001, protocol=fake-token",
        "origin=-, protocol=fake-token",
    ]
    assert calls == [
        ("ws://example.test:8003", "http://127.0.0.1:8080", "fake-token"),
        ("ws://example.test:8003", "http://192.168.130.101:8001", "fake-token"),
        ("ws://example.test:8003", "", "fake-token"),
    ]


def test_preview_output_from_query():
    assert _preview_output_from_query("output=2") == 2
    assert _preview_output_from_query("output=bad") == 0


def test_output_from_payload():
    assert _output_from_payload({"output": "2"}) == 2
    with pytest.raises(Exception):
        _output_from_payload({"output": "bad"})


def test_preview_stream_for_output_reads_current_assignment():
    state = {
        "screens": [
            {
                "index": 1,
                "assignment": {
                    "stream": {
                        "control_ws_url": "ws://example.test:8003/?display_wall=one",
                        "ws_url": "ws://example.test:12997/play",
                    }
                },
            },
            {"index": 2, "assignment": None},
        ]
    }

    assert _preview_stream_for_output(state, 1) == {
        "control_ws_url": "ws://example.test:8003/?display_wall=one",
        "ws_url": "ws://example.test:12997/play",
    }
    assert _preview_stream_for_output(state, 2) == {}


def test_parse_preview_control_payload_accepts_platform_success_shape():
    assert _parse_preview_control_payload(
        b'{"result":"success","result_val":0}'
    ) == {"result": "success", "result_val": 0}


def test_parse_preview_control_payload_rejects_non_json():
    with pytest.raises(OSError, match="non-json"):
        _parse_preview_control_payload(b"not json")


def test_call_preview_control_ws_ignores_pulse_before_success(monkeypatch):
    success = b'{"result":"success","result_val":0}'
    sock = FakeSocket([
        _server_text_frame(b"pulse"),
        _server_text_frame(success),
    ])

    def fake_open(*args, **kwargs):
        return UpstreamWebSocket(sock=sock, headers={})

    monkeypatch.setattr("web_server._open_upstream_websocket", fake_open)

    result = _call_preview_control_ws(
        "ws://example.test:8001/?display_wall=one",
        origin="http://example.test:8001",
        protocol="fake-token",
    )

    assert result == {"result": "success", "result_val": 0}


def test_call_preview_control_ws_reads_success_json_frame(monkeypatch):
    payload = b'{"result":"success","result_val":0}'
    frame = _server_text_frame(payload)
    sock = FakeSocket([frame])
    calls = []

    def fake_open(ws_url, origin, protocol, extensions="", user_agent=""):
        calls.append({
            "ws_url": ws_url,
            "origin": origin,
            "protocol": protocol,
            "extensions": extensions,
            "user_agent": user_agent,
        })
        return UpstreamWebSocket(sock=sock, headers={})

    monkeypatch.setattr("web_server._open_upstream_websocket", fake_open)

    result = _call_preview_control_ws(
        "ws://example.test:8003/?display_wall=one",
        origin="http://example.test:8001",
        protocol="fake-token",
        user_agent="FakeBrowser",
    )

    assert result == {"result": "success", "result_val": 0}
    assert calls == [{
        "ws_url": "ws://example.test:8003/?display_wall=one",
        "origin": "http://example.test:8001",
        "protocol": "fake-token",
        "extensions": "permessage-deflate; client_max_window_bits",
        "user_agent": "FakeBrowser",
    }]
    assert sock.timeout is not None
    assert sock.closed


def test_call_preview_control_ws_rejects_failed_result(monkeypatch):
    payload = b'{"result":"failed","result_val":8}'
    frame = _server_text_frame(payload)

    def fake_open(*args, **kwargs):
        return UpstreamWebSocket(sock=FakeSocket([frame]), headers={})

    monkeypatch.setattr("web_server._open_upstream_websocket", fake_open)

    with pytest.raises(OSError, match="result=failed"):
        _call_preview_control_ws(
            "ws://example.test:8003/?display_wall=one",
            origin="http://example.test:8001",
            protocol="fake-token",
        )


def test_call_preview_control_ws_continues_when_handshake_stays_idle(monkeypatch):
    sock = TimeoutSocket()

    def fake_open(*args, **kwargs):
        return UpstreamWebSocket(sock=sock, headers={}, handshake_elapsed="0.01")

    monkeypatch.setattr("web_server._open_upstream_websocket", fake_open)

    result = _call_preview_control_ws(
        "ws://example.test:8001/?display_wall=one",
        origin="http://example.test:8001",
        protocol="fake-token",
    )

    assert result == {
        "result": "success",
        "result_val": 0,
        "control_ws_mode": "handshake_only",
        "reason": "idle_timeout_after_pulse",
    }
    assert sock.sent
    assert sock.sent[0][0] == 0x81
    assert sock.sent[0][1] & 0x80
    assert sock.sent[0][1] & 0x7F == len(b"pulse")
    assert sock.timeout is not None
    assert sock.closed


def test_websocket_accept_key_matches_rfc_example():
    assert _websocket_accept_key("dGhlIHNhbXBsZSBub25jZQ==") == (
        "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
    )


def test_preview_upstream_handshake_matches_platform_headers():
    headers = _preview_upstream_handshake_headers(
        "/?display_wall=%E6%98%BE%E7%A4%BA%E5%99%A81",
        "192.168.130.101",
        8003,
        "fake-key",
        origin="http://192.168.130.101:8001",
        protocol="fake-token",
        extensions="permessage-deflate; client_max_window_bits",
        user_agent="FakeBrowser",
    )

    assert headers[0] == (
        "GET /?display_wall=%E6%98%BE%E7%A4%BA%E5%99%A81 HTTP/1.1"
    )
    assert "Accept-Encoding: gzip, deflate" in headers
    assert "Connection: Upgrade" in headers
    assert "Host: 192.168.130.101:8003" in headers
    assert "Origin: http://192.168.130.101:8001" in headers
    assert "Sec-WebSocket-Extensions: permessage-deflate; client_max_window_bits" in headers
    assert "Sec-WebSocket-Key: fake-key" in headers
    assert "Sec-WebSocket-Protocol: fake-token" in headers
    assert "Sec-WebSocket-Version: 13" in headers
    assert "Upgrade: websocket" in headers
    assert "User-Agent: FakeBrowser" in headers


def test_preview_upstream_stream_handshake_omits_empty_protocol():
    headers = _preview_upstream_handshake_headers(
        "/play",
        "192.168.130.101",
        12997,
        "fake-key",
        origin="http://192.168.130.101:8001",
        protocol="",
        extensions="permessage-deflate; client_max_window_bits",
        user_agent="FakeBrowser",
    )

    assert headers[0] == "GET /play HTTP/1.1"
    assert "Host: 192.168.130.101:12997" in headers
    assert "Origin: http://192.168.130.101:8001" in headers
    assert "Sec-WebSocket-Extensions: permessage-deflate; client_max_window_bits" in headers
    assert not any(header.startswith("Sec-WebSocket-Protocol:") for header in headers)


def test_preview_upstream_handshake_omits_empty_origin():
    headers = _preview_upstream_handshake_headers(
        "/",
        "192.168.130.101",
        8003,
        "fake-key",
        origin="",
        protocol="fake-token",
    )

    assert not any(header.startswith("Origin:") for header in headers)


def test_parse_http_headers_lowercases_names():
    headers = _parse_http_headers(
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Sec-WebSocket-Protocol: fake-token\r\n"
        "Sec-WebSocket-Extensions: permessage-deflate\r\n"
        "\r\n"
    )

    assert headers["sec-websocket-protocol"] == "fake-token"
    assert headers["sec-websocket-extensions"] == "permessage-deflate"


def test_protocol_requested_by_client():
    assert _protocol_requested_by_client("token-a, token-b", "token-b")
    assert not _protocol_requested_by_client("token-a", "token-b")


class FakeSocket:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.timeout = None
        self.closed = False
        self.sent = []

    def settimeout(self, value):
        self.timeout = value

    def recv(self, size):
        if not self.chunks:
            return b""
        chunk = self.chunks.pop(0)
        if len(chunk) <= size:
            return chunk
        self.chunks.insert(0, chunk[size:])
        return chunk[:size]

    def sendall(self, data):
        self.sent.append(data)

    def close(self):
        self.closed = True


class TimeoutSocket(FakeSocket):
    def __init__(self):
        super().__init__([])

    def recv(self, size):
        raise TimeoutError("idle websocket")


def _server_text_frame(payload):
    return b"\x81" + bytes([len(payload)]) + payload
