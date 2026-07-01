"""
数据采集 — 行情数据
A股指数 / 港股指数 / 美股指数 / 行业板块
"""
import json
from datetime import date, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional

import akshare as ak
import yfinance as yf

from collectors.calendar import get_last_trading_day, is_trading_day


@dataclass
class IndexData:
    """指数行情"""
    name: str
    code: str
    close: float
    open: float = 0
    high: float = 0
    low: float = 0
    change_pct: float = 0  # 涨跌幅 %
    volume: float = 0
    market: str = ""  # A股/港股/美股


@dataclass
class SectorData:
    """行业板块行情"""
    name: str
    change_pct: float
    leading_stock: str = ""


@dataclass
class MarketSnapshot:
    """市场快照"""
    date: str
    indices: list[IndexData] = field(default_factory=list)
    sectors: list[SectorData] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "indices": [asdict(i) for i in self.indices],
            "sectors": [asdict(s) for s in self.sectors],
        }

    def to_text_summary(self) -> str:
        """转为文本摘要供 LLM 使用"""
        lines = [f"## 市场行情 ({self.date})", ""]
        if self.indices:
            lines.append("### 核心指数")
            for idx in self.indices:
                sign = "+" if idx.change_pct >= 0 else ""
                lines.append(
                    f"- {idx.name} ({idx.code}): {idx.close:.2f} "
                    f"({sign}{idx.change_pct:.2f}%) [{idx.market}]"
                )
        if self.sectors:
            lines.append("")
            lines.append("### 领涨板块")
            for s in self.sectors[:5]:
                sign = "+" if s.change_pct >= 0 else ""
                lines.append(f"- {s.name}: {sign}{s.change_pct:.2f}%")
            lines.append("")
            lines.append("### 领跌板块")
            for s in self.sectors[-5:]:
                sign = "+" if s.change_pct >= 0 else ""
                lines.append(f"- {s.name}: {sign}{s.change_pct:.2f}%")
        return "\n".join(lines)


