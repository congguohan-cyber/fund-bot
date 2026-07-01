"""
LLM 分析引擎 — 支持 DeepSeek / Claude / OpenAI-compatible
三层分析流水线：新闻过滤 → 基金逐只 → 综合报告
"""
import json
import re
import time
from datetime import date, datetime

from openai import OpenAI

from config import get_config
from analyzer.prompts import (
    build_news_filter_prompt,
    build_fund_analysis_prompt,
    build_report_prompt,
    build_dialogue_prompt,
)


class LLMClient:
    """统一 LLM 客户端，支持 DeepSeek (默认) / Claude"""

    def __init__(self):
        config = get_config()
        self.provider = config.llm.provider
        self.max_tokens = config.llm.max_tokens
        self.temperature = config.llm.temperature

        if self.provider == "deepseek":
            self.model = config.llm.deepseek_model
            self.client = OpenAI(
                api_key=config.llm.deepseek_key,
                base_url=config.llm.deepseek_base_url,
            )
        elif self.provider == "claude":
            from anthropic import Anthropic
            self.model = config.llm.claude_model
            self._claude = Anthropic(api_key=config.llm.anthropic_key)
            self.client = None
        else:
            raise RuntimeError("No LLM API key configured. Set DEEPSEEK_API_KEY or ANTHROPIC_API_KEY in .env")

    def _call(self, system_prompt: str, user_prompt: str,
              max_tokens: int | None = None,
              temperature: float | None = None) -> str:
        """底层 API 调用（含重试，自动适配 provider）"""
        tok = max_tokens or self.max_tokens
        temp = temperature if temperature is not None else self.temperature

        for attempt in range(3):
            try:
                if self.provider == "deepseek":
                    return self._call_openai(system_prompt, user_prompt, tok, temp)
                elif self.provider == "claude":
                    return self._call_claude(system_prompt, user_prompt, tok, temp)
            except Exception as e:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
        return ""

    def _call_openai(self, system: str, user: str, max_tok: int, temp: float) -> str:
        """OpenAI-compatible API (DeepSeek)"""
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tok,
            temperature=temp,
        )
        return resp.choices[0].message.content or ""

    def _call_claude(self, system: str, user: str, max_tok: int, temp: float) -> str:
        """Claude API"""
        resp = self._claude.messages.create(
            model=self.model,
            max_tokens=max_tok,
            temperature=temp,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text

    def _extract_json(self, text: str) -> dict:
        """从 LLM 回复中提取 JSON"""
        match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        return {"raw_text": text}

    # ---- 阶段一：新闻过滤 ----

    def filter_news(self, user_profile: str, news_list: str,
                    news_count: int) -> dict:
        prompt = build_news_filter_prompt(user_profile, news_list, news_count)
        system = "你是一位资深财经分析师。请以JSON格式输出。"
        result = self._call(system, prompt, max_tokens=2048)
        return self._extract_json(result)

    # ---- 阶段二：基金分析 ----

    def analyze_fund(self, market_summary: str, relevant_news: str,
                     fund_data: str) -> dict:
        prompt = build_fund_analysis_prompt(market_summary, relevant_news, fund_data)
        system = "你是一位专业的基金分析师。请严格以JSON格式输出分析结果。"
        result = self._call(system, prompt, max_tokens=3072)
        return self._extract_json(result)

    # ---- 阶段三：综合报告 ----

    def generate_report(self, market_summary: str, all_fund_analyses: str,
                        report_date: str) -> dict:
        prompt = build_report_prompt(market_summary, all_fund_analyses, report_date)
        system = "你是一位首席投资顾问。请严格以JSON格式输出完整报告。"
        result = self._call(system, prompt, max_tokens=4096)
        return self._extract_json(result)

    # ---- 对话管理 ----

    def process_dialogue(self, user_message: str,
                         current_holdings: str) -> str:
        prompt = build_dialogue_prompt(user_message, current_holdings)
        system = "你是一个友好的基金分析助手，运行在飞书平台。回复简洁（3句话内），不要输出JSON。"
        return self._call(system, prompt, max_tokens=512, temperature=0.7)

    # ---- 文本摘要 ----

    def summarize(self, text: str, max_length: int = 100) -> str:
        system = "你是一个摘要生成器。请将以下内容压缩为一句话，不超过字数要求。"
        result = self._call(system, text, max_tokens=max_length, temperature=0.1)
        return result.strip()


# 模块级单例
llm_client = LLMClient()
