import pytest

from api_client import APIClient, is_success_response
from config import MATRIX_CONFIG
from matrix_service import (
    MatrixError,
    MatrixRuntimeState,
    MatrixScheduler,
    build_stream_descriptor,
    parse_matrix_command,
)


class CapturingAPIClient(APIClient):
    def __init__(self):
        super().__init__(base_url="http://example.invalid")
        self.last_endpoint = None
        self.last_data = None

    def _make_request(self, endpoint, data=None, use_token=True):
        self.last_endpoint = endpoint
        self.last_data = data
        return {"result": "success", "result_val": 0}


class FakeAPIClient:
    def __init__(
        self,
        bound_decoders=None,
        display_walls=None,
        bind_result=None,
        windows=None,
        record_opened_window=True,
    ):
        self.opened_windows = []
        self.closed_windows = []
        self.created_walls = []
        self.bind_calls = []
        self.logged_out = False
        self.login_count = 0
        self.token = None
        self.next_handle = 1001
        self.bind_result = bind_result or {"result": "success", "result_val": 0}
        self.record_opened_window = record_opened_window
        self.windows = list(windows or [])
        self.display_walls = display_walls
        if self.display_walls is None:
            self.display_walls = [
                {
                    "index": 1,
                    "name": "显示器1",
                    "row": 1,
                    "column": 1,
                    "resolution_x": 1920,
                    "resolution_y": 1080,
                },
                {
                    "index": 2,
                    "name": "显示器2",
                    "row": 1,
                    "column": 1,
                    "resolution_x": 1920,
                    "resolution_y": 1080,
                },
                {
                    "index": 3,
                    "name": "显示器3",
                    "row": 1,
                    "column": 1,
                    "resolution_x": 1920,
                    "resolution_y": 1080,
                },
            ]
        self.encoder_info_calls = []
        self.decoder_list_calls = []
        self.display_wall_info_calls = []
        self.display_wall_decoder_list_calls = []
        self.open_display_wall_calls = []
        self.get_display_wall_wnds_calls = []
        if bound_decoders is None:
            bound_decoders = [
                {
                    "name": "显示器1",
                    "ip": "192.168.130.61",
                    "mac": "00-40-01-2b-06-27",
                    "bind_x": 0,
                    "bind_y": 0,
                },
                {
                    "name": "显示器2",
                    "ip": "192.168.130.62",
                    "mac": "00-40-01-2b-06-28",
                    "bind_x": 1,
                    "bind_y": 0,
                },
                {
                    "name": "终端摄像",
                    "ip": "192.168.130.63",
                    "mac": "00-40-01-2b-06-29",
                    "bind_x": 2,
                    "bind_y": 0,
                },
            ]
        self.bound_decoders = list(bound_decoders)

    def login(self, username, password):
        self.login_count += 1
        success = username == "admin" and bool(password)
        if success:
            self.token = "fake-token"
        return success

    def logout(self):
        self.logged_out = True
        self.token = None
        return {"result": "success", "result_val": 0}

    def get_encoder_list(self, page_index=1, page_size=100):
        return {
            "result": "success",
            "result_val": 0,
            "encoders": [
                {"name": "视频会议终端", "ip": "192.168.130.51", "mac": "00-40-01-2b-05-27"},
                {"name": "摄像头1", "ip": "192.168.130.52", "mac": "00-40-01-2b-05-28"},
                {"name": "摄像头2", "ip": "192.168.130.53", "mac": "00-40-01-2b-05-29"},
            ],
        }

    def get_encoder_info(self, mac):
        self.encoder_info_calls.append(mac)
        return {
            "result": "success",
            "result_val": 0,
            "mac": mac,
            "type": 23,
            "status": 1,
            "hdmi_status": 1,
            "video_stream": [
                {
                    "identity": "main",
                    "codec_type": "H264",
                    "framerate": 30,
                    "bitrate": 4096,
                    "image_quality": 3,
                }
            ],
        }

    def get_decoder_list(self, page_index=1, page_size=100):
        self.decoder_list_calls.append({
            "page_index": page_index,
            "page_size": page_size,
        })
        return {
            "result": "success",
            "result_val": 0,
            "decoders": [
                {"name": "显示器1", "ip": "192.168.130.61", "mac": "00-40-01-2b-06-27"},
                {"name": "显示器2", "ip": "192.168.130.62", "mac": "00-40-01-2b-06-28"},
                {"name": "终端摄像", "ip": "192.168.130.63", "mac": "00-40-01-2b-06-29"},
            ],
        }

    def get_display_wall_list(self, page_index=1, page_size=20):
        return {
            "result": "success",
            "result_val": 0,
            "display_walls": self.display_walls,
        }

    def get_display_wall_info(self, name):
        self.display_wall_info_calls.append(name)
        if not any(item.get("name") == name for item in self.display_walls):
            return {"result": "resource not exist", "result_val": 13}
        return {
            "result": "success",
            "result_val": 0,
            "name": name,
            "row": 1,
            "column": 3,
        }

    def create_display_wall(self, name, row, column, resolution_x, resolution_y,
                            factory="", com="", fusion_band=0, lcd_frame=0,
                            border_clipping=0, hfront=0, hback=0,
                            vfront=0, vback=0, hwidth=0, vwidth=0,
                            clock=0, create_time=None):
        wall = {
            "name": name,
            "row": row,
            "column": column,
            "resolution_x": resolution_x,
            "resolution_y": resolution_y,
            "create_time": create_time,
            "factory": factory,
            "com": com,
            "fusion_band": fusion_band,
            "lcd_frame": lcd_frame,
            "border_clipping": border_clipping,
            "hfront": hfront,
            "hback": hback,
            "vfront": vfront,
            "vback": vback,
            "hwidth": hwidth,
            "vwidth": vwidth,
            "clock": clock,
        }
        self.display_walls.append(wall)
        self.created_walls.append(wall)
        return {"result": "success", "result_val": 0}

    def get_display_wall_decoder_list(self, display_wall):
        self.display_wall_decoder_list_calls.append(display_wall)
        return {
            "result": "success",
            "result_val": 0,
            "decoders": self.bound_decoders,
        }

    def bind_decoder(self, display_wall, mac, bind_x, bind_y):
        payload = {
            "display_wall": display_wall,
            "mac": mac,
            "bind_x": bind_x,
            "bind_y": bind_y,
        }
        self.bind_calls.append(payload)
        if not is_success_response(self.bind_result):
            return self.bind_result

        for decoder in self.get_decoder_list()["decoders"]:
            if decoder["mac"] == mac:
                self.bound_decoders.append({
                    **decoder,
                    "bind_x": bind_x,
                    "bind_y": bind_y,
                })
                break
        return self.bind_result

    def open_display_wall(self, name):
        self.open_display_wall_calls.append(name)
        return {"result": "success", "result_val": 0, "name": name}

    def get_display_wall_wnds(self, display_wall):
        self.get_display_wall_wnds_calls.append(display_wall)
        return {
            "result": "success",
            "result_val": 0,
            "wnds": list(self.windows),
        }

    def open_wnd(self, display_wall, src_mac, pos_x, pos_y, width, height):
        handle = self.next_handle
        self.next_handle += 1
        payload = {
            "display_wall": display_wall,
            "src_mac": src_mac,
            "pos_x": pos_x,
            "pos_y": pos_y,
            "width": width,
            "height": height,
        }
        self.opened_windows.append(payload)
        if self.record_opened_window:
            self.windows.append({
                "src_mac": src_mac,
                "src_name": "",
                "src_status": 1,
                "handle": handle,
                "x": pos_x,
                "y": pos_y,
                "width": width,
                "height": height,
                "layer": len(self.windows) + 1,
            })
        return {"result": "success", "result_val": 0, "handle": handle}

    def close_wnd(self, display_wall, handle):
        self.closed_windows.append(handle)
        self.windows = [
            window for window in self.windows
            if window.get("handle") != handle
        ]
        return {"result": "success", "result_val": 0}


