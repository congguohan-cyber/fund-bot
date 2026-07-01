"""Test fixed data collectors"""
import sys
sys.path.insert(0, '.')
from collectors.market import market_collector
from collectors.fund import fund_collector
from datetime import date

yesterday = date(2026, 6, 30)

# Test market
print("=== Market (fixed) ===")
market = market_collector.collect_all(yesterday)
for idx in market.indices:
    print(f"  {idx.name}: {idx.close:.2f} ({idx.change_pct:+.2f}%) [{idx.market}]")
print()

# Test fund NAV
print("=== Fund NAV (fixed) ===")
for code in ["000001", "270042", "001875"]:
    nav = fund_collector.get_latest_nav(code)
    print(f"  {code}: nav={nav.get('nav', 0):.4f} date={nav.get('nav_date', 'N/A')} return={nav.get('daily_return', 0):+.2f}%")
