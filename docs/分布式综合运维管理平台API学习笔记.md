# 分布式综合运维管理平台API学习笔记

## 1. API概述

### 1.1 基本信息
- **传输协议**: HTTP
- **服务端口**: 8001
- **请求方法**: POST（所有请求）
- **请求体位置**: Body中传输
- **认证方式**: JWT令牌校验

### 1.2 API调用流程
1. 首先调用 `Login` 接口获取 token
2. 后续API请求需在HTTP Header中携带token
   - Key: "token"
   - Value: 获取到的令牌

## 2. 错误码表

| 错误码 | 说明 | 描述 |
|--------|------|------|
| 0 | success | 成功 |
| 1 | username or password error | 用户名或密码错误 |
| 2 | token parse failed | 令牌解析错误 |
| 3 | param parse failed | 参数解析错误 |
| 4 | unsupported request | 不支持的请求 |
| 5 | operate sql failed | 操作数据库失败 |
| 6 | server not connected | 服务器未连接 |
| 7 | page index out of range | 请求页码超出索引 |
| 8 | call sdk failed | SDK调用失败 |
| 9 | file upload failed | 文件上传失败 |
| 10 | read file failed | 读取文件失败 |
| 11 | update firmware to device failed | 升级固件到设备失败 |
| 12 | network error | 网络错误 |
| 13 | resource not exist | 资源不存在 |
| 14 | config device failed | 配置设备失败 |
| 15 | update license file failed | 升级授权文件失败 |
| 16 | permission denied | 权限不足 |
| 17 | get stream addr failed | 获取码流地址失败 |
| 18 | json data parse failed | 数据解析json错误 |
| 19 | user name repeat | 用户名重复 |
| 20 | display wall name repeat | 大屏名称重复 |
| 25 | exceed license | 授权不足 |
| 28 | set device ip conflicts | 设置设备IP存在冲突 |

## 3. 核心API模块

### 3.1 系统相关API

#### 3.1.1 登录 (Login)
- **URL**: `POST /mvapi/v1/Login`
- **请求参数**:
  - `username`: 用户名
  - `password`: MD5加密(密码+时间戳)
  - `timestamp`: 校验时间戳
- **响应字段**:
  - `result`: 字符串，处理结果说明（"success"表示成功，其他值为错误说明文）
  - `result_val`: 数字，处理结果码（0表示成功，其他值为错误码）
  - `right`: 用户权限（0-管理员）
  - `token`: 令牌
  - `route`: 用户权限路由

**注意**: 所有API响应都包含`result`和`result_val`字段，需要使用
`result == "success" or result_val == 0` 判断接口是否执行成功。

#### 3.1.2 修改密码 (ChangeUserPassword)
- **URL**: `POST /mvapi/v1/ChangeUserPassword`
- **请求参数**:
  - `username`: 用户名
  - `old_password`: 旧密码MD5
  - `new_password`: 新密码
  - `timestamp`: 时间戳

#### 3.1.3 退出登录 (Logout)
- **URL**: `POST /mvapi/v1/Logout`
- **请求参数**: 无

#### 3.1.4 获取任务进度 (GetTaskProgress)
- **URL**: `POST /mvapi/v1/GetTaskProgress`
- **请求参数**:
  - `id`: 任务ID
- **响应字段**:
  - `progress`: 任务进度百分比

### 3.2 设备信息API

#### 3.2.1 获取设备节点概览信息
- **URL**: `POST /mvapi/v1/device/GetDeviceOverView`
- **响应包含**:
  - 总编码器信息（总数、在线数、故障数、告警数）
  - 总解码器信息（总数、在线数、故障数、告警数）
  - 视频/音频编码器和解码器的详细统计

#### 3.2.2 获取大屏概览信息
- **URL**: `POST /mvapi/v1/device/GetDisplayWallOverView`
- **响应字段**:
  - `total_num`: 总数
  - `fault_num`: 故障数
  - `online_num`: 在线数

#### 3.2.3 获取编码器统计信息
- **URL**: `POST /mvapi/v1/device/GetEncoderSummary`
- **请求参数**:
  - `start`: 起始索引
  - `size`: 获取数量
