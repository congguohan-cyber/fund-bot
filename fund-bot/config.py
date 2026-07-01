"""
基金分析 Bot — 配置管理
从环境变量读取所有配置，支持 .env 文件
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


@dataclass
class FeishuConfig:
    """飞书应用配置"""
    app_id: str = field(default_factory=lambda: os.getenv("FEISHU_APP_ID", ""))
    app_secret: str = field(default_factory=lambda: os.getenv("FEISHU_APP_SECRET", ""))
    verification_token: str = field(default_factory=lambda: os.getenv("FEISHU_VERIFICATION_TOKEN", ""))
    encrypt_key: str = field(default_factory=lambda: os.getenv("FEISHU_ENCRYPT_KEY", ""))
    # 接收消息的用户 open_id
    user_open_id: str = field(default_factory=lambda: os.getenv("FEISHU_USER_OPEN_ID", ""))
    chat_id: str = field(default_factory=lambda: os.getenv("FEISHU_CHAT_ID", ""))


@dataclass
class LLMConfig:
    """LLM API 配置（支持 Claude / DeepSeek / OpenAI-compatible）"""
    # Anthropic
    anthropic_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    claude_model: str = field(default_factory=lambda: os.getenv("CLAUDE_MODEL", "claude-sonnet-5-20251001"))
    # DeepSeek / OpenAI-compatible
    deepseek_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    deepseek_model: str = field(default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
    deepseek_base_url: str = field(default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    # 通用
    max_tokens: int = 4096
    temperature: float = 0.3  # 金融分析需要稳定输出

    @property
    def provider(self) -> str:
        """自动检测可用的 LLM provider"""
        if self.deepseek_key:
            return "deepseek"
        if self.anthropic_key:
            return "claude"
        return "none"


@dataclass
class AppConfig:
    """应用总配置"""
    feishu: FeishuConfig = field(default_factory=FeishuConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    database_path: str = field(default_factory=lambda: os.getenv("DATABASE_PATH", "./data/fund_bot.db"))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")

    # 分析推送时间（北京时间）
    push_hour: int = 7
    push_minute: int = 0


# 全局单例
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """获取配置单例"""
    global _config
    if _config is None:
        _config = AppConfig()
    return _config
