"""工作流专用 LLM 客户端，提供同步聊天与 JSON 解析接口。"""

import json
import os
import re

import httpx


def chat(
    prompt: str,
    system: str = "你是一个专业的 AI 技术分析师。",
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2000,
) -> tuple[str, dict]:
    """调用 LLM 并返回 (回复文本, token用量信息)。

    Args:
        prompt: 用户 prompt。
        system: 系统 prompt。
        model: 模型名，默认从环境变量读取。
        temperature: 采样温度。
        max_tokens: 最大输出 token 数。

    Returns:
        (response_text, usage_dict) 其中 usage_dict 包含 prompt_tokens, completion_tokens。
    """
    api_key = os.getenv("DEEPSEEK_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    model_name = model or os.getenv("LLM_MODEL", "deepseek-chat")

    client = httpx.Client(base_url=base_url, timeout=60.0)
    response = client.post(
        "/chat/completions",
        json={
            "model": model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    response.raise_for_status()
    data = response.json()

    text = data["choices"][0]["message"].get("content", "")
    usage_data = data.get("usage", {})
    usage = {
        "prompt_tokens": usage_data.get("prompt_tokens", 0),
        "completion_tokens": usage_data.get("completion_tokens", 0),
    }

    return text, usage


def chat_json(
    prompt: str,
    system: str = "你是一个专业的 AI 技术分析师。请用 JSON 格式回复。",
    **kwargs,
) -> tuple[dict | list, dict]:
    """调用 LLM 并解析 JSON 响应（带容错）。

    容错策略:
    1. 去掉 markdown 代码块包裹
    2. 直接 json.loads
    3. 失败则用正则匹配第一个 {...} 或 [...] 结构
    4. 再失败才抛出

    Returns:
        (parsed_json, usage_dict)

    Raises:
        json.JSONDecodeError: 三种策略都失败时
    """
    text, usage = chat(prompt, system=system, **kwargs)

    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        start = 1
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip().startswith("```"):
                end = i
                break
        cleaned = "\n".join(lines[start:end])

    try:
        return json.loads(cleaned), usage
    except json.JSONDecodeError:
        pass

    for pattern in (r"\{[\s\S]*\}", r"\[[\s\S]*\]"):
        match = re.search(pattern, cleaned)
        if match:
            try:
                return json.loads(match.group()), usage
            except json.JSONDecodeError:
                continue

    return json.loads(cleaned), usage


def accumulate_usage(tracker: dict, new_usage: dict) -> dict:
    """累加 token 用量到 cost_tracker。

    Args:
        tracker: 现有的 cost_tracker。
        new_usage: 本次调用的 usage_dict。

    Returns:
        更新后的 cost_tracker（包含累计 token 数和成本估算）。
    """
    prompt = tracker.get("prompt_tokens", 0) + new_usage.get("prompt_tokens", 0)
    completion = tracker.get("completion_tokens", 0) + new_usage.get("completion_tokens", 0)

    input_price = float(os.getenv("PRICE_INPUT_PER_MILLION", "1.0"))
    output_price = float(os.getenv("PRICE_OUTPUT_PER_MILLION", "2.0"))
    total_cost = (prompt * input_price + completion * output_price) / 1_000_000

    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_cost_cny": round(total_cost, 6),
    }
