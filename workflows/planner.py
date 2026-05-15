"""Planner 模块：根据目标采集量制定采集与分析策略。"""

import os
import logging

logger = logging.getLogger(__name__)


def plan_strategy(target_count: int | None = None) -> dict:
    """根据目标采集量返回策略配置。

    Args:
        target_count: 目标采集条目数，默认从环境变量 PLANNER_TARGET_COUNT 读取（默认 10）。

    Returns:
        包含策略配置的字典，包含 tier模式（PLANNER_TARGET_COUNT值分别为5，10，20）, per_source_limit源端采集条目限制（5，10，20, relevance_threshold粗筛阈值, max_iterations最大重复审核次数, max_review_items最大抽样审核知识条目，review_pass_threshold审核通过平均阈值，rationale说明。
    """
    if target_count is None:
        target_count = int(os.getenv("PLANNER_TARGET_COUNT", "10"))

    if target_count < 10:
        return {
            "tier": "lite",
            "per_source_limit": 5,
            "relevance_threshold": 0.7,
            "max_iterations": 1,
            "max_review_items": 3,
            "review_pass_threshold": 8.0,
            "rationale": "轻量模式：目标量较少，采用高相关性门槛与单轮迭代以节约成本。",
        }
    elif target_count < 20:
        return {
            "tier": "standard",
            "per_source_limit": 10,
            "relevance_threshold": 0.5,
            "max_iterations": 2,
            "max_review_items": 5,
            "review_pass_threshold": 7.0,
            "rationale": "标准模式：平衡质量与效率，适度放宽相关性要求，允许2轮修正。",
        }
    else:
        return {
            "tier": "full",
            "per_source_limit": 20,
            "relevance_threshold": 0.4,
            "max_iterations": 3,
            "max_review_items": 5,
            "review_pass_threshold": 6.5,
            "rationale": "全量模式：目标量大，降低相关性门槛以获取更多条目，启用完整的 3 轮审核修正。",
        }


def planner_node(state) -> dict:
    """LangGraph 节点包装：调用 plan_strategy 并返回策略计划。

    Args:
        state: 当前工作流状态。

    Returns:
        包含 {"plan": strategy_dict} 的部分状态更新。
    """
    logger.info("[planner_node] 开始制定采集策略")
    target = state.get("target_count", None)
    plan = plan_strategy(target)
    logger.info("[planner_node] 策略已制定: tier=%s, rationale=%s", plan["tier"], plan["rationale"])
    return {"plan": plan}
