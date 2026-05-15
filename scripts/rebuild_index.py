"""知识条目索引生成与更新工具。

功能：
1. 扫描 knowledge/articles/ 目录下所有 .json 文件（排除 index.json 本身）
2. 解析每条知识条目，按 source_url 去重
3. 生成/更新 index.json
"""

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTICLES_DIR = PROJECT_ROOT / "knowledge" / "articles"
INDEX_PATH = ARTICLES_DIR / "index.json"


def rebuild_index(dry_run: bool = False) -> dict:
    """扫描 articles 目录下所有 .json 文件，重建 index.json。

    Args:
        dry_run: 如果为 True，只输出统计信息，不写文件。

    Returns:
        包含统计信息的字典。
    """
    article_files = sorted(ARTICLES_DIR.glob("*.json"))
    article_files = [f for f in article_files if f.name != "index.json"]

    logger.info("发现 %d 个知识条目文件", len(article_files))

    articles = []
    seen_urls = set()
    duplicates = 0

    for filepath in article_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                article = json.load(f)

            url = article.get("source_url", "")
            if url and url in seen_urls:
                duplicates += 1
                logger.debug("跳过重复条目: %s (%s)", article.get("title"), url)
                continue

            if url:
                seen_urls.add(url)

            article["_file"] = filepath.name
            articles.append(article)
        except Exception as e:
            logger.warning("解析失败 %s: %s", filepath.name, e)

    stats = {
        "total_files": len(article_files),
        "valid_articles": len(articles),
        "duplicates_removed": duplicates,
    }

    if dry_run:
        logger.info("[Dry Run] 统计信息: %s", json.dumps(stats, ensure_ascii=False))
        return stats

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    logger.info("index.json 已更新，共 %d 条条目", len(articles))
    return stats


def append_to_index(new_articles: list[dict]) -> dict:
    """追加新条目到 index.json，按 source_url 去重。

    Args:
        new_articles: 新增的条目列表。

    Returns:
        包含统计信息的字典。
    """
    existing = []
    if INDEX_PATH.exists():
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception as e:
            logger.warning("加载现有 index.json 失败: %s", e)
            existing = []

    existing_urls = {a.get("source_url") for a in existing if a.get("source_url")}

    appended = 0
    skipped = 0
    for article in new_articles:
        url = article.get("source_url", "")
        if url and url in existing_urls:
            skipped += 1
            continue
        existing.append(article)
        if url:
            existing_urls.add(url)
        appended += 1

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    stats = {
        "existing_count": len(existing) - appended,
        "appended": appended,
        "skipped_duplicates": skipped,
        "total_count": len(existing),
    }

    logger.info("追加完成: 新增 %d 条，跳过重复 %d 条，总计 %d 条",
                appended, skipped, len(existing))
    return stats


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "rebuild"

    if mode == "rebuild":
        rebuild_index()
    elif mode == "rebuild-dry":
        rebuild_index(dry_run=True)
    else:
        print("用法: python rebuild_index.py [rebuild|rebuild-dry]")
        print("  rebuild       - 重新生成 index.json")
        print("  rebuild-dry   - 只输出统计信息，不写文件")
