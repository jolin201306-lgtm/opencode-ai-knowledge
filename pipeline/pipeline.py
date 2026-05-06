"""四步知识库自动化流水线：采集 → 分析 → 整理 → 保存。"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml

from model_client import Usage, chat_with_retry, estimate_cost, estimate_tokens

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "knowledge" / "raw"
ARTICLES_DIR = BASE_DIR / "knowledge" / "articles"
RSS_SOURCES_FILE = BASE_DIR / "pipeline" / "rss_sources.yaml"

RAW_DIR.mkdir(parents=True, exist_ok=True)
ARTICLES_DIR.mkdir(parents=True, exist_ok=True)


# ── 数据模型 ──────────────────────────────────────────────────────────────

class RawItem:
    """采集层原始数据项。

    Attributes:
        title: 标题。
        url: 来源链接。
        source: 数据来源（github 或 rss）。
        description: 描述文本。
        stars: Star 数（GitHub 来源）。
        language: 编程语言（GitHub 来源）。
        raw: 原始完整数据。
    """

    def __init__(
        self,
        title: str,
        url: str,
        source: str,
        description: str = "",
        stars: int = 0,
        language: str = "",
        raw: Optional[dict] = None,
    ):
        self.title = title
        self.url = url
        self.source = source
        self.description = description
        self.stars = stars
        self.language = language
        self.raw = raw or {}

    def to_dict(self) -> dict:
        """转换为字典。

        Returns:
            原始数据字典。
        """
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "description": self.description,
            "stars": self.stars,
            "language": self.language,
        }


class ArticleItem:
    """分析后的知识条目。

    Attributes:
        id: 唯一标识。
        title: 标题。
        source: 数据来源。
        source_url: 来源链接。
        summary: 摘要。
        highlights: 技术亮点列表。
        tags: 标签列表。
        language: 编程语言。
        stars: Star 数。
        score: 评分（1-10）。
        audience: 受众级别。
        status: 状态。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    def __init__(
        self,
        title: str,
        source: str,
        source_url: str,
        summary: str,
        highlights: list[str],
        tags: list[str],
        score: int,
        audience: str = "intermediate",
        language: str = "",
        stars: int = 0,
    ):
        self.id = f"{source}-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:3]}"
        self.title = title
        self.source = source
        self.source_url = source_url
        self.summary = summary
        self.highlights = highlights
        self.tags = tags
        self.language = language
        self.stars = stars
        self.score = score
        self.audience = audience
        self.status = "analyzed"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.created_at = now
        self.updated_at = now

    def to_dict(self) -> dict:
        """转换为字典。

        Returns:
            知识条目字典。
        """
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "source_url": self.source_url,
            "summary": self.summary,
            "highlights": self.highlights,
            "tags": self.tags,
            "language": self.language,
            "stars": self.stars,
            "score": self.score,
            "audience": self.audience,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ── Step 1: 采集 ─────────────────────────────────────────────────────────

GITHUB_TRENDING_URL = "https://github.com/trending"
GITHUB_AI_KEYWORDS = [
    "ai", "llm", "agent", "ml", "machine learning", "deep learning",
    "transformer", "gpt", "chatgpt", "openai", "claude", "rag",
    "multimodal", "nlp", "neural", "inference", "model",
]
GITHUB_EXCLUDE_KEYWORDS = ["awesome-", "tutorial", "course", "learn"]


async def collect_github(limit: int = 20) -> list[RawItem]:
    """从 GitHub Trending 采集 AI 相关项目。

    Args:
        limit: 采集数量上限。

    Returns:
        原始数据项列表。
    """
    logger.info("开始采集 GitHub Trending (limit=%d)", limit)
    items: list[RawItem] = []

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                GITHUB_TRENDING_URL,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            resp.raise_for_status()

        html = resp.text
        
        # 提取 article 块
        articles = re.findall(r'<article.*?</article>', html, re.DOTALL)
        
        for article in articles:
            if len(items) >= limit:
                break
                
            # 提取仓库链接（格式 /owner/repo）
            links = re.findall(r'href="(/[^/]+/[^/"]+)"', article)
            repo_path = None
            for link in links:
                # 排除 stargazers, forks, login 等
                if '/stargazers' not in link and '/forks' not in link and '/login' not in link:
                    repo_path = link.strip("/")
                    break
            
            if not repo_path or repo_path.count("/") != 1:
                continue
            
            # 提取描述
            desc_matches = re.findall(r'<p[^>]*>(.*?)</p>', article, re.DOTALL)
            desc = ""
            if desc_matches:
                desc = re.sub(r"<[^>]+>", "", desc_matches[0]).strip()
            
            # 提取 stars
            star_match = re.search(r'([\d,]+)\s*stars', article)
            stars = int(star_match.group(1).replace(",", "")) if star_match else 0
            
            repo_name = repo_path.split("/")[-1]
            url = f"https://github.com/{repo_path}"
            
            # AI 关键词过滤
            text = f"{repo_path} {desc}".lower()
            if any(kw in text for kw in GITHUB_AI_KEYWORDS):
                if any(kw in repo_path.lower() for kw in GITHUB_EXCLUDE_KEYWORDS):
                    continue
                    
                items.append(
                    RawItem(
                        title=repo_name,
                        url=url,
                        source="github",
                        description=desc,
                        stars=stars,
                        language="unknown",
                    )
                )
                logger.debug("  命中: %s (stars=%d)", repo_name, stars)

    except Exception as e:
        logger.error("GitHub 采集失败: %s", e)

    logger.info("GitHub 采集完成: %d 条", len(items))
    return items


