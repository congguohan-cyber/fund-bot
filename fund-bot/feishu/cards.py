"""
飞书消息卡片模板
将分析报告转为飞书 Card JSON 格式
参考: https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/card-components
"""
from datetime import datetime


def build_fund_report_card(report: dict) -> dict:
    """
    构建基金分析报告卡片
    输入：LLM生成的报告JSON
    输出：飞书卡片JSON
    """
    sections = report.get("sections", {})
    disclaimer = report.get("disclaimer", "仅供参考，不构成投资建议")

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": report.get("title", "📊 基金投资日报")
            },
            "template": "blue"
        },
        "elements": []
    }

    # 1. 大盘速览
    market_brief = sections.get("market_brief", {})
    if market_brief.get("items"):
        card["elements"].append(_section_header("📈 大盘速览"))
        card["elements"].append({
            "tag": "div",
            "fields": [
                {"tag": "lark_md", "content": item, "is_short": False}
                for item in market_brief["items"]
            ]
        })
        card["elements"].append({"tag": "hr"})

    # 2. 关键新闻
    top_news = sections.get("top_news", {})
    if top_news.get("items"):
        card["elements"].append(_section_header("📰 关键新闻"))
        for item in top_news["items"][:6]:
            tag = item.get("tag", "")
            color = _tag_color(tag)
            content = item.get("content", "")
            card["elements"].append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"{color} **[{tag}]** {content}"
                }
            })
        card["elements"].append({"tag": "hr"})

    # 3. 基金分析
    fund_analysis = sections.get("fund_analysis", {})
    if fund_analysis.get("funds"):
        card["elements"].append(_section_header("📊 基金分析"))
        for fund in fund_analysis["funds"]:
            card["elements"].append(_fund_card_block(fund))
        card["elements"].append({"tag": "hr"})

    # 4. 明日展望
    outlook = sections.get("tomorrow_outlook", {})
    if outlook:
        card["elements"].append(_section_header("🔮 明日展望"))
        card["elements"].append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": outlook.get("summary", "")
            }
        })
        if outlook.get("watch_points"):
            watch_text = "\n".join(f"• {p}" for p in outlook["watch_points"])
            card["elements"].append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**关注点：**\n{watch_text}"}
            })
        card["elements"].append({"tag": "hr"})

    # 5. 风险提示
    risk = sections.get("risk_alerts", {})
    if risk.get("items"):
        card["elements"].append(_section_header("⚠️ 风险提示"))
        risk_text = "\n".join(f"• {r}" for r in risk["items"])
        card["elements"].append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": risk_text}
        })
        card["elements"].append({"tag": "hr"})

    # 6. 底部信息
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    card["elements"].append({
        "tag": "note",
        "elements": [
            {"tag": "plain_text", "content": f"{disclaimer}\n🕐 {now} | 📊 AKShare/东方财富 | 🤖 Claude AI"}
        ]
    })

    return card


def build_fund_list_card(funds: list[dict]) -> dict:
    """构建持仓列表卡片"""
    content_lines = []
    for f in funds:
        content_lines.append(
            f"• **{f.get('fund_name', '')}** ({f.get('fund_code', '')}) "
            f"| {f.get('market', '')} | {f.get('fund_type', '')}"
        )

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "📋 我的基金持仓"},
            "template": "wathet"
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "\n".join(content_lines) if content_lines else "暂无持仓，输入「添加基金 XXX」来添加"
                }
            },
            {"tag": "hr"},
            {
                "tag": "note",
                "elements": [
                    {"tag": "plain_text", "content": f"共 {len(funds)} 只基金 | 💬 输入「分析」查看今日分析"}
                ]
            }
        ]
    }
    return card


