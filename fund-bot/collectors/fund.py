"""
数据采集 — 基金数据
基金净值、重仓股（穿透持仓）、基本信息
"""
from datetime import date, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional

import akshare as ak
import httpx


@dataclass
class StockHolding:
    """重仓股"""
    stock_code: str
    stock_name: str
    weight: float  # 占净值比 %
    change_pct: float = 0  # 今日涨跌幅
    contribution: float = 0  # 对基金净值贡献 (%)


@dataclass
class FundData:
    """基金完整数据"""
    fund_code: str
    fund_name: str
    fund_type: str = ""
    nav: float = 0  # 最新净值
    acc_nav: float = 0  # 累计净值
    nav_date: str = ""  # 净值日期
    nav_change_pct: float = 0  # 日涨跌幅
    holdings: list[StockHolding] = field(default_factory=list)
    holdings_report_date: str = ""  # 持仓报告期
    estimated_nav_change: float = 0  # 基于重仓股推算的涨跌

    def to_text_summary(self) -> str:
        """文本摘要"""
        lines = [
            f"### {self.fund_name} ({self.fund_code})",
            f"- 类型: {self.fund_type}",
            f"- 最新净值: {self.nav:.4f} ({self.nav_date})",
        ]
        sign = "+" if self.nav_change_pct >= 0 else ""
        lines.append(f"- 日涨跌: {sign}{self.nav_change_pct:.2f}%")

        if self.holdings:
            lines.append(f"- 重仓股 (基于 {self.holdings_report_date} 季报):")
            for h in self.holdings[:10]:
                s = "+" if h.change_pct >= 0 else ""
                lines.append(
                    f"  • {h.stock_name}({h.stock_code}) "
                    f"权重{h.weight:.1f}% 今日{s}{h.change_pct:.2f}% "
                    f"→ 贡献{h.contribution:+.3f}%"
                )
            if self.estimated_nav_change != 0:
                sign2 = "+" if self.estimated_nav_change >= 0 else ""
                lines.append(f"- 持仓推算涨跌: {sign2}{self.estimated_nav_change:.2f}%")
                deviation = self.nav_change_pct - self.estimated_nav_change
                if abs(deviation) > 0.5:
                    lines.append(f"  ⚠️ 偏离度较大 ({deviation:+.2f}%)，基金经理可能已调仓")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "fund_code": self.fund_code,
            "fund_name": self.fund_name,
            "fund_type": self.fund_type,
            "nav": self.nav,
            "acc_nav": self.acc_nav,
            "nav_date": self.nav_date,
            "nav_change_pct": self.nav_change_pct,
            "holdings_report_date": self.holdings_report_date,
            "estimated_nav_change": self.estimated_nav_change,
            "holdings": [asdict(h) for h in self.holdings],
        }


