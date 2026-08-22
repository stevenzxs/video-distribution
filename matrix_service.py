"""
矩阵调度服务。

负责把前端的 1v1. 指令转换为平台 API 调度：
输入 N 编码器 -> 输出 N 对应的大屏窗口位置。
"""
import re
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional

from api_client import APIClient, format_api_error, is_success_response
from config import API_BASE_URL, DEVICES, MATRIX_CONFIG, TEST_USER, WS_BASE_URL


COMMAND_PATTERN = re.compile(r"^\s*([1-3])v([1-3])\.\s*$", re.IGNORECASE)
MAC_KEYS = (
    "mac",
    "src_mac",
    "device_mac",
    "dev_mac",
    "mac_addr",
    "macAddr",
    "decoder_mac",
    "decoderMac",
)
IP_KEYS = ("ip", "ip_addr", "ipAddr", "device_ip", "deviceIp", "decoder_ip", "decoderIp")
NAME_KEYS = (
    "name",
    "device_name",
    "deviceName",
    "decoder_name",
    "decoderName",
)
WALL_NAME_KEYS = ("name", "display_wall", "displayWall", "wall_name", "wallName")


class MatrixError(Exception):
    """矩阵调度错误。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class MatrixCommand:
    """已解析的矩阵指令。"""

    input_index: int
    output_index: int
    text: str


class MatrixRuntimeState:
    """保存本进程内最后一次调度状态，用于页面回显。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._assignments: Dict[int, Dict[str, Any]] = {}

    def record(self, output_index: int, route: Dict[str, Any]) -> None:
        with self._lock:
            self._assignments[output_index] = route

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            assignments = {
                str(output_index): route
                for output_index, route in self._assignments.items()
            }

        return {
            "server": DEVICES.get("server", {}),
            "inputs": _indexed_devices(DEVICES.get("encoders", [])),
            "outputs": _indexed_devices(DEVICES.get("decoders", [])),
            "screens": [
                {
                    "index": index,
                    "output": _public_device(
                        DEVICES.get("decoders", [])[index - 1],
                        index,
                    ),
                    "assignment": assignments.get(str(index)),
                }
                for index in range(1, 4)
            ],
            "matrix": {
                "display_wall_name": MATRIX_CONFIG.get("display_wall_name", ""),
                "screen_width": MATRIX_CONFIG.get("screen_width", 1920),
                "screen_height": MATRIX_CONFIG.get("screen_height", 1080),
                "ws_url": WS_BASE_URL,
            },
        }


RUNTIME_STATE = MatrixRuntimeState()


def parse_matrix_command(command: str) -> MatrixCommand:
    """解析形如 1v1. 的 1进1出矩阵指令。"""
    match = COMMAND_PATTERN.match(command or "")
    if not match:
        raise MatrixError("指令格式错误，应为 1v1. 到 3v3. 之间的 1进1出指令")

    input_index = int(match.group(1))
    output_index = int(match.group(2))
    return MatrixCommand(input_index, output_index, f"{input_index}v{output_index}.")


def get_matrix_state() -> Dict[str, Any]:
    """返回页面初始化需要的矩阵状态。"""
    return RUNTIME_STATE.snapshot()


