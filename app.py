import os
from flask import Flask, request
from werobot import WeRoBot
import requests

app = Flask(__name__)

# 配置参数（通过环境变量读取）
CORP_ID = os.getenv("CORP_ID")
APP_SECRET = os.getenv("APP_SECRET")
APP_TOKEN = os.getenv("APP_TOKEN")
ENCODING_AES_KEY = os.getenv("ENCODING_AES_KEY")

CD2_URL = os.getenv("CD2_URL", "http://192.168.1.100:19798")
CD2_USER = os.getenv("CD2_USER")
CD2_PASS = os.getenv("CD2_PASS")
DOWNLOAD_PATH = os.getenv("DOWNLOAD_PATH", "/CloudDrive/115/MyVideos")

# 初始化企业微信机器人
robot = WeRoBot(token=APP_TOKEN, encoding_aes_key=ENCODING_AES_KEY, corp_id=CORP_ID)

def cd2_offline_download(magnet_url):
    """调用 CloudDrive2 API 进行离线下载"""
    with requests.Session() as s:
        # 1. 登录获取 Cookie
        login_data = {"userName": CD2_USER, "password": CD2_PASS}
        s.post(f"{CD2_URL}/api/v1/login", json=login_data)
        
        # 2. 提交离线下载任务
        payload = {
            "path": DOWNLOAD_PATH,
            "url": magnet_url
        }
        # 注意：此 API 路径参考 CD2 最新文档或 F12 抓包分析
        res = s.post(f"{CD2_URL}/api/v1/add_offline_task", json=payload)
        return res.status_code == 200

@robot.text
def handle_text(message):
    content = message.content.strip()
    if content.startswith("magnet:?"):
        success = cd2_offline_download(content)
        return "✅ 已成功提交至 CloudDrive2 离线任务" if success else "❌ 提交失败，请检查 CD2 状态"
    return "💡 请发送有效的磁力链接"

# 将 WeRoBot 挂载到 Flask
app.add_url_rule('/wechat', endpoint='werobot', view_func=robot.make_view(), methods=['GET', 'POST'])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)