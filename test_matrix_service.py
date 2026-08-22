import pytest

from api_client import is_success_response
from matrix_service import MatrixError, MatrixRuntimeState, MatrixScheduler, parse_matrix_command


class FakeAPIClient:
    def __init__(self):
        self.opened_windows = []
        self.logged_out = False

    def login(self, username, password):
        return username == "admin" and bool(password)

    def logout(self):
        self.logged_out = True
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

    def get_decoder_list(self, page_index=1, page_size=100):
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
            "display_walls": [{"name": "矩阵大屏", "row": 1, "column": 3}],
        }

    def open_display_wall(self, name):
        return {"result": "success", "result_val": 0, "name": name}

    def open_wnd(self, display_wall, src_mac, pos_x, pos_y, width, height):
        payload = {
            "display_wall": display_wall,
            "src_mac": src_mac,
            "pos_x": pos_x,
            "pos_y": pos_y,
            "width": width,
            "height": height,
        }
        self.opened_windows.append(payload)
        return {"result": "success", "result_val": 0, "handle": 1001}


def test_api_success_uses_platform_success_shape():
    assert is_success_response({"result": "success", "result_val": 1})
    assert is_success_response({"result": "failed", "result_val": 0})
    assert not is_success_response({"result": "0", "result_val": "success"})
    assert not is_success_response({"result": 0, "result_val": "success"})


def test_parse_matrix_command():
    command = parse_matrix_command(" 1v3. ")
    assert command.input_index == 1
    assert command.output_index == 3
    assert command.text == "1v3."


def test_parse_matrix_command_rejects_invalid_shape():
    with pytest.raises(MatrixError):
        parse_matrix_command("1x1")


def test_scheduler_opens_expected_output_window():
    fake = FakeAPIClient()
    scheduler = MatrixScheduler(
        client_factory=lambda: fake,
        runtime_state=MatrixRuntimeState(),
    )

    route = scheduler.switch_command("1v2.")

    assert route["command"] == "1v2."
    assert route["input"]["name"] == "视频会议终端"
    assert route["output"]["name"] == "显示器2"
    assert route["display_wall"] == "矩阵大屏"
    assert fake.opened_windows == [
        {
            "display_wall": "矩阵大屏",
            "src_mac": "00-40-01-2b-05-27",
            "pos_x": 1920,
            "pos_y": 0,
            "width": 1920,
            "height": 1080,
        }
    ]
    assert fake.logged_out is True
    assert route["stream"]["open_header"]["c"] == "00-40-01-2b-05-27-00-01/v3"
