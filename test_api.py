"""
API测试套件
"""
import pytest
import logging
from api_client import APIClient, format_api_error, is_success_response
from config import TEST_USER, DEVICES, LOG_LEVEL, LOG_FORMAT

# 配置日志
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


class TestBasicAPI:
    """基础API测试"""

    @pytest.fixture(scope="class")
    def client(self):
        """创建API客户端实例"""
        client = APIClient()
        return client

    @pytest.fixture(scope="class")
    def authenticated_client(self, client):
        """创建已认证的客户端"""
        success = client.login(TEST_USER["username"], TEST_USER["password"])
        assert success, "登录失败"
        yield client
        # 测试结束后退出登录
        client.logout()

    def test_login(self, client):
        """测试登录功能"""
        result = client.login(TEST_USER["username"], TEST_USER["password"])
        assert result is True, "登录失败"
        assert client.token is not None, "未获取到token"
        logger.info("✓ 登录测试通过")

    def test_get_api_version(self, authenticated_client):
        """测试获取API版本"""
        result = authenticated_client.get_api_version()
        assert is_success_response(result), f"获取版本失败 {format_api_error(result)}"
        assert "api_server_version" in result
        logger.info(f"✓ API版本: {result.get('api_server_version')}")

    def test_logout(self, client):
        """测试退出登录"""
        client.login(TEST_USER["username"], TEST_USER["password"])
        result = client.logout()
        assert is_success_response(result), f"退出登录失败 {format_api_error(result)}"
        assert client.token is None, "token未清除"
        logger.info("✓ 退出登录测试通过")


class TestDeviceAPI:
    """设备相关API测试"""

    @pytest.fixture(scope="class")
    def client(self):
        """创建并登录客户端"""
        client = APIClient()
        client.login(TEST_USER["username"], TEST_USER["password"])
        yield client
        client.logout()

    def test_get_device_overview(self, client):
        """测试获取设备概览"""
        result = client.get_device_overview()
        assert is_success_response(result), f"获取设备概览失败 {format_api_error(result)}"

        # 检查编码器信息
        if "encoders" in result:
            encoders = result["encoders"]
            logger.info(f"✓ 编码器总数: {encoders.get('total_num', 0)}")
            logger.info(f"  在线: {encoders.get('online_num', 0)}, 故障: {encoders.get('fault_num', 0)}")

        # 检查解码器信息
        if "decoders" in result:
            decoders = result["decoders"]
            logger.info(f"✓ 解码器总数: {decoders.get('total_num', 0)}")
            logger.info(f"  在线: {decoders.get('online_num', 0)}, 故障: {decoders.get('fault_num', 0)}")

    def test_get_display_wall_overview(self, client):
        """测试获取大屏概览"""
        result = client.get_display_wall_overview()
        assert is_success_response(result), f"获取大屏概览失败 {format_api_error(result)}"
        logger.info(f"✓ 大屏总数: {result.get('total_num', 0)}")

    def test_get_encoder_summary(self, client):
        """测试获取编码器统计"""
        result = client.get_encoder_summary(start=0, size=10)
        assert is_success_response(result), f"获取编码器统计失败 {format_api_error(result)}"

        total = result.get("total_num", 0)
        logger.info(f"✓ 编码器统计: 共 {total} 个")

        if "encoders" in result and result["encoders"]:
            for encoder in result["encoders"][:3]:  # 只显示前3个
                logger.info(f"  - {encoder.get('name')}: {encoder.get('ip')} (状态: {'在线' if encoder.get('status') == 1 else '离线'})")

    def test_get_decoder_summary(self, client):
        """测试获取解码器统计"""
        result = client.get_decoder_summary(start=0, size=10)
        assert is_success_response(result), f"获取解码器统计失败 {format_api_error(result)}"

        total = result.get("total_num", 0)
        logger.info(f"✓ 解码器统计: 共 {total} 个")

        if "decoders" in result and result["decoders"]:
            for decoder in result["decoders"][:3]:
                logger.info(f"  - {decoder.get('name')}: {decoder.get('ip')} (状态: {'在线' if decoder.get('status') == 1 else '离线'})")


