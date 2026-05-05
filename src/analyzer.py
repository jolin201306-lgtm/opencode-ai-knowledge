"""Analyzer Agent - 数据标注模块."""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

RAW_DIR = Path("knowledge/raw")
STATUS_DIR = Path("knowledge/status")

# 技术方向标签库
TECH_DIRECTIONS = {
    "LLM": ["llm", "large language model", "gpt", "chatgpt"],
    "Agent": ["agent", "autonomous", "copilot"],
    "Multi-Agent": ["multi-agent", "multi_agent", "swarm"],
    "RAG": ["rag", "retrieval augmented", "vector db", "embedding"],
    "MCP": ["mcp", "model context protocol"],
    "CV": ["computer vision", "image", "vision"],
    "NLP": ["nlp", "natural language", "text"],
    "Fine-tuning": ["fine-tuning", "fine tuning", "lora", "qlora"],
    "Prompt Engineering": ["prompt", "prompting"],
}

# 成熟度判断规则
MATURITY_RULES = {
    "demo": ["demo", "prototype", "experiment", "research"],
    "MVP": ["mvp", "beta", "early"],
    "production-ready": ["production", "stable", "release", "v1", "v2"],
}


def classify_tech_direction(title: str, description: str) -> list[str]:
    """分类技术方向."""
    text = f"{title} {description}".lower()
    matched = []

    for direction, keywords in TECH_DIRECTIONS.items():
        if any(kw in text for kw in keywords):
            matched.append(direction)

    return matched if matched else ["Agent"]


def classify_maturity(description: str, stars: int) -> str:
    """判断项目成熟度."""
    text = description.lower()

    # 先检查关键词
    for maturity, keywords in MATURITY_RULES.items():
        if any(kw in text for kw in keywords):
            return maturity

    # 根据 star 数辅助判断
    if stars >= 10000:
        return "production-ready"
    elif stars >= 1000:
        return "MVP"
    else:
        return "demo"


def calculate_impact_score(stars: int, stars_today: int, description: str) -> tuple[int, str]:
    """计算影响力评分 (1-10).
    
    评分标准：
    - 9-10: 改变格局（突破性创新）
    - 7-8: 直接有帮助（解决实际问题）
    - 5-6: 值得了解（有新意但不成熟）
    - 1-4: 可略过（热度高但实质有限）
    """
    score = 5  # 基础分

    # Star 数权重
    if stars >= 50000:
        score += 2
    elif stars >= 10000:
        score += 1

    # 今日增长权重
    if stars_today >= 1000:
        score += 2
    elif stars_today >= 500:
        score += 1

    # 关键词加分
    impactful_keywords = ["framework", "platform", "infrastructure", "enterprise"]
    if any(kw in description.lower() for kw in impactful_keywords):
        score += 1

    # 限制在 1-10 范围
    score = max(1, min(10, score))

    # 生成评分理由
    if score >= 9:
        reason = "突破性创新，可能改变行业方向"
    elif score >= 7:
        reason = "解决实际问题，可直接应用"
    elif score >= 5:
        reason = "有新意但不够成熟，值得关注"
    else:
        reason = "热度高但实质内容有限"

    return score, reason


def annotate_item(item: dict) -> dict:
    """对单个条目进行标注."""
    title = item.get("title", "")
    description = item.get("description", "")
    popularity = item.get("popularity", {})
    stars = popularity.get("stars", 0)
    stars_today = popularity.get("stars_today", 0)

    tech_direction = classify_tech_direction(title, description)
    maturity = classify_maturity(description, stars)
    impact_score, impact_reason = calculate_impact_score(stars, stars_today, description)

    return {
        **item,
        "tags": {
            "tech_direction": tech_direction,
            "maturity": maturity,
            "impact_score": impact_score,
            "impact_reason": impact_reason,
        },
    }


def generate_annotated_output(items: list[dict], source_file: str) -> dict:
    """生成符合 schema 的 annotated 数据."""
    return {
        "meta": {
            "source_agent": "analyzer",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "version": "v1",
            "status": "success" if items else "partial",
            "source_file": source_file,
        },
        "items": items,
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

    data["analyzer"] = entry

    with open(status_file, "w") as f:
        json.dump(data, f, indent=2)


def run(source_file: str = None, date: str = None) -> dict:
    """执行 Analyzer Agent 主流程.
    
    Args:
        source_file: 原始数据文件路径，默认查找当天文件
        date: 日期字符串 YYYYMMDD，默认今天
    """
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y%m%d")

    if source_file is None:
        source_file = RAW_DIR / f"{date}_trending.json"
    else:
        source_file = Path(source_file)

    logger.info(f"开始执行 Analyzer Agent，日期：{date}")
    update_status(date, "running")

    try:
        if not source_file.exists():
            raise FileNotFoundError(f"原始数据文件不存在：{source_file}")

        with open(source_file, encoding="utf-8") as f:
            raw_data = json.load(f)

        items = raw_data.get("items", [])
        annotated_items = [annotate_item(item) for item in items]

        output = generate_annotated_output(annotated_items, str(source_file))

        output_file = RAW_DIR / f"{date}_trending_annotated.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        update_status(date, output["meta"]["status"], len(annotated_items))
        logger.info(f"Analyzer 完成，标注 {len(annotated_items)} 条项目")
        return output

    except Exception as e:
        error = {"code": "internal_error", "message": str(e)}
        update_status(date, "failed", error=error)
        logger.error(f"Analyzer 失败：{e}")
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    source = sys.argv[1] if len(sys.argv) > 1 else None
    result = run(source)
    print(json.dumps(result, indent=2, ensure_ascii=True))