- **响应包含**: 编码器列表（名称、IP、HDMI状态、在线状态）

#### 3.2.4 获取解码器统计信息
- **URL**: `POST /mvapi/v1/device/GetDecoderSummary`
- **参数与编码器类似**

### 3.3 编码器操作API

#### 3.3.1 获取编码器列表
- **URL**: `POST /mvapi/v1/encoder/GetEncoderList`
- **请求参数**:
  - `page_index`: 页码（起始为1）
  - `page_size`: 单页数量
  - `query_name`: 检索名称
  - `query_ip`: 检索IP
  - `filter`: 类型过滤器（encoder/audio_encoder/ipc）
  - `sort`: 排序条件（name/ip/type/status）
  - `order`: 排序方式（asc/desc）

#### 3.3.2 获取单个编码器详细信息
- **URL**: `POST /mvapi/v1/encoder/GetEncoderInfo`
- **请求参数**: `mac` - 编码器MAC地址
- **响应包含**: 完整的编码器配置信息（网络、音视频、OSD等）

#### 3.3.3 设置编码器信息
- **URL**: `POST /mvapi/v1/encoder/SetEncoderInfo`
- **可配置项**: 名称、网络配置、音视频参数、OSD设置等

#### 3.3.4 其他编码器操作
- **设置服务器IP**: `/mvapi/v1/encoder/SetEncoderServerIP`
- **设置组**: `/mvapi/v1/encoder/SetEncoderGroup`
- **重启编码器**: `/mvapi/v1/encoder/RebootEncoder`
- **复位编码器**: `/mvapi/v1/encoder/ReSetEncoder`
- **删除编码器**: `/mvapi/v1/encoder/DeleteEncoder`
- **设置音量**: `/mvapi/v1/encoder/SetEncoderVolume`
- **调节音量**: `/mvapi/v1/encoder/AdjustEncoderVolume`
- **固件上传**: `/mvapi/v1/encoder/UploadEncoderFirmware`
- **固件更新**: `/mvapi/v1/encoder/UpdateEncoderFirmware`

### 3.4 解码器操作API

#### 3.4.1 获取解码器列表
- **URL**: `POST /mvapi/v1/decoder/GetDecoderList`
- **参数与编码器列表类似**

#### 3.4.2 获取单个解码器详细信息
- **URL**: `POST /mvapi/v1/decoder/GetDecoderInfo`
- **响应包含**: 分辨率、解码类型、音频设置、网络配置、OSD设置等

#### 3.4.3 设置解码器信息
- **URL**: `POST /mvapi/v1/decoder/SetDecoderInfo`
- **可配置项**: 名称、分辨率、音视频参数、网络等

#### 3.4.4 设置测试模式
- **URL**: `POST /mvapi/v1/decoder/SetDecoderTestMode`
- **测试模式**: 0-关闭, 1-灰阶, 2-彩条, 3-几何, 4-信息, 5-白色, 6-红色, 7-绿色, 8-蓝色

### 3.5 大屏幕墙操作API

#### 3.5.1 获取大屏幕墙列表
- **URL**: `POST /mvapi/v1/displaywall/GetDisplayWallList`
- **请求参数**:
  - `page_index`, `page_size`: 分页
  - `query_name`: 检索名称
  - `query_specification`: 检索规格（如"2*3"）
  - `filter`: 类型过滤（0-DLP, 1-LED）
  - `sort`: 排序条件
  - `order`: 排序方式

#### 3.5.2 获取单个大屏详细信息
- **URL**: `POST /mvapi/v1/displaywall/GetDisplayWallInfo`
- **响应包含**: 规格、分辨率、类型、状态、创建时间、补偿设置等

#### 3.5.3 创建大屏幕墙
- **URL**: `POST /mvapi/v1/displaywall/CreateDisplayWall`
- **请求参数**:
  - `name`: 大屏名称
  - `row`, `column`: 行列数
  - `resolution_x`, `resolution_y`: 分辨率
  - `factory`: 制造商（协议）
  - `com`: 控制方式
  - `fusion_band`: 前投影融合带
  - `lcd_frame`: 液晶边框
  - `border_clipping`: 裁剪像素数