def build_help_card() -> dict:
    """构建帮助卡片"""
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "🤖 基金分析助手 — 使用指南"},
            "template": "blue"
        },
        "elements": [
            _section_header("💬 对话指令"),
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        "• **分析 / 看看** — 触发今日基金分析\n"
                        "• **我的基金** — 查看当前持仓\n"
                        "• **添加基金 [代码] [名称] [市场]** — 添加持仓\n"
                        "  例：`添加基金 000001 华夏成长 A股`\n"
                        "• **删除基金 [代码]** — 移除持仓\n"
                        "• **帮助** — 显示此指南"
                    )
                }
            },
            {"tag": "hr"},
            _section_header("⏰ 自动推送"),
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "每个交易日早上7:00自动推送基金分析报告"
                }
            },
        ]
    }
    return card


def build_loading_card() -> dict:
    """构建「分析中」加载卡片"""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "🔍 正在分析中..."},
            "template": "blue"
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        "正在采集最新行情数据...\n"
                        "正在抓取财经新闻...\n"
                        "正在穿透持仓分析...\n"
                        "请稍候，预计需要30-60秒 ⏳"
                    )
                }
            }
        ]
    }


# ---- 卡片构建辅助函数 ----

def _section_header(title: str) -> dict:
    """段落标题"""
    return {
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"**{title}**"
        }
    }


def _tag_color(tag: str) -> str:
    """新闻标签颜色"""
    if tag in ("利好", "利好/"):
        return "🟢"
    elif tag in ("利空", "利空/"):
        return "🔴"
    return "⚪"


def _fund_card_block(fund: dict) -> dict:
    """基金分析卡片块"""
    action_emoji = fund.get("action_emoji", "✅")
    name = fund.get("name", "未知基金")
    change = fund.get("estimated_change", "0.00%")
    action = fund.get("action", "持有")
    reason = fund.get("brief_reason", "")
    detail = fund.get("detail", "")

    # 涨跌颜色
    change_str = str(change)
    if change_str.startswith("+") or (change_str.replace(".", "").isdigit() and float(change_str) > 0):
        change_color = "🟢"
    elif change_str.startswith("-"):
        change_color = "🔴"
    else:
        change_color = "⚪"

    md_content = (
        f"{action_emoji} **{name}** {change_color} {change}\n"
        f"建议：**{action}** — {reason}"
    )
    if detail:
        md_content += f"\n{detail}"

    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": md_content}
    }


def card_to_markdown(report: dict) -> str:
    """
    降级方案：将报告转为 Markdown 文本
    当飞书卡片发送失败时使用
    """
    sections = report.get("sections", {})
    lines = [f"## {report.get('title', '基金投资日报')}", ""]

    # 大盘
    mb = sections.get("market_brief", {})
    if mb.get("items"):
        lines.append("### 📈 大盘速览")
        for item in mb["items"]:
            lines.append(f"- {item}")
        lines.append("")

    # 新闻
    tn = sections.get("top_news", {})
    if tn.get("items"):
        lines.append("### 📰 关键新闻")
        for item in tn["items"]:
            lines.append(f"- [{item.get('tag', '')}] {item.get('content', '')}")
        lines.append("")

    # 基金
    fa = sections.get("fund_analysis", {})
    if fa.get("funds"):
        lines.append("### 📊 基金分析")
        for fund in fa["funds"]:
            lines.append(
                f"- {fund.get('action_emoji', '')} **{fund.get('name', '')}**: "
                f"{fund.get('estimated_change', '')} → {fund.get('action', '')} "
                f"({fund.get('brief_reason', '')})"
            )
        lines.append("")

    # 展望
    out = sections.get("tomorrow_outlook", {})
    if out:
        lines.append("### 🔮 明日展望")
        lines.append(out.get("summary", ""))
        lines.append("")

    # 风险
    risk = sections.get("risk_alerts", {})
    if risk.get("items"):
        lines.append("### ⚠️ 风险提示")
        for r in risk["items"]:
            lines.append(f"- {r}")
        lines.append("")

    lines.append(f"---\n{report.get('disclaimer', '')}")
    return "\n".join(lines)