class FundDataCollector:
    """基金数据采集器"""

    def __init__(self):
        self._nav_cache: dict[str, dict] = {}

    def get_fund_info(self, fund_code: str) -> dict:
        """获取基金基本信息"""
        try:
            df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="基本信息")
            if df is not None and not df.empty:
                info = {}
                for _, row in df.iterrows():
                    info[str(row["项目"])] = str(row["内容"])
                return info
        except Exception:
            pass
        return {}

    def get_latest_nav(self, fund_code: str) -> dict:
        """
        获取最新净值（新版AKShare: fund_open_fund_daily_em() 无参数，返回全量数据）
        """
        if fund_code in self._nav_cache:
            return self._nav_cache[fund_code]
        try:
            df = ak.fund_open_fund_daily_em()
            if df is not None and not df.empty:
                # 筛选目标基金
                match = df[df["基金代码"] == fund_code]
                if match.empty:
                    return {}
                row = match.iloc[0]
                # 获取最新的日期列（列名形如 2026-06-30-单位净值）
                nav_cols = [c for c in df.columns if "-单位净值" in c and not c.startswith("累计")]
                acc_cols = [c for c in df.columns if "-累计净值" in c]
                growth_col = "日增长率" if "日增长率" in df.columns else None
                if nav_cols:
                    latest_date = nav_cols[-1].replace("-单位净值", "")
                    result = {
                        "nav_date": latest_date,
                        "nav": float(row[nav_cols[-1]]) if row[nav_cols[-1]] else 0,
                        "acc_nav": float(row[acc_cols[-1]]) if acc_cols and row[acc_cols[-1]] else 0,
                        "daily_return": float(row[growth_col]) if growth_col and row[growth_col] else 0,
                    }
                    self._nav_cache[fund_code] = result
                    return result
        except Exception:
            pass
        return {}

    def get_top_holdings(self, fund_code: str) -> tuple[list[dict], str]:
        """
        获取前十大重仓股
        Returns: (holdings_list, report_date)
        """
        holdings = []
        report_date = ""
        try:
            # 用 AKShare 获取基金持仓
            df = ak.fund_portfolio_hold_em(symbol=fund_code)
            if df is not None and not df.empty:
                # 有多个报告期数据，取最新
                latest = df.iloc[-1]
                report_date = str(latest.get("季度", ""))
                # 取最新季度的所有记录
                for _, row in df[df["季度"] == report_date].iterrows():
                    holdings.append({
                        "stock_code": str(row.get("股票代码", "")),
                        "stock_name": str(row.get("股票名称", "")),
                        "weight": float(row.get("占净值比例", 0) or 0),
                    })
        except Exception:
            # fallback: 尝试天天基金HTML抓取
            holdings, report_date = self._scrape_eastmoney_holdings(fund_code)

        return holdings, report_date

    def _scrape_eastmoney_holdings(self, fund_code: str) -> tuple[list[dict], str]:
        """从天天基金网页抓取重仓股"""
        holdings = []
        report_date = ""
        try:
            url = f"https://fundf10.eastmoney.com/ccmx_{fund_code}.html"
            resp = httpx.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            # 天天基金会把持仓数据内嵌在页面变量中
            text = resp.text
            # 简单解析（更稳健的做法是解析JSONP数据）
            import re
            import json
            # 找 fundcode 相关数据
            match = re.search(r'var\s+fundcode\s*=\s*"(\d+)"', text)
            if match:
                # 用API接口获取
                api_url = (
                    f"https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
                    f"?type=jjcc&code={fund_code}&topline=10&year=&month=&rt=0.5"
                )
                api_resp = httpx.get(api_url, timeout=10, headers={
                    "Referer": url,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                # 解析返回的HTML table
                api_text = api_resp.text
                # 提取表格行
                rows = re.findall(r'<tr[^>]*>.*?</tr>', api_text, re.DOTALL)
                for row in rows:
                    cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                    if len(cells) >= 4:
                        stock_code = re.sub(r'<[^>]+>', '', cells[0]).strip()
                        stock_name = re.sub(r'<[^>]+>', '', cells[1]).strip()
                        try:
                            weight = float(re.sub(r'<[^>]+>', '', cells[5]).strip().replace('%', ''))
                        except (ValueError, IndexError):
                            weight = 0
                        if stock_code and stock_code.isdigit():
                            holdings.append({
                                "stock_code": stock_code,
                                "stock_name": stock_name,
                                "weight": weight,
                            })
        except Exception:
            pass
        return holdings, report_date or "未知"

    def get_stock_prices(self, stock_codes: list[str]) -> dict[str, float]:
        """
        获取股票最新涨跌幅（新AKShare: stock_zh_a_hist 参数变化）
        Returns: {stock_code: change_pct}
        """
        result = {}
        for code in stock_codes:
            try:
                # 港股跳过（会有单独处理）
                if len(code) > 6 or not code.isdigit():
                    continue
                # A股: ak.stock_zh_a_hist 新参数
                if code.startswith(("6", "5")):
                    symbol = f"{code}"
                elif code.startswith(("0", "3")):
                    symbol = f"{code}"
                elif code.startswith(("4", "8")):
                    symbol = f"{code}"
                else:
                    continue

                df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
                if df is not None and not df.empty:
                    if len(df) >= 2:
                        latest = df.iloc[-1]
                        prev = df.iloc[-2]
                        pct = ((float(latest["收盘"]) - float(prev["收盘"])) / float(prev["收盘"])) * 100
                        result[code] = round(pct, 2)
                    else:
                        result[code] = 0
            except Exception as e:
                result[code] = 0
        return result

    def analyze_fund(self, fund_code: str, fund_name: str,
                     fund_type: str = "") -> FundData:
        """综合分析单只基金：净值 + 持仓穿透"""
        fund_data = FundData(
            fund_code=fund_code,
            fund_name=fund_name,
            fund_type=fund_type,
        )

        # 1. 获取最新净值
        nav_info = self.get_latest_nav(fund_code)
        if nav_info:
            fund_data.nav = nav_info.get("nav", 0)
            fund_data.acc_nav = nav_info.get("acc_nav", 0)
            fund_data.nav_date = nav_info.get("nav_date", "")
            fund_data.nav_change_pct = nav_info.get("daily_return", 0)

        # 2. 获取重仓股
        top_holdings, report_date = self.get_top_holdings(fund_code)
        fund_data.holdings_report_date = report_date

        if top_holdings:
            # 3. 获取这些股票今日涨跌
            stock_codes = [h["stock_code"] for h in top_holdings]
            prices = self.get_stock_prices(stock_codes)

            # 4. 计算每只重仓股对基金的贡献
            total_contribution = 0
            for h in top_holdings:
                code = h["stock_code"]
                change_pct = prices.get(code, 0)
                weight = h["weight"]
                contribution = (change_pct * weight) / 100  # 加权贡献
                total_contribution += contribution
                fund_data.holdings.append(StockHolding(
                    stock_code=code,
                    stock_name=h["stock_name"],
                    weight=weight,
                    change_pct=change_pct,
                    contribution=round(contribution, 4),
                ))

            fund_data.estimated_nav_change = round(total_contribution, 2)

        return fund_data


# 模块级单例
fund_collector = FundDataCollector()