#### 3.5.4 编辑大屏幕墙
- **URL**: `POST /mvapi/v1/displaywall/EditDisplayWall`
- **可修改**: 名称、规格、分辨率、补偿设置等

#### 3.5.5 创建LED大屏
- **URL**: `POST /mvapi/v1/displaywall/CreateLedDisplayWall`
- **特殊参数**: 大屏整体分辨率（非单元分辨率）

#### 3.5.6 删除大屏幕墙
- **URL**: `POST /mvapi/v1/displaywall/DeleteDisplayWall`
- **请求参数**: `display_wall` 数组，包含大屏名称

#### 3.5.7 大屏绑定解码器
- **绑定视频解码器**: `/mvapi/v1/displaywall/BindDecoder`
- **绑定音频解码器**: `/mvapi/v1/displaywall/BindAudioDecoder`
- **解绑解码器**: `/mvapi/v1/displaywall/UnBindDecoder`
- **获取可用解码器**: `/mvapi/v1/displaywall/GetAvailableDecoders`
- **获取已绑定解码器**: `/mvapi/v1/displaywall/GetDispWallDecoderList`

#### 3.5.8 大屏控制操作
- **打开大屏**: `/mvapi/v1/displaywall/OpenDisplayWall`
- **关闭大屏**: `/mvapi/v1/displaywall/CloseDisplayWall`
- **打开音频**: `/mvapi/v1/displaywall/OpenAudio`
- **关闭音频**: `/mvapi/v1/displaywall/CloseAudio`
- **设置音量**: `/mvapi/v1/displaywall/SetDisplayWallVolume`
- **调节音量**: `/mvapi/v1/displaywall/SetDisplayWallVolume2`
- **上传底图**: `/mvapi/v1/displaywall/UploadBasePicture`
- **更新底图**: `/mvapi/v1/displaywall/UpdateBasePicture`

#### 3.5.9 大屏操作模式
- **设置操作模式**: `/mvapi/v1/displaywall/SetDisplayWallOptMode`
  - 0: 自由模式
  - 1: 替换操作模式

### 3.6 窗口操作API

#### 3.6.1 获取大屏所有窗口信息
- **URL**: `POST /mvapi/v1/wnd/GetDisplayWallWnds`
- **响应包含**: 窗口列表（信号源、位置、大小、层次等）

#### 3.6.2 开窗
- **URL**: `POST /mvapi/v1/wnd/OpenWnd`
- **请求参数**:
  - `display_wall`: 大屏名称
  - `src_mac`: 信号源MAC
  - `pos_x`, `pos_y`: 窗口位置
  - `width`, `height`: 窗口大小
- **注意**: 位置和大小必须为偶数，最小窗口128×96

#### 3.6.3 移动窗口
- **移动位置**: `/mvapi/v1/wnd/MoveWnd`
- **移动至全屏**: `/mvapi/v1/wnd/MoveWndToFullScreen`

#### 3.6.4 窗口其他操作
- **调整层次**: `/mvapi/v1/wnd/AdjustWndLayer`
- **替换信号源**: `/mvapi/v1/wnd/ReplaceWndSource`
- **关闭单个窗口**: `/mvapi/v1/wnd/CloseWnd`
- **关闭所有窗口**: `/mvapi/v1/wnd/CloseAllWnds`
- **撤销/重做**: `/mvapi/v1/wnd/Undo`, `/mvapi/v1/wnd/Redo`
- **获取撤销重做状态**: `/mvapi/v1/wnd/GetDisplayWallOperateStatus`

### 3.7 预案操作API

#### 3.7.1 预案类型
- **普通预案**: 保存窗口布局
- **自动预案**: 由多个普通预案组成，自动轮播

