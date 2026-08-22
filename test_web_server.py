from web_server import (
    _check_ws_handshake,
    _check_ws_handshakes,
    _preview_event_needs_port_check,
    _preview_event_summary,
)


def test_preview_event_summary_includes_key_fields():
    summary = _preview_event_summary({
        "output": 1,
        "event": "first_frame",
        "ws_url": "ws://192.168.130.101:8003",
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

    def fake_check(ws_url, origin=""):
        calls.append((ws_url, origin))
        return f"origin={origin or '-'}"

    monkeypatch.setattr("web_server._check_ws_handshake", fake_check)

    results = _check_ws_handshakes("ws://example.test:8003", origin="http://127.0.0.1:8080")

    assert results == ["origin=http://127.0.0.1:8080", "origin=-"]
    assert calls == [
        ("ws://example.test:8003", "http://127.0.0.1:8080"),
        ("ws://example.test:8003", ""),
    ]
