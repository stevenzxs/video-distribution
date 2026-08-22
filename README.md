# 分布式综合运维管理平台 API 测试工具

## 📋 项目简介

这是一个用于测试和调试分布式综合运维管理平台API接口的Python工具集。支持设备管理、大屏控制、窗口操作、预案管理等功能的完整测试。

## 🚀 快速开始

### 1. 安装依赖

```bash
# 使用 pip
pip install requests pytest pytest-html

# 或使用项目配置
pip install -e .
```

### 2. 配置服务器信息

编辑 `config.py` 文件，修改以下配置：

```python
# API服务器配置
API_SERVER_HOST = "192.168.130.101"  # 修改为实际服务器IP
API_SERVER_PORT = 8001

# 测试用户配置
TEST_USER = {
    "username": "admin",      # 修改为实际用户名
    "password": "admin123",   # 修改为实际密码
}
```

### 3. 运行测试

#### 方式一：运行主程序（推荐）

```bash
python main.py
```

这将执行完整的API连通性测试，包括：
- ✅ 登录认证
- ✅ 设备概览
- ✅ 编码器列表
- ✅ 解码器列表
- ✅ 大屏列表
- ✅ 预案列表

#### 方式二：运行单元测试

```bash
# 运行所有测试
pytest test_api.py -v -s

# 运行特定测试类
pytest test_api.py::TestBasicAPI -v -s

# 运行特定测试方法
pytest test_api.py::TestBasicAPI::test_login -v -s

# 生成HTML测试报告
pytest test_api.py --html=report.html --self-contained-html
```

## 📁 项目结构

```
video-distribution/
├── config.py           # 配置文件（服务器IP、用户信息等）
├── api_client.py       # API客户端封装
├── test_api.py         # 单元测试套件
├── main.py             # 主程序入口
├── pyproject.toml      # 项目依赖配置
├── README.md           # 项目说明文档
└── docs/
    ├── 分布式综合运维管理平台API学习笔记.md
    ├── 分布式综合运维管理平台API说明书.pdf
    └── 分布式节点IP.txt
```

## 🔧 API客户端使用示例

### 基础认证

```python
from api_client import APIClient

# 创建客户端
client = APIClient()

# 登录
client.login("admin", "password")

# 获取API版本
version = client.get_api_version()
print(version)

# 退出登录
client.logout()
```

### 获取设备信息

```python
# 获取设备概览
overview = client.get_device_overview()

# 获取编码器列表
encoders = client.get_encoder_list(page_index=1, page_size=20)

# 获取单个编码器详情
encoder_info = client.get_encoder_info(mac="00-40-01-2b-05-27")
```

### 大屏操作

```python
# 获取大屏列表
walls = client.get_display_wall_list()

# 打开大屏
client.open_display_wall("大屏1")

# 开窗显示
client.open_wnd(
    display_wall="大屏1",
    src_mac="00-40-01-2b-05-27",
    pos_x=0,
    pos_y=0,
    width=1920,
    height=1080
)

# 关闭大屏
client.close_display_wall("大屏1")
```

### 预案操作

```python
# 获取预案列表
layouts = client.get_layout_list()

# 保存当前窗口为预案
client.save_layout(name="预案1", display_wall="大屏1")

# 加载预案
client.load_layout(layout_type=0, name="预案1", display_wall="大屏1")
```

## 🐛 常见问题

### 1. 连接超时

**问题**: `requests.exceptions.Timeout: Connection timeout`

**解决方案**:
- 检查服务器IP是否正确
- 确认网络连接正常
- 检查防火墙设置
- 在 `config.py` 中增加 `REQUEST_TIMEOUT` 值

### 2. 登录失败

**问题**: `登录失败: username or password error`

**解决方案**:
- 确认用户名和密码正确
- 检查用户账号是否被锁定
- 验证用户是否有API访问权限

### 3. Token解析错误

**问题**: `token parse failed`

**解决方案**:
- Token可能已过期，重新登录
- 检查系统时间是否正确
- 确认API版本兼容性

## 📝 API错误码参考

| 错误码 | 说明 | 处理建议 |
|--------|------|----------|
| 0 | 成功 | - |
| 1 | 用户名或密码错误 | 检查登录凭证 |
| 2 | Token解析错误 | 重新登录 |
| 3 | 参数解析错误 | 检查请求参数格式 |
| 6 | 服务器未连接 | 检查网络连接 |
| 13 | 资源不存在 | 确认资源名称或ID |
| 16 | 权限不足 | 使用管理员账号 |
| 27 | 资源名称过长 | 大屏等资源名使用短 ASCII，例如 `VW3` |

完整错误码请参考: `docs/分布式综合运维管理平台API学习笔记.md`

## 🔗 相关文档

- [API学习笔记](docs/分布式综合运维管理平台API学习笔记.md) - 完整的API接口说明
- [API说明书PDF](docs/分布式综合运维管理平台API说明书.pdf) - 官方API文档
- [节点IP配置](docs/分布式节点IP.txt) - 测试环境设备IP列表

## 📞 技术支持

如有问题，请参考以下资源：
1. 查看 `docs/` 目录下的详细文档
2. 检查日志输出中的错误信息
3. 使用 `-v -s` 参数运行pytest获取详细测试日志

---