def test_api_success_uses_platform_success_shape():
    assert is_success_response({"result": "success", "result_val": 1})
    assert is_success_response({"result": "failed", "result_val": 0})
    assert not is_success_response({"result": "0", "result_val": "success"})
    assert not is_success_response({"result": 0, "result_val": "success"})


def test_create_display_wall_payload_matches_platform_shape():
    client = CapturingAPIClient()

    client.create_display_wall(
        name="VW3",
        row=1,
        column=3,
        resolution_x=1920,
        resolution_y=1080,
        create_time=1787370000,
    )

    assert client.last_endpoint == "/mvapi/v1/displaywall/CreateDisplayWall"
    assert client.last_data == {
        "name": "VW3",
        "row": 1,
        "column": 3,
        "resolution_x": 1920,
        "resolution_y": 1080,
        "create_time": "1787370000",
        "factory": "",
        "com": -1,
        "fusion_band": {"width_x": 0, "width_y": 0},
        "lcd_frame": {
            "dot_pitch": 0.0,
            "width_up": 0.0,
            "width_down": 0.0,
            "width_left": 0.0,
            "width_right": 0.0,
        },
        "border_clipping": {"up": 0, "down": 0, "left": 0, "right": 0},
        "hfront": 0,
        "hback": 0,
        "vfront": 0,
        "vback": 0,
        "hwidth": 0,
        "vwidth": 0,
        "clock": 0,
    }


