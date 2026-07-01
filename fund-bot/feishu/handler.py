"""
飞书消息处理器 — 接收消息、路由指令、触发分析
"""
import json
import re
import hashlib
from datetime import date

from config import get_config
from database import get_all_funds, add_fund, remove_fund
from feishu.client import feishu_client
from feishu.cards import (
    build_fund_list_card,
    build_help_card,
    build_loading_card,
    build_fund_report_card,
    card_to_markdown,
)


def verify_fingerprint(timestamp: str, nonce: str, body: str) -> str:
    """
    飞书事件签名验证
    返回需匹配的签名
    """
    config = get_config()
    token = config.feishu.verification_token
    # 飞书签名算法: sha256(timestamp + nonce + encrypt_key + body)
    raw = f"{timestamp}{nonce}{token}{body}"
    return hashlib.sha256(raw.encode()).hexdigest()


def handle_event(event_data: dict) -> dict:
    """
    处理飞书事件回调
    返回飞书要求的响应
    """
    event_type = event_data.get("type", "")
    # URL 验证
    if event_type == "url_verification":
        return {"challenge": event_data.get("challenge", "")}

    # 消息事件
    if event_type == "event_callback":
        event = event_data.get("event", {})
        msg_type = event.get("message", {}).get("message_type", "")
        if msg_type == "text":
            return _handle_text_message(event)

    return {"code": 0}


def _handle_text_message(event: dict) -> dict:
    """处理文本消息"""
    message = event.get("message", {})
    sender = event.get("sender", {})
    message_id = message.get("message_id", "")
    content_str = message.get("content", "{}")
    open_id = sender.get("sender_id", {}).get("open_id", "")

    # 解析消息内容
    try:
        content = json.loads(content_str)
        text = content.get("text", "").strip()
    except (json.JSONDecodeError, TypeError):
        text = content_str

    # 提取@bot 后的实际文本
    text = re.sub(r'@\S+\s*', '', text).strip()

    # 路由指令
    if not text:
        return {"code": 0}

    if _match_command(text, ["分析", "看看", "行情", "报告", "日报"]):
        # 异步触发分析（先返回loading，分析完成后发卡片）
        return _trigger_analysis(open_id, message_id)

    elif _match_command(text, ["我的基金", "持仓", "基金列表", "持有哪些"]):
        funds = get_all_funds()
        card = build_fund_list_card(funds)
        feishu_client.reply_card(message_id, card)
        # 如果卡片失败，降级为文本
        # feishu_client.reply_message(message_id, ...)
        return {"code": 0}

    elif text.startswith("添加") or text.startswith("新增"):
        return _handle_add_fund(text, message_id)

    elif text.startswith("删除") or text.startswith("移除"):
        return _handle_remove_fund(text, message_id)

    elif _match_command(text, ["帮助", "help", "怎么用", "功能"]):
        card = build_help_card()
        feishu_client.reply_card(message_id, card)
        return {"code": 0}

    else:
        # 默认回复
        feishu_client.reply_message(
            message_id,
            "💡 你可以试试：\n"
            "• 发送「**分析**」查看今日基金分析\n"
            "• 发送「**我的基金**」查看持仓\n"
            "• 发送「**帮助**」查看使用指南"
        )
        return {"code": 0}


def _match_command(text: str, keywords: list[str]) -> bool:
    """命令关键词匹配"""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _trigger_analysis(open_id: str, message_id: str) -> dict:
    """
    触发分析流程
    由于飞书回调要求3秒内返回，先回复loading卡片，
    实际的长时间分析需要通过异步方式处理
    """
    # 先回复 loading
    loading_card = build_loading_card()
    feishu_client.reply_card(message_id, loading_card)

    # 触发异步分析（实际部署时用消息队列或后台任务）
    # 这里同步执行简化版（飞书FC超时时间较长）
    _ = open_id  # 暂存，异步任务中使用
    _ = message_id

    return {"code": 0}


def _handle_add_fund(text: str, message_id: str) -> dict:
    """处理添加基金指令"""
    # 解析: 添加基金 000001 华夏成长 A股
    # 或: 添加基金 000001
    parts = text.replace("添加", "").replace("新增", "").replace("基金", "").strip().split()
    if len(parts) >= 1:
        fund_code = parts[0]
        fund_name = parts[1] if len(parts) >= 2 else f"基金{fund_code}"
        market = parts[2] if len(parts) >= 3 else "A股"

        success = add_fund(fund_code, fund_name, market)
        if success:
            feishu_client.reply_message(
                message_id,
                f"✅ 已添加基金：**{fund_name}** ({fund_code}) | {market}\n"
                f"系统将自动获取该基金的持仓和净值数据。"
            )
        else:
            feishu_client.reply_message(
                message_id,
                f"⚠️ 基金 {fund_code} 已存在，请勿重复添加。"
            )
    else:
        feishu_client.reply_message(
            message_id,
            "📝 请按格式输入：`添加基金 [代码] [名称] [市场]`\n"
            "例：`添加基金 000001 华夏成长 A股`"
        )
    return {"code": 0}


def _handle_remove_fund(text: str, message_id: str) -> dict:
    """处理删除基金指令"""
    parts = text.replace("删除", "").replace("移除", "").replace("基金", "").strip().split()
    if len(parts) >= 1:
        fund_code = parts[0]
        success = remove_fund(fund_code)
        if success:
            feishu_client.reply_message(
                message_id, f"🗑️ 已删除基金：{fund_code}"
            )
        else:
            feishu_client.reply_message(
                message_id, f"⚠️ 未找到基金：{fund_code}"
            )
    else:
        feishu_client.reply_message(
            message_id, "📝 请按格式输入：`删除基金 [代码]`"
        )
    return {"code": 0}
