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

**最后更新**: 2026-08-21

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

如果设备列表 API 未返回 MAC，请在 `config.py` 对应设备的 `mac` 字段中补充。`MATRIX_CONFIG["display_wall_name"]` 留空时，后端会使用平台返回的第一个大屏。
