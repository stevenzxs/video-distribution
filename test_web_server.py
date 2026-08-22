from web_server import (
    _check_ws_handshake,
    _check_ws_handshakes,
    _preview_output_from_query,
    _preview_event_needs_port_check,
    _preview_event_summary,
    _preview_stream_for_output,
    _websocket_accept_key,
)


def test_preview_event_summary_includes_key_fields():
    summary = _preview_event_summary({
        "output": 1,
        "event": "first_frame",
        "ws_url": "ws://192.168.130.101:8003",
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
    assert "ws_url=ws://192.168.130.101:8003" in summary
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


def test_preview_stream_for_output_reads_current_assignment():
    state = {
        "screens": [
            {"index": 1, "assignment": {"stream": {"ws_url": "ws://example.test:8003"}}},
            {"index": 2, "assignment": None},
        ]
    }

    assert _preview_stream_for_output(state, 1) == {"ws_url": "ws://example.test:8003"}
    assert _preview_stream_for_output(state, 2) == {}


def test_websocket_accept_key_matches_rfc_example():
    assert _websocket_accept_key("dGhlIHNhbXBsZSBub25jZQ==") == (
        "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
    )
