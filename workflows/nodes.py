"""LangGraph 工作流节点函数定义。

每个节点是纯函数：接收 KBState，返回 dict（部分状态更新）。

节点调用链：
┌─────────────┐
│ collect_node │ 采集 GitHub AI 仓库 → sources
└──────┬──────┘
       ▼
┌─────────────┐
│ analyze_node │ LLM 分析每条数据 → analyses (summary, tags, score)
└──────┬──────┘
       ▼
┌─────────────┐
│organize_node │ 过滤低分(<0.6) + URL去重 + LLM修正(有feedback时) → articles
└──────┬──────┘
       ▼
┌─────────────┐
│ review_node  │ LLM四维度审核 → review_passed, review_feedback, iteration
└──────┬──────┘
       │
  ┌────┴────┐
  │ passed? │
  └────┬────┘
       │
  ┌────▼────┐
   │iteration│ < 3 且 not passed → 回到 organize_node (循环)
  └────┬────┘
       │
  >= 2 或 passed → save_node
       ▼
┌─────────────┐
│  save_node   │ 写入 articles/*.json + 更新 index.json → 完成
└─────────────┘
"""

import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from workflows.model_client import accumulate_usage, chat, chat_json
from workflows.state import KBState

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTICLES_DIR = PROJECT_ROOT / "knowledge" / "articles"
INDEX_PATH = ARTICLES_DIR / "index.json"

SCORE_THRESHOLD = 0.6
MAX_REVIEW_ITERATION = 3


