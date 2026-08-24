"""
配置文件
"""

# API服务器配置
API_SERVER_HOST = "192.168.130.101"
API_SERVER_PORT = 8001
API_BASE_URL = f"http://{API_SERVER_HOST}:{API_SERVER_PORT}"

# WebSocket配置
# 抓包确认（docs/ws.txt）：视频调度确认控制 WebSocket 与 HTTP API 同在 8001 端口，
# 带 display_wall 查询参数，握手需 Sec-WebSocket-Protocol 携带登录 token，
# 返回 {"result":"success","result_val":0}。
# 注意：旧文档中 8003 是历史记录，实测连接 8003 会被对端静默挂起约 15 秒后
# 空响应关闭（对端 keep-alive timeout=15），握手永远等不到 101。
WS_CONTROL_SERVER_PORT = 8001
WS_CONTROL_BASE_URL = f"ws://{API_SERVER_HOST}:{WS_CONTROL_SERVER_PORT}"
# 抓包确认 12997/play 是取码流 WebSocket，101 后发送 open_header 并接收二进制帧。
WS_STREAM_SERVER_PORT = 12997
WS_STREAM_BASE_URL = f"ws://{API_SERVER_HOST}:{WS_STREAM_SERVER_PORT}/play"
# 兼容旧代码引用：旧的 WS_BASE_URL 表示 8001 控制入口。
WS_SERVER_PORT = WS_CONTROL_SERVER_PORT
WS_BASE_URL = WS_CONTROL_BASE_URL

# 设备配置
DEVICES = {
    "server": {"name": "服务器", "ip": API_SERVER_HOST},
    "encoders": [
        {"name": "视频会议终端", "ip": "192.168.130.51", "mac": ""},
        {"name": "摄像头1", "ip": "192.168.130.52", "mac": ""},
        {"name": "摄像头2", "ip": "192.168.130.53", "mac": ""},
    ],
    "decoders": [
        {"name": "显示器1", "ip": "192.168.130.61", "mac": ""},
        {"name": "显示器2", "ip": "192.168.130.62", "mac": ""},
        {"name": "终端摄像", "ip": "192.168.130.63", "mac": ""},
    ]
}

# 矩阵调度配置
MATRIX_CONFIG = {
    # 调度时按 GetDisplayWallList 返回的 index/顺序选择大屏：
    # 1v1. -> 显示器1，1v2. -> 显示器2，1v3. -> 显示器3。
    # display_wall_name 仅作为页面初始化和未传 display_wall 时的兼容 fallback。
    "display_wall_name": "显示器1",
    "auto_create_display_wall": False,
    # 单个 1x1 大屏窗口尺寸；实际 OpenWnd 优先使用 GetDisplayWallList 返回的分辨率。
    "screen_width": 1920,
    "screen_height": 1080,
    "display_wall_row": 1,
    "display_wall_factory": "",
    # 控制方式，-1 表示可经解码器转发。
    "display_wall_com": -1,
    "display_wall_fusion_band": {"width_x": 0, "width_y": 0},
    "display_wall_lcd_frame": {
        "dot_pitch": 0.0,
        "width_up": 0.0,
        "width_down": 0.0,
        "width_left": 0.0,
        "width_right": 0.0,
    },
    "display_wall_border_clipping": {
        "up": 0,
        "down": 0,
        "left": 0,
        "right": 0,
    },
    # 自定义分辨率参数，不使用自定义分辨率时保持 0。
    "display_wall_hfront": 0,
    "display_wall_hback": 0,
    "display_wall_vfront": 0,
    "display_wall_vback": 0,
    "display_wall_hwidth": 0,
    "display_wall_vwidth": 0,
    "display_wall_clock": 0,
    # WebSocket 取流通道后缀，文档示例为 MAC-00-01/v3。
    "stream_channel_suffix": "00-01/v3",
    # Web 预览自动重试的取流版本。优先使用 stream_channel_suffix 中配置的版本，
    # 若无码流、收到 H.265 或浏览器解码失败，再按此列表尝试其他版本。
    "stream_versions": ["v1", "v2", "v3"],
}

# 测试用户配置
TEST_USER = {
    "username": "admin",
    "password": "123456",  # 实际密码需要根据系统配置修改
}

# 请求超时配置（秒）
REQUEST_TIMEOUT = 30

# 日志配置
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
