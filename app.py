import os
import xml.etree.ElementTree as ET
import requests
from flask import Flask, request
from wechatpy.enterprise.crypto import WeChatCrypto

app = Flask(__name__)

# --- 1. 读取企微核心配置 ---
CORP_ID = os.getenv("CORP_ID")
APP_SECRET = os.getenv("APP_SECRET")
AGENT_ID = os.getenv("AGENT_ID")        # 注意：主动发送回调消息必须有这个！
APP_TOKEN = os.getenv("APP_TOKEN")
ENCODING_AES_KEY = os.getenv("ENCODING_AES_KEY")

# --- 2. 微信代理地址 ---
# 替换为你的代理 (例如 https://qyapi.你的域名.com)，如果不填则默认官方域名
WECHAT_PROXY = os.getenv("WECHAT_PROXY", "https://qyapi.weixin.qq.com").rstrip("/")

# --- 3. CD2 配置 ---
CD2_URL = os.getenv("CD2_URL")
CD2_USER = os.getenv("CD2_USER")
CD2_PASS = os.getenv("CD2_PASS")
DOWNLOAD_PATH = os.getenv("DOWNLOAD_PATH")

# 初始化企微加密/解密器
crypto = WeChatCrypto(APP_TOKEN, ENCODING_AES_KEY, CORP_ID)

def send_wechat_reply(touser, content):
    """通过你配置的【微信代理】主动给微信发消息"""
    try:
        # 第一步：获取 Access Token (流量走代理域名)
        token_url = f"{WECHAT_PROXY}/cgi-bin/gettoken?corpid={CORP_ID}&corpsecret={APP_SECRET}"
        token_res = requests.get(token_url, timeout=10).json()
        access_token = token_res.get("access_token")
        
        if not access_token:
            print(f"[*] 获取 Token 失败: {token_res}")
            return
            
        # 第二步：下发结果通知 (流量走代理域名)
        send_url = f"{WECHAT_PROXY}/cgi-bin/message/send?access_token={access_token}"
        payload = {
            "touser": touser,
            "msgtype": "text",
            "agentid": AGENT_ID,
            "text": {"content": content}
        }
        requests.post(send_url, json=payload, timeout=10)
    except Exception as e:
        print(f"[*] 发送微信回复异常: {e}")

def cd2_offline_download(magnet_url):
    """调用 CloudDrive2 API 进行离线下载"""
    try:
        with requests.Session() as s:
            # 登录
            login_data = {"userName": CD2_USER, "password": CD2_PASS}
            s.post(f"{CD2_URL}/api/v1/login", json=login_data, timeout=5)
            # 添加任务
            payload = {"path": DOWNLOAD_PATH, "url": magnet_url}
            res = s.post(f"{CD2_URL}/api/v1/add_offline_task", json=payload, timeout=5)
            
            if res.status_code == 200:
                return True, "提交成功"
            return False, f"HTTP {res.status_code}"
    except Exception as e:
        return False, f"请求 CD2 失败: {e}"

# --- 核心路由：处理企业微信的回调通信 ---
@app.route('/wechat', methods=['GET', 'POST'])
def wechat_callback():
    signature = request.args.get('msg_signature', '')
    timestamp = request.args.get('timestamp', '')
    nonce = request.args.get('nonce', '')

    # 【1】处理企业微信后台的 URL 验证 (GET)
    if request.method == 'GET':
        echostr = request.args.get('echostr', '')
        try:
            # 解密并返回明文 echostr 给微信服务器
            return crypto.check_signature(signature, timestamp, nonce, echostr)
        except Exception as e:
            return f"验证失败: {e}", 403

    # 【2】处理你发给机器人的消息 (POST)
    if request.method == 'POST':
        try:
            # 解密发过来的 XML 数据
            msg_xml = crypto.decrypt_message(request.data, signature, timestamp, nonce)
            tree = ET.fromstring(msg_xml)
            
            msg_type = tree.find('MsgType').text
            from_user = tree.find('FromUserName').text
            
            if msg_type == 'text':
                content = tree.find('Content').text.strip()
                
                if content.startswith("magnet:?"):
                    # 1. 提交到本地 CD2
                    success, detail = cd2_offline_download(content)
                    
                    # 2. 提取特征码用于展示
                    hash_code = content.split("urn:btih:")[1][:10].upper() + "..." if "urn:btih:" in content else "未知特征码"
                    
                    # 3. 构造完美的返回文案
                    if success:
                        reply_text = f"✅ 离线任务已建立\n🧲 {hash_code}\n🤖 状态: {detail}"
                    else:
                        reply_text = f"❌ 离线任务失败\n⚠️ 原因: {detail}"
                    
                    # 4. 主动调用代理接口回复给你
                    send_wechat_reply(from_user, reply_text)
                else:
                    send_wechat_reply(from_user, "💡 请发送合法的磁力链接 (magnet:?)")

            # 新规要求：收到任何消息必须在 5 秒内给微信服务器响应一个 "success" 防止超时重试
            return "success"
        except Exception as e:
            print(f"[*] 处理消息异常: {e}")
            return "success"

if __name__ == '__main__':
    print("[*] 机器人服务启动中，监听 5000 端口...")
    app.run(host='0.0.0.0', port=5000)