def test_display_wall_decoder_list_uses_name_field():
    client = CapturingAPIClient()

    client.get_display_wall_decoder_list("VW3")

    assert client.last_endpoint == "/mvapi/v1/displaywall/GetDispWallDecoderList"
    assert client.last_data == {"name": "VW3"}


def test_available_decoder_payload_matches_platform_shape():
    client = CapturingAPIClient()

    client.get_available_decoders("VW3")

    assert client.last_endpoint == "/mvapi/v1/displaywall/GetAvailableDecoder"
    assert client.last_data == {
        "start": 0,
        "size": 100,
        "type": 0,
        "query_name": "",
        "name": "VW3",
    }


def test_bind_decoder_payload_matches_platform_shape():
    client = CapturingAPIClient()

    client.bind_decoder("VW3", "00-40-01-2b-06-27", 0, 0)

    assert client.last_endpoint == "/mvapi/v1/displaywall/BindDecoder"
    assert client.last_data == {
        "mac": "00-40-01-2b-06-27",
        "name": "VW3",
        "bind_x": 0,
        "bind_y": 0,
    }


def test_display_wall_wnds_payload_uses_display_wall_field():
    client = CapturingAPIClient()

    client.get_display_wall_wnds("VW3")

    assert client.last_endpoint == "/mvapi/v1/wnd/GetDisplayWallWnds"
    assert client.last_data == {"display_wall": "VW3"}


def test_parse_matrix_command():
    command = parse_matrix_command(" 1v3. ")
    assert command.input_index == 1
    assert command.output_index == 3
    assert command.text == "1v3."


def test_parse_matrix_command_rejects_invalid_shape():
    with pytest.raises(MatrixError):
        parse_matrix_command("1x1")


def test_stream_channel_appends_default_suffix_to_physical_mac():
    stream = build_stream_descriptor(
        {
            "name": "输入1",
            "mac": "00-40-01-2b-05-27",
        },
        display_wall="显示器1",
    )

    assert stream["control_ws_url"] == (
        "ws://192.168.130.101:8003/?display_wall=%E6%98%BE%E7%A4%BA%E5%99%A81"
    )
    assert stream["ws_url"] == "ws://192.168.130.101:12997/play"
    assert stream["open_header"]["c"] == "00-40-01-2b-05-27-00-01/v3"
    assert [
        candidate["open_header"]["c"]
        for candidate in stream["candidates"]
    ] == [
        "00-40-01-2b-05-27-00-01/v3",
        "00-40-01-2b-05-27-00-01/v1",
        "00-40-01-2b-05-27-00-01/v2",
    ]


def test_stream_channel_keeps_api_mac_with_embedded_channel():
    stream = build_stream_descriptor({
        "name": "输入1",
        "mac": "6c-df-fb-01-5e-80-00-01",
    })

    assert stream["open_header"]["c"] == "6c-df-fb-01-5e-80-00-01/v3"
    assert [
        candidate["open_header"]["c"]
        for candidate in stream["candidates"]
    ] == [
        "6c-df-fb-01-5e-80-00-01/v3",
        "6c-df-fb-01-5e-80-00-01/v1",
        "6c-df-fb-01-5e-80-00-01/v2",
    ]


