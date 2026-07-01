"""
分析编排器 — 主控流程
协调数据采集 → LLM分析 → 飞书推送的完整流水线
"""
import traceback
from datetime import date, datetime
from typing import Optional

from config import get_config
from database import (
    init_database, get_all_funds, save_analysis,
    mark_pushed, get_today_analysis,
)
from collectors.market import market_collector
from collectors.fund import fund_collector
from collectors.news import news_collector
from collectors.calendar import any_market_open, get_yesterday, is_trading_day
from analyzer.engine import llm_client
from feishu.client import feishu_client
from feishu.cards import build_fund_report_card, card_to_markdown


class FundAnalysisOrchestrator:
    """基金分析编排器"""

    def __init__(self):
        self.config = get_config()

    def run_daily_analysis(self, force: bool = False) -> dict | None:
        """
        执行每日分析全流程
        :param force: 强制运行（跳过交易日检查）
        """
        today = date.today()
        d_str = today.strftime("%Y-%m-%d")

        # 1. 交易日检查
        if not force and not any_market_open(today):
            print(f"[编排器] {d_str} 所有市场休市，跳过分析")
            return None

        # 2. 检查是否已分析过
        if not force:
            existing = get_today_analysis(d_str)
            if existing and existing.get("pushed"):
                print(f"[编排器] {d_str} 已分析过，跳过")
                return None

        print(f"[编排器] ====== 开始 {d_str} 基金分析 ======")

        try:
            # 3. 数据采集
            print("[编排器] 阶段1: 采集市场行情...")
            market = market_collector.collect_all(today)
            market_text = market.to_text_summary()

            print("[编排器] 阶段2: 采集基金数据...")
            funds = get_all_funds()
            if not funds:
                print("[编排器] 没有持仓基金，发送提示")
                feishu_client.send_text(
                    "📝 你还没有添加基金持仓。请发送「添加基金 [代码] [名称]」来开始使用。"
                )
                return None

            fund_data_list = []
            fund_keywords = set()
            for f in funds:
                code = f["fund_code"]
                name = f["fund_name"]
                ftype = f.get("fund_type", "")
                print(f"[编排器]   分析: {name} ({code})")
                fund_data = fund_collector.analyze_fund(code, name, ftype)
                fund_data_list.append(fund_data)
                # 收集持仓关键词
                for h in fund_data.holdings:
                    fund_keywords.add(h.stock_name)
                    # 也添加行业关键词
                    fund_keywords.add(fund_data.fund_type)

            # 4. 采集新闻
            print("[编排器] 阶段3: 采集财经新闻...")
            all_news = news_collector.collect_all(today)
            relevant_news = news_collector.filter_relevant(
                all_news, list(fund_keywords)
            )
            news_text = news_collector.to_text_summary(relevant_news)

            # 5. LLM 分析 — 阶段一：新闻过滤
            print("[编排器] 阶段4: LLM新闻过滤...")
            user_profile = _build_user_profile(funds, fund_data_list)
            news_json = llm_client.filter_news(
                user_profile, news_text, len(relevant_news)
            )
            relevant_news_text = json_dumps(news_json, indent=2)

            # 6. LLM 分析 — 阶段二：逐只基金分析
            print("[编排器] 阶段5: LLM逐基金分析...")
            fund_analyses = []
            for fd in fund_data_list:
                fund_text = fd.to_text_summary()
                analysis = llm_client.analyze_fund(
                    market_text, relevant_news_text, fund_text
                )
                fund_analyses.append(analysis)
                print(f"[编排器]   {fd.fund_name} 分析完成")

            # 7. LLM 分析 — 阶段三：综合报告
            print("[编排器] 阶段6: 生成综合报告...")
            all_analyses_text = json_dumps(fund_analyses, indent=2, ensure_ascii=False)
            report = llm_client.generate_report(
                market_text, all_analyses_text, d_str
            )

            # 8. 保存分析记录
            analysis_id = save_analysis(
                date=d_str,
                market_summary=market_text,
                fund_analyses=all_analyses_text,
                news_summary=news_text,
                suggestions=json_dumps(
                    [{
                        "fund_code": fa.get("fund_code", ""),
                        "action": fa.get("suggestion", {}).get("action", ""),
                    } for fa in fund_analyses],
                    ensure_ascii=False
                ),
                risk_alerts=json_dumps(
                    report.get("sections", {}).get("risk_alerts", {}).get("items", []),
                    ensure_ascii=False
                ),
                full_report=json_dumps(report, ensure_ascii=False),
            )

            # 9. 推送飞书
            print("[编排器] 阶段7: 推送飞书...")
            try:
                card = build_fund_report_card(report)
                success = feishu_client.send_card(card)
                if success:
                    mark_pushed(analysis_id)
                    print("[编排器] ✅ 飞书卡片推送成功")
                else:
                    # 降级：发送纯文本
                    print("[编排器] ⚠️ 卡片发送失败，降级为文本")
                    markdown = card_to_markdown(report)
                    feishu_client.send_text(markdown)
                    mark_pushed(analysis_id)
            except Exception as e:
                print(f"[编排器] ⚠️ 飞书推送异常: {e}")
                # 最后一次降级尝试
                try:
                    markdown = card_to_markdown(report)
                    feishu_client.send_text(markdown)
                    mark_pushed(analysis_id)
                except Exception:
                    pass

            print(f"[编排器] ====== {d_str} 分析完成 ======")
            return report

        except Exception as e:
            print(f"[编排器] ❌ 分析失败: {e}")
            traceback.print_exc()

            # 错误通知
            try:
                feishu_client.send_text(
                    f"⚠️ 今日基金分析生成失败\n"
                    f"错误: {str(e)[:200]}\n"
                    f"请稍后重试或发送「分析」手动触发。"
                )
            except Exception:
                pass
            return None

    def send_analysis_to_user(self, open_id: str) -> bool:
        """
        手动触发分析并发送给指定用户
        用于飞书对话中用户主动请求分析
        """
        today = date.today()
        d_str = today.strftime("%Y-%m-%d")

        # 先发送loading
        try:
            feishu_client.send_text("🔍 正在分析中，请稍候...", open_id=open_id)
        except Exception:
            pass

        report = self.run_daily_analysis(force=True)

        if report:
            try:
                card = build_fund_report_card(report)
                feishu_client.send_card(card, open_id=open_id)
                return True
            except Exception:
                markdown = card_to_markdown(report)
                feishu_client.send_text(markdown, open_id=open_id)
                return True
        else:
            feishu_client.send_text(
                "⚠️ 分析生成失败，请稍后重试。", open_id=open_id
            )
            return False


# ---- 辅助函数 ----

def _build_user_profile(funds: list[dict], fund_data_list: list) -> str:
    """构建用户持仓概况"""
    lines = ["## 用户持仓概况"]
    for f, fd in zip(funds, fund_data_list):
        lines.append(
            f"- {f['fund_name']} ({f['fund_code']}) "
            f"| {f.get('market', '')} | {f.get('fund_type', '')}"
        )
        if fd.holdings:
            top3 = [h.stock_name for h in fd.holdings[:3]]
            lines.append(f"  重仓: {', '.join(top3)}")
    return "\n".join(lines)


def json_dumps(obj, **kwargs) -> str:
    """JSON序列化"""
    import json
    kwargs.setdefault("ensure_ascii", False)
    return json.dumps(obj, **kwargs)


# 模块级单例
orchestrator = FundAnalysisOrchestrator()
