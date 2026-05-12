"""Router 路由模式——两层意图分类策略。

第一层：关键词快速匹配（零成本）
第二层：LLM 分类兜底（处理模糊意图）
"""

import asyncio
import json
import logging
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from pipeline.model_client import quick_chat

logger = logging.getLogger(__name__)

# ── 意图定义 ──────────────────────────────────────────────────────────────
INTENT_GITHUB_SEARCH = "github_search"
INTENT_KNOWLEDGE_QUERY = "knowledge_query"
INTENT_GENERAL_CHAT = "general_chat"

# 第一层：关键词映射（意图 -> 关键词列表）
KEYWORD_MAP = {
    INTENT_GITHUB_SEARCH: [
        "github", "github搜索", "搜索项目", "开源项目", "star", "仓库",
        "repository", "awesome", "找代码", "找工具", "找库",
    ],
    INTENT_KNOWLEDGE_QUERY: [
        "知识库", "知识", "之前采集", "之前收集", "之前分析",
        "历史记录", "采集的文章", "分析过的", "已保存",
    ],
}

# LLM 分类 Prompt
CLASSIFY_PROMPT = """你是一个意图分类器。判断用户输入属于哪种意图，仅返回 JSON：
{{"intent": "github_search" | "knowledge_query" | "general_chat"}}

意图说明：
- github_search：用户想搜索 GitHub 项目、查找开源工具/库/代码
- knowledge_query：用户明确想查询本地知识库中已采集/已保存的内容（关键词含"知识库"、"之前采集的"、"我保存的"等）
- general_chat：开放式问答、知识比较、技术分析、不属于以上两类

用户输入：{query}"""

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTICLES_DIR = PROJECT_ROOT / "knowledge" / "articles"


def _keyword_match(query: str) -> str | None:
    """第一层：关键词快速匹配。

    Args:
        query: 用户输入。

    Returns:
        匹配到的意图名称，未匹配返回 None。
    """
    query_lower = query.lower()
    for intent, keywords in KEYWORD_MAP.items():
        if any(kw in query_lower for kw in keywords):
            return intent
    return None


async def _llm_classify(query: str) -> str:
    """第二层：LLM 分类兜底。

    Args:
        query: 用户输入。

    Returns:
        分类后的意图名称。
    """
    prompt = CLASSIFY_PROMPT.format(query=query)
    try:
        result = await quick_chat(prompt=prompt, temperature=0.1)
        match = re.search(r'"intent"\s*:\s*"(\w+)"', result)
        if match:
            intent = match.group(1)
            if intent in (INTENT_GITHUB_SEARCH, INTENT_KNOWLEDGE_QUERY, INTENT_GENERAL_CHAT):
                return intent
    except Exception as e:
        logger.warning("LLM 分类失败，回退到 general_chat: %s", e)
    return INTENT_GENERAL_CHAT


async def classify_intent(query: str) -> str:
    """两层意图分类。

    Args:
        query: 用户输入。

    Returns:
        意图名称。
    """
    intent = _keyword_match(query)
    if intent:
        logger.info("关键词匹配意图: %s", intent)
        return intent

    logger.info("关键词未命中，调用 LLM 分类")
    return await _llm_classify(query)


# ── 意图处理器 ────────────────────────────────────────────────────────────