async def collect_rss(limit: int = 20) -> list[RawItem]:
    """从 RSS 源采集 AI 相关文章。

    Args:
        limit: 采集数量上限。

    Returns:
        原始数据项列表。
    """
    logger.info("开始采集 RSS 源 (limit=%d)", limit)
    items: list[RawItem] = []

    if not RSS_SOURCES_FILE.exists():
        logger.warning("RSS 配置文件不存在: %s", RSS_SOURCES_FILE)
        return items

    with open(RSS_SOURCES_FILE, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    sources = [s for s in config.get("sources", []) if s.get("enabled")]

    async with httpx.AsyncClient(timeout=30.0) as client:
        for src in sources:
            if len(items) >= limit:
                break
            try:
                resp = await client.get(
                    src["url"],
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    },
                )
                resp.raise_for_status()
                text = resp.text

                title_pattern = re.compile(r"<title>(.*?)</title>", re.DOTALL)
                link_pattern = re.compile(
                    r"<link>(.*?)</link>|<link\s+[^>]*href=\"(.*?)\"[^>]*/?>",
                    re.DOTALL,
                )
                desc_pattern = re.compile(
                    r"<description>(.*?)</description>", re.DOTALL
                )

                titles = [
                    re.sub(r"<[^>]+>", "", t).strip()
                    for t in title_pattern.findall(text)
                ]
                titles = [t for t in titles if t][1:]

                links = []
                for m in link_pattern.finditer(text):
                    link = m.group(1) or m.group(2) or ""
                    link = re.sub(r"<[^>]+>", "", link).strip()
                    if link.startswith("http"):
                        links.append(link)

                descriptions = [
                    re.sub(r"<[^>]+>", "", d).strip()
                    for d in desc_pattern.findall(text)
                ]
                descriptions = [d for d in descriptions if d][1:]

                for j in range(min(len(titles), len(links))):
                    if len(items) >= limit:
                        break
                    items.append(
                        RawItem(
                            title=titles[j],
                            url=links[j],
                            source="rss",
                            description=descriptions[j] if j < len(descriptions) else "",
                            raw={"source_name": src["name"], "category": src["category"]},
                        )
                    )

            except Exception as e:
                logger.warning("RSS 源采集失败 [%s]: %s", src["name"], e)

    logger.info("RSS 采集完成: %d 条", len(items))
    return items


# ── Step 2: 分析 ─────────────────────────────────────────────────────────

ANALYSIS_PROMPT = """你是一个技术内容分析专家。请分析以下技术内容，以 JSON 格式输出：

标题: {title}
链接: {url}
描述: {description}

请输出严格的 JSON（不要包含 ```json 标记），格式如下：
{{
  "summary": "50字以内的中文摘要",
  "highlights": ["技术亮点1", "技术亮点2", "技术亮点3"],
  "tags": ["LLM", "Agent", ...],
  "score": 7,
  "audience": "intermediate"
}}

评分标准（1-10）：
- 9-10: 改变格局的重大突破
- 7-8: 对实践直接有帮助
- 5-6: 值得了解
- 1-4: 可略过

受众级别：beginner / intermediate / advanced"""


