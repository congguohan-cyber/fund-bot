"""
数据采集 — 财经新闻
从财联社、东方财富等来源抓取当日新闻
"""
import re
from datetime import date, datetime
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup


@dataclass
class NewsItem:
    """新闻条目"""
    title: str
    source: str  # 来源：cls 财联社 / eastmoney 东方财富
    url: str = ""
    summary: str = ""
    time: str = ""
    tags: list[str] = field(default_factory=list)  # 关键词标签


class NewsCollector:
    """财经新闻采集器"""

    def __init__(self):
        self._cache: dict[str, list[NewsItem]] = {}

    def collect_all(self, target_date: date | None = None) -> list[NewsItem]:
        """采集所有来源的新闻"""
        d = target_date or date.today()
        d_str = d.strftime("%Y-%m-%d")

        if d_str in self._cache:
            return self._cache[d_str]

        all_news: list[NewsItem] = []

        # 财联社快讯
        cls_news = self._fetch_cls_news(d)
        all_news.extend(cls_news)

        # 东方财富头条
        em_news = self._fetch_eastmoney_news()
        all_news.extend(em_news)

        # 华尔街见闻（可选，可能被墙）
        # wsj_news = self._fetch_wallstreetcn_news()
        # all_news.extend(wsj_news)

        self._cache[d_str] = all_news
        return all_news

    def _fetch_cls_news(self, target_date: date) -> list[NewsItem]:
        """抓取财联社电报/快讯"""
        items = []
        try:
            # 财联社电报API
            url = "https://www.cls.cn/api/sw?app=CailianpressWeb&os=web&sv=8.4.6"
            resp = httpx.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.cls.cn/telegraph",
            })
            data = resp.json()
            roll_data = data.get("data", {}).get("roll_data", [])
            for item in roll_data[:50]:  # 取最近50条
                title = item.get("title", "") or item.get("content", "")
                ctime = item.get("ctime", 0)
                if title and len(title) > 5:
                    # 过滤广告和低质内容
                    skip_keywords = ["广告", "推广", "直播"]
                    if any(k in title for k in skip_keywords):
                        continue
                    items.append(NewsItem(
                        title=re.sub(r'<[^>]+>', '', title).strip(),
                        source="财联社",
                        url=f"https://www.cls.cn/detail/{item.get('id', '')}",
                        time=datetime.fromtimestamp(ctime).strftime("%H:%M") if ctime else "",
                    ))
        except Exception:
            pass
        return items

    def _fetch_eastmoney_news(self) -> list[NewsItem]:
        """抓取东方财富财经要闻"""
        items = []
        try:
            url = "https://finance.eastmoney.com/a/czqyw.html"
            resp = httpx.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })
            resp.encoding = "gbk"
            soup = BeautifulSoup(resp.text, "lxml")
            # 查找新闻列表
            news_list = soup.select(".newsList li, .listBox li, .articleItem")
            for elem in news_list[:40]:
                link = elem.find("a")
                if link and link.text.strip():
                    title = link.text.strip()
                    if len(title) > 8:
                        items.append(NewsItem(
                            title=title,
                            source="东方财富",
                            url=link.get("href", ""),
                        ))
        except Exception:
            pass
        return items

    def filter_relevant(self, news: list[NewsItem],
                        fund_keywords: list[str]) -> list[NewsItem]:
        """
        简单的关键词匹配过滤新闻
        fund_keywords: 从持仓中提取的关键词（如 ["新能源", "白酒", "半导体"]）
        """
        if not fund_keywords:
            return news[:15]  # 无偏好时返回最近15条

        relevant = []
        for item in news:
            title_lower = item.title.lower()
            for kw in fund_keywords:
                if kw.lower() in title_lower:
                    item.tags.append(kw)
                    relevant.append(item)
                    break

        # 返回匹配的 + 补充几条头条
        result = relevant[:12]
        if len(result) < 8:
            for item in news:
                if item not in result:
                    result.append(item)
                    if len(result) >= 12:
                        break
        return result

    def to_text_summary(self, news: list[NewsItem]) -> str:
        """转为文本摘要"""
        if not news:
            return "今日暂无相关新闻"
        lines = ["## 今日财经新闻", ""]
        for i, n in enumerate(news[:15], 1):
            tags_str = f" [{', '.join(n.tags)}]" if n.tags else ""
            source_str = f"({n.source})"
            lines.append(f"{i}. {n.title} {source_str}{tags_str}")
        return "\n".join(lines)


# 模块级单例
news_collector = NewsCollector()
