"""Reviser 修正节点。

根据审核反馈对分析结果进行针对性修正。
"""

import json
import logging

from workflows.model_client import accumulate_usage, chat_json
from workflows.state import KBState

logger = logging.getLogger(__name__)

REVISION_PROMPT_TEMPLATE = """你是一个专业的技术内容编辑。请根据审核反馈，对提供的分析结果列表进行修正。

原始分析结果列表:
{analyses_json}

审核反馈:
{feedback}

要求:
1. 仅针对反馈中指出的问题进行改进（如摘要不准确、标签泛泛、评分不合理等）。
2. 保持原有的 JSON 结构（包含 source_url, title, summary, tags, score, stars, language）。
3. 确保输出是合法的 JSON 数组。"""


def revise_node(state: KBState) -> dict:
    """修正节点：利用 LLM 根据审核反馈优化 analyses。

    Args:
        state: 当前工作流状态。

    Returns:
        包含 updated analyses 和 cost_tracker 的部分状态更新。
        若无 analyses 或 feedback 则返回空字典（跳过更新）。
    """
    analyses = state.get("analyses", [])
    feedback = state.get("review_feedback", "")
    failed_urls = set(state.get("failed_urls", []))
    tracker = state.get("cost_tracker", {})

    if not analyses or not feedback:
        return {}

    # 区分未通过和已通过的条目
    failed_analyses = [a for a in analyses if a.get("source_url") in failed_urls]
    passed_analyses = [a for a in analyses if a.get("source_url") not in failed_urls]

    if not failed_analyses:
        # 理论上不应发生（若 review 未通过，应有 failed_urls）
        logger.warning("[revise_node] 未找到未通过的条目，跳过修正")
        return {}

    logger.info("[revise_node] 开始修正 %d 条未通过的分析结果", len(failed_analyses))

    analyses_json = json.dumps(failed_analyses, ensure_ascii=False, indent=2)
    prompt = REVISION_PROMPT_TEMPLATE.format(analyses_json=analyses_json, feedback=feedback)

    try:
        improved, usage = chat_json(
            prompt,
            system="你是一个严谨的技术分析修订助手。",
            temperature=0.4,
            max_tokens=8000,
        )
        
        # 确保返回的是列表
        if not isinstance(improved, list):
            logger.warning("[revise_node] LLM 返回非列表格式，跳过更新")
            return {"cost_tracker": tracker}

        tracker = accumulate_usage(tracker, usage)

        # 合并已通过的条目和修正后的未通过条目
        improved_sources = {a.get("source_url") for a in improved}
        final_analyses = passed_analyses + improved

        # 防御性检查：如果 LLM 遗漏了某些条目，尝试从原始 failed_analyses 中找回（可选，视需求而定）
        # 这里假设 LLM 会返回所有输入的条目

        logger.info("[revise_node] 修正完成，最终保留 %d 条 (通过 %d + 修正 %d)", len(final_analyses), len(passed_analyses), len(improved))
        return {"analyses": final_analyses, "cost_tracker": tracker}

    except Exception as e:
        logger.warning("[revise_node] 修正失败: %s", e)
        return {"cost_tracker": tracker}
