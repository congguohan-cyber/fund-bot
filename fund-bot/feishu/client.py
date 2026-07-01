"""
飞书 API 客户端 — 鉴权 + 消息发送
"""
import json as _json
import time
from datetime import datetime

import httpx

from config import get_config


class FeishuClient:
    """飞书开放平台 API 客户端"""

    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self):
        config = get_config()
        self.app_id = config.feishu.app_id
        self.app_secret = config.feishu.app_secret
        self._tenant_token: str = ""
        self._token_expire: float = 0

    def _get_tenant_token(self) -> str:
        """获取 tenant_access_token（含缓存）"""
        now = time.time()
        if self._tenant_token and now < self._token_expire - 60:
            return self._tenant_token

        try:
            resp = httpx.post(
                f"{self.BASE_URL}/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
                timeout=10,
            )
            data = resp.json()
            if data.get("code") == 0:
                self._tenant_token = data["tenant_access_token"]
                self._token_expire = now + data.get("expire", 7200)
                return self._tenant_token
            else:
                raise Exception(f"获取飞书token失败: {data}")
        except Exception as e:
            raise Exception(f"飞书鉴权失败: {e}")

    def _headers(self) -> dict:
        """请求头"""
        return {
            "Authorization": f"Bearer {self._get_tenant_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def send_text(self, content: str, open_id: str = "",
                  chat_id: str = "") -> bool:
        """发送纯文本消息"""
        config = get_config()
        target_open_id = open_id or config.feishu.user_open_id
        target_chat_id = chat_id or config.feishu.chat_id

        body = {
            "content": json_dumps({"text": content}),
            "msg_type": "text",
        }
        return self._send_msg(body, target_open_id, target_chat_id)

    def send_card(self, card_json: dict, open_id: str = "",
                  chat_id: str = "") -> bool:
        """
        发送飞书消息卡片
        card_json: 飞书卡片 JSON 结构
        """
        config = get_config()
        target_open_id = open_id or config.feishu.user_open_id
        target_chat_id = chat_id or config.feishu.chat_id

        body = {
            "content": json_dumps(card_json),
            "msg_type": "interactive",
        }
        return self._send_msg(body, target_open_id, target_chat_id)

    def send_card_to_user(self, card_json: dict, open_id: str) -> bool:
        """发送卡片给指定用户"""
        return self.send_card(card_json, open_id=open_id)

    def send_card_to_chat(self, card_json: dict, chat_id: str) -> bool:
        """发送卡片到指定群聊"""
        return self.send_card(card_json, chat_id=chat_id)

    def reply_message(self, message_id: str, content: str,
                      msg_type: str = "text") -> bool:
        """回复用户消息"""
        body = {
            "content": json_dumps({"text": content}),
            "msg_type": msg_type,
        }
        try:
            resp = httpx.post(
                f"{self.BASE_URL}/im/v1/messages/{message_id}/reply",
                headers=self._headers(),
                json=body,
                timeout=10,
            )
            return resp.json().get("code") == 0
        except Exception:
            return False

    def reply_card(self, message_id: str, card_json: dict) -> bool:
        """回复卡片消息"""
        body = {
            "content": json_dumps(card_json),
            "msg_type": "interactive",
        }
        try:
            resp = httpx.post(
                f"{self.BASE_URL}/im/v1/messages/{message_id}/reply",
                headers=self._headers(),
                json=body,
                timeout=10,
            )
            return resp.json().get("code") == 0
        except Exception:
            return False

    def _send_msg(self, body: dict, open_id: str, chat_id: str) -> bool:
        """通用消息发送"""
        if open_id:
            body["receive_id"] = open_id
        elif chat_id:
            body["receive_id"] = chat_id
        else:
            return False

        try:
            resp = httpx.post(
                f"{self.BASE_URL}/im/v1/messages",
                params={"receive_id_type": "open_id" if open_id else "chat_id"},
                headers=self._headers(),
                json=body,
                timeout=10,
            )
            result = resp.json()
            if result.get("code") != 0:
                print(f"[飞书] 发送消息失败: {result}")
                return False
            return True
        except Exception as e:
            print(f"[飞书] 发送异常: {e}")
            return False


def json_dumps(obj) -> str:
    """JSON序列化（飞书API要求content字段为JSON字符串）"""
    return _json.dumps(obj, ensure_ascii=False)


# 模块级单例
feishu_client = FeishuClient()
