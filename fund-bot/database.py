"""
基金分析 Bot — SQLite 数据库层
管理基金持仓、持仓快照、分析记录
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

from config import get_config


def _ensure_data_dir(db_path: str) -> None:
    """确保数据库目录存在"""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    config = get_config()
    _ensure_data_dir(config.database_path)
    conn = sqlite3.connect(config.database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    """上下文管理器获取数据库连接"""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database() -> None:
    """初始化数据库表结构"""
    with get_db() as conn:
        conn.executescript("""
            -- 用户基金持仓
            CREATE TABLE IF NOT EXISTS fund_holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fund_code TEXT NOT NULL UNIQUE,
                fund_name TEXT NOT NULL,
                market TEXT NOT NULL DEFAULT 'A股',
                fund_type TEXT DEFAULT '',
                purchase_date TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            -- 基金持仓快照（重仓股，每季度更新）
            CREATE TABLE IF NOT EXISTS fund_holdings_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fund_code TEXT NOT NULL,
                report_date TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                stock_name TEXT NOT NULL,
                weight REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                UNIQUE(fund_code, report_date, stock_code)
            );

            -- 每日分析记录
            CREATE TABLE IF NOT EXISTS daily_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_date TEXT NOT NULL,
                market_summary TEXT,
                fund_analyses TEXT,
                news_summary TEXT,
                suggestions TEXT,
                risk_alerts TEXT,
                full_report TEXT,
                pushed INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            -- 交易日历缓存
            CREATE TABLE IF NOT EXISTS trading_calendar_cache (
                date TEXT PRIMARY KEY,
                market TEXT NOT NULL,
                is_trading_day INTEGER NOT NULL,
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            -- 索引
            CREATE INDEX IF NOT EXISTS idx_holdings_snapshot_fund
                ON fund_holdings_snapshot(fund_code);
            CREATE INDEX IF NOT EXISTS idx_holdings_snapshot_date
                ON fund_holdings_snapshot(report_date);
            CREATE INDEX IF NOT EXISTS idx_daily_analysis_date
                ON daily_analysis(analysis_date);
        """)


# ---- 基金持仓 CRUD ----

def get_all_funds() -> list[dict]:
    """获取所有持仓基金"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM fund_holdings ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]


def add_fund(fund_code: str, fund_name: str, market: str = "A股",
             fund_type: str = "", purchase_date: str = "", notes: str = "") -> bool:
    """添加基金"""
    with get_db() as conn:
        try:
            conn.execute(
                """INSERT INTO fund_holdings (fund_code, fund_name, market, fund_type, purchase_date, notes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (fund_code, fund_name, market, fund_type, purchase_date, notes)
            )
            return True
        except sqlite3.IntegrityError:
            return False


def remove_fund(fund_code: str) -> bool:
    """删除基金"""
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM fund_holdings WHERE fund_code = ?", (fund_code,)
        )
        return cursor.rowcount > 0


# ---- 持仓快照 ----

def save_holdings_snapshot(fund_code: str, report_date: str,
                           holdings: list[dict]) -> None:
    """
    保存基金重仓股快照
    holdings: [{"stock_code": "600519", "stock_name": "贵州茅台", "weight": 7.5}, ...]
    """
    with get_db() as conn:
        for h in holdings:
            conn.execute(
                """INSERT OR REPLACE INTO fund_holdings_snapshot
                   (fund_code, report_date, stock_code, stock_name, weight)
                   VALUES (?, ?, ?, ?, ?)""",
                (fund_code, report_date, h["stock_code"], h["stock_name"], h.get("weight", 0))
            )


def get_latest_holdings(fund_code: str) -> list[dict]:
    """获取基金最新一期重仓股"""
    with get_db() as conn:
        # 找到最新报告日期
        latest = conn.execute(
            "SELECT report_date FROM fund_holdings_snapshot WHERE fund_code = ? "
            "ORDER BY report_date DESC LIMIT 1",
            (fund_code,)
        ).fetchone()
        if not latest:
            return []
        rows = conn.execute(
            "SELECT * FROM fund_holdings_snapshot "
            "WHERE fund_code = ? AND report_date = ?",
            (fund_code, latest["report_date"])
        ).fetchall()
        return [dict(r) for r in rows]


# ---- 分析记录 ----

def save_analysis(date: str, market_summary: str, fund_analyses: str,
                  news_summary: str, suggestions: str, risk_alerts: str,
                  full_report: str = "") -> int:
    """保存每日分析结果"""
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO daily_analysis
               (analysis_date, market_summary, fund_analyses, news_summary,
                suggestions, risk_alerts, full_report)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (date, market_summary, fund_analyses, news_summary,
             suggestions, risk_alerts, full_report)
        )
        return cursor.lastrowid


def mark_pushed(analysis_id: int) -> None:
    """标记分析已推送"""
    with get_db() as conn:
        conn.execute(
            "UPDATE daily_analysis SET pushed = 1 WHERE id = ?",
            (analysis_id,)
        )


def get_today_analysis(date: str) -> dict | None:
    """获取指定日期的分析"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM daily_analysis WHERE analysis_date = ?",
            (date,)
        ).fetchone()
        return dict(row) if row else None
