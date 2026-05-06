"""统一的 LLM 调用客户端，支持 DeepSeek、Qwen、OpenAI 等 OpenAI 兼容 API。"""

import asyncio
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class Usage:
    """Token 用量统计。

    Attributes:
        prompt_tokens: 输入 token 数量。
        completion_tokens: 输出 token 数量。
        total_tokens: 总 token 数量。
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


# ── 模型定价表（USD / 1M tokens） ──────────────────────────────────────
PRICING = {
    # DeepSeek
    "deepseek-chat": {"input": 0.27, "output": 1.10},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    # Qwen
    "qwen-plus": {"input": 0.56, "output": 1.68},
    "qwen-max": {"input": 2.80, "output": 8.40},
    "qwen-turbo": {"input": 0.14, "output": 0.42},
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4": {"input": 30.00, "output": 60.00},
}

# ── 模型定价表（CNY / 1M tokens） ──────────────────────────────────────
PRICING_CNY = {
    "deepseek": {"input": 1.0, "output": 2.0},
    "qwen": {"input": 4.0, "output": 12.0},
    "openai": {"input": 150.0, "output": 600.0},
}


class CostTracker:
    """追踪 LLM 调用的 token 消耗和成本。

    Attributes:
        _records: 记录列表，每次调用包含 provider、usage 和时间戳。
    """

    def __init__(self):
        """初始化成本追踪器。"""
        self._records: list[dict] = []

    def record(self, usage: Usage, provider: str) -> None:
        """记录一次 API 调用。

        Args:
            usage: Token 用量统计对象。
            provider: LLM 提供商名称（如 deepseek、qwen、openai）。
        """
        self._records.append({
            "provider": provider.lower(),
            "usage": usage,
            "timestamp": time.time(),
        })

    def estimated_cost(self, provider: str) -> float:
        """返回指定提供商的估算成本（元）。

        Args:
            provider: LLM 提供商名称。

        Returns:
            估算成本（人民币），保留 4 位小数。
        """
        provider = provider.lower()
        prices = PRICING_CNY.get(provider, PRICING_CNY["openai"])

        total_input = sum(
            r["usage"].prompt_tokens for r in self._records if r["provider"] == provider
        )
        total_output = sum(
            r["usage"].completion_tokens for r in self._records if r["provider"] == provider
        )

        input_cost = (total_input / 1_000_000) * prices["input"]
        output_cost = (total_output / 1_000_000) * prices["output"]
        return round(input_cost + output_cost, 4)

    def save_to_json(self, filepath: str) -> None:
        """将统计结果保存到 JSON 文件。

        Args:
            filepath: 保存路径，如 "knowledge/status/cost_report.json"。
        """
        if not self._records:
            logger.info("无成本记录，跳过保存")
            return

        providers = set(r["provider"] for r in self._records)
        report_data = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_calls": len(self._records),
            "breakdown": {},
        }

        total_input = 0
        total_output = 0
        total_cost = 0.0

        for p in providers:
            calls = [r for r in self._records if r["provider"] == p]
            input_tokens = sum(r["usage"].prompt_tokens for r in calls)
            output_tokens = sum(r["usage"].completion_tokens for r in calls)
            cost = self.estimated_cost(p)

            total_input += input_tokens
            total_output += output_tokens
            total_cost += cost

            report_data["breakdown"][p] = {
                "calls": len(calls),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "estimated_cost_cny": cost,
            }

        report_data["total"] = {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "total_cost_cny": round(total_cost, 4),
        }

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        logger.info("成本报告已保存至: %s", filepath)

    def report(self, provider: Optional[str] = None) -> None:
        """打印成本报告。

        Args:
            provider: 指定提供商（可选），为 None 时打印所有提供商。
        """
        providers = (
            [provider.lower()] if provider else set(r["provider"] for r in self._records)
        )

        logger.info("=" * 50)
        logger.info("LLM 成本报告")
        logger.info("=" * 50)

        total_calls = 0
        total_input = 0
        total_output = 0
        total_cost = 0.0

        for p in providers:
            calls = [r for r in self._records if r["provider"] == p]
            if not calls:
                continue

            input_tokens = sum(r["usage"].prompt_tokens for r in calls)
            output_tokens = sum(r["usage"].completion_tokens for r in calls)
            cost = self.estimated_cost(p)

            total_calls += len(calls)
            total_input += input_tokens
            total_output += output_tokens
            total_cost += cost

            logger.info(
                "  %-10s | 调用: %d 次 | 输入: %d | 输出: %d | 成本: %.4f 元",
                p, len(calls), input_tokens, output_tokens, cost
            )

        logger.info("-" * 50)
        logger.info(
            "  总计     | 调用: %d 次 | 输入: %d | 输出: %d | 成本: %.4f 元",
            total_calls, total_input, total_output, total_cost
        )
        logger.info("=" * 50)


# 全局成本追踪实例
tracker = CostTracker()


@dataclass
class LLMResponse:
    """LLM 响应。

    Attributes:
        content: 模型返回的文本内容。
        usage: Token 用量统计。
        model: 实际使用的模型名称。
        latency_ms: 请求耗时（毫秒）。
    """

    content: str
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    latency_ms: float = 0.0


# ── 模型定价表（USD / 1M tokens） ──────────────────────────────────────
PRICING = {
    # DeepSeek
    "deepseek-chat": {"input": 0.27, "output": 1.10},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    # Qwen
    "qwen-plus": {"input": 0.56, "output": 1.68},
    "qwen-max": {"input": 2.80, "output": 8.40},
    "qwen-turbo": {"input": 0.14, "output": 0.42},
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4": {"input": 30.00, "output": 60.00},
}


def estimate_cost(model: str, usage: Usage) -> float:
    """估算 API 调用成本（USD）。

    Args:
        model: 模型名称。
        usage: Token 用量统计对象。

    Returns:
        预估成本（美元），保留 6 位小数。
    """
    price = PRICING.get(model, {"input": 3.00, "output": 9.00})
    input_cost = (usage.prompt_tokens / 1_000_000) * price["input"]
    output_cost = (usage.completion_tokens / 1_000_000) * price["output"]
    return round(input_cost + output_cost, 6)


def estimate_tokens(text: str) -> int:
    """粗略估算文本的 token 数量。

    适用于中英文混合场景，约 1 token ≈ 1.5 字符。

    Args:
        text: 待估算的文本。

    Returns:
        预估的 token 数量。
    """
    if not text:
        return 0
    return max(1, int(len(text) * 0.67))


class LLMProvider(ABC):
    """LLM 提供商抽象基类。"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """发送聊天请求并返回响应。

        Args:
            messages: 聊天消息列表，格式为 [{"role": "...", "content": "..."}]。
            model: 模型名称。
            temperature: 温度参数，控制输出随机性（0.0-1.0）。
            max_tokens: 最大输出 token 数。

        Returns:
            LLM 响应对象。

        Raises:
            RuntimeError: API 调用失败时抛出。
        """
        ...


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI 兼容 API 实现。

    通过 httpx 直接调用兼容 OpenAI 格式的 API 端点。

    Attributes:
        api_key: API 密钥。
        base_url: API 基础 URL。
        default_model: 默认使用的模型名称。
        timeout: 请求超时时间（秒）。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        default_model: str = "",
        timeout: float = 60.0,
    ):
        """初始化 Provider。

        Args:
            api_key: API 密钥。
            base_url: API 基础 URL。
            default_model: 默认模型名称。
            timeout: 请求超时时间（秒）。
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 httpx 异步客户端。

        Returns:
            配置好的 AsyncClient 实例。
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(self.timeout, connect=10.0),
            )
        return self._client

    async def close(self):
        """关闭 httpx 客户端连接。"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def chat(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """发送聊天请求。

        Args:
            messages: 聊天消息列表。
            model: 模型名称。
            temperature: 温度参数。
            max_tokens: 最大输出 token 数。

        Returns:
            LLM 响应对象。

        Raises:
            RuntimeError: API 返回非 200 状态码时抛出。
        """
        client = self._get_client()
        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        start = time.monotonic()
        resp = await client.post("/v1/chat/completions", json=payload)
        latency = (time.monotonic() - start) * 1000

        if resp.status_code != 200:
            raise RuntimeError(
                f"API 错误 [{resp.status_code}]: {resp.text[:500]}"
            )

        data = resp.json()
        choice = data["choices"][0]
        usage_data = data.get("usage", {})

        return LLMResponse(
            content=choice["message"]["content"],
            usage=Usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            ),
            model=data.get("model", model),
            latency_ms=round(latency, 1),
        )


# ── 提供商配置 ──────────────────────────────────────────────────────────
PROVIDER_CONFIG = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
        "api_key_env": "QWEN_API_KEY",
    },
    "openai": {
        "base_url": "https://api.openai.com",
        "default_model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
    },
}


def get_provider() -> OpenAICompatibleProvider:
    """从环境变量获取并实例化当前配置的 LLM Provider。

    读取 LLM_PROVIDER 环境变量确定提供商类型（默认 deepseek），
    并读取对应的 API Key 环境变量进行初始化。

    Returns:
        配置好的 OpenAICompatibleProvider 实例。

    Raises:
        ValueError: LLM_PROVIDER 值不在支持的列表中时抛出。
        EnvironmentError: 未配置对应的 API Key 环境变量时抛出。
    """
    provider_name = os.getenv("LLM_PROVIDER", "deepseek").lower()
    config = PROVIDER_CONFIG.get(provider_name)
    if not config:
        raise ValueError(
            f"未知的 LLM_PROVIDER: '{provider_name}'，"
            f"可选值: {list(PROVIDER_CONFIG.keys())}"
        )

    api_key_env = config["api_key_env"]
    api_key = os.getenv(api_key_env, "")
    if not api_key:
        raise EnvironmentError(
            f"未设置环境变量 {api_key_env}，请配置 API Key"
        )

    return OpenAICompatibleProvider(
        api_key=api_key,
        base_url=config["base_url"],
        default_model=config["default_model"],
    )


async def chat_with_retry(
    messages: list[dict],
    model: Optional[str] = None,
    max_retries: int = 3,
    base_delay: float = 1.0,
    **kwargs,
) -> LLMResponse:
    """带重试机制的聊天函数。

    使用指数退避策略进行重试，默认最多重试 3 次。

    Args:
        messages: 聊天消息列表。
        model: 模型名称（可选，默认使用 Provider 的默认模型）。
        max_retries: 最大重试次数。
        base_delay: 基础延迟时间（秒），用于指数退避计算。
        **kwargs: 传递给 chat() 的额外参数（如 temperature、max_tokens）。

    Returns:
        LLM 响应对象。

    Raises:
        Exception: 达到最大重试次数后，抛出最后一次异常。
    """
    provider = get_provider()
    provider_name = os.getenv("LLM_PROVIDER", "deepseek").lower()
    model_name = model or provider.default_model

    last_err: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            response = await provider.chat(
                messages=messages,
                model=model_name,
                **kwargs,
            )
            tracker.record(response.usage, provider_name)
            cost = estimate_cost(response.model, response.usage)
            logger.info(
                "LLM 调用成功 | model=%s | tokens=%d | cost=$%.6f | latency=%.0fms",
                response.model,
                response.usage.total_tokens,
                cost,
                response.latency_ms,
            )
            return response
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "LLM 调用失败 (第 %d/%d 次): %s，%0.1fs 后重试",
                    attempt + 1,
                    max_retries,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "LLM 调用失败，已达最大重试次数 %d: %s",
                    max_retries,
                    e,
                )

    raise last_err or RuntimeError("LLM 调用失败")


async def quick_chat(
    prompt: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs,
) -> str:
    """便捷函数：一句话调用 LLM。

    自动构建消息列表并调用 chat_with_retry，仅返回文本内容。

    Args:
        prompt: 用户提示词。
        system: 系统提示词（可选）。
        model: 模型名称（可选）。
        **kwargs: 传递给 chat_with_retry 的额外参数。

    Returns:
        模型返回的文本内容。
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = await chat_with_retry(messages=messages, model=model, **kwargs)
    return response.content


