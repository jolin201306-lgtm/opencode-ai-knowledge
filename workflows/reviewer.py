"""Reviewer 审核节点。

对知识条目进行 5 维度加权评分，控制质量门槛。
"""

import json
import logging

from workflows.model_client import accumulate_usage, chat_json
from workflows.state import KBState

logger = logging.getLogger(__name__)

# 评分权重配置
SCORE_WEIGHTS = {
    "summary_quality": 0.25,
    "technical_depth": 0.25,
    "relevance": 0.20,
    "originality": 0.15,
    "formatting": 0.15,
}

PASS_THRESHOLD = 7.0
MAX_REVIEW_ITEMS = 5
MAX_ITERATION = 3
MIN_SCORE = 1
MAX_SCORE = 10

REVIEW_SYSTEM_PROMPT = """你是一个严格的技术内容质量审核员。
评分标准：
- 宁可给低分，绝不放水
- 分数必须是 1-10 的整数
- **必须审核列表中的每一条条目，严禁遗漏！**
- 如果输入包含 N 条条目，你的输出必须包含 N 个评分结果。"""

REVIEW_PROMPT_TEMPLATE = """审核以下知识条目，必须对列表中的**每一条**（共 {expected_count} 条）进行独立评分，**严禁遗漏或合并**。
输出的 JSON 对象中，"items" 列表必须包含 **恰好 {expected_count} 个元素**。

条目列表:
{articles_json}

评分标准:
- summary_quality (摘要质量): 8-10准确有细节, 5-7泛泛, 1-4不准确
- technical_depth (技术深度): 8-10深入有数据, 5-7表面, 1-4无细节
- relevance (相关性): 8-10核心相关, 5-7周边, 1-4无关
- originality (原创性): 8-10原创创新, 5-7封装, 1-4搬运
- formatting (格式规范): 8-10标签精准(3-5个), 5-7部分合理, 1-4缺失/无关

请输出 JSON:
{{
  "items": [
    {{"title": "条目标题 1", "source_url": "URL 1", "scores": {{"summary_quality": 8, "technical_depth": 7, "relevance": 9, "originality": 6, "formatting": 8}}, "weighted_score": 7.65}},
    {{"title": "条目标题 2", "source_url": "URL 2", "scores": {{"summary_quality": 8, "technical_depth": 7, "relevance": 9, "originality": 6, "formatting": 8}}, "weighted_score": 7.65}},
    {{"title": "条目标题 3", "source_url": "URL 3", "scores": {{"summary_quality": 8, "technical_depth": 7, "relevance": 9, "originality": 6, "formatting": 8}}, "weighted_score": 7.65}}
  ],
  "feedback": "整体改进建议"
}}"""


def _clamp_score(score: float | int) -> float:
    """将分数限制在 [MIN_SCORE, MAX_SCORE] 范围内。

    Args:
        score: 原始分数。

    Returns:
        钳位后的分数（float）。
    """
    return max(MIN_SCORE, min(MAX_SCORE, float(score)))


def _calc_weighted(scores: dict) -> float:
    """计算加权总分。

    Args:
        scores: 五维度分数字典。

    Returns:
        加权总分（1-10 范围）。
    """
    return sum(
        _clamp_score(scores.get(dim, 5)) * weight
        for dim, weight in SCORE_WEIGHTS.items()
    )


