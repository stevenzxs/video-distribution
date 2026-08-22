"""
配置文件
"""

# API服务器配置
API_SERVER_HOST = "192.168.130.101"
API_SERVER_PORT = 8001
API_BASE_URL = f"http://{API_SERVER_HOST}:{API_SERVER_PORT}"

# WebSocket配置
WS_SERVER_PORT = 8003
WS_BASE_URL = f"ws://{API_SERVER_HOST}:{WS_SERVER_PORT}"

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
    # 后端会确保该大屏存在；不存在时按输出解码器数量创建 1xN 大屏。
    "display_wall_name": "视频矩阵大屏",
    "auto_create_display_wall": True,
    # 1行3列大屏中单个输出窗口尺寸，位置会按输出序号横向排列。
    "screen_width": 1920,
    "screen_height": 1080,
    "display_wall_row": 1,
    "display_wall_factory": "",
    "display_wall_com": "",
    "display_wall_fusion_band": 0,
    "display_wall_lcd_frame": 0,
    "display_wall_border_clipping": 0,
    # WebSocket 取流通道后缀，文档示例为 MAC-00-01/v3。
    "stream_channel_suffix": "00-01/v3",
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