**最后更新**: 2026-08-22

## Web矩阵控制台

启动本地控制台：

```bash
python web_server.py --host 127.0.0.1 --port 8080
```

打开 `http://127.0.0.1:8080` 后，页面上方是 1 行 3 列输出屏幕，下方是 3 路输入单选和 3 路输出多选矩阵按钮。选择输入 1 和输出 1 时，前端会提交 `1v1.`，后端解析后调用平台 API，把输入 1 编码器开窗到输出 1 对应的大屏位置。

硬件资源在 `config.py` 中维护：
- 服务器：`DEVICES["server"]`
- 3 个编码器：`DEVICES["encoders"]`
- 3 个解码器：`DEVICES["decoders"]`
- 大屏名称和单屏尺寸：`MATRIX_CONFIG`

如果设备列表 API 未返回 MAC，请在 `config.py` 对应设备的 `mac` 字段中补充。大屏名称不再写死为 `VW3`，后端会从 `GetDisplayWallList` 解析平台已有大屏，按输出序号映射到 `显示器1/显示器2/显示器3`。

Web 控制台会复用一次登录获得的 token，不会在每次矩阵切换后调用 `Logout`。连续测试 `1v2.`、`2v2.` 时应直接复用当前会话继续下发矩阵指令。

### 简化调度流程

当前 Web 控制台按平台已有资源直接调度，不再自动创建大屏、绑定解码器、打开大屏、查询窗口或关闭旧窗口。一次 `1v1.` 调度只执行：

1. `Login` 登录并获取 token。
2. `GetEncoderList` 获取编码器列表，按输入序号选择编码器。
3. `GetDisplayWallList` 获取大屏列表，按输出序号选择大屏；参考 `docs/GetDisplayWallList.json`，输出 1/2/3 对应 `显示器1/显示器2/显示器3`。
4. 调用 `/mvapi/v1/wnd/OpenWnd`，例如 `1v1.` 使用 `display_wall="显示器1"`、`pos_x=0`、`pos_y=0`、`width=1920`、`height=1080`。
5. Web 页面通过本地 `/api/preview/ws?output=1` 代理获取视频流；代理连接上游
   `ws://192.168.130.101:8003/?display_wall=%E6%98%BE%E7%A4%BA%E5%99%A81`，并使用登录 token 作为 `Sec-WebSocket-Protocol`。

如果物理大屏窗口已确认存在，但 Web 页面上方预览黑屏，重点看日志里的
`输入N网页取流地址` 和 `输入N网页取流通道`。8003 取流地址需要携带当前大屏名，
例如输出 1 应连接 `ws://192.168.130.101:8003/?display_wall=%E6%98%BE%E7%A4%BA%E5%99%A81`；
只连接 `ws://192.168.130.101:8003` 会出现 TCP 可达但 WebSocket 握手超时。平台
WebSocket 握手还需要 `Sec-WebSocket-Protocol` 携带当前登录 token，前端会使用
本地 WebSocket 代理连接上游 8003，并把 `Origin` 固定为 API 服务地址
`http://192.168.130.101:8001`。代理还会把浏览器请求中的
`Sec-WebSocket-Extensions`、`User-Agent` 等握手头桥接到上游，保持与平台页面
抓包的取流请求一致。
平台有时会在编码器 MAC 中直接返回通道号，例如
`6c-df-fb-01-5e-80-00-01`，此时 WebSocket 取流通道应为
`6c-df-fb-01-5e-80-00-01/v3`，不能再拼成
`6c-df-fb-01-5e-80-00-01-00-01/v3`。当前代码会自动识别这种 8 段 MAC。

页面预览区会显示 WebSocket 取流状态：`未收到码流` 表示 8003 没有回帧；
`收到 H.265` 表示浏览器预览暂不能直接解码该流；`H.264 解码失败` 表示已收到
H.264 码流但浏览器 WebCodecs 解码失败。物理大屏和 Web 页面预览是两条链路，
物理大屏有画面但页面提示上述状态时，应优先处理浏览器取流/编码兼容问题。
Web 预览会自动尝试 `MATRIX_CONFIG["stream_versions"]` 中配置的取流版本，默认
按当前 `stream_channel_suffix` 的版本优先，再尝试 `/v1`、`/v2`、`/v3` 中剩余版本。
浏览器预览还会把诊断事件回传到本地后端日志，格式为
`预览事件: output=1, event=first_frame, channel=...`，可用于确认哪个通道收到帧、
收到的是 H.264 还是 H.265，以及最终是否解码成功。
如果日志出现 `预览取流端口检查 ... status=tcp_failed`，说明本机连不上
WebSocket 取流端口 `8003`，应检查服务器取流服务、防火墙或网络路由。
如果 TCP 可达但 `预览取流握手检查` 显示 `handshake_timeout` 或
`handshake_rejected`，说明 8003 端口不是正常响应浏览器 WebSocket Upgrade，
需要继续查取流服务的 WebSocket 握手要求、Origin 限制或连接路径。后端会分别
记录带 `Origin` 和不带 `Origin` 的握手结果：如果两者都是 `handshake_timeout`，
通常不是跨域限制，而是该端口未按标准 WebSocket 握手响应当前连接地址；首先确认
连接地址是否包含 `?display_wall=当前大屏名`。
