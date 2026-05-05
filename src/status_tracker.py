"""#007 每日进度状态追踪."""

import argparse
import io
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Windows 控制台编码兼容
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8") if hasattr(sys.stdout, 'buffer') else sys.stdout
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8") if hasattr(sys.stderr, 'buffer') else sys.stderr

# 确保路径相对于项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
STATUS_DIR = PROJECT_ROOT / "knowledge/status"
VALID_STATES = {"pending", "running", "success", "failed", "skipped", "partial"}
STAGES = ["collector", "analyzer", "organizer"]


def get_status_file(date: str) -> Path:
    """获取状态文件路径."""
    return STATUS_DIR / f"{date}.json"


def read_status(date: str) -> dict:
    """读取状态文件."""
    status_file = get_status_file(date)
    if not status_file.exists():
        return {"date": date, "collector": {}, "analyzer": {}, "organizer": {}}

    with open(status_file, encoding="utf-8") as f:
        return json.load(f)


def write_status(data: dict) -> None:
    """写入状态文件."""
    status_file = get_status_file(data["date"])
    status_file.parent.mkdir(parents=True, exist_ok=True)
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def update_stage_status(date: str, stage: str, status: str, items: int = 0, error: dict = None) -> None:
    """更新指定阶段的状态."""
    if status not in VALID_STATES:
        raise ValueError(f"无效状态: {status}，可选值: {VALID_STATES}")
    if stage not in STAGES:
        raise ValueError(f"无效阶段: {stage}，可选值: {STAGES}")

    data = read_status(date)

    if not data.get(stage):
        data[stage] = {}

    data[stage]["status"] = status
    data[stage]["updated_at"] = datetime.now(timezone.utc).isoformat()

    if status == "running" and "started_at" not in data[stage]:
        data[stage]["started_at"] = data[stage]["updated_at"]

    if status in ("success", "failed", "skipped", "partial"):
        data[stage]["completed_at"] = data[stage]["updated_at"]
        data[stage]["items_processed"] = items
        if error:
            data[stage]["error"] = error

    write_status(data)
    logger.info(f"状态更新: {date}/{stage} → {status}")


def query_date(date: str) -> dict:
    """查询指定日期的状态."""
    data = read_status(date)
    return data


def query_last_n(n: int) -> list[dict]:
    """查询最近 N 天的状态."""
    today = datetime.now(timezone.utc)
    results = []

    for i in range(n):
        date = (today - timedelta(days=i)).strftime("%Y%m%d")
        data = read_status(date)
        results.append(data)

    return results


def format_report(data: dict) -> str:
    """格式化状态报告."""
    date = data.get("date", "未知")
    lines = [f"📅 日期: {date}", "=" * 50]

    for stage in STAGES:
        stage_data = data.get(stage, {})
        if not stage_data:
            status = "未开始"
            items = "-"
            time_info = ""
        else:
            status = stage_data.get("status", "未知")
            items = stage_data.get("items_processed", "-")
            started = stage_data.get("started_at", "")
            completed = stage_data.get("completed_at", "")

            if started and completed:
                start_dt = datetime.fromisoformat(started)
                end_dt = datetime.fromisoformat(completed)
                duration = (end_dt - start_dt).total_seconds()
                time_info = f" (耗时 {duration:.0f}s)"
            else:
                time_info = ""

        status_icon = {
            "success": "✅",
            "failed": "❌",
            "running": "🔄",
            "pending": "⏳",
            "skipped": "⏭️",
            "partial": "⚠️",
        }.get(status, "❓")

        lines.append(f"  {status_icon} {stage}: {status} (处理 {items} 条){time_info}")

        if "error" in stage_data:
            error = stage_data["error"]
            lines.append(f"      错误: {error.get('code', 'unknown')} - {error.get('message', '')}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="查询每日任务状态")
    parser.add_argument("--date", help="查询指定日期 YYYYMMDD")
    parser.add_argument("--last", type=int, help="查询最近 N 天")
    parser.add_argument("--update", action="store_true", help="更新状态模式")
    parser.add_argument("--stage", choices=STAGES, help="阶段名（配合 --update）")
    parser.add_argument("--status", choices=VALID_STATES, help="状态值（配合 --update）")
    parser.add_argument("--items", type=int, help="处理条数（配合 --update）")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.update:
        if not args.date or not args.stage or not args.status:
            parser.error("--update 需要 --date --stage --status")
        update_stage_status(args.date, args.stage, args.status, args.items or 0)
        print(f"状态已更新: {args.date}/{args.stage} → {args.status}")
        return

    if args.date:
        data = query_date(args.date)
        print(format_report(data))
    elif args.last:
        results = query_last_n(args.last)
        for data in results:
            print(format_report(data))
            print()
    else:
        # 默认显示今天状态
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        data = query_date(today)
        print(format_report(data))


if __name__ == "__main__":
    main()