def review_node(state: KBState) -> dict:
    """审核节点：对 articles 逐条进行 5 维度加权评分，>= 7.0 为通过。

    Args:
        state: 当前工作流状态。

    Returns:
        包含 review_passed、review_feedback、iteration、cost_tracker 的部分状态更新。
    """
    logger.info("[review_node] 开始审核 %d 条知识条目", len(state.get("articles", [])))

    iteration = state.get("iteration", 0) + 1
    tracker = state.get("cost_tracker", {})
    articles = state.get("articles", [])

    if not articles:
        logger.info("[review_node] 无条目可审核，自动通过")
        return {
            "review_passed": True,
            "review_feedback": "",
            "failed_urls": [],
            "iteration": iteration,
            "cost_tracker": tracker,
        }

    # 获取动态阈值与审核数量配置
    plan = state.get("plan", {})
    pass_threshold = plan.get("review_pass_threshold", 7.0)

    review_items = articles[:plan.get("max_review_items", 5)]
    expected_count = len(review_items)
    
    if expected_count == 0:
        logger.info("[review_node] 无条目需审核，自动通过")
        return {
            "review_passed": True,
            "review_feedback": "",
            "failed_urls": [],
            "iteration": iteration,
            "cost_tracker": tracker,
        }

    articles_json = json.dumps(review_items, ensure_ascii=False, indent=2)
    prompt = REVIEW_PROMPT_TEMPLATE.format(articles_json=articles_json, expected_count=expected_count)

    try:
        result, usage = chat_json(
            prompt,
            system=REVIEW_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=8192,
        )
        tracker = accumulate_usage(tracker, usage)

        # 解析逐条评分
        items = result if isinstance(result, list) else result.get("items", [])
        feedback = result.get("feedback", "") if isinstance(result, dict) else ""

        if not items:
            logger.warning("[review_node] 未解析到有效评分项")
            return {
                "review_passed": False,
                "review_feedback": "LLM 未返回有效评分",
                "failed_urls": [],
                "iteration": iteration,
                "cost_tracker": tracker,
            }

        total_weighted = 0.0
        failed_urls = []
        low_scores = []
        details = []
        
        # 构建 title -> url 映射 (备用)
        title_to_url = {item.get("title"): item.get("source_url", "") for item in review_items}

        for item in items:
            title = item.get("title", "unknown")
            scores = item.get("scores", {})
            
            # 1. 维持原有逻辑：计算单条加权总分 (摘要 × 0.25 + 深度 × 0.25 + 相关性 × 0.20 + 原创 × 0.15 + 格式 × 0.15)
            weighted = _calc_weighted(scores)
            total_weighted += weighted
            
            # 优先使用 LLM 返回的 URL，否则通过 title 匹配
            source_url = item.get("source_url") or title_to_url.get(title, "")
            
            # 记录未达标的条目 (即使平均分通过，也记录单项低分供参考)
            if weighted < pass_threshold:
                if source_url:
                    failed_urls.append(source_url)
                low_scores.append(f"'{title}' (得分 {weighted:.2f})")

            details.append({
                "title": title,
                "scores": {k: _clamp_score(v) for k, v in scores.items()},
                "weighted": round(weighted, 2),
            })

            logger.info(
                "[review_node] '%s': summary=%.1f, technical=%.1f, relevance=%.1f, originality=%.1f, formatting=%.1f, weighted=%.2f",
                title,
                _clamp_score(scores.get("summary_quality", 5)),
                _clamp_score(scores.get("technical_depth", 5)),
                _clamp_score(scores.get("relevance", 5)),
                _clamp_score(scores.get("originality", 5)),
                _clamp_score(scores.get("formatting", 5)),
                weighted,
            )

        # 2. 新逻辑：计算所有条目总分的平均值
        average_score = total_weighted / len(items)
        review_passed = average_score >= pass_threshold

        logger.info(
            "[review_node] 审核结论: 平均分 %.2f (阈值 %.1f) -> passed=%s",
            average_score, pass_threshold, review_passed
        )

        # 生成反馈
        actionable_feedback = ""
        if not review_passed:
            base_msg = f"整体平均分 {average_score:.2f} 低于阈值 {pass_threshold}。"
            details_msg = f" 需重点改进: {', '.join(low_scores)}" if low_scores else ""
            actionable_feedback = f"[审核反馈-第{iteration}轮] {base_msg}{details_msg}"

        return {
            "review_passed": review_passed,
            "review_feedback": actionable_feedback,
            "failed_urls": failed_urls,
            "iteration": iteration,
            "cost_tracker": tracker,
        }

    except Exception as e:
        logger.warning("[review_node] 审核失败，自动拦截: %s", e)
        # 将审核失败视为未通过，防止脏数据入库
        return {
            "review_passed": False,
            "review_feedback": f"系统异常，审核终止: {e}",
            "failed_urls": [],
            "iteration": iteration,
            "cost_tracker": tracker,
        }
