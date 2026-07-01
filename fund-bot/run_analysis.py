"""GitHub Actions 运行入口 — 每日基金分析"""
import os
import sys
import traceback

# 确保当前目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print(f"=== 环境信息 ===")
print(f"CWD: {os.getcwd()}")
print(f"Python: {sys.version}")
print(f"Path: {sys.path[:3]}")

# 调试：检查环境变量
env_keys = ["FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_USER_OPEN_ID",
            "DEEPSEEK_API_KEY", "FORCE_ANALYSIS"]
for k in env_keys:
    v = os.environ.get(k, "")
    masked = v[:6] + "***" if v and len(v) > 6 else "(missing)"
    print(f"ENV {k}: {masked}")

# 检查关键模块
print(f"\n=== 模块检查 ===")
for mod in ["akshare", "yfinance", "openai", "httpx", "lark_oapi", "fastapi"]:
    try:
        __import__(mod)
        print(f"  {mod}: OK")
    except ImportError:
        print(f"  {mod}: MISSING!")

# 初始化数据库
print(f"\n=== 数据库 ===")
try:
    from database import init_database
    os.makedirs("data", exist_ok=True)
    init_database()
    print("DB OK")
except Exception:
    traceback.print_exc()
    sys.exit(1)

# 运行分析
print(f"\n=== 运行分析 ===")
try:
    from orchestrator import orchestrator
    force = os.environ.get("FORCE_ANALYSIS", "false").lower() == "true"
    report = orchestrator.run_daily_analysis(force=force)
    if report:
        print("\n=== 分析成功 ===")
    else:
        print("\n=== 跳过（非交易日或已分析）===")
except Exception:
    traceback.print_exc()
    sys.exit(1)
