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
    1. 提取 ```json 代码块内容
    2. 无代码块则正则匹配最外层 {} 或 []
    3. 移除非法控制字符
    4. 尝试修复尾随逗号等常见语法错误
    5. 失败则抛出带上下文提示的异常
    """
    text, usage = chat(prompt, system=system, **kwargs)

    # 1. 尝试提取 markdown 代码块
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        cleaned = match.group(1).strip()
    else:
        # 2. 匹配最外层 JSON 结构
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
        cleaned = match.group(1).strip() if match else text.strip()

    # 3. 移除不可见控制字符（除 \n, \r, \t 外）
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', cleaned)

    # 4. 直接解析
    try:
        return json.loads(cleaned), usage
    except json.JSONDecodeError:
        pass

    # 5. 容错修复（处理尾随逗号等）
    try:
        fixed = re.sub(r",\s*([}\]])", r"\1", cleaned)
        return json.loads(fixed), usage
    except json.JSONDecodeError:
        pass

    # 6. 最终失败，提供清晰调试信息
    snippet = cleaned[:500] + ("..." if len(cleaned) > 500 else "")
    raise json.JSONDecodeError(f"LLM 返回 JSON 解析失败。片段:\n{snippet}", cleaned, 0)


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
