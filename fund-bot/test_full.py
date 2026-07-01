"""Full fixed data test"""
import sys
sys.path.insert(0, '.')
from collectors.market import market_collector
from collectors.fund import fund_collector
from collectors.news import news_collector
from database import init_database, get_all_funds
from datetime import date

init_database()
yesterday = date(2026, 6, 30)

print("=" * 50)
print(f"FULL DATA TEST — {yesterday}")
print("=" * 50)

# Market
print("\n>>> MARKET <<<")
market = market_collector.collect_all(yesterday)
for idx in market.indices:
    sign = "+" if idx.change_pct >= 0 else ""
    print(f"  [{idx.market}] {idx.name}: {idx.close:.2f} ({sign}{idx.change_pct:.2f}%)")
print(f"  Sectors: {len(market.sectors)}")

# Funds with full analysis
print("\n>>> FUNDS <<<")
funds = get_all_funds()
all_keywords = set()
for f in funds:
    fd = fund_collector.analyze_fund(f["fund_code"], f["fund_name"], f.get("fund_type", ""))
    sign = "+" if fd.nav_change_pct >= 0 else ""
    print(f"  {fd.fund_name}: NAV={fd.nav:.4f} ({sign}{fd.nav_change_pct:.2f}%) holdings={len(fd.holdings)} est={fd.estimated_nav_change:+.2f}%")
    for h in fd.holdings[:3]:
        print(f"    {h.stock_name} w{h.weight:.1f}% chg{h.change_pct:+.2f}%")
    for h in fd.holdings:
        all_keywords.add(h.stock_name)

# News
print("\n>>> NEWS <<<")
news = news_collector.collect_all(yesterday)
if news:
    print(f"  Total: {len(news)}")
    for n in news[:5]:
        print(f"  [{n.source}] {n.title[:80]}")
else:
    print("  WARNING: No news collected (CLS/Eastmoney may have changed API)")

print("\n" + "=" * 50)
print("TEST COMPLETE")