class MatrixScheduler:
    """把矩阵指令调度到硬件平台。"""

    def __init__(
        self,
        client_factory: Callable[[], APIClient] = APIClient,
        runtime_state: MatrixRuntimeState = RUNTIME_STATE,
    ) -> None:
        self.client_factory = client_factory
        self.runtime_state = runtime_state

    def switch_command(self, command: str) -> Dict[str, Any]:
        parsed = parse_matrix_command(command)
        client = self.client_factory()

        if not client.login(TEST_USER["username"], TEST_USER["password"]):
            raise MatrixError("登录 API 平台失败，请检查用户名、密码和服务器连接", 502)

        try:
            encoder = self._resolve_device(client, "encoder", parsed.input_index)
            output = self._resolve_device(client, "decoder", parsed.output_index)
            display_wall = self._ensure_display_wall(
                client,
                output_count=len(DEVICES.get("decoders", [])),
            )
            self._validate_display_wall_output(
                client,
                display_wall,
                output,
                parsed.output_index,
            )
            window = self._open_output_window(
                client,
                display_wall,
                encoder["mac"],
                parsed.output_index,
            )

            route = {
                "command": parsed.text,
                "input": encoder,
                "output": output,
                "display_wall": display_wall,
                "window": window,
                "stream": build_stream_descriptor(encoder),
            }
            self.runtime_state.record(parsed.output_index, route)
            return route
        finally:
            try:
                client.logout()
            except Exception:
                pass

    def _resolve_device(
        self,
        client: APIClient,
        device_type: str,
        index: int,
    ) -> Dict[str, Any]:
        configs = DEVICES[f"{device_type}s"]
        configured = configs[index - 1]

        if configured.get("mac"):
            return _public_device(configured, index)

        if device_type == "encoder":
            result = client.get_encoder_list(page_index=1, page_size=100)
            items = result.get("encoders", []) if is_success_response(result) else []
        else:
            result = client.get_decoder_list(page_index=1, page_size=100)
            items = result.get("decoders", []) if is_success_response(result) else []

        if not is_success_response(result):
            label = "编码器" if device_type == "encoder" else "解码器"
            raise MatrixError(f"获取{label}列表失败 {format_api_error(result)}", 502)

        matched = _find_matching_device(configured, items)
        if matched is None and len(items) >= index:
            matched = items[index - 1]
        if matched is None:
            raise MatrixError(
                f"未找到{configured.get('name')}({configured.get('ip')})，"
                "请确认设备在线或在 config.py 中补充 mac",
                502,
            )

        merged = {**configured, **matched}
        mac = _first_value(merged, MAC_KEYS)
        if not mac:
            raise MatrixError(
                f"已找到{configured.get('name')}，但 API 未返回 MAC；"
                "请在 config.py 的对应设备中填写 mac",
                502,
            )

        merged["mac"] = _normalize_mac(mac)
        return _public_device(merged, index)

    def _ensure_display_wall(self, client: APIClient, output_count: int) -> str:
        name = _target_display_wall_name(output_count)
        wall = self._find_display_wall(client, name)
        if wall:
            info_result = client.get_display_wall_info(name)
            if is_success_response(info_result):
                return name
            if info_result.get("result_val") != 13:
                raise MatrixError(
                    f"获取大屏 {name} 详情失败 {format_api_error(info_result)}",
                    502,
                )

        if not MATRIX_CONFIG.get("auto_create_display_wall", True):
            raise MatrixError(
                f"大屏 {name} 不存在，请先在平台创建 1x{output_count} 大屏，"
                "或开启 MATRIX_CONFIG.auto_create_display_wall",
                502,
            )

        return self._create_display_wall(client, name, output_count)

    def _find_display_wall(
        self,
        client: APIClient,
        name: str,
    ) -> Optional[Dict[str, Any]]:
        result = client.get_display_wall_list(page_index=1, page_size=20)
        if not is_success_response(result):
            raise MatrixError(f"获取大屏列表失败 {format_api_error(result)}", 502)

        for wall in _extract_display_wall_records(result):
            if str(_first_value(wall, WALL_NAME_KEYS) or "").strip() == name:
                return wall

        return None

    def _create_display_wall(
        self,
        client: APIClient,
        name: str,
        output_count: int,
    ) -> str:
        row = int(MATRIX_CONFIG.get("display_wall_row", 1) or 1)
        column = max(1, _ceil_div(output_count, row))
        screen_width = _even_int(MATRIX_CONFIG.get("screen_width", 1920))
        screen_height = _even_int(MATRIX_CONFIG.get("screen_height", 1080))

        create_result = client.create_display_wall(
            name=name,
            row=row,
            column=column,
            resolution_x=screen_width,
            resolution_y=screen_height,
            factory=str(MATRIX_CONFIG.get("display_wall_factory", "")),
            com=str(MATRIX_CONFIG.get("display_wall_com", "")),
            fusion_band=int(MATRIX_CONFIG.get("display_wall_fusion_band", 0) or 0),
            lcd_frame=int(MATRIX_CONFIG.get("display_wall_lcd_frame", 0) or 0),
            border_clipping=int(MATRIX_CONFIG.get("display_wall_border_clipping", 0) or 0),
        )
        if not is_success_response(create_result) and create_result.get("result_val") != 20:
            raise MatrixError(
                f"创建大屏 {name} 失败 {format_api_error(create_result)}；"
                f"创建参数: row={row}, column={column}, "
                f"resolution={screen_width}x{screen_height}",
                502,
            )

        info_result = client.get_display_wall_info(name)
        if not is_success_response(info_result):
            raise MatrixError(
                f"大屏 {name} 创建后仍无法获取详情 {format_api_error(info_result)}",
                502,
            )

        return name

    def _validate_display_wall_output(
        self,
        client: APIClient,
        display_wall: str,
        output: Dict[str, Any],
        output_index: int,
    ) -> None:
        info_result = client.get_display_wall_info(display_wall)
        if is_success_response(info_result):
            row = _optional_int(info_result.get("row"))
            column = _optional_int(info_result.get("column"))
            if row and column and output_index > row * column:
                raise MatrixError(
                    f"输出{output_index}超出大屏 {display_wall} 的规格 "
                    f"{row}x{column}",
                    502,
                )

        bound_result = client.get_display_wall_decoder_list(display_wall)
        if not is_success_response(bound_result):
            raise MatrixError(
                f"获取大屏 {display_wall} 已绑定解码器失败 "
                f"{format_api_error(bound_result)}",
                502,
            )

        bound_decoders = _extract_device_records(bound_result)
        if not bound_decoders:
            raise MatrixError(
                f"大屏 {display_wall} 未绑定任何解码器，OpenWnd 会被底层 SDK 拒绝。"
                "请先在平台将 3 个输出解码器绑定到该大屏，或在 config.py 的 "
                "MATRIX_CONFIG.display_wall_name 指定已经完成绑定的 1x3 大屏。",
                502,
            )

        if not _device_record_matches(output, bound_decoders):
            bound_summary = _summarize_devices(bound_decoders)
            raise MatrixError(
                f"输出{output_index}对应的解码器 {output.get('name')} "
                f"({output.get('ip') or output.get('mac')}) 未绑定到大屏 {display_wall}。"
                f"当前已绑定: {bound_summary}",
                502,
            )

    def _open_output_window(
        self,
        client: APIClient,
        display_wall: str,
        src_mac: str,
        output_index: int,
    ) -> Dict[str, Any]:
        screen_width = _even_int(MATRIX_CONFIG.get("screen_width", 1920))
        screen_height = _even_int(MATRIX_CONFIG.get("screen_height", 1080))
        pos_x = (output_index - 1) * screen_width
        pos_y = 0

        open_wall_result = client.open_display_wall(display_wall)
        if not is_success_response(open_wall_result):
            raise MatrixError(
                f"打开大屏 {display_wall} 失败 {format_api_error(open_wall_result)}",
                502,
            )

        result = client.open_wnd(
            display_wall=display_wall,
            src_mac=src_mac,
            pos_x=pos_x,
            pos_y=pos_y,
            width=screen_width,
            height=screen_height,
        )
        if not is_success_response(result):
            raise MatrixError(
                f"开窗失败 {format_api_error(result)}，命令位置为"
                f"({pos_x}, {pos_y}, {screen_width}, {screen_height})",
                502,
            )

        return {
            "pos_x": pos_x,
            "pos_y": pos_y,
            "width": screen_width,
            "height": screen_height,
            "result": result,
        }


