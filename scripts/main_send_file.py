import json
import base64
import random
import time
import hashlib
from pathlib import Path
from typing import Dict, Any
from urllib.parse import quote
import os
import uuid
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


# 计算AES-128-ECB加密后的文件大小
def calculate_encrypted_size(raw_size: int) -> int:
    """
    计算AES-128-ECB加密后的文件大小
    
    根据文档公式：filesize = ceil((rawsize + 1) / 16) * 16
    因为PKCS7填充会至少填充1个字节
    """
    return ((raw_size + 1 + 15) // 16) * 16
    

# 准备上传参数
def prepare_image_upload( image_path: str) -> Dict[str, Any]:
    """
    准备图片上传：计算所有必要参数
    返回包含所有上传所需参数的字典
    """
    if not Path(image_path).exists():
        return {
            "success": False,
            "error": f"图片文件不存在: {image_path}"
        }
    
    try:
        # 读取文件
        with open(image_path, 'rb') as f:
            file_data = f.read()
        
        # 计算文件参数
        rawsize = len(file_data)
        rawfilemd5 = hashlib.md5(file_data).hexdigest()
        
        # 生成随机参数
        filekey = ''.join(random.choices('0123456789abcdef', k=32))  # 16字节hex
        aeskey_hex = ''.join(random.choices('0123456789abcdef', k=32))  # 16字节hex
        
        # 计算加密后大小
        filesize = calculate_encrypted_size(rawsize)
        
        return {
            "success": True,
            "filekey": filekey,
            "aeskey_hex": aeskey_hex,
            "rawsize": rawsize,
            "rawfilemd5": rawfilemd5,
            "filesize": filesize,
            "file_data": file_data
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"准备图片失败: {str(e)}"
        }

# 加密文件
def aes_encrypt_file(file_path: str, aes_key_hex: str) -> bytes:
        """
        使用AES-128-ECB模式加密文件，使用PKCS7 padding
        
        根据文档第二步：本地加密文件
        """
        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import pad
        except ImportError as exc:
            raise RuntimeError("缺少依赖 pycryptodome，请先执行: pip install -r requirements.txt") from exc

        if len(aes_key_hex) != 32:
            raise ValueError("AES密钥必须是32个十六进制字符（16字节）")
        
        # 将十六进制字符串转换为字节
        aes_key = bytes.fromhex(aes_key_hex)
        
        # 读取文件
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        # 创建AES-128-ECB加密器
        cipher = AES.new(aes_key, AES.MODE_ECB)
        
        # 对数据进行PKCS7填充并加密
        padded_data = pad(file_data, AES.block_size, style='pkcs7')
        encrypted_data = cipher.encrypt(padded_data)
        
        return encrypted_data

# 编码AES密钥
def encode_aes_key(aes_key_hex: str) -> str:
    """
    将AES密钥编码为"base64(hex string)"格式
    
    根据文档8.4节：先把hex文本当作字节，再base64
    例如：hex "00112233445566778899aabbccddeeff" → "MDAxMTIyMzM0NDU1NjY3Nzg4OTlhYWJiY2NkZGVlZmY="
    """
    # 将十六进制字符串转换为字节
    hex_bytes = aes_key_hex.encode('utf-8')
    # 进行base64编码
    return base64.b64encode(hex_bytes).decode('utf-8')


# 申请上传参数
def get_upload_params(  use_token: str,
                        filekey: str,
                        media_type: int,
                        to_user_id: str,
                        rawsize: int,
                        rawfilemd5: str,
                        filesize: int,
                        aeskey_hex: str,
                        no_need_thumb: bool = True) -> Dict[str, Any]:
    """
    第一步：申请上传参数 (getuploadurl)
    
    根据文档8.2节第一步
    """
    try:
        import requests
    except ImportError:
        return {
            "success": False,
            "error": "缺少依赖 requests，请先执行: pip install -r requirements.txt"
        }

    random_uint32 = os.urandom(4)
    x_wechat_uin = base64.b64encode(random_uint32).decode('utf-8')
    # 构造请求体
    body = {
        "filekey": filekey,
        "media_type": media_type,  # 1=图片
        "to_user_id": to_user_id,
        "rawsize": rawsize,
        "rawfilemd5": rawfilemd5,
        "filesize": filesize,
        "no_need_thumb": no_need_thumb,
        "aeskey": aeskey_hex,
        "base_info": {
            "channel_version": "1.0.0"
        }
    }
    # 发送请求
    raw = json.dumps(body, ensure_ascii=False)  
    headers = {  
    "Content-Type": "application/json",  
    "AuthorizationType": "ilink_bot_token",  
    "Authorization": f"Bearer {use_token}",  
    "X-WECHAT-UIN": x_wechat_uin,  
    "Content-Length": str(len(raw.encode("utf-8"))),  
    }  
    
    try:
        resp = requests.post(
            "https://ilinkai.weixin.qq.com/ilink/bot/getuploadurl",
            headers=headers,
            data=raw.encode('utf-8'),
            timeout=15,
        )
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": f"申请上传参数请求失败: {e}"
        }

    if resp.status_code != 200:
        return {
            "success": False,
            "error": f"申请上传参数失败，HTTP状态码: {resp.status_code}",
            "response": resp.text
        }
    
    try:
        result = resp.json()
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"申请上传参数响应不是有效 JSON: {e}",
            "response": resp.text[:500],
        }

    if result.get("ret") not in (None, 0):
        return {
            "success": False,
            "error": f"申请上传参数 API 返回失败: {result.get('msg') or result.get('errmsg') or result}",
            "response": result,
        }

    upload_param = result.get("upload_param", "")
    
    if not upload_param:
        return {
            "success": False,
            "error": "响应中未包含upload_param",
            "response": result
        }
    
    return {
        "success": True,
        "upload_param": upload_param,  # 就是encrypted_query_param
        "thumb_upload_param": result.get("thumb_upload_param", ""),
        "response": result
    }

