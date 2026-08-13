#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude Code <-> AgentOS 多表消息通道工具
用法:
  python agentos_chat.py send "消息内容"      # 发消息给 AgentOS
  python agentos_chat.py read                 # 读 AgentOS 的未读回复
  python agentos_chat.py read --all           # 读全部消息
"""
import os
import sys
import time
import requests
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 凭证从环境变量或本地 demo/.env 读取（.env 不进 git，防止密钥泄露）
_ENV = Path(__file__).parent / ".env"
if _ENV.exists():
    for _line in _ENV.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

APP_ID = os.environ["APP_ID"]
APP_SECRET = os.environ["APP_SECRET"]
APP_TOKEN = os.environ["APP_TOKEN"]      # Base token
MSG_TABLE = os.environ["MSG_TABLE"]      # 协作消息表


def token():
    r = requests.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                      json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=15)
    return r.json()["tenant_access_token"]


def api(path, method="GET", body=None):
    h = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{MSG_TABLE}{path}"
    r = requests.request(method, url, headers=h, json=body, timeout=15)
    d = r.json()
    if d.get("code") != 0:
        raise RuntimeError(f"api error {d.get('code')}: {d.get('msg')}")
    return d.get("data", {})


def send(text, image_path=None):
    fields = {
        "发送方": "ClaudeCode",
        "消息内容": text,
        "状态": "未读",
        "时间": int(time.time() * 1000),
    }
    if image_path:
        with open(image_path, "rb") as f:
            data = f.read()
        import os
        r = requests.post("https://open.feishu.cn/open-apis/drive/v1/medias/upload_all",
                          headers={"Authorization": f"Bearer {token()}"},
                          data={"file_name": os.path.basename(image_path),
                                "parent_type": "bitable_image", "parent_node": APP_TOKEN,
                                "size": str(len(data))},
                          files={"file": (os.path.basename(image_path), data)}, timeout=120)
        d = r.json()
        assert d.get("code") == 0, f"upload failed: {d}"
        fields["附件"] = [{"file_token": d["data"]["file_token"]}]
    api("/records", "POST", {"fields": fields})
    print(f"[已发送] {text}" + (" [含图片]" if image_path else ""))


def read(show_all=False):
    items = api("/records/search", "POST", {"filter": {"conjunction": "and", "conditions": [
        {"field_name": "发送方", "operator": "is", "value": ["AgentOS"]},
    ]}}).get("items", [])
    for rec in items:
        f = rec["fields"]
        sender = f.get("发送方")
        status = f.get("状态")
        text = f.get("消息内容", [{}])[0].get("text", "") if isinstance(f.get("消息内容"), list) else f.get("消息内容")
        t = f.get("时间")
        if not show_all and status == "已读":
            continue
        print(f"[{sender}] {text}")
        # mark as read
        api(f"/records/{rec['record_id']}", "PUT", {"fields": {"状态": "已读"}})
    if not items:
        print("[无消息]")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    elif sys.argv[1] == "send" and len(sys.argv) > 2:
        if "--image" in sys.argv:
            idx = sys.argv.index("--image")
            send(sys.argv[2], sys.argv[idx + 1])
        else:
            send(sys.argv[2])
    elif sys.argv[1] == "read":
        read(show_all="--all" in sys.argv)
    else:
        print(__doc__)
