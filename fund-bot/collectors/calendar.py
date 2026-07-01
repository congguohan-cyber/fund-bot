"""
数据采集 — 交易日历
判断 A股/港股/美股 今天是否交易日
"""
from datetime import date, datetime, timedelta
from typing import Literal

import akshare as ak
from database import get_db

Market = Literal["A股", "港股", "美股"]


def _is_weekend(d: date) -> bool:
    """判断是否周末"""
    return d.weekday() >= 5


def _get_a_share_trading_days(year: int) -> set[str]:
    """获取A股某年交易日列表（带缓存）"""
    cache_key = f"a_share_{year}"
    with get_db() as conn:
        cached = conn.execute(
            "SELECT date FROM trading_calendar_cache WHERE market = 'A股' AND date LIKE ?",
            (f"{year}%",)
        ).fetchall()
        if cached:
            return {r["date"] for r in cached}

    # 从 AKShare 获取
    try:
        df = ak.tool_trade_date_hist_sina()
        trading_days = set()
        for _, row in df.iterrows():
            trade_date = str(row["trade_date"])
            if trade_date.startswith(str(year)):
                trading_days.add(trade_date)
                # 写入缓存
                with get_db() as conn:
                    conn.execute(
                        "INSERT OR IGNORE INTO trading_calendar_cache (date, market, is_trading_day) VALUES (?, 'A股', 1)",
                        (trade_date,)
                    )
        return trading_days
    except Exception:
        # fallback: 简单排除周末 + 春节/国庆附近
        return _fallback_trading_days(year, "A股")


def _get_hk_trading_days(year: int) -> set[str]:
    """获取港股交易日列表"""
    # 港股基本跟随A股，但有差异
    try:
        df = ak.stock_hk_index_daily(symbol="hscei")  # 用国企指数获取日历
        trading_days = set()
        for _, row in df.iterrows():
            d = str(row["date"])
            if d.startswith(str(year)):
                trading_days.add(d)
        return trading_days
    except Exception:
        return _fallback_trading_days(year, "港股")


def _get_us_trading_days(year: int) -> set[str]:
    """获取美股交易日列表"""
    cache_key = f"us_{year}"
    with get_db() as conn:
        cached = conn.execute(
            "SELECT date FROM trading_calendar_cache WHERE market = '美股' AND date LIKE ?",
            (f"{year}%",)
        ).fetchall()
        if cached:
            return {r["date"] for r in cached}

    try:
        from exchange_calendars import get_calendar
        xnys = get_calendar("XNYS")
        # 获取全年交易日
        sessions = xnys.sessions_in_range(
            f"{year}-01-01", f"{year}-12-31"
        )
        trading_days = {d.strftime("%Y-%m-%d") for d in sessions}
        # 缓存
        with get_db() as conn:
            for d in trading_days:
                conn.execute(
                    "INSERT OR IGNORE INTO trading_calendar_cache (date, market, is_trading_day) VALUES (?, '美股', 1)",
                    (d,)
                )
        return trading_days
    except ImportError:
        return _fallback_trading_days(year, "美股")


def _fallback_trading_days(year: int, market: str) -> set[str]:
    """
    降级方案：排除周末 + 已知主要节假日
    不如 AKShare 精确，但不会误判
    """
    from dateutil.rrule import rrule, DAILY
    import calendar

    # 主要节假日闭市
    holidays = {
        # A股长假期（简化）
        "A股": [
            # 春节前后约7天，元旦1天，清明1天，五一5天，端午1天，中秋1天，国庆7天
            # 这里简化处理：1月1日，5月1-3日，10月1-7日
            f"{year}-01-01", f"{year}-01-02",
            *(f"{year}-01-{d:02d}" for d in range(24, 32)),  # 春节附近
            *(f"{year}-05-{d:02d}" for d in range(1, 6)),
            *(f"{year}-10-{d:02d}" for d in range(1, 8)),
        ],
        "港股": [
            f"{year}-01-01",
            *(f"{year}-01-{d:02d}" for d in range(29, 32)),
            *(f"{year}-04-{d:02d}" for d in [5, 7, 8]),
            *(f"{year}-05-{d:02d}" for d in [1, 26]),
            *(f"{year}-07-{d:02d}" for d in [1]),
            *(f"{year}-10-{d:02d}" for d in [1]),
            f"{year}-12-25",
        ],
        "美股": [
            f"{year}-01-01",
            f"{year}-07-04",
            f"{year}-12-25",
        ],
    }

    market_holidays = set(holidays.get(market, []))
    trading_days = set()

    for d in rrule(DAILY, dtstart=date(year, 1, 1), until=date(year, 12, 31)):
        d_str = d.strftime("%Y-%m-%d")
        if d.weekday() < 5 and d_str not in market_holidays:
            trading_days.add(d_str)

    return trading_days


def is_trading_day(target_date: date | None = None, market: Market = "A股") -> bool:
    """
    判断指定日期是否为交易日
    :param target_date: 目标日期，默认今天
    :param market: 市场 (A股/港股/美股)
    """
    d = target_date or date.today()
    d_str = d.strftime("%Y-%m-%d")

    # 周末必休市
    if _is_weekend(d):
        return False

    # 查询缓存
    with get_db() as conn:
        cached = conn.execute(
            "SELECT is_trading_day FROM trading_calendar_cache WHERE date = ? AND market = ?",
            (d_str, market)
        ).fetchone()
        if cached is not None:
            return bool(cached["is_trading_day"])

    # 实时查询
    year = d.year
    if market == "A股":
        trading_days = _get_a_share_trading_days(year)
    elif market == "港股":
        trading_days = _get_hk_trading_days(year)
    else:
        trading_days = _get_us_trading_days(year)

    is_trade = d_str in trading_days

    # 缓存结果
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO trading_calendar_cache (date, market, is_trading_day) VALUES (?, ?, ?)",
            (d_str, market, int(is_trade))
        )

    return is_trade


def any_market_open(target_date: date | None = None) -> bool:
    """检查是否有任一市场开市"""
    return any(
        is_trading_day(target_date, m) for m in ("A股", "港股", "美股")
    )


def get_yesterday() -> date:
    """获取上一个自然日（用于分析昨天的行情）"""
    return date.today() - timedelta(days=1)


def get_last_trading_day(market: Market = "A股") -> date:
    """获取最近的交易日"""
    d = date.today() - timedelta(days=1)
    for _ in range(14):  # 最多回退14天
        if is_trading_day(d, market):
            return d
        d -= timedelta(days=1)
    return date.today() - timedelta(days=1)  # fallback