async def handle_github_search(query: str) -> str:
    """处理器：GitHub 搜索。

    提取搜索关键词后调用 GitHub Search API。

    Args:
        query: 用户输入。

    Returns:
        格式化的搜索结果字符串。
    """
    keyword = query
    for kw in KEYWORD_MAP[INTENT_GITHUB_SEARCH]:
        keyword = keyword.replace(kw, "").strip()
    keyword = keyword or "AI agent"

    encoded = urllib.parse.quote(keyword)
    url = f"https://api.github.com/search/repositories?q={encoded}&sort=stars&order=desc&per_page=5"

    req = urllib.request.Request(url, headers={"User-Agent": "AI-Knowledge-Assistant"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error("GitHub API 请求失败: %s", e)
        return f"GitHub 搜索失败：{e}"

    items = data.get("items", [])
    if not items:
        return f"未找到与「{keyword}」相关的 GitHub 项目。"

    lines = [f"GitHub 搜索「{keyword}」结果：\n"]
    for i, repo in enumerate(items, 1):
        lines.append(
            f"{i}. **{repo['full_name']}** ⭐{repo['stargazers_count']}\n"
            f"   {repo.get('description', '暂无描述')}\n"
            f"   {repo['html_url']}"
        )
    return "\n\n".join(lines)


async def handle_knowledge_query(query: str) -> str:
    """处理器：知识库检索。

    直接扫描 knowledge/articles/ 目录下所有 JSON 文件。

    Args:
        query: 用户输入。

    Returns:
        格式化的知识条目列表。
    """
    articles = []

    if not ARTICLES_DIR.exists():
        return "知识库为空，尚未采集任何文章。"

    for json_file in ARTICLES_DIR.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                articles.append(json.load(f))
        except Exception as e:
            logger.warning("跳过无效文件 %s: %s", json_file.name, e)

    if not articles:
        return "知识库为空，尚未采集任何文章。"

    query_lower = query.lower()
    query_words = query_lower.split()
    matched = []
    for article in articles:
        title = article.get("title", "").lower()
        summary = article.get("summary", "").lower()
        tags = " ".join(article.get("tags", [])).lower()
        if any(kw in title or kw in summary or kw in tags for kw in query_words):
            matched.append(article)

    if not matched:
        return f"知识库中未找到与「{query}」相关的内容。"

    lines = [f"知识库检索「{query}」结果（共 {len(matched)} 条）：\n"]
    for i, art in enumerate(matched[:10], 1):
        lines.append(
            f"{i}. **{art['title']}** [{art.get('source', '')}]\n"
            f"   {art.get('summary', '')}\n"
            f"   标签: {', '.join(art.get('tags', []))}\n"
            f"   {art.get('source_url', '')}"
        )
    return "\n\n".join(lines)


async def handle_general_chat(query: str) -> str:
    """处理器：普通聊天。

    直接调用 LLM 回答。

    Args:
        query: 用户输入。

    Returns:
        LLM 回复文本。
    """
    return await quick_chat(prompt=query)


# ── 路由分发 ──────────────────────────────────────────────────────────────

HANDLERS = {
    INTENT_GITHUB_SEARCH: handle_github_search,
    INTENT_KNOWLEDGE_QUERY: handle_knowledge_query,
    INTENT_GENERAL_CHAT: handle_general_chat,
}


async def route(query: str) -> str:
    """统一路由入口。

    根据用户输入进行意图分类，分发到对应的处理器。

    Args:
        query: 用户输入。

    Returns:
        处理器返回的响应字符串。
    """
    if not query or not query.strip():
        return "请输入您的问题。"

    intent = await classify_intent(query)
    handler = HANDLERS.get(intent, handle_general_chat)
    logger.info("路由分发 -> %s", intent)
    return await handler(query)


# ── 测试入口 ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        logger.info("输入: %s", query)
        result = asyncio.run(route(query))
        print(result)
    else:
        test_cases = [
            ("github搜索 Python AI框架", "关键词 -> github_search"),
            ("帮我查一下之前采集的关于 LLM 的文章", "关键词 -> knowledge_query"),
            ("你好，今天天气怎么样？", "关键词未命中 -> LLM -> general_chat"),
            ("有什么好用的开源 Agent 框架", "模糊意图 -> LLM 分类"),
        ]

        async def run_tests():
            for q, expect in test_cases:
                logger.info("=" * 50)
                logger.info("输入: %s (预期: %s)", q, expect)
                result = await route(q)
                logger.info("输出: %s", result[:150])
                logger.info("=" * 50)

        asyncio.run(run_tests())
