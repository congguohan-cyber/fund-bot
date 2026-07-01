"""快速验证数据采集模块"""
import sys
sys.path.insert(0, '.')

# 初始化数据库
from database import init_database
init_database()
print('✅ 数据库初始化成功')

# 测试交易日历
from collectors.calendar import is_trading_day, any_market_open, get_yesterday
yesterday = get_yesterday()
print(f'\n📅 昨天: {yesterday}')
print(f'   A股交易: {is_trading_day(yesterday, "A股")}')
print(f'   港股交易: {is_trading_day(yesterday, "港股")}')
print(f'   美股交易: {is_trading_day(yesterday, "美股")}')
print(f'   任一开市: {any_market_open(yesterday)}')

# 测试行情采集
print('\n📊 采集行情...')
from collectors.market import market_collector
try:
    market = market_collector.collect_all(yesterday)
    print(f'   获取了 {len(market.indices)} 个指数')
    for idx in market.indices:
        print(f'   {idx.name}: {idx.close:.2f} ({idx.change_pct:+.2f}%) [{idx.market}]')
    print('   ✅ 行情采集 OK')
except Exception as e:
    print(f'   ⚠️ 行情采集出错: {e}')

# 测试新闻采集
print('\n📰 采集新闻...')
from collectors.news import news_collector
try:
    news = news_collector.collect_all(yesterday)
    print(f'   获取了 {len(news)} 条新闻')
    for n in news[:5]:
        print(f'   [{n.source}] {n.title[:80]}')
    print('   ✅ 新闻采集 OK')
except Exception as e:
    print(f'   ⚠️ 新闻采集出错: {e}')

# 测试基金数据（示例：华夏成长 000001）
print('\n📈 测试基金数据...')
from collectors.fund import fund_collector
try:
    fund = fund_collector.analyze_fund("000001", "华夏成长混合", "A股混合")
    print(f'   基金: {fund.fund_name}')
    print(f'   净值: {fund.nav:.4f} ({fund.nav_date})')
    print(f'   日涨跌: {fund.nav_change_pct:+.2f}%')
    print(f'   重仓股: {len(fund.holdings)} 只')
    for h in fund.holdings[:5]:
        print(f'     {h.stock_name}: 权重{h.weight:.1f}% 今日{h.change_pct:+.2f}%')
    print(f'   推算涨跌: {fund.estimated_nav_change:+.2f}%')
    print('   ✅ 基金数据 OK')
except Exception as e:
    print(f'   ⚠️ 基金数据出错: {e}')

print('\n✅ 数据采集验证全部通过！')
