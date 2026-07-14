"""Webhook notification senders.

Push channels are auto-detected from the WEBHOOK_URL domain, so a single
secret covers all of them:

  - pushplus.plus          -> PushPlus -> personal WeChat (个人微信)
  - sctapi.ftqq.com        -> Server酱 -> personal WeChat (个人微信)
  - qyapi.weixin.qq.com    -> WeChat Work group robot (企业微信群机器人)
  - oapi.dingtalk.com      -> DingTalk custom robot (钉钉自定义机器人)

The personal-WeChat channels exist because plain WeChat group chats do NOT
support webhooks; Server酱 / PushPlus relay through their 公众号 instead.
"""
from __future__ import annotations

import sys
from typing import Callable

import requests


def send_wechat_work(webhook_url: str, content: str) -> bool:
    """Send a markdown message to a WeChat Work group robot."""
    payload = {"msgtype": "markdown", "markdown": {"content": content}}
    return _post(webhook_url, payload, "WeChat Work",
                 ok=lambda d: d.get("errcode", 0) == 0)


def send_dingtalk(webhook_url: str, title: str, text: str) -> bool:
    """Send a markdown message to a DingTalk group robot."""
    payload = {"msgtype": "markdown", "markdown": {"title": title, "text": text}}
    return _post(webhook_url, payload, "DingTalk",
                 ok=lambda d: d.get("errcode", 0) == 0)


def send_serverchan(webhook_url: str, content: str, title: str) -> bool:
    """Push to personal WeChat via Server酱 (ServerChan).

    Get a sendkey at https://sct.ftqq.com/, set
    WEBHOOK_URL = https://sctapi.ftqq.com/{SENDKEY}.send . Success = code == 0.
    """
    payload = {"title": title, "desp": content}
    return _post(webhook_url, payload, "Server酱",
                 ok=lambda d: d.get("code", -1) == 0)


def send_pushplus(webhook_url: str, content: str, title: str) -> bool:
    """Push to personal WeChat via PushPlus.

    Get a token at https://www.pushplus.plus/ (+ 实名认证), set
    WEBHOOK_URL = https://www.pushplus.plus/send?token={TOKEN} . Success = code == 200.
    """
    payload = {"title": title, "content": content, "template": "markdown"}
    return _post(webhook_url, payload, "PushPlus",
                 ok=lambda d: d.get("code", -1) == 200)


def _post(url: str, payload: dict, name: str,
          ok: Callable[[dict], bool]) -> bool:
    """POST JSON and check the response with the channel-specific `ok` test."""
    try:
        resp = requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"[warn] {name} request failed: {e}", file=sys.stderr)
        return False

    if not resp.ok:
        print(f"[warn] {name} HTTP {resp.status_code}: {resp.text[:200]}",
              file=sys.stderr)
        return False

    try:
        data = resp.json()
    except ValueError:
        data = {}

    if ok(data):
        print(f"[info] {name} notification sent", file=sys.stderr)
        return True
    print(f"[warn] {name} API error: {data}", file=sys.stderr)
    return False


def notify(webhook_url: str, content: str, title: str) -> bool:
    """Auto-detect the push channel from the URL domain and send the message."""
    if not webhook_url:
        return False
    if "qyapi.weixin.qq.com" in webhook_url:
        return send_wechat_work(webhook_url, content)
    if "oapi.dingtalk.com" in webhook_url:
        return send_dingtalk(webhook_url, title, content)
    if "sctapi.ftqq.com" in webhook_url:
        return send_serverchan(webhook_url, content, title)
    if "pushplus.plus" in webhook_url:
        return send_pushplus(webhook_url, content, title)
    masked = webhook_url[:60] + ("..." if len(webhook_url) > 60 else "")
    print(f"[warn] unknown webhook domain, cannot determine type: {masked}",
          file=sys.stderr)
    return False
