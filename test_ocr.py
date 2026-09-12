# test_ocr.py —— 测试百度 OCR 能不能跑通
# 用法：python test_ocr.py 你的图片.jpg

import sys
import os
import base64
import requests
from baidu_ocr_config import (
    BAIDU_OCR_API_KEY,
    BAIDU_OCR_SECRET_KEY,
)


def get_access_token():
    """用 API Key + Secret Key 换一个临时 access_token"""
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type":    "client_credentials",
        "client_id":     BAIDU_OCR_API_KEY,
        "client_secret": BAIDU_OCR_SECRET_KEY,
    }
    r = requests.post(url, params=params, timeout=10)
    data = r.json()
    if "access_token" not in data:
        print("✗ 获取 access_token 失败：")
        print(data)
        sys.exit(1)
    return data["access_token"]


def ocr_image(image_path, token):
    """上传图片，返回识别出的文字"""
    if not os.path.exists(image_path):
        print(f"✗ 文件不存在：{image_path}")
        sys.exit(1)

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    url = "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    payload = {
        "image":     img_b64,
        "language_type": "CHN_ENG",
    }

    r = requests.post(
        url, params={"access_token": token},
        headers=headers, data=payload, timeout=30
    )
    return r.json()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python test_ocr.py 图片路径")
        print("例：python test_ocr.py 菜单.jpg")
        sys.exit(1)

    image_path = sys.argv[1]

    print("① 获取 access_token...")
    token = get_access_token()
    print(f"   ✓ 拿到 token（前 20 字符）：{token[:20]}...")

    print(f"② 上传图片并识别：{image_path}")
    result = ocr_image(image_path, token)

    if "words_result" not in result:
        print("✗ 识别失败：")
        print(result)
        sys.exit(1)

    print(f"③ 识别成功，共 {len(result['words_result'])} 行：\n")
    for i, line in enumerate(result["words_result"], 1):
        print(f"   {i:2d}. {line['words']}")