async def analyze_item(item: RawItem) -> Optional[ArticleItem]:
    """调用 LLM 分析单条原始数据。

    Args:
        item: 原始数据项。

    Returns:
        分析后的知识条目，分析失败返回 None。
    """
    logger.info("分析: %s", item.title)

    messages = [
        {
            "role": "user",
            "content": ANALYSIS_PROMPT.format(
                title=item.title,
                url=item.url,
                description=item.description or "无描述",
            ),
        }
    ]

    try:
        response = await chat_with_retry(messages=messages, temperature=0.3)
        content = response.content.strip()

        content = re.sub(r"^```json\s*", "", content)
        content = re.sub(r"\s*```$", "", content)

        result = json.loads(content)

        return ArticleItem(
            title=item.title,
            source=item.source,
            source_url=item.url,
            summary=result.get("summary", ""),
            highlights=result.get("highlights", []),
            tags=result.get("tags", []),
            score=result.get("score", 5),
            audience=result.get("audience", "intermediate"),
            language=item.language,
            stars=item.stars,
        )
    except Exception as e:
        logger.error("分析失败 [%s]: %s", item.title, e)
        return None


# ── Step 3: 整理 ─────────────────────────────────────────────────────────

def normalize_url(url: str) -> str:
    """规范化 URL，用于去重比对。

    去除末尾斜杠、统一小写，并提取 GitHub 仓库路径（owner/repo）。

    Args:
        url: 原始 URL。

    Returns:
        规范化后的标识符。
    """
    url = url.strip().lower().rstrip("/")
    # 提取 GitHub 仓库路径
    match = re.search(r"github\.com/([^/]+/[^/]+)", url)
    if match:
        return match.group(1)
    return url


def load_existing_articles() -> dict[str, dict]:
    """加载已有知识条目用于去重。

    Returns:
        规范化 URL/路径 到已有条目数据的映射。
    """
    existing: dict[str, dict] = {}
    for f in ARTICLES_DIR.glob("*.json"):
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
                url = data.get("source_url", "")
                if url:
                    existing[normalize_url(url)] = data
        except Exception as e:
            logger.warning("加载已有条目失败 [%s]: %s", f.name, e)
    return existing


def deduplicate(
    articles: list[ArticleItem],
    existing: dict[str, dict],
) -> list[ArticleItem]:
    """对知识条目去重。

    基于规范化的 URL（对于 GitHub 项目则是 owner/repo 路径）进行精准去重。

    Args:
        articles: 待去重的条目列表。
        existing: 已有条目的规范化 URL 映射。

    Returns:
        去重后的新条目列表。
    """
    existing_keys = set(existing.keys())
    result = []
    for article in articles:
        key = normalize_url(article.source_url)
        if key in existing_keys:
            logger.info("跳过重复: %s (匹配键: %s)", article.title, key)
            continue
        result.append(article)
    return result


def validate_article(article: ArticleItem) -> list[str]:
    """校验知识条目的格式和必填字段。

    Args:
        article: 待校验的知识条目。

    Returns:
        错误列表，空列表表示校验通过。
    """
    errors: list[str] = []
    if not article.title:
        errors.append("title 为空")
    if not article.source_url or not article.source_url.startswith("http"):
        errors.append("source_url 格式无效")
    if not article.summary or len(article.summary) < 20:
        errors.append("summary 少于 20 字")
    if not article.tags:
        errors.append("tags 为空")
    if not (1 <= article.score <= 10):
        errors.append("score 不在 1-10 范围")
    if article.audience not in ("beginner", "intermediate", "advanced"):
        errors.append("audience 值非法")
    return errors


# ── Step 4: 保存 ─────────────────────────────────────────────────────────

