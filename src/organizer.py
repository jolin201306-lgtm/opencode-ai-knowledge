"""Organizer Agent - Markdown 报告生成模块."""

import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

RAW_DIR = Path("knowledge/raw")
ARTICLES_DIR = Path("knowledge/articles")
STATUS_DIR = Path("knowledge/status")


def generate_report(items: list[dict], date: str) -> str:
    """生成 Markdown 格式的日报."""
    lines = []

    # 标题
    lines.append(f"# AI 知识库日报 - {date}")
    lines.append("")

    # 概览
    total = len(items)
    avg_score = sum(item["tags"]["impact_score"] for item in items) / total if total > 0 else 0

    lines.append("## 概览")
    lines.append(f"- 采集总数：{total}")
    lines.append(f"- 平均影响力评分：{avg_score:.1f}")
    lines.append(f"- 生成时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")

    # 按技术方向分类
    tech_groups = defaultdict(list)
    for item in items:
        for tech in item["tags"]["tech_direction"]:
            tech_groups[tech].append(item)

    lines.append("## 按技术方向分类")
    lines.append("")

    for tech, group in sorted(tech_groups.items()):
        lines.append(f"### {tech}")
        lines.append("")
        lines.append("| 项目 | 影响力 | 成熟度 | 摘要 |")
        lines.append("|------|--------|--------|------|")

        for item in sorted(group, key=lambda x: x["tags"]["impact_score"], reverse=True):
            title = item["title"]
            url = item["url"]
            score = item["tags"]["impact_score"]
            maturity = item["tags"]["maturity"]
            desc = item.get("description", "")[:50] + "..." if len(item.get("description", "")) > 50 else item.get("description", "")
            lines.append(f"| [{title}]({url}) | {score}/10 | {maturity} | {desc} |")

        lines.append("")

    # 标签索引
    lines.append("## 标签索引")
    lines.append("")
    for tech, group in sorted(tech_groups.items(), key=lambda x: len(x[1]), reverse=True):
        lines.append(f"- #{tech} ({len(group)})")
    lines.append("")

    # Top 推荐
    lines.append("## Top 推荐")
    lines.append("")
    top_items = sorted(items, key=lambda x: x["tags"]["impact_score"], reverse=True)[:5]
    for i, item in enumerate(top_items, 1):
        lines.append(f"### {i}. [{item['title']}]({item['url']})")
        lines.append(f"- **评分**: {item['tags']['impact_score']}/10")
        lines.append(f"- **技术方向**: {', '.join(item['tags']['tech_direction'])}")
        lines.append(f"- **成熟度**: {item['tags']['maturity']}")
        lines.append(f"- **理由**: {item['tags']['impact_reason']}")
        lines.append(f"- **Stars**: {item['popularity']['stars']:,} (+{item['popularity']['stars_today']:,} today)")
        lines.append("")

    return "\n".join(lines)


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

    data["organizer"] = entry

    with open(status_file, "w") as f:
        json.dump(data, f, indent=2)


def run(source_file: str = None, date: str = None) -> str:
    """执行 Organizer Agent 主流程.
    
    Args:
        source_file: 标注数据文件路径，默认查找当天文件
        date: 日期字符串 YYYYMMDD，默认今天
    """
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y%m%d")

    if source_file is None:
        source_file = RAW_DIR / f"{date}_trending_annotated.json"
    else:
        source_file = Path(source_file)

    logger.info(f"开始执行 Organizer Agent，日期：{date}")
    update_status(date, "running")

    try:
        if not source_file.exists():
            raise FileNotFoundError(f"标注数据文件不存在：{source_file}")

        with open(source_file, encoding="utf-8") as f:
            annotated_data = json.load(f)

        items = annotated_data.get("items", [])
        report = generate_report(items, date)

        output_file = ARTICLES_DIR / f"{date}_report.md"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(report)

        update_status(date, "success", len(items))
        logger.info(f"Organizer 完成，生成 {len(items)} 条项目的报告")
        return report

    except Exception as e:
        error = {"code": "internal_error", "message": str(e)}
        update_status(date, "failed", error=error)
        logger.error(f"Organizer 失败：{e}")
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    source = sys.argv[1] if len(sys.argv) > 1 else None
    result = run(source)
    print(result)