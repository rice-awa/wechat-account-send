import requests
import json
import time
import base64
import os
import uuid
from pathlib import Path
import sys

def get_hermes_path():
    """获取 Hermes 配置路径"""
    home = Path.home()
    return home / '.hermes'

def get_openclaw_path():
    """获取 OpenClaw 安装路径，支持 Windows、Linux、MacOS"""
    # 支持环境变量指定的路径
    state_dir = os.environ.get('OPENCLAW_STATE_DIR')
    if state_dir and os.path.exists(state_dir):
        return Path(state_dir)
    
    # 默认路径
    home = Path.home()
    if sys.platform == 'win32':
        # Windows: C:\Users\用户名\.openclaw
        return home / '.openclaw'
    else:
        # Linux/MacOS: ~/.openclaw
        return home / '.openclaw'

def find_account_json(account_id, use_path=False):
    """
    根据账号ID查找对应的JSON文件并返回内容。
    优先从 Hermes 路径读取，fallback 到 OpenClaw 路径。
    """
    try:
        if use_path:
            base_path = Path(use_path)
        else:
            # 检查 Hermes 路径
            hermes_path = get_hermes_path()
            hermes_weixin_path = hermes_path / 'weixin' / 'accounts'
            openclaw_path = get_openclaw_path()
            openclaw_weixin_path = openclaw_path / 'openclaw-weixin' / 'accounts'
            
            # 适配不同环境，任一路径存在即可
            if hermes_weixin_path.exists():
                base_path = hermes_path
                accounts_path = hermes_weixin_path
            elif openclaw_weixin_path.exists():
                base_path = openclaw_path
                accounts_path = openclaw_weixin_path
            else:
                return {"error": f"微信配置路径不存在: \n  Hermes: {hermes_weixin_path}\n  OpenClaw: {openclaw_weixin_path}"}
        
        # 构建完整路径
        weixin_accounts_path = base_path / 'weixin' / 'accounts'
        # 如果是 OpenClaw 路径
        if not weixin_accounts_path.exists():
            weixin_accounts_path = base_path / 'openclaw-weixin' / 'accounts'
        
        if not weixin_accounts_path.exists():
            return {"error": f"微信账号路径不存在: {weixin_accounts_path}"}
        
        datas = {}
        for file_suffix in ['', '.context-tokens', '.sync']:
            json_file = weixin_accounts_path / f"{account_id}{file_suffix}.json"
            if json_file.exists():
                with open(json_file, 'r', encoding='utf-8') as f:
                    key = account_id + file_suffix if file_suffix else account_id
                    datas[key] = json.load(f)
        
        return {
            "account_id": account_id,
            "file_path": str(weixin_accounts_path),
            "data": datas
        }
        
    except Exception as e:
        return {"error": f"读取失败: {str(e)}"}

def send_weixin_message(BASE_URL,BOT_TOKEN,TARGET_USER_ID,CONTEXT_TOKEN,TXT_MSG):
    """
    通过微信后端API发送一条文本测试消息。
    """
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
            resp_json = response.json()
            print(f"API 返回码 (ret): {resp_json.get('ret')}")
            print("✅ 消息发送成功！")
            print("服务器响应详情:")
            print(json.dumps(resp_json, indent=2, ensure_ascii=False))
        else:
            print(f"❌ 请求失败，HTTP状态码非200。")
            print(f"响应内容: {response.text[:500]}")  # 打印前500字符以便调试
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求异常: {e}")
    except json.JSONDecodeError as e:
        print(f"❌ 解析服务器响应失败: {e}")
        print(f"原始响应文本: {response.text[:500]}")
    print("=" * 50)


def find_hermes_weixin_account():
    """自动查找 Hermes 微信配置"""
    hermes_path = get_hermes_path()
    weixin_accounts_path = hermes_path / 'weixin' / 'accounts'
    
    if not weixin_accounts_path.exists():
        return None
    
    for f in weixin_accounts_path.iterdir():
        if f.suffix == '.json' and f.name.endswith('.bot.json'):
            return f.stem
        elif f.suffix == '.json' and not f.name.endswith('.context-tokens.json') and not f.name.endswith('.sync.json'):
            if f.name == 'wechat_account.json':
                continue
            return f.stem
    return None

def main():
    """主函数：支持命令行参数或自动从 Hermes/OpenClaw 配置读取"""
    hermes_account_id = find_hermes_weixin_account()
    
    if len(sys.argv) == 3 and sys.argv[1] == '--auto':
        if not hermes_account_id:
            print("❌ 未找到 Hermes 微信配置")
            sys.exit(1)
        
        print(f"使用 Hermes 配置自动发现账号: {hermes_account_id}")
        result = find_account_json(hermes_account_id)
        if "error" in result:
            print(f"❌ {result['error']}")
            sys.exit(1)
        
        data = result["data"]
        bot_config = data.get(hermes_account_id, {})
        token = bot_config.get('token', '')
        user_id = bot_config.get('user_id', '')
        
        context_tokens_file = hermes_account_id + '.context-tokens.json'
        context_token = ''
        if context_tokens_file in data:
            context_tokens_data = data[context_tokens_file]
            if context_tokens_data:
                context_token = list(context_tokens_data.values())[0]
        
        if not token:
            print("❌ 未找到 token 配置")
            sys.exit(1)
        
        print(f"Token: {token[:10]}...")
        print(f"User ID: {user_id}")
        
        MSG = sys.argv[2]
        send_weixin_message("https://ilinkai.weixin.qq.com", token, user_id, context_token, MSG)
        
    elif len(sys.argv) == 3:
        account_id = sys.argv[1]
        MSG = sys.argv[2]
        result = find_account_json(account_id)
        if "error" in result:
            print(f"❌ {result['error']}")
            sys.exit(1)
        
        data = result["data"]
        BASE_URL = data.get(account_id, {}).get('baseUrl', 'https://ilinkai.weixin.qq.com')
        BOT_TOKEN = data.get(account_id, {}).get('token', '')
        TARGET_USER_ID = data.get(account_id, {}).get('userId', '')
        
        context_tokens_file = account_id + '.context-tokens.json'
        CONTEXT_TOKEN = ''
        if context_tokens_file in data:
            context_data = data[context_tokens_file]
            if context_data:
                CONTEXT_TOKEN = list(context_data.values())[0]
        
        send_weixin_message(BASE_URL, BOT_TOKEN, TARGET_USER_ID, CONTEXT_TOKEN, MSG)
        
    elif len(sys.argv) == 2 and sys.argv[1] in ['-h', '--help']:
        print("微信消息发送脚本")
        print("")
        print("用法:")
        print("  python3 main_send_msg.py --auto <消息>   # 从 Hermes 配置自动读取")
        print("  python3 main_send_msg.py <account_id> <消息>")
        print("")
        print("示例:")
        print("  python3 main_send_msg.py --auto '你好'")
        print("  python3 main_send_msg.py wechat_12345 '你好'")
        sys.exit(0)
        
    else:
        print("用法:")
        print("  python3 main_send_msg.py --auto <消息>   # 从 Hermes 配置自动读取")
        print("  python3 main_send_msg.py <account_id> <消息>")
        print("")
        print("示例:")
        print("  python3 main_send_msg.py --auto '你好'")
        print("  python3 main_send_msg.py wechat_12345 '你好'")
        sys.exit(1)

if __name__ == "__main__":
    main()