# ── 测试代码 ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # 测试 token 估算
    logger.info("=== Token 估算测试 ===")
    for text in ["Hello world", "你好世界", "这是一段中文测试文本"]:
        logger.info("  '%s' -> 约 %d tokens", text, estimate_tokens(text))

    # 测试成本计算
    logger.info("=== 成本计算测试 ===")
    test_usage = Usage(
        prompt_tokens=1000, completion_tokens=500, total_tokens=1500
    )
    for model in ["deepseek-chat", "qwen-plus", "gpt-4o-mini"]:
        cost = estimate_cost(model, test_usage)
        logger.info("  %s: $%.6f", model, cost)

    # 测试 Provider 配置
    logger.info("=== Provider 配置 ===")
    for name, cfg in PROVIDER_CONFIG.items():
        logger.info("  %s: %s @ %s", name, cfg["default_model"], cfg["base_url"])

    # 测试实际调用（需要配置环境变量）
    logger.info("=== 实际调用测试 ===")
    api_key = os.getenv("DEEPSEEK_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    if api_key:

        async def run_test():
            """执行实际调用测试。"""
            try:
                result = await quick_chat(
                    system="你是一个简洁的助手，回答不超过20字。",
                    prompt="你好，介绍一下你自己。",
                )
                logger.info("  回复: %s", result)
            except EnvironmentError as e:
                logger.warning("  跳过: %s", e)

        asyncio.run(run_test())
    else:
        logger.info("  跳过: 未配置 API Key，跳过实际调用测试")
