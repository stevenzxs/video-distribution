"""
API客户端封装
"""
import hashlib
import time
import requests
import logging
from typing import Dict, Any, Optional
from config import API_BASE_URL, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


def is_success_response(result: Optional[Dict[str, Any]]) -> bool:
    """判断API响应是否成功。"""
    return (
        isinstance(result, dict)
        and (result.get("result") == "success" or result.get("result_val") == 0)
    )


def format_api_error(result: Optional[Dict[str, Any]]) -> str:
    """格式化API错误信息。"""
    if not isinstance(result, dict):
        return "无效响应"
    return f"[code:{result.get('result_val')}]: {result.get('result')}"


def _int_or_default(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_or_default(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _mapping_or_empty(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _fusion_band_payload(value: Any) -> Dict[str, int]:
    data = _mapping_or_empty(value)
    return {
        "width_x": _int_or_default(data.get("width_x"), 0),
        "width_y": _int_or_default(data.get("width_y"), 0),
    }


def _lcd_frame_payload(value: Any) -> Dict[str, float]:
    data = _mapping_or_empty(value)
    return {
        "dot_pitch": _float_or_default(data.get("dot_pitch"), 0.0),
        "width_up": _float_or_default(data.get("width_up"), 0.0),
        "width_down": _float_or_default(data.get("width_down"), 0.0),
        "width_left": _float_or_default(data.get("width_left"), 0.0),
        "width_right": _float_or_default(data.get("width_right"), 0.0),
    }


def _border_clipping_payload(value: Any) -> Dict[str, int]:
    data = _mapping_or_empty(value)
    return {
        "up": _int_or_default(data.get("up"), 0),
        "down": _int_or_default(data.get("down"), 0),
        "left": _int_or_default(data.get("left"), 0),
        "right": _int_or_default(data.get("right"), 0),
    }


class APIClient:
    """分布式综合运维管理平台API客户端"""

    def __init__(self, base_url: str = API_BASE_URL, timeout: int = REQUEST_TIMEOUT):
        self.base_url = base_url
        self.timeout = timeout
        self.token: Optional[str] = None
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json; charset=utf-8"
        })

    def _get_md5_password(self, password: str, timestamp: str) -> str:
        """生成MD5加密密码"""
        combined = password + timestamp
        return hashlib.md5(combined.encode()).hexdigest().lower()

    def _make_request(self, endpoint: str, data: Optional[Dict] = None,
                     use_token: bool = True) -> Dict[str, Any]:
        """统一请求方法"""
        url = f"{self.base_url}{endpoint}"

        headers = {}
        if use_token and self.token:
            headers["token"] = self.token

        try:
            logger.info(f"请求 {endpoint}")
            logger.debug(f"请求数据: {data}")

            response = self.session.post(
                url,
                json=data,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()

            result = response.json()
            logger.debug(f"响应数据: {result}")

            # 检查业务错误码（result 为 "success" 或 result_val 为 0 表示成功）
            if not is_success_response(result):
                logger.error(f"API错误 {format_api_error(result)}")

            return result

        except requests.exceptions.Timeout:
            logger.error(f"请求超时: {endpoint}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"请求异常: {e}")
            raise
        except ValueError as e:
            logger.error(f"JSON解析失败: {e}")
            raise

    def login(self, username: str, password: str) -> bool:
        """
        登录获取token

        Args:
            username: 用户名
            password: 密码（明文）

        Returns:
            是否登录成功
        """
        timestamp = str(int(time.time()))
        encrypted_password = self._get_md5_password(password, timestamp)

        data = {
            "username": username,
            "password": encrypted_password,
            "timestamp": timestamp
        }

        result = self._make_request("/mvapi/v1/Login", data, use_token=False)

        if is_success_response(result):
            self.token = result.get("token")
            logger.info(f"登录成功，用户: {username}, 权限: {result.get('right')}")
            return True
        else:
            logger.error(f"登录失败 {format_api_error(result)}")
            return False

    def logout(self) -> Dict[str, Any]:
        """退出登录"""
        result = self._make_request("/mvapi/v1/Logout")
        if is_success_response(result):
            self.token = None
            logger.info("退出登录成功")
        return result

    def get_api_version(self) -> Dict[str, Any]:
        """获取API版本信息"""
        return self._make_request("/mvapi/v1/GetAPIServerInfo")

    def get_task_progress(self, task_id: str) -> Dict[str, Any]:
        """获取任务进度"""
        data = {"id": task_id}
        return self._make_request("/mvapi/v1/GetTaskProgress", data)

    # ==================== 设备信息API ====================

    def get_device_overview(self) -> Dict[str, Any]:
        """获取设备节点概览信息"""
        return self._make_request("/mvapi/v1/device/GetDeviceOverView")

    def get_display_wall_overview(self) -> Dict[str, Any]:
        """获取大屏概览信息"""
        return self._make_request("/mvapi/v1/device/GetDisplayWallOverView")

    def get_encoder_summary(self, start: int = 0, size: int = 10) -> Dict[str, Any]:
        """获取编码器统计信息"""
        data = {"start": start, "size": size}
        return self._make_request("/mvapi/v1/device/GetEncoderSummary", data)

    def get_decoder_summary(self, start: int = 0, size: int = 10) -> Dict[str, Any]:
        """获取解码器统计信息"""
        data = {"start": start, "size": size}
        return self._make_request("/mvapi/v1/device/GetDecoderSummary", data)

    def get_encoder_fault(self, start: int = 0, size: int = 10) -> Dict[str, Any]:
        """获取编码器故障信息"""
        data = {"start": start, "size": size}
        return self._make_request("/mvapi/v1/device/GetEncoderFault", data)

    def get_decoder_fault(self, start: int = 0, size: int = 10) -> Dict[str, Any]:
        """获取解码器故障信息"""
        data = {"start": start, "size": size}
        return self._make_request("/mvapi/v1/device/GetDecoderFault", data)

    # ==================== 编码器操作API ====================

    def get_encoder_list(self, page_index: int = 1, page_size: int = 20,
                        query_name: str = "", query_ip: str = "",
                        filter_list: list = None, sort: str = "",
                        order: str = "asc") -> Dict[str, Any]:
        """获取编码器列表"""
        data = {
            "page_index": page_index,
            "page_size": page_size,
            "query_name": query_name,
            "query_ip": query_ip,
            "filter": filter_list or [],
            "sort": sort,
            "order": order
        }
        return self._make_request("/mvapi/v1/encoder/GetEncoderList", data)

    def get_encoder_info(self, mac: str) -> Dict[str, Any]:
        """获取单个编码器详细信息"""
        data = {"mac": mac}
        return self._make_request("/mvapi/v1/encoder/GetEncoderInfo", data)

    def set_encoder_volume(self, mac: str, volume: int) -> Dict[str, Any]:
        """设置编码器音量"""
        data = {"mac": mac, "volume": volume}
        return self._make_request("/mvapi/v1/encoder/SetEncoderVolume", data)

    def reboot_encoder(self, mode: int, device1: list = None,
                      device2: list = None) -> Dict[str, Any]:
        """重启编码器"""
        data = {
            "mode": mode,
            "device1": device1 or [],
            "device2": device2 or []
        }
        return self._make_request("/mvapi/v1/encoder/RebootEncoder", data)

    # ==================== 解码器操作API ====================

    def get_decoder_list(self, page_index: int = 1, page_size: int = 20,
                        query_name: str = "", query_ip: str = "",
                        filter_list: list = None, sort: str = "",
                        order: str = "asc") -> Dict[str, Any]:
        """获取解码器列表"""
        data = {
            "page_index": page_index,
            "page_size": page_size,
            "query_name": query_name,
            "query_ip": query_ip,
            "filter": filter_list or [],
            "sort": sort,
            "order": order
        }
        return self._make_request("/mvapi/v1/decoder/GetDecoderList", data)

    def get_decoder_info(self, mac: str) -> Dict[str, Any]:
        """获取单个解码器详细信息"""
        data = {"mac": mac}
        return self._make_request("/mvapi/v1/decoder/GetDecoderInfo", data)

    def set_decoder_test_mode(self, mac: str, test_mode: int) -> Dict[str, Any]:
        """设置解码器测试模式"""
        data = {"mac": mac, "test_mode": test_mode}
        return self._make_request("/mvapi/v1/decoder/SetDecoderTestMode", data)

    # ==================== 大屏操作API ====================

    def get_display_wall_list(self, page_index: int = 1, page_size: int = 20,
                              query_name: str = "", query_specification: str = "",
                              filter_list: list = None, sort: str = "",
                              order: str = "asc") -> Dict[str, Any]:
        """获取大屏列表"""
        data = {
            "page_index": page_index,
            "page_size": page_size,
            "query_name": query_name,
            "query_specification": query_specification,
            "filter": filter_list or [],
            "sort": sort,
            "order": order
        }
        return self._make_request("/mvapi/v1/displaywall/GetDisplayWallList", data)

    def get_display_wall_info(self, name: str) -> Dict[str, Any]:
        """获取单个大屏详细信息"""
        data = {"name": name}
        return self._make_request("/mvapi/v1/displaywall/GetDisplayWallInfo", data)

    def create_display_wall(self, name: str, row: int, column: int,
                            resolution_x: int, resolution_y: int,
                            factory: str = "", com: Any = -1,
                            fusion_band: Optional[Dict[str, Any]] = None,
                            lcd_frame: Optional[Dict[str, Any]] = None,
                            border_clipping: Optional[Dict[str, Any]] = None,
                            hfront: int = 0, hback: int = 0,
                            vfront: int = 0, vback: int = 0,
                            hwidth: int = 0, vwidth: int = 0,
                            clock: int = 0,
                            create_time: Optional[Any] = None) -> Dict[str, Any]:
        """创建大屏幕墙"""
        if create_time is None:
            create_time = str(int(time.time()))

        data = {
            "name": name,
            "row": _int_or_default(row, 1),
            "column": _int_or_default(column, 1),
            "resolution_x": _int_or_default(resolution_x, 1920),
            "resolution_y": _int_or_default(resolution_y, 1080),
            "create_time": str(create_time),
            "factory": str(factory or ""),
            "com": _int_or_default(com, -1),
            "fusion_band": _fusion_band_payload(fusion_band),
            "lcd_frame": _lcd_frame_payload(lcd_frame),
            "border_clipping": _border_clipping_payload(border_clipping),
            "hfront": _int_or_default(hfront, 0),
            "hback": _int_or_default(hback, 0),
            "vfront": _int_or_default(vfront, 0),
            "vback": _int_or_default(vback, 0),
            "hwidth": _int_or_default(hwidth, 0),
            "vwidth": _int_or_default(vwidth, 0),
            "clock": _int_or_default(clock, 0),
        }
        return self._make_request("/mvapi/v1/displaywall/CreateDisplayWall", data)

    def open_display_wall(self, name: str) -> Dict[str, Any]:
        """打开大屏"""
        data = {"name": name}
        return self._make_request("/mvapi/v1/displaywall/OpenDisplayWall", data)

    def close_display_wall(self, name: str) -> Dict[str, Any]:
        """关闭大屏"""
        data = {"name": name}
        return self._make_request("/mvapi/v1/displaywall/CloseDisplayWall", data)

    def get_display_wall_decoder_list(self, display_wall: str) -> Dict[str, Any]:
        """获取大屏已绑定解码器列表"""
        data = {"name": display_wall}
        return self._make_request("/mvapi/v1/displaywall/GetDispWallDecoderList", data)

    def get_available_decoders(self, display_wall: str, start: int = 0,
                               size: int = 100, decoder_type: int = 0,
                               query_name: str = "") -> Dict[str, Any]:
        """获取大屏可用解码器列表"""
        data = {
            "start": start,
            "size": size,
            "type": decoder_type,
            "query_name": query_name,
            "name": display_wall,
        }
        return self._make_request("/mvapi/v1/displaywall/GetAvailableDecoder", data)

    def bind_decoder(self, display_wall: str, mac: str, bind_x: int,
                     bind_y: int) -> Dict[str, Any]:
        """绑定视频解码器到大屏位置"""
        data = {
            "mac": mac,
            "name": display_wall,
            "bind_x": bind_x,
            "bind_y": bind_y,
        }
        return self._make_request("/mvapi/v1/displaywall/BindDecoder", data)

    # ==================== 窗口操作API ====================

    def get_display_wall_wnds(self, display_wall: str) -> Dict[str, Any]:
        """获取大屏所有窗口信息"""
        data = {"display_wall": display_wall}
        return self._make_request("/mvapi/v1/wnd/GetDisplayWallWnds", data)

    def open_wnd(self, display_wall: str, src_mac: str,
                 pos_x: int, pos_y: int, width: int, height: int) -> Dict[str, Any]:
        """开窗"""
        data = {
            "display_wall": display_wall,
            "src_mac": src_mac,
            "pos_x": pos_x,
            "pos_y": pos_y,
            "width": width,
            "height": height
        }
        return self._make_request("/mvapi/v1/wnd/OpenWnd", data)

    def close_wnd(self, display_wall: str, handle: int) -> Dict[str, Any]:
        """关闭单个窗口"""
        data = {"display_wall": display_wall, "handle": handle}
        return self._make_request("/mvapi/v1/wnd/CloseWnd", data)

    def close_all_wnds(self, display_wall: str) -> Dict[str, Any]:
        """关闭大屏所有窗口"""
        data = {"display_wall": display_wall}
        return self._make_request("/mvapi/v1/wnd/CloseAllWnds", data)

    def replace_wnd_source(self, display_wall: str, handle: int,
                           src_mac: str) -> Dict[str, Any]:
        """替换窗口信号源"""
        data = {
            "display_wall": display_wall,
            "handle": handle,
            "src_mac": src_mac,
        }
        return self._make_request("/mvapi/v1/wnd/ReplaceWndSource", data)

    def move_wnd(self, display_wall: str, handle: int, pos_x: int,
                 pos_y: int, width: int, height: int) -> Dict[str, Any]:
        """移动窗口位置和大小"""
        data = {
            "display_wall": display_wall,
            "handle": handle,
            "pos_x": pos_x,
            "pos_y": pos_y,
            "width": width,
            "height": height,
        }
        return self._make_request("/mvapi/v1/wnd/MoveWnd", data)

    # ==================== 预案操作API ====================

    def get_layout_list(self, page_index: int = 1, page_size: int = 20,
                       query_name: str = "", filter_list: list = None,
                       sort: str = "", order: str = "asc") -> Dict[str, Any]:
        """获取预案列表"""
        data = {
            "page_index": page_index,
            "page_size": page_size,
            "query_name": query_name,
            "filter": filter_list or [],
            "sort": sort,
            "order": order
        }
        return self._make_request("/mvapi/v1/layout/GetLayoutList", data)

    def save_layout(self, name: str, display_wall: str) -> Dict[str, Any]:
        """保存当前窗口为预案"""
        data = {"name": name, "display_wall": display_wall}
        return self._make_request("/mvapi/v1/layout/SaveLayout", data)

    def load_layout(self, layout_type: int, name: str,
                   display_wall: str) -> Dict[str, Any]:
        """加载预案"""
        data = {
            "type": layout_type,
            "name": name,
            "display_wall": display_wall
        }
        return self._make_request("/mvapi/v1/layout/LoadLayout", data)