class TestEncoderAPI:
    """编码器操作API测试"""

    @pytest.fixture(scope="class")
    def client(self):
        """创建并登录客户端"""
        client = APIClient()
        client.login(TEST_USER["username"], TEST_USER["password"])
        yield client
        client.logout()

    def test_get_encoder_list(self, client):
        """测试获取编码器列表"""
        result = client.get_encoder_list(page_index=1, page_size=20)
        assert is_success_response(result), f"获取编码器列表失败 {format_api_error(result)}"

        logger.info(f"✓ 编码器列表: 总页数 {result.get('page_num', 0)}, 总数 {result.get('total_num', 0)}")

        if "encoders" in result and result["encoders"]:
            logger.info(f"  当前页显示 {len(result['encoders'])} 个编码器")
            return result["encoders"]
        return []

    def test_get_encoder_list_with_filter(self, client):
        """测试带过滤条件的编码器列表"""
        # 测试按名称检索
        for device in DEVICES["encoders"]:
            result = client.get_encoder_list(query_name=device["name"])
            if is_success_response(result):
                logger.info(f"✓ 检索编码器 '{device['name']}': 找到 {result.get('total_num', 0)} 个")


class TestDecoderAPI:
    """解码器操作API测试"""

    @pytest.fixture(scope="class")
    def client(self):
        """创建并登录客户端"""
        client = APIClient()
        client.login(TEST_USER["username"], TEST_USER["password"])
        yield client
        client.logout()

    def test_get_decoder_list(self, client):
        """测试获取解码器列表"""
        result = client.get_decoder_list(page_index=1, page_size=20)
        assert is_success_response(result), f"获取解码器列表失败 {format_api_error(result)}"

        logger.info(f"✓ 解码器列表: 总页数 {result.get('page_num', 0)}, 总数 {result.get('total_num', 0)}")

        if "decoders" in result and result["decoders"]:
            logger.info(f"  当前页显示 {len(result['decoders'])} 个解码器")


class TestDisplayWallAPI:
    """大屏操作API测试"""

    @pytest.fixture(scope="class")
    def client(self):
        """创建并登录客户端"""
        client = APIClient()
        client.login(TEST_USER["username"], TEST_USER["password"])
        yield client
        client.logout()

    def test_get_display_wall_list(self, client):
        """测试获取大屏列表"""
        result = client.get_display_wall_list(page_index=1, page_size=20)
        assert is_success_response(result), f"获取大屏列表失败 {format_api_error(result)}"

        logger.info(f"✓ 大屏列表: 总页数 {result.get('page_num', 0)}, 总数 {result.get('total_num', 0)}")

        if "display_walls" in result and result["display_walls"]:
            for wall in result["display_walls"]:
                logger.info(f"  - {wall.get('name')}: {wall.get('row')}x{wall.get('column')} (类型: {'DLP' if wall.get('type') == 0 else 'LED'})")


class TestLayoutAPI:
    """预案操作API测试"""

    @pytest.fixture(scope="class")
    def client(self):
        """创建并登录客户端"""
        client = APIClient()
        client.login(TEST_USER["username"], TEST_USER["password"])
        yield client
        client.logout()

    def test_get_layout_list(self, client):
        """测试获取预案列表"""
        result = client.get_layout_list(page_index=1, page_size=20)
        assert is_success_response(result), f"获取预案列表失败 {format_api_error(result)}"

        logger.info(f"✓ 预案列表: 总页数 {result.get('page_num', 0)}, 总数 {result.get('total_num', 0)}")

        if "layouts" in result and result["layouts"]:
            for layout in result["layouts"]:
                layout_type = "普通预案" if layout.get("type") == 0 else "自动预案"
                logger.info(f"  - {layout.get('name')} ({layout_type})")


if __name__ == "__main__":
    # 直接运行时执行所有测试
    pytest.main([__file__, "-v", "-s"])