def build_stream_descriptor(encoder: Dict[str, Any]) -> Dict[str, Any]:
    """生成浏览器连接取流 WebSocket 需要的信息。"""
    channel = _stream_channel(encoder["mac"])
    return {
        "ws_url": WS_BASE_URL,
        "open_header": {
            "a": "",
            "a2": encoder.get("name", ""),
            "c": channel,
            "s": API_BASE_URL,
            "t": "open",
        },
        "close_header": {
            "a": "",
            "a2": encoder.get("name", ""),
            "c": channel,
            "s": API_BASE_URL,
            "t": "close",
        },
    }


def _indexed_devices(devices: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_public_device(device, index) for index, device in enumerate(devices, 1)]


def _target_display_wall_name(output_count: int) -> str:
    configured = str(MATRIX_CONFIG.get("display_wall_name", "")).strip()
    if configured:
        return configured
    return f"视频矩阵大屏{output_count}"


def _public_device(device: Dict[str, Any], index: int) -> Dict[str, Any]:
    return {
        "index": index,
        "name": str(_first_value(device, NAME_KEYS) or f"设备{index}"),
        "ip": str(_first_value(device, IP_KEYS) or ""),
        "mac": str(_first_value(device, MAC_KEYS) or ""),
    }


def _find_matching_device(
    configured: Dict[str, Any],
    candidates: Iterable[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    configured_ip = str(configured.get("ip", "")).strip()
    configured_name = str(configured.get("name", "")).strip()

    for candidate in candidates:
        if configured_ip and str(_first_value(candidate, IP_KEYS) or "").strip() == configured_ip:
            return candidate

    for candidate in candidates:
        if configured_name and str(_first_value(candidate, NAME_KEYS) or "").strip() == configured_name:
            return candidate

    return None


def _first_value(data: Dict[str, Any], keys: Iterable[str]) -> Optional[Any]:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def _ceil_div(value: int, divisor: int) -> int:
    return -(-value // divisor)


def _optional_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_mac(mac: Any) -> str:
    return str(mac).strip().replace(":", "-")


def _extract_device_records(payload: Any) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if _first_value(value, (*MAC_KEYS, *IP_KEYS, *NAME_KEYS)):
                records.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return records


def _extract_display_wall_records(payload: Any) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if _first_value(value, WALL_NAME_KEYS):
                records.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload.get("display_walls", payload) if isinstance(payload, dict) else payload)
    return records


def _device_record_matches(
    expected: Dict[str, Any],
    candidates: Iterable[Dict[str, Any]],
) -> bool:
    expected_mac = _normalize_mac(expected.get("mac", ""))
    expected_ip = str(expected.get("ip", "")).strip()
    expected_name = str(expected.get("name", "")).strip()

    for candidate in candidates:
        candidate_mac = _normalize_mac(_first_value(candidate, MAC_KEYS) or "")
        candidate_ip = str(_first_value(candidate, IP_KEYS) or "").strip()
        candidate_name = str(_first_value(candidate, NAME_KEYS) or "").strip()

        if expected_mac and candidate_mac and expected_mac == candidate_mac:
            return True
        if expected_ip and candidate_ip and expected_ip == candidate_ip:
            return True
        if expected_name and candidate_name and expected_name == candidate_name:
            return True

    return False


def _summarize_devices(devices: Iterable[Dict[str, Any]]) -> str:
    labels = []
    for device in devices:
        name = _first_value(device, NAME_KEYS)
        ip = _first_value(device, IP_KEYS)
        mac = _first_value(device, MAC_KEYS)
        parts = [str(item) for item in (name, ip, mac) if item]
        if parts:
            labels.append("/".join(parts))

    return ", ".join(labels[:6]) if labels else "无"


def _stream_channel(mac: str) -> str:
    normalized = _normalize_mac(mac)
    if "/" in normalized:
        return normalized

    suffix = str(MATRIX_CONFIG.get("stream_channel_suffix", "")).strip()
    if not suffix:
        return normalized
    return f"{normalized}-{suffix}"


def _even_int(value: Any) -> int:
    number = int(value)
    return number if number % 2 == 0 else number + 1
