"""LangGraph 工作流组装与编译。

工作流图定义：
┌─────────────────────────────────────────────────────────────────┐
│ 节点定义                                                         │
├─────────────────────────────────────────────────────────────────┤
│ collect   → 采集 GitHub AI 仓库 (sources)                       │
│ analyze   → LLM 生成摘要、标签、评分 (analyses)                 │
│ organize  → 过滤低分、去重、反馈修正 (articles)                  │
│ review    → 四维度审核 (review_passed, review_feedback)          │
│ save      → 写入本地文件 + index.json                           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 边定义                                                           │
├─────────────────────────────────────────────────────────────────┤
│ 有向边 (顺序执行):                                               │
│   collect → analyze → organize → review                          │
│                                                                  │
│ 条件边 (审核路由):                                               │
│   review → [review_passed?] ─┬─ True  → save → END              │
│                              └─ False → organize (循环修正)      │
│                                                                  │
│ 循环规则: review → organize → review 最多 3 次，第 3 次强制通过   │
│                                                                  │
│ 入口点: collect                                                   │
└─────────────────────────────────────────────────────────────────┘
"""

import logging
import os
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from langgraph.graph import END, StateGraph

from workflows.nodes import (
    analyze_node,
    collect_node,
    organize_node,
    review_node,
    save_node,
)
from workflows.state import KBState

logger = logging.getLogger(__name__)


def _route_after_review(state: KBState) -> str:
    """审核后的路由函数。

    Args:
        state: 当前工作流状态。

    Returns:
        下一个节点名称："save" 或 "organize"。
    """
    if state.get("review_passed"):
        return "save"
    return "organize"


def build_graph() -> StateGraph:
    """构建并编译 LangGraph 工作流。

    Returns:
        编译后的 LangGraph 应用。
    """
    graph = StateGraph(KBState)

    # 注册节点
    graph.add_node("collect", collect_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("organize", organize_node)
    graph.add_node("review", review_node)
    graph.add_node("save", save_node)

    # 线性边
    graph.add_edge("collect", "analyze")
    graph.add_edge("analyze", "organize")
    graph.add_edge("organize", "review")

    # 条件边：审核后分支
    graph.add_conditional_edges(
        "review",
        _route_after_review,
        {
            "save": "save",
            "organize": "organize",
        },
    )

    # 入口点与终边
    graph.set_entry_point("collect")
    graph.add_edge("save", END)

    return graph.compile()


def _initial_state() -> KBState:
    """返回工作流初始状态。

    Returns:
        空的 KBState 字典。
    """
    return {
        "sources": [],
        "analyses": [],
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "iteration": 0,
        "cost_tracker": {},
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    app = build_graph()
    initial = _initial_state()

    logger.info("=" * 60)
    logger.info("LangGraph 工作流启动")
    logger.info("=" * 60)

    for event in app.stream(initial):
        node_name = list(event.keys())[0]
        output = event[node_name]

        logger.info("[节点: %s] 执行完成", node_name)

        if node_name == "collect":
            logger.info("  采集到 %d 个仓库", len(output.get("sources", [])))
        elif node_name == "analyze":
            logger.info("  分析完成 %d 条", len(output.get("analyses", [])))
        elif node_name == "organize":
            logger.info("  整理后保留 %d 条", len(output.get("articles", [])))
        elif node_name == "review":
            logger.info("  审核结果: passed=%s, iteration=%d",
                        output.get("review_passed"), output.get("iteration"))
        elif node_name == "save":
            logger.info("  保存完成")

    logger.info("=" * 60)
    logger.info("工作流执行完毕")
    logger.info("=" * 60)