def save_raw(items: list[RawItem]) -> Path:
    """保存原始采集数据。

    Args:
        items: 原始数据项列表。

    Returns:
        保存的文件路径。
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    file_path = RAW_DIR / f"raw-{timestamp}.json"

    data = {
        "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(items),
        "items": [item.to_dict() for item in items],
    }

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("原始数据已保存: %s (%d 条)", file_path.name, len(items))
    return file_path


def save_articles(articles: list[ArticleItem]) -> list[Path]:
    """保存知识条目为独立 JSON 文件。

    Args:
        articles: 知识条目列表。

    Returns:
        保存的文件路径列表。
    """
    saved: list[Path] = []
    date_str = datetime.now().strftime("%Y%m%d")

    for article in articles:
        slug = re.sub(r"[^a-z0-9]+", "-", article.title.lower()).strip("-")[:40]
        filename = f"{date_str}-{article.source}-{slug}.json"
        file_path = ARTICLES_DIR / filename

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(article.to_dict(), f, ensure_ascii=False, indent=2)

        saved.append(file_path)
        logger.info("知识条目已保存: %s", filename)

    logger.info("共保存 %d 条知识条目", len(saved))
    return saved


# ── 流水线编排 ────────────────────────────────────────────────────────────

async def run_pipeline(
    sources: list[str],
    limit: int = 20,
    dry_run: bool = False,
) -> dict[str, Any]:
    """执行完整的四步流水线。

    Args:
        sources: 数据源列表（github / rss）。
        limit: 每个源的采集数量上限。
        dry_run: 干跑模式，不保存文件。

    Returns:
        流水线执行结果统计。
    """
    start_time = time.time()
    stats = {
        "sources": sources,
        "limit": limit,
        "dry_run": dry_run,
        "collected": 0,
        "analyzed": 0,
        "deduplicated": 0,
        "saved": 0,
        "errors": 0,
    }

    # Step 1: 采集
    logger.info("=" * 50)
    logger.info("Step 1/4: 采集")
    logger.info("=" * 50)

    all_items: list[RawItem] = []
    tasks = []
    if "github" in sources:
        tasks.append(collect_github(limit))
    if "rss" in sources:
        tasks.append(collect_rss(limit))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            logger.error("采集阶段异常: %s", result)
            stats["errors"] += 1
        else:
            all_items.extend(result)

    stats["collected"] = len(all_items)
    logger.info("采集阶段完成: 共 %d 条", len(all_items))

    if not all_items:
        logger.warning("未采集到任何数据，流水线终止")
        return stats

    if not dry_run:
        save_raw(all_items)

    # Step 2: 分析
    logger.info("=" * 50)
    logger.info("Step 2/4: 分析")
    logger.info("=" * 50)

    articles: list[ArticleItem] = []
    for item in all_items:
        result = await analyze_item(item)
        if result:
            articles.append(result)
            stats["analyzed"] += 1
        else:
            stats["errors"] += 1

    logger.info("分析阶段完成: 成功 %d 条，失败 %d 条", stats["analyzed"], stats["errors"])

    if not articles:
        logger.warning("未产生任何分析结果，流水线终止")
        return stats

    # Step 3: 整理
    logger.info("=" * 50)
    logger.info("Step 3/4: 整理")
    logger.info("=" * 50)

    existing = load_existing_articles()
    unique_articles = deduplicate(articles, existing)
    stats["deduplicated"] = len(unique_articles)

    valid_articles: list[ArticleItem] = []
    for article in unique_articles:
        errors = validate_article(article)
        if errors:
            logger.warning("条目校验失败 [%s]: %s", article.title, ", ".join(errors))
            stats["errors"] += 1
        else:
            valid_articles.append(article)

    logger.info("整理阶段完成: 有效条目 %d", len(valid_articles))

    # Step 4: 保存
    logger.info("=" * 50)
    logger.info("Step 4/4: 保存")
    logger.info("=" * 50)

    if dry_run:
        logger.info("干跑模式，跳过文件保存")
        for article in valid_articles:
            logger.info("  - %s [%s] score=%d", article.title, article.source, article.score)
    else:
        saved_paths = save_articles(valid_articles)
        stats["saved"] = len(saved_paths)

    elapsed = time.time() - start_time
    stats["elapsed_seconds"] = round(elapsed, 1)

    # 输出成本报告
    from model_client import tracker
    tracker.report()
    if not dry_run:
        tracker.save_to_json("knowledge/status/cost_report.json")

    logger.info("=" * 50)
    logger.info("流水线执行完成")
    logger.info("采集=%d | 分析=%d | 去重后=%d | 保存=%d | 错误=%d | 耗时=%.1fs",
                stats["collected"], stats["analyzed"], stats["deduplicated"],
                stats["saved"], stats["errors"], stats["elapsed_seconds"])
    logger.info("=" * 50)

    return stats


# ── CLI ───────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    Returns:
        解析后的参数命名空间。
    """
    parser = argparse.ArgumentParser(
        description="AI 知识库自动化流水线（采集 → 分析 → 整理 → 保存）",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default="github,rss",
        help="数据源列表，逗号分隔（github, rss），默认: github,rss",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="每个源的采集数量上限，默认: 20",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="干跑模式，不保存文件",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="输出详细日志",
    )
    return parser.parse_args()


def main() -> None:
    """CLI 入口函数。"""
    args = parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sources = [s.strip().lower() for s in args.sources.split(",")]
    valid_sources = {"github", "rss"}
    invalid = set(sources) - valid_sources
    if invalid:
        logger.error("非法数据源: %s，可选值: %s", ", ".join(invalid), ", ".join(valid_sources))
        sys.exit(1)

    logger.info("流水线启动 | sources=%s | limit=%d | dry_run=%s",
                sources, args.limit, args.dry_run)

    stats = asyncio.run(run_pipeline(sources, args.limit, args.dry_run))

    if stats["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