# 上传到CDN
def upload_to_cdn(  upload_param: str,
                    filekey: str,
                    encrypted_data: bytes) -> Dict[str, Any]:
    """
    第三步：上传到CDN
    
    根据文档8.2节第三步
    """
    try:
        import httpx
    except ImportError:
        return {
            "success": False,
            "error": "缺少依赖 httpx，请先执行: pip install -r requirements.txt"
        }

    # 构建CDN上传URL
    encoded_param = quote(upload_param, safe='')
    cdn_url = f"https://novac2c.cdn.weixin.qq.com/c2c/upload?encrypted_query_param={encoded_param}&filekey={filekey}"
    # 构造请求头
    headers = {
        "Content-Type": "application/octet-stream"
    }
    
    try:
        # 发送请求
        resp = httpx.post(
            cdn_url,
            headers=headers,
            content=encrypted_data,
            timeout=30,
        )
        
        if resp.status_code == 200:
            encrypt_query_param = resp.headers.get('x-encrypted-param', '')
            
            if not encrypt_query_param:
                return {
                    "success": False,
                    "error": "未在响应头中找到x-encrypted-param",
                    "headers": dict(resp.headers)
                }
            return {
                "success": True,
                "encrypt_query_param": encrypt_query_param,
                "response_headers": dict(resp.headers)
            }
        else:
            return {
                "success": False,
                "error": f"上传失败，HTTP状态码: {resp.status_code}",
                "response": resp.text
            }
    except httpx.RequestError as e:
        return {
            "success": False,
            "error": f"上传请求失败: {str(e)}"
        }

