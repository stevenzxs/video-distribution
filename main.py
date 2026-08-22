"""
分布式综合运维管理平台API测试工具
"""
import sys
import logging
from api_client import APIClient, format_api_error, is_success_response
from config import TEST_USER, LOG_LEVEL, LOG_FORMAT

# 配置日志
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


def print_section(title: str):
    """打印分节标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def check_basic_connection():
    """测试基本连接和认证"""
    print_section("1. 基础连接测试")

    client = APIClient()

    # 测试登录
    print("\n正在登录...")
    success = client.login(TEST_USER["username"], TEST_USER["password"])

    if not success:
        print("❌ 登录失败！请检查用户名密码和服务器连接")
        return None

    print(f"✓ 登录成功！Token: {client.token[:20]}...")

    # 获取API版本
    print("\n正在获取API版本...")
    result = client.get_api_version()
    if is_success_response(result):
        print(f"✓ API服务器版本: {result.get('api_server_version')}")
    else:
        print(f"❌ 获取版本失败 {format_api_error(result)}")

    return client


def check_device_overview(client: APIClient):
    """测试设备概览"""
    print_section("2. 设备概览")

    print("\n正在获取设备概览...")
    result = client.get_device_overview()

    if not is_success_response(result):
        print(f"❌ 获取失败 {format_api_error(result)}")
        return

    # 编码器信息
    if "encoders" in result:
        encoders = result["encoders"]
        print(f"\n📹 编码器:")
        print(f"   总数: {encoders.get('total_num', 0)}")
        print(f"   在线: {encoders.get('online_num', 0)}")
        print(f"   故障: {encoders.get('fault_num', 0)}")
        print(f"   告警: {encoders.get('warn_num', 0)}")

        if "video_encoder" in encoders:
            ve = encoders["video_encoder"]
            print(f"   └─ 视频编码器: 在线 {ve.get('online_num', 0)} / 离线 {ve.get('offline_num', 0)}")

        if "audio_encoder" in encoders:
            ae = encoders["audio_encoder"]
            print(f"   └─ 音频编码器: 在线 {ae.get('online_num', 0)} / 离线 {ae.get('offline_num', 0)}")

    # 解码器信息
    if "decoders" in result:
        decoders = result["decoders"]
        print(f"\n🖥️  解码器:")
        print(f"   总数: {decoders.get('total_num', 0)}")
        print(f"   在线: {decoders.get('online_num', 0)}")
        print(f"   故障: {decoders.get('fault_num', 0)}")
        print(f"   告警: {decoders.get('warn_num', 0)}")

        if "video_encoder" in decoders:
            vd = decoders["video_encoder"]
            print(f"   └─ 视频解码器: 在线 {vd.get('online_num', 0)} / 离线 {vd.get('offline_num', 0)}")

        if "audio_encoder" in decoders:
            ad = decoders["audio_encoder"]
            print(f"   └─ 音频解码器: 在线 {ad.get('online_num', 0)} / 离线 {ad.get('offline_num', 0)}")


def check_encoder_list(client: APIClient):
    """测试编码器列表"""
    print_section("3. 编码器列表")

    print("\n正在获取编码器列表...")
    result = client.get_encoder_list(page_index=1, page_size=20)

    if not is_success_response(result):
        print(f"❌ 获取失败 {format_api_error(result)}")
        return

    total = result.get("total_num", 0)
    print(f"\n✓ 共找到 {total} 个编码器")

    if "encoders" in result and result["encoders"]:
        print("\n编码器列表:")
        print("-" * 100)
        print(f"{'序号':<6} {'名称':<20} {'IP地址':<18} {'状态':<8} {'HDMI':<8} {'类型':<12}")
        print("-" * 100)

        for encoder in result["encoders"]:
            idx = encoder.get("index", "")
            name = encoder.get("name", "未命名")[:18]
            ip = encoder.get("ip", "N/A")
            status = "🟢 在线" if encoder.get("status") == 1 else "🔴 离线"
            hdmi = "✓ 已连接" if encoder.get("hdmi_status") == 1 else "✗ 未连接"

            # 类型映射
            type_map = {
                2: "视频编码器",
                4: "多媒体编码器",
                12: "IPC",
                5: "软编",
                23: "7000编码器",
                50: "音频编码器"
            }
            enc_type = type_map.get(encoder.get("type"), f"类型{encoder.get('type')}")

            print(f"{idx:<6} {name:<20} {ip:<18} {status:<8} {hdmi:<8} {enc_type:<12}")
    else:
        print("\n⚠️  未找到编码器")


def check_decoder_list(client: APIClient):
    """测试解码器列表"""
    print_section("4. 解码器列表")

    print("\n正在获取解码器列表...")
    result = client.get_decoder_list(page_index=1, page_size=20)

    if not is_success_response(result):
        print(f"❌ 获取失败 {format_api_error(result)}")
        return

    total = result.get("total_num", 0)
    print(f"\n✓ 共找到 {total} 个解码器")

    if "decoders" in result and result["decoders"]:
        print("\n解码器列表:")
        print("-" * 80)
        print(f"{'序号':<6} {'名称':<20} {'IP地址':<18} {'状态':<8} {'类型':<12}")
        print("-" * 80)

        for decoder in result["decoders"]:
            idx = decoder.get("index", "")
            name = decoder.get("name", "未命名")[:18]
            ip = decoder.get("ip", "N/A")
            status = "🟢 在线" if decoder.get("status") == 1 else "🔴 离线"

            # 类型映射
            type_map = {
                3: "解码器",
                51: "音频解码器"
            }
            dec_type = type_map.get(decoder.get("type"), f"类型{decoder.get('type')}")

            print(f"{idx:<6} {name:<20} {ip:<18} {status:<8} {dec_type:<12}")
    else:
        print("\n⚠️  未找到解码器")


def check_display_wall_list(client: APIClient):
    """测试大屏列表"""
    print_section("5. 大屏列表")

    print("\n正在获取大屏列表...")
    result = client.get_display_wall_list(page_index=1, page_size=20)

    if not is_success_response(result):
        print(f"❌ 获取失败 {format_api_error(result)}")
        return

    total = result.get("total_num", 0)
    print(f"\n✓ 共找到 {total} 个大屏")

    if "display_walls" in result and result["display_walls"]:
        print("\n大屏列表:")
        print("-" * 100)
        print(f"{'序号':<6} {'名称':<20} {'规格':<12} {'分辨率':<20} {'类型':<8} {'状态':<8}")
        print("-" * 100)

        for wall in result["display_walls"]:
            idx = wall.get("index", "")
            name = wall.get("name", "未命名")[:18]
            spec = f"{wall.get('row', 0)}x{wall.get('column', 0)}"
            resolution = f"{wall.get('resolution_x', 0)}x{wall.get('resolution_y', 0)}"
            wall_type = "DLP" if wall.get("type") == 0 else "LED"
            status = "🟢 开启" if wall.get("status") == 1 else "🔴 关闭"

            print(f"{idx:<6} {name:<20} {spec:<12} {resolution:<20} {wall_type:<8} {status:<8}")
    else:
        print("\n⚠️  未找到大屏")


def check_layout_list(client: APIClient):
    """测试预案列表"""
    print_section("6. 预案列表")

    print("\n正在获取预案列表...")
    result = client.get_layout_list(page_index=1, page_size=20)

    if not is_success_response(result):
        print(f"❌ 获取失败 {format_api_error(result)}")
        return

    total = result.get("total_num", 0)
    print(f"\n✓ 共找到 {total} 个预案")

    if "layouts" in result and result["layouts"]:
        print("\n预案列表:")
        print("-" * 60)
        print(f"{'名称':<30} {'类型':<20}")
        print("-" * 60)

        for layout in result["layouts"]:
            name = layout.get("name", "未命名")[:28]
            layout_type = "📋 普通预案" if layout.get("type") == 0 else "🔄 自动预案"

            print(f"{name:<30} {layout_type:<20}")
    else:
        print("\n⚠️  未找到预案")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("  分布式综合运维管理平台 API 测试工具")
    print("=" * 60)

    try:
        # 1. 测试基本连接
        client = check_basic_connection()
        if not client:
            return 1

        # 2. 测试设备概览
        check_device_overview(client)

        # 3. 测试编码器列表
        check_encoder_list(client)

        # 4. 测试解码器列表
        check_decoder_list(client)

        # 5. 测试大屏列表
        check_display_wall_list(client)

        # 6. 测试预案列表
        check_layout_list(client)

        # 退出登录
        print_section("测试完成")
        print("\n正在退出登录...")
        client.logout()
        print("✓ 已退出")

        print("\n" + "=" * 60)
        print("  🎉 所有测试完成！")
        print("=" * 60 + "\n")

        return 0

    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
        return 1
    except Exception as e:
        print(f"\n\n❌ 测试过程中发生错误: {e}")
        logger.exception("测试异常")
        return 1


if __name__ == "__main__":
    sys.exit(main())
