from web_server import _preview_event_summary


def test_preview_event_summary_includes_key_fields():
    summary = _preview_event_summary({
        "output": 1,
        "event": "first_frame",
        "channel": "6c-df-fb-01-5e-80-00-01/v1",
        "codec": "H.264",
        "width": 1920,
        "height": 1080,
        "bytes": 4096,
        "frames": 1,
    })

    assert "output=1" in summary
    assert "event=first_frame" in summary
    assert "channel=6c-df-fb-01-5e-80-00-01/v1" in summary
    assert "codec=H.264" in summary
    assert "frames=1" in summary