#### 3.7.2 预案操作
- **获取预案列表**: `/mvapi/v1/layout/GetLayoutList`
- **获取普通预案详情**: `/mvapi/v1/layout/GetLayoutInfo`
- **获取自动预案详情**: `/mvapi/v1/layout/GetAutoLayoutInfo`
- **保存普通预案**: `/mvapi/v1/layout/SaveLayout`
- **保存自动预案**: `/mvapi/v1/layout/SaveAutoLayout`
- **编辑预案**: `/mvapi/v1/layout/EditLayout`
- **编辑自动预案**: `/mvapi/v1/layout/EditAutoLayout`
- **删除预案**: `/mvapi/v1/layout/DeleteLayout`
- **加载预案**: `/mvapi/v1/layout/LoadLayout`
- **停止自动预案**: `/mvapi/v1/layout/StopAutoLayout`

### 3.8 跑马灯操作API

#### 3.8.1 跑马灯属性
- **基本属性**: 名称、位置、大小、对齐方式、透明设置
- **背景**: 背景色
- **字体**: 文本、字体、字重、字号、颜色
- **图片**: 图片URL和名称
- **动作**: 静态/动态显示、移动方向、移动速度

#### 3.8.2 跑马灯操作
- **获取列表**: `/mvapi/v1/marquee/GetMarqueeList`
- **获取详情**: `/mvapi/v1/marquee/GetMarqueeInfo`
- **新建**: `/mvapi/v1/marquee/CreateMarquee`
- **编辑**: `/mvapi/v1/marquee/EditMarquee`
- **删除**: `/mvapi/v1/marquee/DeleteMarquee`
- **上传图片**: `/mvapi/v1/marquee/UploadMarqueePicture`
- **上传到大屏**: `/mvapi/v1/marquee/UploadMarquee`
- **打开**: `/mvapi/v1/marquee/OpenMarquee`
- **关闭**: `/mvapi/v1/marquee/StopMarquee`

### 3.9 逻辑阵列操作API

#### 3.9.1 逻辑阵列概念
将多个编码器组合成一个逻辑编码器

#### 3.9.2 操作接口
- **获取列表**: `/mvapi/v1/logicencoder/GetLogicEncoderList`
- **创建**: `/mvapi/v1/logicencoder/CreateLogicEncoder`
- **获取可用编码器**: `/mvapi/v1/logicencoder/GetAvailableEncoder`
- **编辑**: `/mvapi/v1/logicencoder/EditLogicEncoder`
- **删除**: `/mvapi/v1/logicencoder/DeleteLogicEncoder`

### 3.10 中控操作API

#### 3.10.1 中控信息
- **COM口**: 8个COM口配置
- **IO口**: 8个IO口配置
- **继电器**: 8个继电器配置

#### 3.10.2 操作接口
- **获取列表**: `/mvapi/v1/ctrlboard/GetCtrlBoardList`
- **获取详情**: `/mvapi/v1/ctrlboard/GetCtrlBoardInfo`
- **发送消息**: `/mvapi/v1/ctrlboard/SendMessageToCtrlBoard`

### 3.11 用户操作API

#### 3.11.1 用户角色
- 0: 超级管理员
- 1: 管理员
- 2: 大屏调度员
- 3: 运维管理员
- 4: 运维监测员

#### 3.11.2 用户操作
- **获取用户列表**: `/mvapi/v1/user/GetUserList`
- **获取创建者列表**: `/mvapi/v1/user/GetAllCreator`
- **获取目录树**: `/mvapi/v1/user/GetFolderTree`
- **获取资源列表**: `/mvapi/v1/user/GetFolderResourceList`
- **创建用户**: `/mvapi/v1/user/CreateUser`
- **编辑用户资源**: `/mvapi/v1/user/EditUserSource`
- **删除用户**: `/mvapi/v1/user/DeleteUser`

### 3.12 资源分组操作API

#### 3.12.1 目录类型
- 0: 视频信号
- 1: 逻辑处理器
- 2: 预案
- 3: 跑马灯
- 4: 音频
- 5: 只要编码器
- 6: 只要IPC

