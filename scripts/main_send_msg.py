import json
import time
import base64
import os
import uuid
from pathlib import Path
import sys

try:
    from wechat_common import (
        find_account_json,
        find_weixin_account,
        get_hermes_path,
        get_openclaw_path,
        load_account_credentials,
        print_auto_discovery_help,
    )
except ImportError:
    sys.path.append(str(Path(__file__).resolve().parent))
    from wechat_common import (
        find_account_json,
        find_weixin_account,
        get_hermes_path,
        get_openclaw_path,
        load_account_credentials,
        print_auto_discovery_help,
    )

def send_weixin_message(BASE_URL,BOT_TOKEN,TARGET_USER_ID,CONTEXT_TOKEN,TXT_MSG):
    """
    通过微信后端API发送一条文本测试消息。
    """
    try:
        import requests
    except ImportError:
        print("❌ 缺少依赖 requests，请先执行: pip install -r requirements.txt")
        return False

    # 1. 构建请求URL (关键：端点路径为 /ilink/bot/sendmessage)
    api_endpoint = f"{BASE_URL.rstrip('/')}/ilink/bot/sendmessage"
    
    # 2. 生成请求唯一标识 (client_id) 和随机UIN
    timestamp_ms = int(time.time() * 1000)
    random_suffix = uuid.uuid4().hex[:8]
    client_id = f"openclaw-weixin:{timestamp_ms}-{random_suffix}"
    random_uint32 = os.urandom(4)
    x_wechat_uin = base64.b64encode(random_uint32).decode('utf-8')
    
    # 3. 构建请求体 (JSON)
    payload = {
        "msg": {
            "from_user_id": "",  # 机器人发送时固定为空字符串
            "to_user_id": TARGET_USER_ID,
            "client_id": client_id,
            "message_type": 2,   # 固定为2，代表Bot消息
            "message_state": 2,  # 固定为2，代表完成态
            "context_token": CONTEXT_TOKEN,  # 重要：如果为空，首次发送可能失败
            "item_list": [
                {
                    "type": 1,  # 1 代表文本消息
                    "text_item": {
                        "text": TXT_MSG
                    }
                }
            ]
        },
        "base_info": {
            "channel_version": "1.0.0"  # 应与您的信道插件版本一致
        }
    }
    # 4. 构建请求头
    raw = json.dumps(payload, ensure_ascii=False)  
    headers = {  
    "Content-Type": "application/json",  
    "AuthorizationType": "ilink_bot_token",  
    "Authorization": f"Bearer {BOT_TOKEN}",  
    "X-WECHAT-UIN": x_wechat_uin,  
    "Content-Length": str(len(raw.encode("utf-8"))),  
    }  
    print("=" * 50)
    print("【微信消息发送测试】")
    print(f"目标用户: {TARGET_USER_ID}")
    print(f"客户端ID: {client_id}")
    print(f"上下文Token: {CONTEXT_TOKEN if CONTEXT_TOKEN else '(为空，可能影响首次发送)'}")
    print("-" * 30)
    if not BOT_TOKEN:
        print("❌ 未找到 token 配置")
        return False
    if not TARGET_USER_ID:
        print("❌ 未找到 user_id/userId 配置")
        return False
    if not TXT_MSG:
        print("❌ 消息内容不能为空")
        return False

    try:
        # 5. 发送POST请求
        response = requests.post(
            api_endpoint,
            headers=headers,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            timeout=15  # 秒
        )
        # 6. 处理响应
        print(f"HTTP 状态码: {response.status_code}")
        if response.status_code == 200:
            try:
                resp_json = response.json()
            except json.JSONDecodeError as e:
                print(f"❌ 解析服务器响应失败: {e}")
                print(f"原始响应文本: {response.text[:500]}")
                return False
            print(f"API 返回码 (ret): {resp_json.get('ret')}")
            print("服务器响应详情:")
            print(json.dumps(resp_json, indent=2, ensure_ascii=False))
            if resp_json.get("ret") == 0:
                print("✅ 消息发送成功！")
                return True
            print(f"❌ API 返回失败: {resp_json.get('msg') or resp_json.get('errmsg') or resp_json}")
            return False
        else:
            print(f"❌ 请求失败，HTTP状态码非200。")
            print(f"响应内容: {response.text[:500]}")  # 打印前500字符以便调试
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求异常: {e}")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ 解析服务器响应失败: {e}")
        print(f"原始响应文本: {response.text[:500]}")
        return False
    print("=" * 50)


def find_hermes_weixin_account():
    """兼容旧接口：自动查找微信配置。"""
    account = find_weixin_account()
    return account.account_id if account else None

def main():
    """主函数：支持命令行参数或自动从 Hermes/OpenClaw 配置读取"""
    if len(sys.argv) == 3 and sys.argv[1] == '--auto':
        account = find_weixin_account()
        if not account:
            print("❌ 未找到微信配置")
            print_auto_discovery_help()
            sys.exit(1)
        
        print(f"自动发现微信账号: {account.account_id} ({account.platform})")
        credentials = load_account_credentials(account.account_id)
        if "error" in credentials:
            print(f"❌ {credentials['error']}")
            sys.exit(1)
        
        MSG = sys.argv[2]
        success = send_weixin_message(
            credentials["base_url"],
            credentials["token"],
            credentials["user_id"],
            credentials["context_token"],
            MSG,
        )
        sys.exit(0 if success else 1)
        
    elif len(sys.argv) == 3:
        account_id = sys.argv[1]
        MSG = sys.argv[2]
        credentials = load_account_credentials(account_id)
        if "error" in credentials:
            print(f"❌ {credentials['error']}")
            sys.exit(1)
        
        success = send_weixin_message(
            credentials["base_url"],
            credentials["token"],
            credentials["user_id"],
            credentials["context_token"],
            MSG,
        )
        sys.exit(0 if success else 1)
        
    elif len(sys.argv) == 2 and sys.argv[1] in ['-h', '--help']:
        print("微信消息发送脚本")
        print("")
        print("用法:")
        print("  python3 main_send_msg.py --auto <消息>   # 自动读取 Hermes Agent/OpenClaw 配置")
        print("  python3 main_send_msg.py <account_id> <消息>")
        print("")
        print("示例:")
        print("  python3 main_send_msg.py --auto '你好'")
        print("  python3 main_send_msg.py wechat_12345 '你好'")
        print("")
        print_auto_discovery_help()
        sys.exit(0)
        
    else:
        print("用法:")
        print("  python3 main_send_msg.py --auto <消息>   # 自动读取 Hermes Agent/OpenClaw 配置")
        print("  python3 main_send_msg.py <account_id> <消息>")
        print("")
        print("示例:")
        print("  python3 main_send_msg.py --auto '你好'")
        print("  python3 main_send_msg.py wechat_12345 '你好'")
        sys.exit(1)

if __name__ == "__main__":
    main()
