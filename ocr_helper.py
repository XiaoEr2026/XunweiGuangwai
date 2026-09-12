# ocr_helper.py —— 封装百度 OCR
import base64
import os
import requests
from baidu_ocr_config import (
    BAIDU_OCR_API_KEY,
    BAIDU_OCR_SECRET_KEY,
)


def _get_token():
    """用 API Key + Secret Key 换临时 access_token"""
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type":    "client_credentials",
        "client_id":     BAIDU_OCR_API_KEY,
        "client_secret": BAIDU_OCR_SECRET_KEY,
    }
    r = requests.post(url, params=params, timeout=10)
    data = r.json()
    return data.get("access_token")


def ocr_image(image_path):
    """识别本地图片，返回 (是否成功, 结果)
       成功：result 是文字行的列表，比如 ['黑椒牛柳饭 15元', '番茄鸡蛋盖饭 12元']
       失败：result 是错误信息字符串
    """
    if not os.path.exists(image_path):
        return False, f"文件不存在：{image_path}"

    token = _get_token()
    if not token:
        return False, "获取 access_token 失败，检查 baidu_ocr_config.py 里的凭证"

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    url = "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    payload = {
        "image":         img_b64,
        "language_type": "CHN_ENG",
    }

    r = requests.post(
        url,
        params={"access_token": token},
        headers=headers,
        data=payload,
        timeout=30,
    )
    result = r.json()

    if "words_result" not in result:
        return False, f"识别失败：{result}"

    lines = [item["words"] for item in result["words_result"]]
    return True, lines