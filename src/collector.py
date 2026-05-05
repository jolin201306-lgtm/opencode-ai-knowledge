"""Collector Agent - GitHub Trending 数据采集模块."""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# 确保路径相对于项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
RAW_DIR = PROJECT_ROOT / "knowledge/raw"
STATUS_DIR = PROJECT_ROOT / "knowledge/status"

# AI 关键词白名单
AI_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "ml", "deep learning",
    "llm", "large language model", "gpt", "chatgpt", "openai", "claude", "gemini",
    "agent", "multi-agent", "autonomous", "swarm", "copilot",
    "transformer", "rag", "retrieval augmented generation", "multimodal",
    "neural network", "nlp", "langchain", "langgraph", "mcp",
    "model context protocol", "vector db", "embedding",
]

# 排除词黑名单
EXCLUDE_KEYWORDS = [
    "crypto", "blockchain", "web3", "nft", "defi",
    "minecraft", "game", "wordpress", "theme",
]


def parse_trending_repos(text: str) -> list[dict]:
    """解析 GitHub Trending 页面文本，提取项目信息."""
    repos = []

    # 匹配模式：owner / repo + description + language + stars + forks + stars today
    pattern = re.compile(
        r"(\S+)\s*/\s*\n\s*(\S+)\s*\n\s*"  # owner / repo
        r"([^\n]+?)\s*\n\s*"                # description
        r"([A-Za-z+#]+)\s*\n\s*"            # language
        r"([\d,]+)\s*\n\s*"                 # total stars
        r"([\d,]+)\s*\n\s*"                 # forks
        r"Built by.*?\n\s*"                 # built by line
        r"([\d,]+)\s*stars today",          # stars today
        re.DOTALL
    )

    for match in pattern.finditer(text):
        try:
            owner = match.group(1).strip()
            repo_name = match.group(2).strip()
            description = match.group(3).strip()
            language = match.group(4).strip()
            stars = int(match.group(5).replace(",", ""))
            stars_today = int(match.group(7).replace(",", ""))

            repos.append({
                "title": f"{owner}/{repo_name}",
                "url": f"https://github.com/{owner}/{repo_name}",
                "source": "github_trending",
                "popularity": {
                    "stars": stars,
                    "stars_today": stars_today,
                },
                "language": language,
                "description": description,
            })
        except Exception as e:
            logger.warning(f"解析单个项目失败：{e}")
            continue

    return repos


def is_ai_related(repos: list[dict]) -> list[dict]:
    """根据关键词白名单过滤 AI 相关项目."""
    filtered = []
    for repo in repos:
        text = " ".join([
            repo.get("title", ""),
            repo.get("description", ""),
            repo.get("language", "") or "",
        ]).lower()

        if any(kw in text for kw in EXCLUDE_KEYWORDS):
            continue

        if any(kw in text for kw in AI_KEYWORDS):
            filtered.append(repo)

    return filtered


def generate_raw_output(repos: list[dict]) -> dict:
    """生成符合 schema 的 raw 数据."""
    return {
        "meta": {
            "source_agent": "collector",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "version": "v1",
            "status": "success" if repos else "partial",
        },
        "items": repos,
    }


def update_status(date: str, status: str, items_count: int = 0, error: dict = None):
    """更新状态文件."""
    status_file = STATUS_DIR / f"{date}.json"
    status_file.parent.mkdir(parents=True, exist_ok=True)

    if status_file.exists():
        with open(status_file) as f:
            data = json.load(f)
    else:
        data = {
            "date": date,
            "collector": {},
            "analyzer": {},
            "organizer": {},
        }

    entry = {
        "status": status,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "items_processed": items_count,
    }
    if error:
        entry["error"] = error

    data["collector"] = entry

    with open(status_file, "w") as f:
        json.dump(data, f, indent=2)


def run(text: str, date: str = None) -> dict:
    """执行 Collector Agent 主流程.
    
    Args:
        text: GitHub Trending 页面文本内容
        date: 日期字符串 YYYYMMDD，默认今天
    """
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y%m%d")

    logger.info(f"开始执行 Collector Agent，日期：{date}")
    update_status(date, "running")

    try:
        repos = parse_trending_repos(text)
        ai_repos = is_ai_related(repos)
        ai_repos.sort(key=lambda x: x["popularity"]["stars_today"], reverse=True)

        output = generate_raw_output(ai_repos)

        output_file = RAW_DIR / f"{date}_trending.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        update_status(date, output["meta"]["status"], len(ai_repos))
        logger.info(f"Collector 完成，采集 {len(ai_repos)} 条 AI 相关项目")
        return output

    except Exception as e:
        error = {"code": "internal_error", "message": str(e)}
        update_status(date, "failed", error=error)
        logger.error(f"Collector 失败：{e}")
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        with open(input_file, encoding="utf-8") as f:
            text = f.read()
    else:
        print("用法：python collector.py <input_file>")
        sys.exit(1)
    result = run(text)
    print(json.dumps(result, indent=2, ensure_ascii=True))