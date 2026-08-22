"""
快速API连通性测试脚本
用于快速验证API服务器是否可访问
"""
import sys
import io
import requests
import hashlib
import time
from api_client import format_api_error, is_success_response
from config import API_BASE_URL, TEST_USER

# 修复Windows控制台编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


def test_connection():
    """测试基本连接"""
    print("=" * 60)
    print("  快速连通性测试")
    print("=" * 60)

    print(f"\n目标服务器: {API_BASE_URL}")
    print(f"用户名: {TEST_USER['username']}")

    # 1. 测试服务器可达性
    print("\n[1/3] 测试服务器连接...")
    try:
        response = requests.get(API_BASE_URL, timeout=5)
        print(f"✓ 服务器响应: HTTP {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("❌ 连接失败: 无法连接到服务器")
        print("   请检查:")
        print("   1. 服务器IP地址是否正确")
        print("   2. 服务器是否正常运行")
        print("   3. 网络连接是否正常")
        return False
    except requests.exceptions.Timeout:
        print("❌ 连接超时: 服务器响应超时")
        return False
    except Exception as e:
        print(f"❌ 未知错误: {e}")
        return False

    # 2. 测试登录接口
    print("\n[2/3] 测试登录接口...")
    login_url = f"{API_BASE_URL}/mvapi/v1/Login"

    timestamp = str(int(time.time()))
    password = TEST_USER['password'] + timestamp
    encrypted_password = hashlib.md5(password.encode()).hexdigest().lower()

    login_data = {
        "username": TEST_USER['username'],
        "password": encrypted_password,
        "timestamp": timestamp
    }

    try:
        response = requests.post(
            login_url,
            json=login_data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=10
        )

        if response.status_code != 200:
            print(f"❌ HTTP错误: {response.status_code}")
            return False

        result = response.json()

        if is_success_response(result):
            print("✓ 登录成功!")
            print(f"  Token: {result.get('token')[:30]}...")
            print(f"  权限: {'管理员' if result.get('right') == 0 else '普通用户'}")

            # 3. 测试获取版本信息
            print("\n[3/3] 测试API版本接口...")
            version_url = f"{API_BASE_URL}/mvapi/v1/GetAPIServerInfo"

            version_response = requests.post(
                version_url,
                json={},
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "token": result.get('token')
                },
                timeout=10
            )

            if version_response.status_code == 200:
                version_result = version_response.json()
                if is_success_response(version_result):
                    print(f"✓ API版本: {version_result.get('api_server_version')}")
                else:
                    print(f"⚠️  获取版本失败 {format_api_error(version_result)}")

            print("\n" + "=" * 60)
            print("  🎉 API连通性测试通过!")
            print("=" * 60)
            print("\n可以运行以下命令进行完整测试:")
            print("  python main.py          # 运行主程序")
            print("  pytest test_api.py -v   # 运行单元测试")
            return True

        else:
            error_messages = {
                1: "用户名或密码错误",
                2: "Token解析错误",
                6: "服务器未连接",
            }
            error_code = result.get("result_val")
            error_msg = error_messages.get(error_code, result.get("result"))
            print(f"❌ 登录失败 [code:{error_code}]: {error_msg}")
            print("   请检查config.py中的用户名和密码配置")
            return False

    except requests.exceptions.Timeout:
        print("❌ 请求超时")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求异常: {e}")
        return False
    except ValueError as e:
        print(f"❌ 响应解析失败: {e}")
        print(f"   响应内容: {response.text[:200]}")
        return False


if __name__ == "__main__":
    import sys
    success = test_connection()
    sys.exit(0 if success else 1)