#### 3.12.2 操作接口
- **获取文件夹资源**: `/mvapi/v1/organization/GetFolderResource`
- **创建文件夹**: `/mvapi/v1/organization/CreateFolder`
- **删除文件夹**: `/mvapi/v1/organization/DeleteFolder`
- **重命名文件夹**: `/mvapi/v1/organization/RenameFolder`
- **移动资源**: `/mvapi/v1/organization/MoveResource`
- **移动文件夹**: `/mvapi/v1/organization/MoveFolder`

## 4. WebSocket取流

### 4.1 连接信息
- **端口**: 8003
- **协议**: WebSocket
- **连接地址**: `ws://<服务器IP>:8003`

### 4.2 取流步骤
1. 连接WebSocket服务器
2. 发送取流信息头（JSON格式）:
```json
{
  "a": "",
  "a2": "21",  // 信号源名称
  "c": "00-40-01-2b-05-27-00-01/v3",  // MAC/码流
  "s": "http://192.168.0.100:8001",  // API服务器
  "t": "open"  // 操作: open/close
}
```
3. 服务器返回码流数据

### 4.3 码流数据格式
每帧数据包含:
- 码流版本 (2 byte): v1/v2/v3
- 码流类型 (1 byte): 1-视频, 2-音频
- 帧序列 (4 byte)
- 宽度 (2 byte)
- 高度 (2 byte)
- 编码方式 (1 byte): 2-H.264, 3-H.265
- 帧类型 (1 byte): 1-I帧, 2-P帧
- 时间戳 (4 byte)
- 数据 (n byte)

## 5. 重要注意事项

### 5.1 认证与安全
- 所有API调用前必须先登录获取token
- Token需在HTTP Header中携带
- Token过期后需重新登录

### 5.2 分页处理
- 页码从1开始
- 需指定page_index和page_size
- 响应包含page_num（总页数）和total_num（总数量）

### 5.3 设备类型标识
- 编码器类型: 2-视频编码器, 4-多媒体编码器, 12-IPC, 5-软编, 23-7000编码器, 50-音频编码器
- 解码器类型: 3-解码器, 51-音频解码器
- 大屏类型: 0-DLP, 1-LED

### 5.4 状态码
- 设备状态: 0-离线, 1-在线
- HDMI状态: 0-未连接, 1-已连接
- 大屏状态: 0-关闭, 1-开启, -1-未选择协议

### 5.5 操作模式
- mode参数: 0-全选, 1-勾选
- 全选模式: 需提供device1（反选列表）
- 勾选模式: 需提供device2（选中列表）

### 5.6 窗口操作限制
- 窗口位置和大小参数必须为偶数
- 窗口最小尺寸: 128×96
- 替换窗口信号源会导致handle改变

### 5.7 固件更新
- 先上传固件文件
- 再调用更新接口
- 通过任务ID查询更新进度

## 6. 常见使用场景

### 6.1 初始化流程
1. 登录获取token
2. 获取设备概览信息
3. 获取大屏列表
4. 获取编码器/解码器列表

### 6.2 大屏显示流程
1. 创建或选择大屏
2. 绑定解码器到大屏
3. 打开大屏
4. 开窗显示信号源
5. 调整窗口位置和大小

### 6.3 预案使用流程
1. 配置好窗口布局
2. 保存为普通预案
3. 组合多个普通预案为自动预案
4. 加载预案到大屏
5. 停止自动预案

### 6.4 设备管理流程
1. 获取设备列表
2. 查看设备详细信息
3. 配置设备参数
4. 监控设备状态
5. 设备固件更新

## 7. 开发建议

### 7.1 错误处理
- 每次API调用后检查 `result == "success" or result_val == 0`
- 根据错误码进行相应处理
- Token过期需重新登录

### 7.2 性能优化
- 合理使用分页避免一次性加载大量数据
- 定期轮询设备状态而非实时查询
- 批量操作使用全选/勾选模式

### 7.3 用户体验
- 长时间操作提供进度查询
- 关键操作前验证权限
- 提供操作撤销/重做功能

### 7.4 安全性
- 密码使用MD5加密
- 敏感操作验证用户权限
- Token妥善保管避免泄露

---

**文档版本**: v1.0  
**创建时间**: 2026-08-21  
**适用范围**: 分布式综合运维管理平台API集成开发
