"""LangGraph 工作流节点函数定义。

每个节点是纯函数：接收 KBState，返回 dict（部分状态更新）。

节点调用链：
┌─────────────┐
│ collect_node │ 采集 GitHub AI 仓库 → sources（预去重）
└──────┬──────┘
       ▼
┌─────────────┐
│ analyze_node │ LLM 分析每条数据 → analyses (summary, tags, score)
└──────┬──────┘
       ▼
┌─────────────┐
│organize_node │ 内存去重 + 持久化去重 + 格式化 → articles
└──────┬──────┘
       ▼
┌──────────────────────────────────────────────────────────────┐
│ 以下节点已迁移至独立模块，并在本文件中调用：                   │
│  - workflows/reviewer.py: review_node (五维审核 articles)     │
│  - workflows/reviser.py:  revise_node (反馈修正 analyses)     │
└──────────────────────────────────────────────────────────────┘
       ▼
┌─────────────┐
│human_flag_node│ 审核超 3 轮未通过，触发人工介入
└──────┬──────┘
       ▼
┌─────────────┐
│  save_node   │ 写入 articles/*.json + 更新 index.json → 完成
└─────────────┘

流转逻辑：
collect → analyze → organize → review → [通过] → save
                                     → [不通过, iter < 3] → revise → organize (循环)
                                     → [不通过, iter >= 3] → human_flag → END
"""

import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from workflows.model_client import accumulate_usage, chat, chat_json
from workflows.state import KBState

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTICLES_DIR = PROJECT_ROOT / "knowledge" / "articles"
INDEX_PATH = ARTICLES_DIR / "index.json"

# GitHub API 重试配置
GITHUB_API_MAX_RETRIES = 3
GITHUB_API_RETRY_DELAY = 5  # 秒


def _load_existing_urls() -> set:
    """从 index.json 加载已存在的 source_url 集合。

    Returns:
        已存在的 URL 集合，加载失败返回空集合。
    """
    if not INDEX_PATH.exists():
        return set()
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            index_data = json.load(f)
        return {item.get("source_url") for item in index_data if item.get("source_url")}
    except Exception as e:
        logger.warning("[collect_node] 加载 index.json 失败: %s", e)
        return set()