def test_scheduler_opens_expected_output_window_from_display_wall_list():
    fake = FakeAPIClient()
    scheduler = MatrixScheduler(
        client_factory=lambda: fake,
        runtime_state=MatrixRuntimeState(),
    )

    route = scheduler.switch_command("1v2.")

    assert route["command"] == "1v2."
    assert route["input"]["name"] == "视频会议终端"
    assert route["output"]["name"] == "显示器2"
    assert route["display_wall"] == "显示器2"
    assert fake.opened_windows == [
        {
            "display_wall": "显示器2",
            "src_mac": "00-40-01-2b-05-27",
            "pos_x": 0,
            "pos_y": 0,
            "width": 1920,
            "height": 1080,
        }
    ]
    assert fake.logged_out is False
    assert fake.login_count == 1
    assert fake.encoder_info_calls == []
    assert fake.decoder_list_calls == []
    assert fake.display_wall_info_calls == []
    assert fake.display_wall_decoder_list_calls == []
    assert fake.open_display_wall_calls == []
    assert fake.get_display_wall_wnds_calls == []
    assert fake.closed_windows == []
    assert fake.bind_calls == []
    assert fake.created_walls == []
    assert route["stream"]["open_header"]["c"] == "00-40-01-2b-05-27-00-01/v3"
    assert route["stream"]["control_ws_url"] == (
        "ws://192.168.130.101:8003/?display_wall=%E6%98%BE%E7%A4%BA%E5%99%A82"
    )
    assert route["stream"]["ws_url"] == "ws://192.168.130.101:12997/play"
    assert route["stream"]["ws_proxy_path"] == "/api/preview/ws?output=2"
    assert route["stream"]["control_ws_protocol"] == "fake-token"
    assert route["stream"]["ws_protocol"] == ""


def test_scheduler_reuses_login_for_consecutive_switches():
    fake = FakeAPIClient()
    scheduler = MatrixScheduler(
        client_factory=lambda: fake,
        runtime_state=MatrixRuntimeState(),
    )

    first_route = scheduler.switch_command("1v2.")
    second_route = scheduler.switch_command("2v2.")

    assert first_route["command"] == "1v2."
    assert second_route["command"] == "2v2."
    assert fake.login_count == 1
    assert fake.logged_out is False
    assert fake.opened_windows == [
        {
            "display_wall": "显示器2",
            "src_mac": "00-40-01-2b-05-27",
            "pos_x": 0,
            "pos_y": 0,
            "width": 1920,
            "height": 1080,
        },
        {
            "display_wall": "显示器2",
            "src_mac": "00-40-01-2b-05-28",
            "pos_x": 0,
            "pos_y": 0,
            "width": 1920,
            "height": 1080,
        },
    ]
    assert fake.closed_windows == []


def test_scheduler_uses_display_wall_resolution_for_open_wnd():
    fake = FakeAPIClient(display_walls=[
        {
            "index": 1,
            "name": "显示器1",
            "row": 1,
            "column": 1,
            "resolution_x": 1280,
            "resolution_y": 720,
        }
    ])
    scheduler = MatrixScheduler(
        client_factory=lambda: fake,
        runtime_state=MatrixRuntimeState(),
    )

    route = scheduler.switch_command("1v1.")

    assert route["display_wall"] == "显示器1"
    assert fake.opened_windows[0] == {
        "display_wall": "显示器1",
        "src_mac": "00-40-01-2b-05-27",
        "pos_x": 0,
        "pos_y": 0,
        "width": 1280,
        "height": 720,
    }


def test_scheduler_reports_missing_output_display_wall():
    fake = FakeAPIClient(display_walls=[])
    scheduler = MatrixScheduler(
        client_factory=lambda: fake,
        runtime_state=MatrixRuntimeState(),
    )

    with pytest.raises(MatrixError, match="大屏列表中没有输出1"):
        scheduler.switch_command("1v1.")

    assert fake.opened_windows == []