class MarketDataCollector:
    """行情数据采集器"""

    # A股核心指数
    A_INDEXES = {
        "000001": ("上证指数", "A股"),
        "399001": ("深证成指", "A股"),
        "399006": ("创业板指", "A股"),
        "000688": ("科创50", "A股"),
        "000300": ("沪深300", "A股"),
        "000905": ("中证500", "A股"),
        "000852": ("中证1000", "A股"),
    }

    # 港股核心指数
    HK_INDEXES = {
        "HSI": ("恒生指数", "港股"),
        "HSCEI": ("国企指数", "港股"),
        "HSTECH": ("恒生科技", "港股"),
    }

    # 美股核心指数 (yfinance tickers)
    US_INDEXES = {
        "^GSPC": ("标普500", "美股"),
        "^IXIC": ("纳斯达克", "美股"),
        "^DJI": ("道琼斯", "美股"),
        "^VIX": ("VIX恐慌指数", "美股"),
    }

    def __init__(self):
        self._cache: dict[str, MarketSnapshot] = {}

    def collect_all(self, target_date: date | None = None) -> MarketSnapshot:
        """采集所有市场行情"""
        d = target_date or date.today()
        d_str = d.strftime("%Y-%m-%d")

        if d_str in self._cache:
            return self._cache[d_str]

        snapshot = MarketSnapshot(date=d_str)
        indices: list[IndexData] = []

        # A股指数
        a_last = get_last_trading_day("A股")
        if a_last and a_last <= d:
            a_indices = self._collect_a_shares(a_last)
            indices.extend(a_indices)

        # 港股指数
        hk_last = get_last_trading_day("港股")
        if hk_last and hk_last <= d:
            hk_indices = self._collect_hk(hk_last)
            indices.extend(hk_indices)

        # 美股指数
        us_last = get_last_trading_day("美股")
        if us_last and us_last <= d:
            us_indices = self._collect_us(us_last)
            indices.extend(us_indices)

        snapshot.indices = indices
        snapshot.sectors = self._collect_a_sectors(a_last if a_last else d)

        self._cache[d_str] = snapshot
        return snapshot

    def _collect_a_shares(self, target_date: date) -> list[IndexData]:
        """采集A股指数（新版AKShare无pct_chg字段，手动计算）"""
        results = []
        d_str = target_date.strftime("%Y-%m-%d")
        try:
            for code, (name, market) in self.A_INDEXES.items():
                try:
                    prefix = "sh" if code.startswith(("0", "6", "9")) else "sz"
                    idx_df = ak.stock_zh_index_daily(symbol=f"{prefix}{code}")
                    idx_df["date"] = idx_df["date"].astype(str)
                    # 找到目标日期及前一天
                    match = idx_df[idx_df["date"] == d_str]
                    if match.empty:
                        continue
                    idx = match.index[0]
                    r = match.iloc[0]
                    # 计算涨跌幅 = (今日收盘 - 昨日收盘) / 昨日收盘
                    if idx > 0:
                        prev = idx_df.iloc[idx - 1]
                        pct = ((float(r["close"]) - float(prev["close"])) / float(prev["close"])) * 100
                    else:
                        pct = 0.0
                    results.append(IndexData(
                        name=name, code=code,
                        close=float(r["close"]),
                        open=float(r.get("open", 0)),
                        high=float(r.get("high", 0)),
                        low=float(r.get("low", 0)),
                        change_pct=round(pct, 2),
                        volume=float(r.get("volume", 0)),
                        market=market,
                    ))
                except Exception:
                    continue
        except Exception:
            pass
        return results

    def _collect_hk(self, target_date: date) -> list[IndexData]:
        """采集港股指数（新版AKShare: stock_hk_index_daily_em）"""
        results = []
        d_str = target_date.strftime("%Y-%m-%d")
        try:
            df = ak.stock_hk_index_daily_em()
            if df is not None and not df.empty:
                df["date"] = df["date"].astype(str)
                match = df[df["date"] == d_str]
                if match.empty:
                    return results
                # 该API返回所有港股主要指数，我们选取关键几个
                name_map = {
                    "恒生指数": ("恒生指数", "HSI"),
                    "国企指数": ("国企指数", "HSCEI"),
                    "恒生科技指数": ("恒生科技", "HSTECH"),
                }
                for _, row in match.iterrows():
                    idx_name = str(row.get("指数名称", ""))
                    if idx_name in name_map:
                        display_name, code = name_map[idx_name]
                        # 计算涨跌幅
                        idx_row = df[df["date"] == d_str]
                        if len(idx_row) > 0:
                            r = idx_row.iloc[0]
                            prev_idx = df.index[df["date"] == d_str][0]
                            if prev_idx > 0:
                                prev_r = df.iloc[prev_idx - 1]
                                pct = ((float(r["收盘"]) - float(prev_r["收盘"])) / float(prev_r["收盘"])) * 100
                            else:
                                pct = 0
                            results.append(IndexData(
                                name=display_name, code=code,
                                close=float(r["收盘"]),
                                open=float(r.get("开盘", 0)),
                                high=float(r.get("最高", 0)),
                                low=float(r.get("最低", 0)),
                                change_pct=round(pct, 2),
                                volume=float(r.get("成交量", 0)),
                                market=market,
                            ))
        except Exception:
            pass
        return results

    def _collect_us(self, target_date: date) -> list[IndexData]:
        """采集美股指数（yfinance）"""
        results = []
        try:
            for ticker, (name, market) in self.US_INDEXES.items():
                try:
                    yf_ticker = yf.Ticker(ticker)
                    # 获取最近几天数据
                    hist = yf_ticker.history(period="5d")
                    if hist is not None and not hist.empty:
                        r = hist.iloc[-1]
                        prev = hist.iloc[-2] if len(hist) > 1 else r
                        pct = ((r["Close"] - prev["Close"]) / prev["Close"]) * 100
                        results.append(IndexData(
                            name=name, code=ticker,
                            close=float(r["Close"]),
                            open=float(r["Open"]),
                            high=float(r["High"]),
                            low=float(r["Low"]),
                            change_pct=round(pct, 2),
                            volume=float(r["Volume"]),
                            market=market,
                        ))
                except Exception:
                    continue
        except Exception:
            pass
        return results

    def _collect_a_sectors(self, target_date: date) -> list[SectorData]:
        """采集A股行业板块涨跌"""
        sectors = []
        try:
            df = ak.stock_board_industry_name_em()
            if df is not None and not df.empty:
                df = df.sort_values("涨跌幅", ascending=False)
                for _, row in df.iterrows():
                    sectors.append(SectorData(
                        name=str(row["板块名称"]),
                        change_pct=float(row["涨跌幅"]),
                        leading_stock=str(row.get("领涨股票", "")),
                    ))
        except Exception:
            pass
        return sectors


# 模块级单例
market_collector = MarketDataCollector()