def _fetch_github_api(url: str, token: str | None = None) -> dict:
    """调用 GitHub API，支持认证与重试。

    Args:
        url: 完整的 API URL。
        token: GitHub Personal Access Token（可选）。

    Returns:
        API 响应的 JSON 数据。

    Raises:
        urllib.error.HTTPError: 重试耗尽后仍失败时抛出。
    """
    headers = {
        "User-Agent": "AI-Knowledge-Assistant",
        "Accept": "application/vnd.github.v3+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for attempt in range(1, GITHUB_API_MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 403 and attempt < GITHUB_API_MAX_RETRIES:
                # 限流触发，等待后重试
                reset_time = e.headers.get("X-RateLimit-Reset")
                if reset_time:
                    wait = int(reset_time) - int(time.time()) + 1
                    wait = max(wait, GITHUB_API_RETRY_DELAY)
                else:
                    wait = GITHUB_API_RETRY_DELAY * attempt
                logger.warning(
                    "[collect_node] GitHub API 限流，%d 秒后重试 (%d/%d)",
                    wait, attempt, GITHUB_API_MAX_RETRIES,
                )
                time.sleep(wait)
                continue
            logger.error("[collect_node] GitHub API 请求失败 (HTTP %d): %s", e.code, e.reason)
            raise
        except Exception as e:
            if attempt < GITHUB_API_MAX_RETRIES:
                wait = GITHUB_API_RETRY_DELAY * attempt
                logger.warning(
                    "[collect_node] 请求异常，%d 秒后重试 (%d/%d): %s",
                    wait, attempt, GITHUB_API_MAX_RETRIES, e,
                )
                time.sleep(wait)
                continue
            logger.error("[collect_node] 请求异常，重试耗尽: %s", e)
            raise

    raise RuntimeError("[collect_node] GitHub API 重试耗尽")


def collect_node(state: KBState) -> dict:
    """采集节点：调用 GitHub Search API 采集 AI 相关仓库（预去重 + 认证 + 重试）。

    Args:
        state: 当前工作流状态。

    Returns:
        包含 sources 和 cost_tracker 的部分状态更新。
    """
    logger.info("[collect_node] 开始采集 GitHub AI 仓库")

    # 获取策略配置 (如果 planner 运行过)
    plan = state.get("plan", {})

    # 构建查询参数
    query = os.getenv("GITHUB_QUERY", "AI agent LLM")
    per_page = int(plan.get("per_source_limit", os.getenv("GITHUB_PER_PAGE", "15")))
    since = os.getenv("GITHUB_SINCE", "")  # 例: 2026-05-01

    logger.info("[collect_node] 使用策略: %s, per_page=%d", plan.get("tier", "default"), per_page)

    encoded = urllib.parse.quote(query)
    url = f"https://api.github.com/search/repositories?q={encoded}&sort=stars&order=desc&per_page={per_page}"
    if since:
        url += f"&since={since}"

    logger.info("[collect_node] 查询参数: query='%s', per_page=%d, since='%s'", query, per_page, since)

    # 加载已存在的 URL 用于预去重
    existing_urls = _load_existing_urls()
    logger.info("[collect_node] 已加载 %d 条已有 URL 用于预去重", len(existing_urls))

    # 调用 API（带认证与重试）
    token = os.getenv("GITHUB_TOKEN")
    data = _fetch_github_api(url, token)

    sources = []
    skipped = 0
    for item in data.get("items", []):
        source_url = item["html_url"]
        if source_url in existing_urls:
            skipped += 1
            continue
        sources.append({
            "source_url": source_url,
            "title": item["full_name"],
            "description": item.get("description", ""),
            "stars": item.get("stargazers_count", 0),
            "language": item.get("language", ""),
            "topics": item.get("topics", []),
        })

    logger.info(
        "[collect_node] 采集完成: API 返回 %d 条，跳过重复 %d 条，新增 %d 条",
        len(data.get("items", [])), skipped, len(sources),
    )
    return {"sources": sources, "cost_tracker": state.get("cost_tracker", {})}


def analyze_node(state: KBState) -> dict:
    """分析节点：用 LLM 对每条数据生成中文摘要、标签、评分。

    采用增强版 Prompt (CoT + Few-Shot + 明确标准) 提升分析深度和准确性。

    Args:
        state: 当前工作流状态。

    Returns:
        包含 analyses 和 cost_tracker 的部分状态更新。
    """
    logger.info("[analyze_node] 开始分析 %d 条数据", len(state["sources"]))

    analyses = []
    tracker = state.get("cost_tracker", {})

    system_prompt = """你是一个资深 AI 架构师和技术分析师。你的任务是根据 GitHub 仓库的基础信息，进行深度的技术分析和评估。
请基于仓库的描述、话题等有限信息，结合你的先验知识，推断其技术栈、架构设计、应用场景等。
分析必须客观、准确、深入，避免泛泛而谈。"""

    examples = """【分析参考示例】
示例 1 (高质量):
输入: {title: "langgenius/dify", description: "LLM app development platform...", topics: ["llm", "rag", "agent", "workflow"], stars: 40000}
输出: {
  "summary": "开源的 LLM 应用开发平台，提供可视化的 Agent/Workflow 编排界面，内置 RAG 引擎，支持 50+ 模型接入，解决企业级 AI 应用落地难题。",
  "tags": ["LLM-Application", "RAG", "Agent-Orchestration", "Low-Code"],
  "score": 0.92
}

示例 2 (低质量):
输入: {title: "awesome-list", description: "List of AI tools", topics: ["list", "ai"], stars: 200}
输出: {
  "summary": "GitHub 上的 AI 工具资源列表，包含各类工具链接，无代码实现或技术深度。",
  "tags": ["Awesome-List", "Resource-Collection"],
  "score": 0.15
}"""

    prompt_template = """请分析以下 GitHub 仓库，并输出严格的 JSON 格式结果。

【基础信息】
- 名称: {title}
- 描述: {description}
- 语言: {language}
- 话题: {topics}
- Star 数: {stars}

【分析要求】
1. **摘要 (summary)**: 50-100 字。必须包含：核心技术点、解决的业务痛点/场景、架构或算法亮点。拒绝流水账式的描述。
2. **标签 (tags)**: 3-5 个。必须是具体的技术名词或架构模式（如 "Vector-Database", "MoE-Architecture"），严禁使用 "AI", "Tool", "Project" 等泛泛词汇。
3. **评分 (score)**: 0.0-1.0 之间。
   - 0.85-1.0: 行业标杆，有重大创新或极高 Star (10k+)，技术架构领先。
   - 0.7-0.85: 优秀项目，解决特定痛点，文档完善，有一定独特性。
   - 0.5-0.7: 实用工具，有参考价值，但属于常见封装或集成。
   - <0.5: 教程、Demo、过期项目或纯资源列表，技术含量低。

{examples}

请输出 JSON:
{{
  "summary": "...",
  "tags": ["...", "..."],
  "score": ...
}}"""

    for item in state["sources"]:
        desc = item.get('description') or '无描述'
        lang = item.get('language') or '未指定'
        topics = ', '.join(item.get('topics', [])) or '无话题'
        stars = item.get('stars', 0)

        prompt = prompt_template.format(
            title=item['title'],
            description=desc,
            language=lang,
            topics=topics,
            stars=stars,
            examples=examples
        )

        try:
            # 降低 temperature 提升稳定性
            result, usage = chat_json(prompt, system=system_prompt, temperature=0.3)
            tracker = accumulate_usage(tracker, usage)

            # 校验结果
            if not isinstance(result, dict):
                raise ValueError("LLM 返回非 JSON 对象")

            # 字段提取与清洗
            summary = result.get("summary", "")
            tags = result.get("tags", [])
            score = result.get("score", 0.5)

            # 容错处理
            if not isinstance(tags, list):
                tags = [str(tags)]
            try:
                score = float(score)
                score = max(0.0, min(1.0, score))
            except ValueError:
                score = 0.5

            analyses.append({
                "source_url": item["source_url"],
                "title": item["title"],
                "summary": summary,
                "tags": tags,
                "score": score,
                "stars": stars,
                "language": lang,
            })
        except Exception as e:
            logger.warning("[analyze_node] 分析失败 %s: %s", item["title"], e)

    logger.info("[analyze_node] 完成分析 %d 条", len(analyses))
    return {"analyses": analyses, "cost_tracker": tracker}


def organize_node(state: KBState) -> dict:
    """整理节点：去重、格式化。

    Args:
        state: 当前工作流状态。

    Returns:
        包含 articles 和 cost_tracker 的部分状态更新。
    """
    logger.info("[organize_node] 开始整理 %d 条分析结果", len(state["analyses"]))

    analyses = state["analyses"]
    tracker = state.get("cost_tracker", {})

    # 1. 内存去重
    seen_urls = set()
    deduped = []
    for a in analyses:
        if a["source_url"] not in seen_urls:
            seen_urls.add(a["source_url"])
            deduped.append(a)

    # 2. 持久化去重 (对比 index.json)
    existing_urls = set()
    if INDEX_PATH.exists():
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as f:
                index_data = json.load(f)
            existing_urls = {item.get("source_url") for item in index_data if item.get("source_url")}
        except Exception as e:
            logger.warning("[organize_node] 加载 index.json 失败: %s", e)

    deduped_final = [a for a in deduped if a["source_url"] not in existing_urls]
    if len(deduped_final) < len(deduped):
        logger.info("[organize_node] 数据库去重：过滤掉 %d 条已存在", len(deduped) - len(deduped_final))

    # 3. 格式化为标准 articles
    articles = []
    for item in deduped_final:
        articles.append({
            "id": f"{item.get('source', 'article')}-{time.strftime('%Y%m%d')}-{abs(hash(item['source_url'])) % 1000:03d}",
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


def human_flag_node(state: KBState) -> dict:
    """人工审核节点：当自动审核达到最大次数仍未通过时触发。

    Args:
        state: 当前工作流状态。

    Returns:
        包含 cost_tracker 的部分状态更新。
    """
    logger.info("[human_flag_node] 触发人工审核，iteration=%d", state.get("iteration", 0))
    return {"cost_tracker": state.get("cost_tracker", {})}


def human_flag_node(state: KBState) -> dict:
    """人工审核节点：当自动审核达到最大次数仍未通过时触发。

    Args:
        state: 当前工作流状态。

    Returns:
        包含 cost_tracker 的部分状态更新。
    """
    logger.info("[human_flag_node] 触发人工审核，iteration=%d", state.get("iteration", 0))
    # 这里可以接入飞书通知或其他人工介入逻辑
    return {"cost_tracker": state.get("cost_tracker", {})}


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
