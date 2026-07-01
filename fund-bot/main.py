"""
基金分析飞书 Bot — 主入口
支持：
  1. 阿里云 FC HTTP 触发器（飞书事件回调 + 手动API）
  2. 阿里云 FC 定时触发器（每日自动分析）
  3. 本地开发调试
"""
import json
import traceback
from datetime import date
from typing import Optional

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse

from config import get_config
from database import init_database
from feishu.handler import handle_event
from feishu.client import feishu_client
from feishu.cards import build_help_card
from orchestrator import orchestrator

# ---- FastAPI 应用 ----

app = FastAPI(
    title="基金分析 Bot",
    description="飞书基金分析助手 - 每日自动分析 + 对话交互",
    version="1.0.0",
)


@app.on_event("startup")
async def startup():
    """应用启动：初始化数据库"""
    print("[启动] 初始化数据库...")
    init_database()
    print("[启动] 基金分析 Bot 已就绪")


# ---- 飞书事件回调 ----

@app.post("/feishu/event")
async def feishu_event(request: Request):
    """接收飞书事件回调"""
    try:
        body = await request.body()
        body_str = body.decode("utf-8")
        event_data = json.loads(body_str)

        # 验证签名（可选，生产环境建议开启）
        # timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
        # nonce = request.headers.get("X-Lark-Request-Nonce", "")
        # ...

        result = handle_event(event_data)
        return JSONResponse(content=result)

    except Exception as e:
        print(f"[事件回调] 异常: {e}")
        traceback.print_exc()
        return JSONResponse(content={"code": -1, "msg": str(e)})


# ---- 手动触发API ----

@app.get("/api/analyze")
async def manual_analyze(force: bool = False):
    """手动触发每日分析"""
    report = orchestrator.run_daily_analysis(force=force)
    if report:
        return {"code": 0, "msg": "分析完成", "date": str(date.today())}
    return {"code": 0, "msg": "跳过（非交易日或已分析）"}


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "service": "fund-analysis-bot",
        "date": str(date.today()),
    }


@app.post("/api/send_to_user")
async def send_to_user(request: Request):
    """手动发送分析给指定用户"""
    body = await request.json()
    open_id = body.get("open_id", "")
    if not open_id:
        return {"code": -1, "msg": "缺少 open_id"}
    success = orchestrator.send_analysis_to_user(open_id)
    return {"code": 0 if success else -1, "msg": "ok" if success else "发送失败"}


# ---- 定时触发器入口（阿里云FC） ----

def handler(event, context):
    """
    阿里云 FC 入口函数
    支持：
      - HTTP 触发器 → 转发到 FastAPI (通过 uvicorn)
      - 定时触发器 → 直接执行分析
    """
    # 判断触发器类型
    trigger_type = event.get("triggerType", "") if isinstance(event, dict) else ""
    trigger_name = event.get("triggerName", "") if isinstance(event, dict) else ""

    # 定时触发器
    if trigger_type == "timer" or "timer" in trigger_name.lower():
        return _handle_timer_trigger(event, context)

    # HTTP 触发器 — 使用 ASGI 适配
    return _handle_http_trigger(event, context)


def _handle_timer_trigger(event, context):
    """处理定时触发器（每天早上7:00）"""
    print(f"[定时触发] 开始每日基金分析...")
    report = orchestrator.run_daily_analysis()
    if report:
        return {"code": 0, "msg": "每日分析完成"}
    return {"code": 0, "msg": "跳过（休市或已分析）"}


def _handle_http_trigger(event, context):
    """
    处理 HTTP 触发器 — 使用 asgi 适配
    将 FC event 转为 ASGI scope，适配 FastAPI
    """
    # 使用 mangum 或自定义 ASGI 适配器
    # 阿里云 FC Python runtime 可以直接运行 uvicorn
    try:
        from mangum import Mangum
        asgi_handler = Mangum(app)
        return asgi_handler(event, context)
    except ImportError:
        # 降级：手动处理 HTTP 请求
        return _simple_http_handler(event)


def _simple_http_handler(event):
    """简化的 HTTP 处理（无 mangum 时）"""
    path = event.get("path", "/")
    method = event.get("httpMethod", "GET")

    if path == "/feishu/event" and method == "POST":
        body = event.get("body", "{}")
        if event.get("isBase64Encoded"):
            import base64
            body = base64.b64decode(body).decode()
        event_data = json.loads(body) if isinstance(body, str) else body
        result = handle_event(event_data)
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(result, ensure_ascii=False),
        }

    elif path == "/api/analyze":
        report = orchestrator.run_daily_analysis(force=True)
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "code": 0, "msg": "ok" if report else "skipped"
            }, ensure_ascii=False),
        }

    elif path == "/api/health":
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"status": "ok"}, ensure_ascii=False),
        }

    return {
        "statusCode": 404,
        "body": json.dumps({"error": "not found"}, ensure_ascii=False),
    }


# ---- 本地开发入口 ----

if __name__ == "__main__":
    import uvicorn
    import os

    # 初始化数据库
    init_database()
    print("✅ 数据库就绪")

    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 启动本地开发服务器: http://localhost:{port}")
    print(f"📡 飞书事件回调: POST http://localhost:{port}/feishu/event")
    print(f"📊 手动分析: GET  http://localhost:{port}/api/analyze")
    print(f"❤️  健康检查: GET  http://localhost:{port}/api/health")
    print()

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
    )
