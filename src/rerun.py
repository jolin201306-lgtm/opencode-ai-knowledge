"""#006 按日期重跑单阶段任务."""

import argparse
import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# 确保路径相对于项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
RAW_DIR = PROJECT_ROOT / "knowledge/raw"
ARTICLES_DIR = PROJECT_ROOT / "knowledge/articles"
STATUS_DIR = PROJECT_ROOT / "knowledge/status"
RERUN_LOG = PROJECT_ROOT / "knowledge/rerun_log.json"

STAGES = ["collector", "analyzer", "organizer"]

FILE_PATTERNS = {
    "collector": "{date}_trending.json",
    "analyzer": "{date}_trending_annotated.json",
    "organizer": "{date}_report.md",
}


def get_next_version(file_path: Path) -> int:
    """获取下一个版本号."""
    if not file_path.exists():
        return 1

    base = file_path.stem
    # 匹配 _v{n} 后缀
    if "_v" in base:
        try:
            current = int(base.split("_v")[-1])
            return current + 1
        except ValueError:
            return 1
    return 1


def find_latest_version(file_path: Path) -> Path:
    """查找最新版本的文件."""
    if file_path.exists():
        return file_path

    base = file_path.stem
    ext = file_path.suffix
    parent = file_path.parent

    # 查找所有版本
    versions = []
    for f in parent.glob(f"{base}_v*{ext}"):
        try:
            v = int(f.stem.split("_v")[-1])
            versions.append((v, f))
        except ValueError:
            continue

    if versions:
        versions.sort(key=lambda x: x[0], reverse=True)
        return versions[0][1]

    return file_path


def get_file_path(stage: str, date: str, version: int = None) -> Path:
    """获取文件路径."""
    pattern = FILE_PATTERNS.get(stage, "")
    if not pattern:
        raise ValueError(f"未知阶段: {stage}")

    filename = pattern.format(date=date)
    if version and version > 1:
        base, ext = filename.rsplit(".", 1)
        filename = f"{base}_v{version}.{ext}"

    if stage == "organizer":
        return ARTICLES_DIR / filename
    return RAW_DIR / filename


def run_stage(stage: str, date: str, version: int = None) -> dict:
    """执行单个阶段的重跑."""
    logger.info(f"重跑 {stage} (date={date}, version={version})")

    if version is None:
        target = get_file_path(stage, date)
        version = get_next_version(target)

    # 根据阶段调用对应的 Agent
    if stage == "collector":
        from collector import run as collector_run
        result = collector_run(date=date)
        output = get_file_path(stage, date, version)
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    elif stage == "analyzer":
        # 查找 collector 输出
        source = find_latest_version(get_file_path("collector", date))
        if not source.exists():
            raise FileNotFoundError(f"找不到 collector 输出: {source}")

        from analyzer import run as analyzer_run
        result = analyzer_run(source_file=str(source), date=date)
        output = get_file_path(stage, date, version)
        with open(output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    elif stage == "organizer":
        source = find_latest_version(get_file_path("analyzer", date))
        if not source.exists():
            raise FileNotFoundError(f"找不到 analyzer 输出: {source}")

        from organizer import run as organizer_run
        result = organizer_run(source_file=str(source), date=date)
        output = get_file_path(stage, date, version)
        ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            f.write(result)

    else:
        raise ValueError(f"未知阶段: {stage}")

    logger.info(f"{stage} 重跑完成 → {output}")
    return {
        "stage": stage,
        "date": date,
        "version": version,
        "output": str(output),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def rollback(date: str, stage: str, version: int) -> Path:
    """回滚到指定版本."""
    current = get_file_path(stage, date)
    target = get_file_path(stage, date, version)

    if not target.exists():
        raise FileNotFoundError(f"目标版本不存在: {target}")

    # 备份当前版本
    if current.exists():
        backup_version = get_next_version(current)
        backup = get_file_path(stage, date, backup_version)
        shutil.copy2(current, backup)
        logger.info(f"备份当前版本 → {backup}")

    # 恢复目标版本
    shutil.copy2(target, current)
    logger.info(f"回滚 {stage} 到 v{version}")
    return current


def compare_versions(date: str, stage: str, v1: int, v2: int) -> dict:
    """对比两个版本的差异."""
    file1 = get_file_path(stage, date, v1)
    file2 = get_file_path(stage, date, v2)

    if not file1.exists():
        raise FileNotFoundError(f"版本 v{v1} 不存在: {file1}")
    if not file2.exists():
        raise FileNotFoundError(f"版本 v{v2} 不存在: {file2}")

    with open(file1, encoding="utf-8") as f:
        data1 = json.load(f)
    with open(file2, encoding="utf-8") as f:
        data2 = json.load(f)

    # 简化对比：比较 items 数量
    items1 = data1.get("items", [])
    items2 = data2.get("items", [])

    return {
        "v1": {"file": str(file1), "items": len(items1)},
        "v2": {"file": str(file2), "items": len(items2)},
        "diff": len(items2) - len(items1),
    }


def log_rerun(record: dict) -> None:
    """记录重跑到清单文件."""
    RERUN_LOG.parent.mkdir(parents=True, exist_ok=True)

    if RERUN_LOG.exists():
        with open(RERUN_LOG, encoding="utf-8") as f:
            log = json.load(f)
    else:
        log = {"reruns": []}

    log["reruns"].append(record)
    with open(RERUN_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="重跑指定日期/阶段的任务")
    parser.add_argument("--date", required=True, help="日期 YYYYMMDD")
    parser.add_argument("--stage", choices=STAGES, help="阶段名，不指定则重跑全部")
    parser.add_argument("--version", type=int, help="版本号")
    parser.add_argument("--rollback", type=int, help="回滚到指定版本")
    parser.add_argument("--compare", nargs=2, type=int, metavar=("V1", "V2"), help="对比两个版本")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.rollback:
        if not args.stage:
            parser.error("回滚需要指定 --stage")
        target = rollback(args.date, args.stage, args.rollback)
        print(f"回滚完成 → {target}")
        return

    if args.compare:
        if not args.stage:
            parser.error("对比需要指定 --stage")
        diff = compare_versions(args.date, args.stage, args.compare[0], args.compare[1])
        print(json.dumps(diff, indent=2, ensure_ascii=False))
        return

    stages = [args.stage] if args.stage else STAGES
    results = []

    for stage in stages:
        try:
            record = run_stage(stage, args.date, args.version)
            log_rerun(record)
            results.append(record)
        except Exception as e:
            logger.error(f"{stage} 重跑失败: {e}")
            results.append({
                "stage": stage,
                "date": args.date,
                "status": "failed",
                "error": str(e),
            })

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
