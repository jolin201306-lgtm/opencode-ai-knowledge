"""LangGraph 工作流共享状态定义。

KBState 作为工作流中各节点间的通信载体，遵循"报告式通信"原则：
传递的是结构化摘要与决策结果，而非原始数据。
"""

from typing import TypedDict


class KBState(TypedDict, total=False):
    """知识库工作流共享状态。

    Attributes:
        sources: 采集到的原始数据列表，每条包含 source_url、title、raw_content 等摘要。
        analyses: LLM 分析后的结构化结果列表，包含 summary、tags、score、key_points 等。
        articles: 格式化并去重后的标准知识条目列表，符合 AGENTS.md 定义的 JSON 规范。
        review_feedback: 审核环节的具体反馈意见，用于指导 Worker 节点下一轮改进。
        review_passed: 审核是否通过，True 表示质量达标可进入下一环节，False 需重试。
        iteration: 当前审核循环次数，上限为 3 次。
        cost_tracker: Token 用量追踪，包含 prompt_tokens、completion_tokens、total_cost_cny 等。
    """

    sources: list[dict]
    analyses: list[dict]
    articles: list[dict]
    review_feedback: str
    review_passed: bool
    iteration: int
    cost_tracker: dict
