"""LangGraph 工作流组装与编译。

工作流图定义：
┌─────────────────────────────────────────────────────────────────┐
│ 节点定义                                                         │
├─────────────────────────────────────────────────────────────────┤
│ planner   → 根据 target_count 制定策略 (plan)                    │
│ collect   → 采集 GitHub AI 仓库（预去重）→ sources               │
│ analyze   → LLM 生成摘要、标签、评分 (analyses)                 │
│ organize  → 过滤、去重、格式化 (articles)                        │
│ review    → 五维审核 articles (review_passed, failed_urls)      │
│ revise    → 根据反馈修正 analyses (temperature=0.4)             │
│ human_flag→ 人工审核入口 (iteration >= 3 且未通过)               │
│ save      → 写入本地文件 + index.json                           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 流程路由                                                         │
├─────────────────────────────────────────────────────────────────┤
│ 0. 策略阶段                                                       │
│    entry_point → planner → collect                               │
│                                                                  │
│ 1. 采集阶段                                                       │
│    collect → [有新增?] ─┬─ True  → analyze                       │
│                         └─ False → save                          │
│                                                                  │
│ 2. 分析与整理阶段                                                 │
│    analyze → organize                                            │
│                                                                  │
│ 3. 审核阶段                                                       │
│    organize → review                                             │
│                                                                  │
│ 4. 审核后 3 路路由 (route_after_review)                          │
│    review → [passed?] ─┬─ True   → save                          │
│                        ├─ False & iter < 3 → revise              │
│                        └─ False & iter >= 3 → human_flag         │
│                                                                  │
│ 5. 修正循环                                                       │
│    revise → organize → review                                    │
│                                                                  │
│ 6. 终止条件                                                       │
│    human_flag → END                                              │
│    save → END                                                    │
└─────────────────────────────────────────────────────────────────┘
"""

import logging
import os
import sys
import warnings
from pathlib import Path

# 过滤 LangChain/LangGraph 内部废弃警告
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

# 确保项目根目录在 sys.path 中
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from langgraph.graph import END, StateGraph

from workflows.nodes import (
    analyze_node,
    collect_node,
    human_flag_node,
    organize_node,
    save_node,
)
from workflows.planner import planner_node
from workflows.reviser import revise_node
from workflows.reviewer import review_node
from workflows.state import KBState

logger = logging.getLogger(__name__)


def _route_after_collect(state: KBState) -> str:
    """采集后的路由函数。

    Args:
        state: 当前工作流状态。

    Returns:
        下一个节点名称："analyze" 或 "save"。
    """
    if not state.get("sources"):
        return "save"
    return "analyze"


def route_after_review(state: KBState) -> str:
    """审核后的 3 路条件路由函数。

    Args:
        state: 当前工作流状态。

    Returns:
        下一个节点名称："save" (通过), "revise" (修正), 或 "human_flag" (人工审核)。
    """
    passed = state.get("review_passed", False)
    iteration = state.get("iteration", 0)
    
    # 动态读取策略配置中的最大迭代次数
    plan = state.get("plan", {})
    max_iter = plan.get("max_iterations", 3)

    if passed:
        return "save"
    
    if iteration < max_iter:
        return "revise"
    
    return "human_flag"


def build_graph() -> StateGraph:
    """构建并编译 LangGraph 工作流。

    Returns:
        编译后的 LangGraph 应用。
    """
    graph = StateGraph(KBState)

    # 注册节点
    graph.add_node("planner", planner_node)
    graph.add_node("collect", collect_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("organize", organize_node)
    graph.add_node("review", review_node)
    graph.add_node("revise", revise_node)
    graph.add_node("human_flag", human_flag_node)
    graph.add_node("save", save_node)

    # 设置 planner 为入口点
    graph.set_entry_point("planner")

    # 顺序边：planner -> collect
    graph.add_edge("planner", "collect")

    # 条件边：采集后分支（无新增则直接保存）
    graph.add_conditional_edges(
        "collect",
        _route_after_collect,
        {
            "analyze": "analyze",
            "save": "save",
        },
    )

    # 顺序边：分析 -> 整理
    graph.add_edge("analyze", "organize")

    # 顺序边：整理 -> 审核
    graph.add_edge("organize", "review")

    # 3 路条件边：审核后分支
    graph.add_conditional_edges(
        "review",
        route_after_review,
        {
            "save": "save",
            "revise": "revise",
            "human_flag": "human_flag",
        },
    )

    # 顺序边：修正 -> 整理 (形成循环)
    graph.add_edge("revise", "organize")

    # 终边
    graph.add_edge("human_flag", END)

    # 终边
    graph.add_edge("human_flag", END)
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
        "failed_urls": [],
        "iteration": 0,
        "cost_tracker": {},
        "plan": {},
    }


if __name__ == "__main__":
    from dotenv import load_dotenv

    # 加载 .env 文件（若存在）
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger.info("已加载环境变量: %s", env_path)
    else:
        logger.warning("未找到 .env 文件，使用系统环境变量")

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
            sources = output.get("sources", [])
            logger.info("  新增 %d 个仓库（已过滤重复）", len(sources))
            if not sources:
                logger.info("  无新增条目，跳过后续流程")
        elif node_name == "analyze":
            logger.info("  分析完成 %d 条", len(output.get("analyses", [])))
        elif node_name == "organize":
            logger.info("  整理后保留 %d 条", len(output.get("articles", [])))
        elif node_name == "review":
            logger.info("  审核结果: passed=%s, iteration=%d",
                        output.get("review_passed"), output.get("iteration"))
        elif node_name == "revise":
            logger.info("  修正完成 %d 条", len(output.get("analyses", [])))
        elif node_name == "organize":
            logger.info("  整理后保留 %d 条", len(output.get("articles", [])))
        elif node_name == "human_flag":
            logger.info("  触发人工审核流程")
        elif node_name == "save":
            logger.info("  保存完成")

    logger.info("=" * 60)
    logger.info("工作流执行完毕")
    logger.info("=" * 60)