def collect_node(state: KBState) -> dict:
    """采集节点：调用 GitHub Search API 采集 AI 相关仓库。

    Args:
        state: 当前工作流状态。

    Returns:
        包含 sources 和 cost_tracker 的部分状态更新。
    """
    logger.info("[collect_node] 开始采集 GitHub AI 仓库")

    query = os.getenv("GITHUB_QUERY", "AI agent LLM")
    encoded = urllib.parse.quote(query)
    url = f"https://api.github.com/search/repositories?q={encoded}&sort=stars&order=desc&per_page=10"

    req = urllib.request.Request(url, headers={"User-Agent": "AI-Knowledge-Assistant"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    sources = []
    for item in data.get("items", []):
        sources.append({
            "source_url": item["html_url"],
            "title": item["full_name"],
            "description": item.get("description", ""),
            "stars": item.get("stargazers_count", 0),
            "language": item.get("language", ""),
            "topics": item.get("topics", []),
        })

    logger.info("[collect_node] 采集到 %d 个仓库", len(sources))
    return {"sources": sources, "cost_tracker": state.get("cost_tracker", {})}


def analyze_node(state: KBState) -> dict:
    """分析节点：用 LLM 对每条数据生成中文摘要、标签、评分。

    Args:
        state: 当前工作流状态。

    Returns:
        包含 analyses 和 cost_tracker 的部分状态更新。
    """
    logger.info("[analyze_node] 开始分析 %d 条数据", len(state["sources"]))

    analyses = []
    tracker = state.get("cost_tracker", {})

    for item in state["sources"]:
        prompt = f"""分析以下 GitHub 仓库，输出 JSON：
名称: {item['title']}
描述: {item['description']}
语言: {item['language']}
话题: {', '.join(item['topics'])}

输出格式:
{{"summary": "50字内中文摘要", "tags": ["tag1", "tag2"], "score": 0-1之间的浮分数}}"""

        try:
            result, usage = chat_json(prompt, system="你是一个 AI 技术分析师。")
            usage = accumulate_usage(tracker, usage)
            tracker = usage

            analyses.append({
                "source_url": item["source_url"],
                "title": item["title"],
                "summary": result.get("summary", ""),
                "tags": result.get("tags", []),
                "score": result.get("score", 0.5),
                "stars": item["stars"],
                "language": item.get("language", ""),
            })
        except Exception as e:
            logger.warning("[analyze_node] 分析失败 %s: %s", item["title"], e)

    logger.info("[analyze_node] 完成分析 %d 条", len(analyses))
    return {"analyses": analyses, "cost_tracker": tracker}


def organize_node(state: KBState) -> dict:
    """整理节点：过滤低分、去重、如有审核反馈则用 LLM 修正。

    Args:
        state: 当前工作流状态。

    Returns:
        包含 articles 和 cost_tracker 的部分状态更新。
    """
    logger.info("[organize_node] 开始整理 %d 条分析结果", len(state["analyses"]))

    analyses = state["analyses"]
    feedback = state.get("review_feedback", "")
    iteration = state.get("iteration", 0)
    tracker = state.get("cost_tracker", {})

    filtered = [a for a in analyses if a.get("score", 0) >= SCORE_THRESHOLD]

    seen_urls = set()
    deduped = []
    for a in filtered:
        if a["source_url"] not in seen_urls:
            seen_urls.add(a["source_url"])
            deduped.append(a)

    articles = []
    for item in deduped:
        if iteration > 0 and feedback:
            prompt = f"""根据审核反馈修正以下条目：
原条目: {json.dumps(item, ensure_ascii=False)}
审核反馈: {feedback}

请修正后输出 JSON: {{"title": "...", "summary": "...", "tags": [...], "score": 0-1}}"""

            try:
                result, usage = chat_json(prompt, system="你是一个严谨的知识整理助手。")
                usage = accumulate_usage(tracker, usage)
                tracker = usage
                item.update(result)
            except Exception as e:
                logger.warning("[organize_node] 修正失败: %s", e)

        articles.append({
            "id": f"supervisor-{time.strftime('%Y%m%d')}-{abs(hash(item['source_url'])) % 1000:03d}",
            "title": item["title"],
            "source": "github",
            "source_url": item["source_url"],
            "summary": item["summary"],
            "highlights": [],
            "tags": item["tags"],
            "language": item.get("language", ""),
            "stars": item.get("stars", 0),
            "status": "analyzed",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    logger.info("[organize_node] 整理完成，保留 %d 条", len(articles))
    return {"articles": articles, "cost_tracker": tracker}


def review_node(state: KBState) -> dict:
    """审核节点：LLM 四维度评分，iteration >= 3 强制通过。

    Args:
        state: 当前工作流状态。

    Returns:
        包含 review_passed、review_feedback、iteration、cost_tracker 的部分状态更新。
    """
    logger.info("[review_node] 开始审核 %d 条文章", len(state["articles"]))

    iteration = state.get("iteration", 0) + 1

    if iteration >= MAX_REVIEW_ITERATION:
        logger.info("[review_node] 达到最大审核次数 %d，强制通过", iteration)
        return {
            "review_passed": True,
            "review_feedback": "强制通过（达到最大审核次数）",
            "iteration": iteration,
            "cost_tracker": state.get("cost_tracker", {}),
        }

    articles_summary = json.dumps(state["articles"], ensure_ascii=False, indent=2)
    prompt = f"""审核以下知识条目，严格评分。不要输出 passed 字段，只输出分数：

条目列表:
{articles_summary}

审核维度（1-10分，标准严格）:
- 摘要质量(summary_quality): >=7 才表示摘要准确、完整、有信息量
- 标签准确(tag_accuracy): >=7 才表示标签精准、无泛泛标签如"AI"
- 分类合理(category_reasonable): >=7 才表示分类准确、层级合理
- 一致性(consistency): >=7 才表示各条目风格统一、格式规范

如果有任何一个维度 < 5 分，说明质量较差，请给出具体修改建议。

输出格式:
{{"scores": {{"summary_quality": 分数, "tag_accuracy": 分数, "category_reasonable": 分数, "consistency": 分数}}, "feedback": "具体改进建议，指出不足"}}"""

    tracker = state.get("cost_tracker", {})
    try:
        result, usage = chat_json(prompt, system="你是一个严格的质量审核员。宁可给低分也不要放水。")
        usage = accumulate_usage(tracker, usage)
        tracker = usage

        scores = result.get("scores", {})
        avg = (
            scores.get("summary_quality", 5)
            + scores.get("tag_accuracy", 5)
            + scores.get("category_reasonable", 5)
            + scores.get("consistency", 5)
        ) / 4

        passed = avg >= 7
        feedback = result.get("feedback", "")

        logger.info(
            "[review_node] 四维度评分: summary=%s, tags=%s, category=%s, consistency=%s, avg=%.1f, passed=%s",
            scores.get("summary_quality"),
            scores.get("tag_accuracy"),
            scores.get("category_reasonable"),
            scores.get("consistency"),
            avg,
            passed,
        )

        return {
            "review_passed": passed,
            "review_feedback": feedback if not passed else "",
            "iteration": iteration,
            "cost_tracker": tracker,
        }
    except Exception as e:
        logger.warning("[review_node] 审核失败: %s", e)
        return {
            "review_passed": False,
            "review_feedback": str(e),
            "iteration": iteration,
            "cost_tracker": tracker,
        }


def save_node(state: KBState) -> dict:
    """保存节点：将 articles 写入 knowledge/articles/ 目录，同时更新 index.json。

    Args:
        state: 当前工作流状态。

    Returns:
        包含 cost_tracker 的部分状态更新。
    """
    logger.info("[save_node] 开始保存 %d 条文章", len(state["articles"]))

    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    tracker = state.get("cost_tracker", {})

    saved_files = []
    for article in state["articles"]:
        slug = re.sub(r"[^\w\s-]", "", article["title"]).strip().lower()
        slug = re.sub(r"[\s_/]+", "-", slug)[:40]
        filename = f"{time.strftime('%Y%m%d')}-{article['source']}-{slug}.json"
        filepath = ARTICLES_DIR / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(article, f, ensure_ascii=False, indent=2)
        saved_files.append(str(filepath))

    existing = []
    if INDEX_PATH.exists():
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    existing_ids = {a.get("id") for a in existing}
    for article in state["articles"]:
        if article["id"] not in existing_ids:
            existing.append(article)

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    logger.info("[save_node] 已保存 %d 条文章到 %s", len(saved_files), ARTICLES_DIR)
    return {"cost_tracker": tracker}