def send_weixin_file(BOT_TOKEN,TARGET_USER_ID,CONTEXT_TOKEN,IMAGE_PATH):
    """
    根据文件类型发送微信文件
    
    参数说明：
    BOT_TOKEN: 机器人令牌
    TARGET_USER_ID: 目标用户ID
    CONTEXT_TOKEN: 上下文令牌
    FILE_PATH: 文件路径（支持图片、视频、文件等多种类型）
    
    媒体类型说明：
    1: 图片消息类型
    2: 视频消息类型
    3: 文件消息类型
    音频文件当前按文件消息发送
    """
    try:
        import requests
    except ImportError:
        print("❌ 缺少依赖 requests，请先执行: pip install -r requirements.txt")
        return False

    if not BOT_TOKEN:
        print("❌ 未找到 token 配置")
        return False
    if not TARGET_USER_ID:
        print("❌ 未找到 user_id/userId 配置")
        return False
    file_path = Path(IMAGE_PATH).expanduser()
    if not file_path.exists():
        print(f"❌ 文件不存在: {file_path}")
        return False
    if not file_path.is_file():
        print(f"❌ 不是普通文件: {file_path}")
        return False
    if file_path.stat().st_size == 0:
        print(f"❌ 文件为空: {file_path}")
        return False

    # 根据文件后缀判断媒体类型
    IMAGE_PATH = str(file_path)
    file_ext = file_path.suffix.lower().lstrip('.')
    
    # 图片类型
    image_extensions = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff', 'svg']
    # 视频类型
    video_extensions = ['mp4', 'mov', 'avi', 'wmv', 'flv', 'mkv', 'webm', 'mpeg', 'mpg']
    # 音频类型
    audio_extensions = ['mp3', 'wav', 'aac', 'flac', 'm4a', 'ogg', 'wma']
    # 文档类型
    document_extensions = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt']
    # 压缩文件类型
    archive_extensions = ['zip', 'rar', '7z', 'tar', 'gz']
    
    # 判断文件类型
    if file_ext in image_extensions:
        media_type = 1
    elif file_ext in video_extensions:
        media_type = 2
    elif file_ext in audio_extensions:
        # The sendmessage payload in this script has no dedicated audio branch;
        # sending audio as a file is more reliable than failing late.
        media_type = 3
    elif file_ext in document_extensions or file_ext in archive_extensions:
        media_type = 3
    else:
        # 默认处理为文件类型
        media_type = 3
        print(f"警告：未知文件类型 .{file_ext}，将作为普通文件发送")

    # 1.准备上传参数
    print("1. 准备上传参数...")
    prepare_result = prepare_image_upload(IMAGE_PATH)
    if not prepare_result["success"]:
        print(f"准备失败: {prepare_result.get('error')}")
        return False
    else:
        print(f"准备成功，filekey: {prepare_result['filekey'][:16]}..., aeskey: {prepare_result['aeskey_hex'][:16]}...")

        filekey = prepare_result["filekey"]
        aeskey_hex = prepare_result["aeskey_hex"]
        rawsize = prepare_result["rawsize"]
        rawfilemd5 = prepare_result["rawfilemd5"]
        filesize = prepare_result["filesize"]

         # 2.申请上传参数
        print("2. 申请上传参数...")
        upload_params = get_upload_params(
            use_token=BOT_TOKEN,
            filekey=filekey,
            media_type=media_type,
            to_user_id=TARGET_USER_ID,
            rawsize=rawsize,
            rawfilemd5=rawfilemd5,
            filesize=filesize,
            aeskey_hex=aeskey_hex,
            no_need_thumb=True
        )
        if not upload_params.get("success"):
            print(f"❌ 申请上传参数失败: {upload_params.get('error')}")
            if upload_params.get("response"):
                print(f"响应详情: {str(upload_params['response'])[:500]}")
            return False
        print(f"获取到upload_param: {upload_params['upload_param'][:20]}...")
            
        # 3. 加密文件...
        print("3. 加密文件...")
        try:
            encrypted_data = aes_encrypt_file(IMAGE_PATH,aeskey_hex)
        except (OSError, ValueError, RuntimeError) as e:
            print(f"❌ 加密文件失败: {e}")
            return False
        print(f"  加密完成，原始大小: {rawsize}, 加密后大小: {len(encrypted_data)}")
        # 4. 上传到CDN...
        print("4. 上传到CDN...")
        upload_result = upload_to_cdn(upload_params["upload_param"],filekey, encrypted_data)
        if not upload_result.get("success"):
            print(f"❌ 上传 CDN 失败: {upload_result.get('error')}")
            if upload_result.get("response"):
                print(f"响应详情: {str(upload_result['response'])[:500]}")
            return False
        encrypt_query_param = upload_result["encrypt_query_param"]
        print(f"  上传成功，encrypt_query_param: {encrypt_query_param[:20]}...")
        # 编码AES密钥
        encoded_aes_key = encode_aes_key(aeskey_hex)    
        upload_result = {
            "success": True,
            "encrypt_query_param": encrypt_query_param,
            "aes_key_hex": aeskey_hex,
            "encoded_aes_key": encoded_aes_key,
            "file_size": rawsize,
            "filesize": filesize,
            "filekey": filekey
        }

        # 5. 发送图片...
        print("5. 发送文件...")
        timestamp_ms = int(time.time() * 1000)
        random_suffix = uuid.uuid4().hex[:8]
        client_id = f"openclaw-weixin:{timestamp_ms}-{random_suffix}"
        random_uint32 = os.urandom(4)
        x_wechat_uin = base64.b64encode(random_uint32).decode('utf-8')
        # 构造图片消息体（第四步）
        if media_type == 1:
            payload = {
                "msg": {
                    "from_user_id": "",
                    "to_user_id": TARGET_USER_ID,
                    "client_id": client_id,
                    "message_type": 2,
                    "message_state": 2,
                    "context_token": CONTEXT_TOKEN,
                    "item_list": [
                        {
                            "type": 2,  # 图片消息类型
                            "image_item": {
                                "media": {
                                    "encrypt_query_param": upload_result["encrypt_query_param"],
                                    "aes_key": upload_result["encoded_aes_key"],
                                    "encrypt_type": 1
                                },
                                "mid_size": upload_result["file_size"]  # 明文文件大小
                            }
                        }
                    ]
                },
                "base_info": {
                    "channel_version": "1.0.0"
                }
            }
        # 构造文件消息体（第四步）
        elif media_type == 3:
            payload = {
                "msg": {
                    "from_user_id": "",
                    "to_user_id": TARGET_USER_ID,
                    "client_id": client_id,
                    "message_type": 2,
                    "message_state": 2,
                    "context_token": CONTEXT_TOKEN,
                    "item_list": [
                        {
                            "type": 4,
                            "file_item": {
                                "media": {
                                    "encrypt_query_param": upload_result["encrypt_query_param"],
                                    "aes_key": upload_result["encoded_aes_key"],
                                    "encrypt_type": 1
                                },
                                "file_name": Path(IMAGE_PATH).name,
                                # "len": filesize, 写了发不出去，应该是前面有问题
                                # "md5": rawfilemd5 同
                            }
                        }
                    ]
                },
                "base_info": {
                    "channel_version": "1.0.0"
                }
            }
        
        # 构造视频消息体（第四步）
        elif media_type == 2:
            payload = {
                "msg": {
                    "from_user_id": "",
                    "to_user_id": TARGET_USER_ID,
                    "client_id": client_id,
                    "message_type": 2,
                    "message_state": 2,
                    "context_token": CONTEXT_TOKEN,
                    "item_list": [
                        {
                            "type": 5,
                            "video_item": {
                                "media": {
                                    "encrypt_query_param": upload_result["encrypt_query_param"],
                                    "aes_key": upload_result["encoded_aes_key"],
                                    "encrypt_type": 1
                                },
                                "video_size": upload_result["file_size"]  # 明文文件大小
                            }
                        }
                    ]
                },
                "base_info": {
                    "channel_version": "1.0.0"
                }
            }
        else:
            print(f"❌ 不支持的媒体类型: {media_type}")
            return False
        
        # 发送请求
        # 4. 构建请求头
        raw = json.dumps(payload, ensure_ascii=False)  
        headers = {  
        "Content-Type": "application/json",  
        "AuthorizationType": "ilink_bot_token",  
        "Authorization": f"Bearer {BOT_TOKEN}",  
        "X-WECHAT-UIN": x_wechat_uin,  
        "Content-Length": str(len(raw.encode("utf-8"))),  
        }  
            # 发送POST请求
        try:
            response = requests.post(
                "https://ilinkai.weixin.qq.com/ilink/bot/sendmessage",
                headers=headers,
                data=raw.encode('utf-8'),
                timeout=15,
            )
        except requests.exceptions.RequestException as e:
            print(f"❌ 发送文件消息请求失败: {e}")
            return False
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
                print("✅ 文件发送成功！")
                return True
            print(f"❌ API 返回失败: {resp_json.get('msg') or resp_json.get('errmsg') or resp_json}")
            return False
        else:
            print(f"❌ 请求失败，HTTP状态码非200。")
            print(f"响应内容: {response.text[:500]}")  # 打印前500字符以便调试
            return False

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
        
        FILE_PATH = sys.argv[2]
        success = send_weixin_file(
            credentials["token"],
            credentials["user_id"],
            credentials["context_token"],
            FILE_PATH,
        )
        sys.exit(0 if success else 1)
        
    elif len(sys.argv) == 3:
        account_id = sys.argv[1]
        FILE_PATH = sys.argv[2]
        credentials = load_account_credentials(account_id)
        if "error" in credentials:
            print(f"❌ {credentials['error']}")
            sys.exit(1)

        success = send_weixin_file(
            credentials["token"],
            credentials["user_id"],
            credentials["context_token"],
            FILE_PATH,
        )
        sys.exit(0 if success else 1)

    elif len(sys.argv) == 5:
        BOT_TOKEN = sys.argv[1]
        TARGET_USER_ID = sys.argv[2]
        CONTEXT_TOKEN = sys.argv[3]
        FILE_PATH = sys.argv[4]
        success = send_weixin_file(BOT_TOKEN, TARGET_USER_ID, CONTEXT_TOKEN, FILE_PATH)
        sys.exit(0 if success else 1)
        
    elif len(sys.argv) == 2 and sys.argv[1] in ['-h', '--help']:
        print("微信文件发送脚本")
        print("")
        print("用法:")
        print("  python3 main_send_file.py --auto <文件路径>   # 自动读取 Hermes Agent/OpenClaw 配置")
        print("  python3 main_send_file.py <account_id> <文件路径>")
        print("  python3 main_send_file.py <token> <user_id> <context_token> <文件路径>")
        print("")
        print("示例:")
        print("  python3 main_send_file.py --auto /path/to/image.jpg")
        print("  python3 main_send_file.py wechat_12345 /path/to/image.jpg")
        print("  python3 main_send_file.py <token> <user_id> <context_token> /path/to/image.jpg")
        print("")
        print_auto_discovery_help()
        sys.exit(0)
        
    else:
        print("用法:")
        print("  python3 main_send_file.py --auto <文件路径>   # 自动读取 Hermes Agent/OpenClaw 配置")
        print("  python3 main_send_file.py <account_id> <文件路径>")
        print("  python3 main_send_file.py <token> <user_id> <context_token> <文件路径>")
        print("")
        print("示例:")
        print("  python3 main_send_file.py --auto /path/to/image.jpg")
        print("  python3 main_send_file.py wechat_12345 /path/to/image.jpg")
        print("  python3 main_send_file.py <token> <user_id> <context_token> /path/to/image.jpg")
        sys.exit(1)

if __name__ == "__main__":
    main()
